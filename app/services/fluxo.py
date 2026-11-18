"""
Visão de caixa: quanto entra e sai das contas, mês a mês, no passado (real) e
no futuro (projetado).

Regras:
- Transferência entre as próprias contas (categoria natureza='transferencia')
  não é receita nem despesa: só move saldo.
- Compras no cartão não saem do caixa na data da compra; o caixa sai quando a
  fatura é paga (passado: transações 'pagamento_cartao'; futuro: faturas em aberto
  pelo vencimento).
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from app.models import db, Categoria, CartaoCredito, Conta, Fatura, Transacao

ZERO = Decimal('0')


def ids_fora_do_resultado(user_id):
    """Categorias que não contam como receita/despesa (transferência, pagamento de fatura)."""
    return {c.id: c.natureza for c in Categoria.query.filter(
        Categoria.user_id == user_id, Categoria.natureza != 'normal').all()}


def filtro_resultado():
    """Condição SQL para somar receitas/despesas de verdade (sem transferências e pagamentos de fatura)."""
    especiais = db.session.query(Categoria.id).filter(Categoria.natureza != 'normal')
    return ~Transacao.categoria_id.in_(especiais)


def _mes(d):
    return date(d.year, d.month, 1)


def caixa_mensal(user_id, meses_passados=12, meses_futuros=12, estimar=True, hoje=None, meses_media=3):
    hoje = hoje or date.today()
    especiais = ids_fora_do_resultado(user_id)
    contas = Conta.query.filter_by(user_id=user_id, ativa=True).all()
    saldo_hoje = sum((Decimal(c.saldo_atual or 0) for c in contas), ZERO)
    ids_contas = [c.id for c in contas]

    mes_atual = _mes(hoje)
    inicio = mes_atual - relativedelta(months=meses_passados)
    fim = mes_atual + relativedelta(months=meses_futuros)

    # movimentos de caixa (tudo que não é compra no cartão)
    movs = Transacao.query.filter(
        Transacao.conta_id.in_(ids_contas) if ids_contas else db.false(),
        db.or_(Transacao.forma_pagamento.is_(None), Transacao.forma_pagamento != 'cartao_credito'),
        Transacao.data >= inicio,
        Transacao.data < fim + relativedelta(months=1),
    ).all()

    real = defaultdict(lambda: {'entradas': ZERO, 'saidas_contas': ZERO, 'saidas_cartoes': ZERO, 'liquido': ZERO})
    pendente = defaultdict(lambda: {'entradas': ZERO, 'saidas_contas': ZERO})
    for t in movs:
        m = _mes(t.data)
        valor = Decimal(t.valor)
        realizado = t.pago and t.data <= hoje
        natureza = especiais.get(t.categoria_id, 'normal')
        if realizado:
            real[m]['liquido'] += valor if t.tipo == 'receita' else -valor
            if natureza == 'transferencia':
                continue
            if natureza == 'pagamento_cartao':
                real[m]['saidas_cartoes'] += valor if t.tipo == 'despesa' else -valor
            elif t.tipo == 'receita':
                real[m]['entradas'] += valor
            else:
                real[m]['saidas_contas'] += valor
        else:
            if natureza != 'normal':
                continue  # pagamento de fatura futuro é coberto pelas faturas em aberto
            chave = 'entradas' if t.tipo == 'receita' else 'saidas_contas'
            pendente[max(m, mes_atual)][chave] += valor

    # faturas em aberto (caixa sai no vencimento; vencidas contam no mês atual)
    faturas = defaultdict(lambda: ZERO)
    for f in Fatura.query.join(CartaoCredito).filter(
            CartaoCredito.user_id == user_id, Fatura.status != 'paga').all():
        devido = Decimal(f.valor_total or 0) - Decimal(f.valor_pago or 0)
        if devido > 0:
            faturas[max(_mes(f.data_vencimento), mes_atual)] += devido

    # médias dos últimos meses completos (para estimar o que ainda não está lançado)
    completos = [mes_atual - relativedelta(months=i) for i in range(1, meses_media + 1)]
    def media(chave):
        return sum((real[m][chave] for m in completos), ZERO) / len(completos)
    medias = {k: media(k) for k in ('entradas', 'saidas_contas', 'saidas_cartoes')}

    # saldo no fim de cada mês passado: volta a partir do saldo de hoje
    meses = []
    m = inicio
    while m < mes_atual:
        meses.append(m)
        m += relativedelta(months=1)
    saldos_passados = {}
    acumulado = saldo_hoje - real[mes_atual]['liquido']  # saldo no fim do mês anterior
    for m in reversed(meses):
        saldos_passados[m] = acumulado
        acumulado -= real[m]['liquido']

    resultado = []
    for m in meses:
        r = real[m]
        resultado.append(_linha(m, r['entradas'], r['saidas_contas'], r['saidas_cartoes'],
                                saldos_passados[m], 'real'))

    saldo = saldo_hoje
    m = mes_atual
    while m < fim:
        conhecidas = {
            'entradas': real[m]['entradas'] + pendente[m]['entradas'],
            'saidas_contas': real[m]['saidas_contas'] + pendente[m]['saidas_contas'],
            'saidas_cartoes': real[m]['saidas_cartoes'] + faturas[m],
        }
        totais = dict(conhecidas)
        estimado = False
        if estimar:
            for chave in totais:
                if medias[chave] > totais[chave]:
                    totais[chave] = medias[chave]
                    estimado = True
        # o que ainda vai acontecer no mês (o realizado já está no saldo de hoje)
        a_entrar = totais['entradas'] - real[m]['entradas']
        a_sair = (totais['saidas_contas'] - real[m]['saidas_contas']) + \
                 (totais['saidas_cartoes'] - real[m]['saidas_cartoes'])
        saldo += a_entrar - a_sair
        resultado.append(_linha(m, totais['entradas'], totais['saidas_contas'], totais['saidas_cartoes'],
                                saldo, 'atual' if m == mes_atual else 'projetado', estimado))
        m += relativedelta(months=1)

    futuros = [r for r in resultado if r['tipo'] != 'real']
    menor = min(futuros, key=lambda r: r['saldo']) if futuros else None
    def saldo_em(n):
        return futuros[n]['saldo'] if len(futuros) > n else None
    return {
        'meses': resultado,
        'resumo': {
            'saldo_hoje': float(saldo_hoje),
            'saldo_6_meses': saldo_em(6),
            'saldo_12_meses': saldo_em(min(12, len(futuros) - 1)) if futuros else None,
            'menor_saldo': menor['saldo'] if menor else None,
            'menor_saldo_mes': menor['rotulo'] if menor else None,
            'media_entradas': float(medias['entradas']),
            'media_saidas': float(medias['saidas_contas'] + medias['saidas_cartoes']),
            'sobra_media': float(medias['entradas'] - medias['saidas_contas'] - medias['saidas_cartoes']),
            'estimar': estimar,
            'meses_media': meses_media,
        },
    }


MESES_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def _linha(m, entradas, saidas_contas, saidas_cartoes, saldo, tipo, estimado=False):
    return {
        'mes': m.strftime('%Y-%m'),
        'rotulo': f'{MESES_PT[m.month - 1]}/{str(m.year)[2:]}',
        'entradas': round(float(entradas), 2),
        'saidas_contas': round(float(saidas_contas), 2),
        'saidas_cartoes': round(float(saidas_cartoes), 2),
        'resultado': round(float(entradas - saidas_contas - saidas_cartoes), 2),
        'saldo': round(float(saldo), 2),
        'tipo': tipo,
        'estimado': estimado,
    }
