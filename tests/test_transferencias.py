"""Transferência entre as próprias contas: duas pontas, fora de receitas/despesas."""
from datetime import date, timedelta
from decimal import Decimal

ONTEM = (date.today() - timedelta(days=1)).isoformat()


def _segunda_conta(app, a):
    from app.models import db, Conta
    with app.app_context():
        c = Conta(nome='Reserva', tipo='poupanca', saldo_inicial=Decimal('500'), saldo_atual=Decimal('500'), user_id=a['user'])
        db.session.add(c); db.session.commit()
        return c.id


def _saldos(app, *ids):
    from app.models import db, Conta
    with app.app_context():
        return [db.session.get(Conta, i).saldo_atual for i in ids]


def _pernas(app, a):
    from app.models import Transacao, Conta
    with app.app_context():
        return [(t.id, t.tipo, t.conta_id, t.valor, t.pago, t.categoria.natureza, t.id_externo)
                for t in Transacao.query.join(Conta).filter(Conta.user_id == a['user'],
                                                             Transacao.id_externo.like('TRF%')).order_by(Transacao.tipo).all()]


def test_cria_duas_pontas_e_move_saldo(app, usuarios, client_a):
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    r = client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': reserva,
                                                    'valor': '300', 'data': ONTEM, 'pago': 'on'})
    assert r.status_code == 302
    pernas = _pernas(app, a)
    assert [(p[1], p[2], p[3], p[4], p[5]) for p in pernas] == [
        ('despesa', a['conta'], Decimal('300'), True, 'transferencia'),
        ('receita', reserva, Decimal('300'), True, 'transferencia')]
    assert pernas[0][6] == pernas[1][6]                      # mesma chave liga as pontas
    assert _saldos(app, a['conta'], reserva) == [700, 800]


def test_nao_conta_como_receita_nem_despesa(app, usuarios, client_a):
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    hoje = date.today()
    client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': reserva,
                                                'valor': '300', 'data': hoje.isoformat(), 'pago': 'on'})
    d = client_a.get(f'/api/fluxo-caixa?ano={hoje.year}').get_json()
    assert d['receitas'][hoje.month - 1] == 0 and d['despesas'][hoje.month - 1] == 0
    html = client_a.get('/transacoes').get_data(as_text=True)
    assert 'Transferência entre contas' in html and 'bi-arrow-left-right"></i> Transferência' in html


def test_editar_excluir_e_marcar_mexem_nas_duas_pontas(app, usuarios, client_a):
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': reserva,
                                                'valor': '300', 'data': ONTEM, 'pago': 'on'})
    saida = _pernas(app, a)[0][0]
    # editar: valor e sentido
    assert client_a.get(f'/transacoes/{saida}/editar').status_code == 302   # vai para o formulário de transferência
    client_a.post(f'/transferencias/{saida}/editar', data={'conta_origem_id': reserva, 'conta_destino_id': a['conta'],
                                                           'valor': '100', 'data': ONTEM, 'pago': 'on'})
    assert _saldos(app, a['conta'], reserva) == [1100, 400]
    # desmarcar pago em uma ponta desfaz nas duas
    client_a.post(f'/transacoes/{saida}/toggle-pago')
    assert _saldos(app, a['conta'], reserva) == [1000, 500]
    assert all(not p[4] for p in _pernas(app, a))
    client_a.post(f'/transacoes/{saida}/toggle-pago')
    # excluir uma ponta exclui a outra e devolve os saldos
    client_a.post(f'/transacoes/{saida}/deletar')
    assert _pernas(app, a) == [] and _saldos(app, a['conta'], reserva) == [1000, 500]


def test_validacoes(app, usuarios, client_a):
    a, b = usuarios
    reserva = _segunda_conta(app, a)
    client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': a['conta'],
                                                'valor': '10', 'data': ONTEM, 'pago': 'on'})
    assert _pernas(app, a) == []
    r = client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': b['conta'],
                                                    'valor': '10', 'data': ONTEM, 'pago': 'on'})
    assert r.status_code == 404 and _pernas(app, a) == []      # conta de outro usuário
    futuro = (date.today() + timedelta(days=5)).isoformat()
    client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': reserva,
                                                'valor': '10', 'data': futuro, 'pago': 'on'})
    assert all(not p[4] for p in _pernas(app, a)) and _saldos(app, a['conta'], reserva) == [1000, 500]


def test_extrato_concilia_com_transferencia_lancada(app, usuarios):
    """Linha do banco 'Pix enviado - Fulano' casa com a transferência lançada na tela (não duplica)."""
    from app.models import db, Conta
    from app.matching import processar_matching
    from app.services.saldos import salvar_transferencia
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    d = date.today() - timedelta(days=2)
    with app.app_context():
        salvar_transferencia(a['user'], db.session.get(Conta, a['conta']), db.session.get(Conta, reserva),
                             Decimal('300'), d, '', True)
        db.session.commit()
        itens = [{'data': d, 'valor': Decimal('300'), 'tipo': 'despesa', 'descricao': 'Pix enviado - Fulano de Tal'}]
        r = processar_matching(itens, a['conta'], a['user'])
        assert r[0]['status_sugerido'] == 'conciliar'


def test_conciliar_extrato_paga_as_duas_pontas(app, usuarios):
    from app.models import db, Conta, Transacao, ConciliacaoBancaria, ItemConciliacao
    from app.services.saldos import salvar_transferencia
    from app.services.importacao import aplicar_conciliacao
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    d = date.today() - timedelta(days=1)
    with app.app_context():
        saida, entrada = salvar_transferencia(a['user'], db.session.get(Conta, a['conta']), db.session.get(Conta, reserva),
                                              Decimal('200'), d, '', False)
        conc = ConciliacaoBancaria(user_id=a['user'], conta_id=a['conta'], arquivo_nome='x.ofx', formato='OFX',
                                   data_inicio=d, data_fim=d, status='pendente_revisao')
        db.session.add(conc); db.session.flush()
        db.session.add(ItemConciliacao(conciliacao_id=conc.id, data=d, descricao='Pix enviado - Fulano', valor=Decimal('200'),
                                       tipo='despesa', status='pendente', acao_sugerida='conciliar', transacao_id=saida.id))
        db.session.commit()
        aplicar_conciliacao(db.session.get(ConciliacaoBancaria, conc.id))
        assert all(t.pago for t in Transacao.query.filter(Transacao.id_externo.like('TRF%')).all())
    assert _saldos(app, a['conta'], reserva) == [800, 700]


def test_totais_separam_recebido_e_a_receber(app, usuarios, client_a):
    from app.models import db
    from tests.test_fluxo import _t
    a, _ = usuarios
    reserva = _segunda_conta(app, a)
    hoje = date.today()
    with app.app_context():
        db.session.add_all([
            _t(a['conta'], a['receita'], 'receita', '1000', hoje.replace(day=1), pago=True),
            _t(a['conta'], a['receita'], 'receita', '2500', hoje.replace(day=1), pago=False),   # prevista
        ])
        db.session.commit()
    client_a.post('/transferencias/nova', data={'conta_origem_id': a['conta'], 'conta_destino_id': reserva,
                                                'valor': '400', 'data': hoje.replace(day=1).isoformat(), 'pago': 'on'})
    nb = ' '
    html = client_a.get(f'/transacoes?mes={hoje.month}&ano={hoje.year}').get_data(as_text=True)
    assert f'R${nb}3.500,00' in html and f'recebido R${nb}1.000 · a receber R${nb}2.500' in html
    html = client_a.get(f'/?mes={hoje.month}&ano={hoje.year}').get_data(as_text=True)
    assert f'Recebido R${nb}1.000 · a receber R${nb}2.500' in html
