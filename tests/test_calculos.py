"""Conferência dos cálculos de saldo, fatura, limite, parcelas, recorrência, metas e relatórios."""
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

HOJE = date.today()
ONTEM = (HOJE - timedelta(days=1)).isoformat()
AMANHA = (HOJE + timedelta(days=1)).isoformat()


def _get(app, model, id_):
    from app.models import db
    with app.app_context():
        return db.session.get(model, id_)


def _saldo(app, conta_id):
    from app.models import Conta
    return _get(app, Conta, conta_id).saldo_atual


def _form(a, **kw):
    dados = {'descricao': 'Teste', 'valor': '100', 'tipo': 'despesa', 'data': ONTEM,
             'conta_id': a['conta'], 'categoria_id': a['despesa'], 'forma_pagamento': 'dinheiro'}
    dados.update(kw)
    return dados


def _ultima(app):
    from app.models import Transacao
    with app.app_context():
        return Transacao.query.order_by(Transacao.id.desc()).first()


# ------------------------------------------------------------- saldo da conta

def test_data_futura_nao_fica_paga(app, usuarios, client_a):
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, data=AMANHA, pago='on'))
    t = _ultima(app)
    assert t.pago is False and _saldo(app, a['conta']) == 1000
    r = client_a.post(f'/transacoes/{t.id}/toggle-pago')
    assert r.status_code == 400 and _saldo(app, a['conta']) == 1000


def test_editar_transacao_paga_para_futuro_devolve_saldo(app, usuarios, client_a):
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, pago='on'))
    t = _ultima(app)
    assert _saldo(app, a['conta']) == 900
    client_a.post(f'/transacoes/{t.id}/editar', data=_form(a, data=AMANHA, pago='on', valor='150'))
    assert _ultima(app).pago is False and _saldo(app, a['conta']) == 1000
    client_a.post(f'/transacoes/{t.id}/editar', data=_form(a, pago='on', valor='150'))
    assert _saldo(app, a['conta']) == 850
    client_a.post(f'/transacoes/{t.id}/deletar')
    assert _saldo(app, a['conta']) == 1000


def test_editar_de_dinheiro_para_cartao_nao_mexe_no_saldo(app, usuarios, client_a):
    from app.models import CartaoCredito, Fatura
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, pago='on'))
    t = _ultima(app)
    client_a.post(f'/transacoes/{t.id}/editar',
                  data=_form(a, forma_pagamento='cartao_credito', cartao_credito_id=a['cartao'], pago='on'))
    t = _ultima(app)
    assert _saldo(app, a['conta']) == 1000          # saiu da conta, foi para a fatura
    assert t.pago is False and t.fatura_id
    assert _get(app, Fatura, t.fatura_id).valor_total == 100
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 100


# ------------------------------------------------------------- cartão e faturas

def test_parcelas_somam_o_total_e_excluir_libera_limite(app, usuarios, client_a):
    from app.models import CartaoCredito, Fatura, Transacao
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, valor='100', forma_pagamento='cartao_credito',
                                                  cartao_credito_id=a['cartao'], total_parcelas='3'))
    with app.app_context():
        parcelas = Transacao.query.filter_by(cartao_credito_id=a['cartao']).order_by(Transacao.numero_parcela).all()
        assert [p.valor for p in parcelas] == [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')]
        ids = [p.id for p in parcelas]
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 100
    client_a.post(f'/transacoes/{ids[1]}/deletar')   # excluir a parcela do meio
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == Decimal('66.67')
    client_a.post(f'/transacoes/{ids[0]}/deletar')
    client_a.post(f'/transacoes/{ids[2]}/deletar')
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 0
    with app.app_context():
        assert all(f.valor_total == 0 for f in Fatura.query.filter_by(cartao_id=a['cartao']).all())


def test_excluir_compra_a_vista_no_cartao_libera_limite(app, usuarios, client_a):
    from app.models import CartaoCredito
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, valor='250', forma_pagamento='cartao_credito',
                                                  cartao_credito_id=a['cartao'], total_parcelas='1'))
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 250
    t = _ultima(app)
    client_a.post(f'/transacoes/{t.id}/editar', data=_form(a, valor='300', forma_pagamento='cartao_credito',
                                                            cartao_credito_id=a['cartao']))
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 300
    client_a.post(f'/transacoes/{t.id}/deletar')
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 0


def test_pagamento_parcial_depois_restante(app, usuarios, client_a):
    from app.models import CartaoCredito, Fatura
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, valor='500', forma_pagamento='cartao_credito',
                                                  cartao_credito_id=a['cartao'], total_parcelas='1'))
    fid = _ultima(app).fatura_id
    client_a.post(f'/faturas/{fid}/pagar', data={'valor_pago': '200', 'conta_id': a['conta']})
    f = _get(app, Fatura, fid)
    assert f.valor_pago == 200 and f.status != 'paga'
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 300
    client_a.post(f'/faturas/{fid}/pagar', data={'valor_pago': '300', 'conta_id': a['conta']})
    f = _get(app, Fatura, fid)
    assert f.valor_pago == 500 and f.status == 'paga'
    assert _get(app, CartaoCredito, a['cartao']).limite_utilizado == 0
    assert _saldo(app, a['conta']) == 500
    # pagar de novo uma fatura paga não desconta outra vez
    client_a.post(f'/faturas/{fid}/pagar', data={'valor_pago': '500', 'conta_id': a['conta']})
    assert _saldo(app, a['conta']) == 500 and _get(app, CartaoCredito, a['cartao']).limite_utilizado == 0


def test_recalcular_fatura_desconta_estorno(app, usuarios):
    from app.models import db, CartaoCredito, Fatura, Transacao
    from app.services.saldos import recalcular_fatura, recalcular_limite
    a, _ = usuarios
    with app.app_context():
        f = Fatura(cartao_id=a['cartao'], mes_referencia=1, ano_referencia=2030, data_fechamento=date(2030, 1, 31),
                   data_vencimento=date(2030, 2, 8), valor_total=0, valor_pago=0, status='aberta')
        db.session.add(f); db.session.flush()
        for tipo, v in (('despesa', '300'), ('receita', '50')):
            db.session.add(Transacao(descricao='x', valor=Decimal(v), tipo=tipo, data=date(2030, 1, 5),
                                     forma_pagamento='cartao_credito', cartao_credito_id=a['cartao'],
                                     fatura_id=f.id, conta_id=a['conta'],
                                     categoria_id=a['despesa'] if tipo == 'despesa' else a['receita']))
        assert recalcular_fatura(f.id) == 250
        assert recalcular_limite(a['cartao']) == 250
        db.session.commit()
        assert db.session.get(CartaoCredito, a['cartao']).limite_utilizado == 250


# ------------------------------------------------------------- recorrência

def test_recorrencia_mensal_sem_deriva_de_data(app, usuarios, client_a):
    from app.models import Transacao
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, data='2031-01-31', recorrente='on',
                                                  frequencia_recorrencia='mensal',
                                                  data_inicio_recorrencia='2031-01-31',
                                                  quantidade_recorrencias='4'))
    with app.app_context():
        datas = sorted(t.data for t in Transacao.query.filter_by(conta_id=a['conta']).all())
    assert datas == [date(2031, 1, 31), date(2031, 2, 28), date(2031, 3, 31), date(2031, 4, 30)]


# ------------------------------------------------------------- metas

def test_deposito_de_meta_nao_conta_duas_vezes(app, usuarios, client_a):
    from app.models import db, Meta
    a, _ = usuarios
    with app.app_context():
        m = Meta(user_id=a['user'], titulo='Reserva', valor_alvo=Decimal('1000'), valor_inicial=Decimal('0'),
                 data_inicio=HOJE, data_fim=HOJE + relativedelta(years=1))
        db.session.add(m); db.session.commit()
        mid = m.id
    client_a.post(f'/metas/{mid}/deposito', data={'valor': '600', 'data': HOJE.isoformat()})
    m = _get(app, Meta, mid)
    assert m.status == 'ativa'                       # 600 de 1000: não está concluída
    client_a.post(f'/metas/{mid}/deposito', data={'valor': '400', 'data': HOJE.isoformat()})
    with app.app_context():
        m = db.session.get(Meta, mid)
        assert m.status == 'concluida' and m.valor_acumulado() == 1000


# ------------------------------------------------------------- relatórios

def test_evolucao_patrimonial_acumula_saldo(app, usuarios, client_a):
    from app.models import db, Conta
    from tests.test_fluxo import _t
    a, _ = usuarios
    with app.app_context():
        db.session.add_all([
            _t(a['conta'], a['receita'], 'receita', '300', HOJE - timedelta(days=5)),
            _t(a['conta'], a['despesa'], 'despesa', '100', HOJE - timedelta(days=2)),
            _t(a['conta'], a['despesa'], 'despesa', '999', HOJE - timedelta(days=3), pago=False),
        ])
        db.session.get(Conta, a['conta']).saldo_atual = Decimal('1200')  # 1000 + 300 - 100
        db.session.commit()
    d = client_a.get('/api/evolucao-patrimonial?periodo=mes').get_json()
    serie = dict(zip(d['datas'], d['valores']))
    assert d['datas'] == sorted(d['datas'])
    assert serie[HOJE.isoformat()] == 1200
    assert serie[(HOJE - timedelta(days=2)).isoformat()] == 1200
    assert serie[(HOJE - timedelta(days=3)).isoformat()] == 1300
    assert serie[(HOJE - timedelta(days=5)).isoformat()] == 1300
    assert serie[(HOJE - timedelta(days=6)).isoformat()] == 1000


def test_analise_cartoes_ignora_parcelas_futuras(app, usuarios, client_a):
    a, _ = usuarios
    client_a.post('/transacoes/nova', data=_form(a, valor='1200', data=HOJE.isoformat(),
                                                  forma_pagamento='cartao_credito',
                                                  cartao_credito_id=a['cartao'], total_parcelas='12'))
    c = client_a.get('/api/analise-cartoes').get_json()['cartoes'][0]
    assert c['gasto_medio_mensal'] == round(100 / 6, 2)   # só a parcela de hoje nos últimos 6 meses
