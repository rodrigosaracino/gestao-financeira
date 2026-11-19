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


# ---------------------------------------------------------------- transferências

PREFIXO_TRANSFERENCIA = 'TRF'


def categorias_transferencia(user_id):
    """(enviada, recebida): categorias de transferência entre as próprias contas (cria se faltar)."""
    from app.models import Categoria
    pares = {}
    for tipo, nome in (('despesa', 'Transferência enviada (minhas contas)'),
                       ('receita', 'Transferência recebida (minhas contas)')):
        cat = (Categoria.query.filter_by(user_id=user_id, tipo=tipo, natureza='transferencia').first()
               or Categoria.query.filter_by(user_id=user_id, nome=nome).first())
        if not cat:
            cat = Categoria(nome=nome, tipo=tipo, cor='#7f8c8d', user_id=user_id, natureza='transferencia')
            db.session.add(cat)
            db.session.flush()
        elif cat.natureza != 'transferencia':
            cat.natureza = 'transferencia'
        pares[tipo] = cat
    return pares['despesa'], pares['receita']


def eh_transferencia_manual(transacao):
    return bool(transacao and (transacao.id_externo or '').startswith(PREFIXO_TRANSFERENCIA))


def pernas_transferencia(transacao):
    """As duas transações (saída, entrada) de uma transferência lançada na tela."""
    if not eh_transferencia_manual(transacao):
        return [transacao]
    pernas = Transacao.query.filter(Transacao.id_externo == transacao.id_externo).all()
    pernas = [p for p in pernas if p.conta and transacao.conta and p.conta.user_id == transacao.conta.user_id]
    return sorted(pernas, key=lambda p: 0 if p.tipo == 'despesa' else 1)


def salvar_transferencia(user_id, origem, destino, valor, data_transf, descricao, pago, existente=None):
    """
    Cria (ou atualiza) uma transferência: saída na conta de origem e entrada na de
    destino, nas categorias de transferência (não contam como receita nem despesa).
    """
    import uuid
    enviada, recebida = categorias_transferencia(user_id)
    pago = bool(pago) and pode_ficar_pago(data_transf)
    descricao = (descricao or '').strip() or f'Transferência {origem.nome} → {destino.nome}'
    if existente:
        pernas = pernas_transferencia(existente)
        for p in pernas:   # desfaz o efeito antigo no saldo
            if p.pago:
                aplicar(p.conta, p.tipo, p.valor, sinal=-1)
        saida = next((p for p in pernas if p.tipo == 'despesa'), None)
        entrada = next((p for p in pernas if p.tipo == 'receita'), None)
        chave = existente.id_externo
    else:
        saida = entrada = None
        chave = PREFIXO_TRANSFERENCIA + uuid.uuid4().hex
    if saida is None:
        saida = Transacao(tipo='despesa', id_externo=chave)
        db.session.add(saida)
    if entrada is None:
        entrada = Transacao(tipo='receita', id_externo=chave)
        db.session.add(entrada)
    for perna, conta, cat in ((saida, origem, enviada), (entrada, destino, recebida)):
        perna.descricao = descricao[:200]
        perna.valor = Decimal(valor)
        perna.data = data_transf
        perna.conta_id = conta.id
        perna.conta = conta
        perna.categoria_id = cat.id
        perna.forma_pagamento = 'dinheiro'
        perna.cartao_credito_id = None
        perna.fatura_id = None
        perna.pago = pago
        if pago:
            aplicar(conta, perna.tipo, perna.valor)
    db.session.flush()
    return saida, entrada
