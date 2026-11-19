"""Visão de caixa e exclusão de transferências/pagamento de fatura dos totais."""
from datetime import date
from decimal import Decimal


def _t(conta, cat, tipo, valor, d, **kw):
    from app.models import Transacao
    return Transacao(descricao=kw.pop('descricao', 'x'), valor=Decimal(valor), tipo=tipo, data=d,
                     conta_id=conta, categoria_id=cat, pago=kw.pop('pago', True), **kw)


def _cenario(app, a):
    """Saldo hoje 1000. Out: salário 3000, mercado 500, transferência recebida 700, fatura paga 400.
    Nov (mês atual, hoje=15/11): compra no cartão 200 (não é caixa), fatura aberta vence 20/11 = 200."""
    from app.models import db, Categoria, Conta, Fatura
    with app.app_context():
        transf = Categoria(nome='Transferência recebida (minhas contas)', tipo='receita', cor='#7f8c8d',
                           user_id=a['user'], natureza='transferencia')
        pagto = Categoria(nome='Pagamento de Fatura', tipo='despesa', cor='#ff3b57',
                          user_id=a['user'], natureza='pagamento_cartao')
        db.session.add_all([transf, pagto]); db.session.flush()
        db.session.add_all([
            _t(a['conta'], a['receita'], 'receita', '3000', date(2026, 10, 5)),
            _t(a['conta'], a['despesa'], 'despesa', '500', date(2026, 10, 10)),
            _t(a['conta'], transf.id, 'receita', '700', date(2026, 10, 12)),
            _t(a['conta'], pagto.id, 'despesa', '400', date(2026, 10, 20)),
            _t(a['conta'], a['despesa'], 'despesa', '200', date(2026, 11, 3), forma_pagamento='cartao_credito',
               cartao_credito_id=a['cartao'], pago=False),
        ])
        db.session.add(Fatura(cartao_id=a['cartao'], mes_referencia=10, ano_referencia=2026,
                              data_fechamento=date(2026, 10, 31), data_vencimento=date(2026, 11, 20),
                              valor_total=Decimal('200'), valor_pago=Decimal('0')))
        db.session.commit()
        return transf.id, pagto.id


def test_caixa_mensal_real_e_projecao(app, usuarios):
    from app.services.fluxo import caixa_mensal
    a, _ = usuarios
    _cenario(app, a)
    with app.app_context():
        r = caixa_mensal(a['user'], meses_passados=2, meses_futuros=3, estimar=False, hoje=date(2026, 11, 15),
                         meses_media=1)
    meses = {m['mes']: m for m in r['meses']}
    out = meses['2026-10']
    assert out['tipo'] == 'real'
    assert out['entradas'] == 3000      # transferência fora
    assert out['saidas_contas'] == 500  # pagamento de fatura vai para cartões
    assert out['saidas_cartoes'] == 400
    assert out['saldo'] == 1000         # nada realizado em novembro
    assert meses['2026-09']['saldo'] == 1000 - (3000 - 500 + 700 - 400)
    nov = meses['2026-11']
    assert nov['tipo'] == 'atual' and nov['saidas_cartoes'] == 200 and nov['saidas_contas'] == 0
    assert nov['saldo'] == 800          # 1000 - fatura de 200 (a compra no cartão não sai na data)
    assert meses['2027-01']['saldo'] == 800


def test_caixa_com_estimativa_usa_media(app, usuarios):
    from app.services.fluxo import caixa_mensal
    a, _ = usuarios
    _cenario(app, a)
    with app.app_context():
        r = caixa_mensal(a['user'], meses_passados=2, meses_futuros=3, estimar=True, hoje=date(2026, 11, 15),
                         meses_media=1)
    dez = {m['mes']: m for m in r['meses']}['2026-12']
    assert dez['estimado'] and dez['entradas'] == 3000 and dez['saidas_contas'] == 500 and dez['saidas_cartoes'] == 400
    assert r['resumo']['sobra_media'] == 2100


def test_relatorios_ignoram_transferencias(app, usuarios, client_a):
    a, _ = usuarios
    _cenario(app, a)
    d = client_a.get('/api/fluxo-caixa?ano=2026').get_json()
    assert d['receitas'][9] == 3000                  # outubro: sem os 700 de transferência
    assert d['despesas'][9] == 500                   # sem o pagamento de fatura (compras já são despesa)
    g = client_a.get('/api/gastos-por-categoria?mes=10&ano=2026').get_json()
    assert 'Pagamento de Fatura' not in g['categorias']


def test_api_caixa_e_dashboard(app, usuarios, client_a):
    a, _ = usuarios
    _cenario(app, a)
    r = client_a.get('/api/caixa-longo-prazo?estimar=0&passados=3&futuros=4')
    assert r.status_code == 200 and len(r.get_json()['meses']) == 7
    assert client_a.get('/').status_code == 200


def test_editar_natureza_da_categoria(app, usuarios, client_a):
    from app.models import db, Categoria
    a, _ = usuarios
    resp = client_a.post(f"/categorias/{a['receita']}/editar",
                         data={'nome': 'Resgate', 'tipo': 'receita', 'cor': '#123456', 'natureza': 'transferencia'})
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(Categoria, a['receita']).natureza == 'transferencia'
    _, b = usuarios
    assert client_a.get(f"/categorias/{b['receita']}/editar").status_code == 404


def test_lista_de_transacoes_totais_sem_transferencias(app, usuarios, client_a):
    a, _ = usuarios
    _cenario(app, a)
    html = client_a.get('/transacoes?mes=10&ano=2026').get_data(as_text=True)
    assert 'R$ 3000.00' in html          # receitas: sem os 700 de transferência
    assert 'R$ 500.00' in html           # despesas: sem os 400 de pagamento de fatura
    assert '+ R$ 2500.00' in html
    assert 'Fora dos totais: R$ 400.00' in html
