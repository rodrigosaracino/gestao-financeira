"""
Regras únicas de saldo, fatura e limite (usadas pelas telas e pela importação).

Invariantes:
- Conta.saldo_atual = saldo_inicial + efeito de toda transação paga que não é de cartão.
- Só fica "paga" a transação com data de hoje ou do passado (o que é futuro ainda
  não aconteceu; se ficasse paga, o saldo e a projeção divergiriam quando a data chegasse).
- Fatura.valor_total = compras - estornos lançados nela.
- CartaoCredito.limite_utilizado = o que falta pagar nas faturas não pagas.
"""
import re
from datetime import date
from decimal import Decimal, ROUND_DOWN

from app.models import db, CartaoCredito, Fatura, Transacao

CENTAVO = Decimal('0.01')


def pode_ficar_pago(data_transacao, hoje=None):
    return data_transacao <= (hoje or date.today())


def efeito_no_saldo(tipo, valor):
    return Decimal(valor) if tipo == 'receita' else -Decimal(valor)


def aplicar(conta, tipo, valor, sinal=1):
    conta.saldo_atual = Decimal(conta.saldo_atual or 0) + sinal * efeito_no_saldo(tipo, valor)


def recalcular_fatura(fatura_id):
    """Total da fatura = compras - estornos lançados nela."""
    if not fatura_id:
        return None
    fatura = db.session.get(Fatura, fatura_id)
    if not fatura:
        return None
    db.session.flush()
    total = Decimal('0')
    for t in Transacao.query.filter_by(fatura_id=fatura_id).all():
        total += Decimal(t.valor) if t.tipo == 'despesa' else -Decimal(t.valor)
    fatura.valor_total = total
    return total


def recalcular_limite(cartao_id):
    """Limite usado = soma do que falta pagar nas faturas não pagas."""
    if not cartao_id:
        return None
    cartao = db.session.get(CartaoCredito, cartao_id)
    if not cartao:
        return None
    db.session.flush()
    usado = Decimal('0')
    for f in Fatura.query.filter(Fatura.cartao_id == cartao_id, Fatura.status != 'paga').all():
        usado += max(Decimal('0'), Decimal(f.valor_total or 0) - Decimal(f.valor_pago or 0))
    cartao.limite_utilizado = usado
    return usado


def dividir_em_parcelas(valor_total, n):
    """Parcelas em centavos exatos; a última absorve a diferença (soma = total)."""
    valor_total = Decimal(valor_total)
    parcela = (valor_total / n).quantize(CENTAVO, rounding=ROUND_DOWN)
    return [parcela] * (n - 1) + [valor_total - parcela * (n - 1)]


_RE_SUFIXO_PARCELA = re.compile(
    r'\s*(\(\s*\d{1,2}\s*/\s*\d{1,2}\s*\)|-?\s*PARC(?:ELA)?\.?\s*\d{1,2}\s*(?:/|DE)\s*\d{1,2})\s*$', re.I)


def _base_compra(descricao):
    from app.matching import normalizar_descricao
    return normalizar_descricao(_RE_SUFIXO_PARCELA.sub('', descricao or '').strip() or (descricao or ''))


def parcelas_seguintes(transacao):
    """
    Esta parcela e as seguintes da mesma compra no cartão (numero >= o desta),
    ordenadas. Reconhece a série pelo vínculo (transacao_pai_id) ou, para compras
    importadas, pelo cartão, total de parcelas, descrição sem o "x/n", data
    coerente com o número da parcela e valor parecido (o banco varia centavos).
    Duas compras iguais no mesmo dia com valores diferentes são séries diferentes.
    """
    from dateutil.relativedelta import relativedelta
    n, total = transacao.numero_parcela, transacao.total_parcelas
    if not (transacao.cartao_credito_id and n and total and total > 1):
        return [transacao]
    raiz = transacao.transacao_pai_id or transacao.id
    base = _base_compra(transacao.descricao)
    serie = {transacao.id: transacao}
    for t in Transacao.query.filter(Transacao.cartao_credito_id == transacao.cartao_credito_id,
                                    Transacao.total_parcelas == total,
                                    Transacao.numero_parcela >= n).all():
        if t.id in serie:
            continue
        mesma_raiz = (t.transacao_pai_id or t.id) == raiz
        if not mesma_raiz and t.numero_parcela == n:
            continue  # outra parcela com o mesmo número é de outra compra
        esperado = transacao.data + relativedelta(months=t.numero_parcela - n)
        tolerancia = max(Decimal('1.00'), Decimal(transacao.valor) * Decimal('0.02'))
        mesma_compra = (_base_compra(t.descricao) == base and abs((t.data - esperado).days) <= 20
                        and abs(Decimal(t.valor) - Decimal(transacao.valor)) <= tolerancia)
        if mesma_raiz or mesma_compra:
            serie[t.id] = t
    return sorted(serie.values(), key=lambda t: (t.numero_parcela, t.data))
