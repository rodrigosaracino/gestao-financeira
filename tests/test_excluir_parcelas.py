"""Excluir parcela: só esta ou esta e as próximas."""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta


def _compra(client, a, valor='600', parcelas='6', descricao='Notebook', data='2031-01-05'):
    client.post('/transacoes/nova', data={
        'descricao': descricao, 'valor': valor, 'tipo': 'despesa', 'data': data, 'conta_id': a['conta'],
        'categoria_id': a['despesa'], 'forma_pagamento': 'cartao_credito',
        'cartao_credito_id': a['cartao'], 'total_parcelas': parcelas})


def _parcelas(app, cartao, descricao='Notebook'):
    from app.models import Transacao
    with app.app_context():
        return [(t.id, t.numero_parcela) for t in Transacao.query.filter(
            Transacao.cartao_credito_id == cartao, Transacao.descricao.like(f'{descricao}%')
        ).order_by(Transacao.numero_parcela).all()]


def _limite(app, cartao):
    from app.models import db, CartaoCredito
    with app.app_context():
        return db.session.get(CartaoCredito, cartao).limite_utilizado


def test_so_esta_parcela(app, usuarios, client_a):
    a, _ = usuarios
    _compra(client_a, a)
    ids = dict((n, i) for i, n in _parcelas(app, a['cartao']))
    client_a.post(f'/transacoes/{ids[3]}/deletar', data={'escopo': 'esta'})
    assert [n for _, n in _parcelas(app, a['cartao'])] == [1, 2, 4, 5, 6]
    assert _limite(app, a['cartao']) == 500


def test_esta_e_as_proximas(app, usuarios, client_a):
    a, _ = usuarios
    _compra(client_a, a)
    _compra(client_a, a, valor='90', parcelas='3', descricao='Outra compra')   # não pode ser afetada
    ids = dict((n, i) for i, n in _parcelas(app, a['cartao']))
    r = client_a.post(f'/transacoes/{ids[4]}/deletar', data={'escopo': 'proximas'}, follow_redirects=True)
    assert '3 parcelas excluídas' in r.get_data(as_text=True)
    assert [n for _, n in _parcelas(app, a['cartao'])] == [1, 2, 3]
    assert len(_parcelas(app, a['cartao'], 'Outra compra')) == 3
    assert _limite(app, a['cartao']) == 300 + 90


def test_proximas_reconhece_parcelas_importadas_sem_vinculo(app, usuarios, client_a):
    """Parcelas vindas do extrato: sem transacao_pai_id, descrição 'PARC x/n' e '- Parcela x/n'."""
    from app.models import db, CartaoCredito, Transacao
    from app.routes import obter_ou_criar_fatura
    from app.services.saldos import recalcular_fatura, recalcular_limite
    a, _ = usuarios
    inicio = date(2031, 1, 10)
    with app.app_context():
        cartao = db.session.get(CartaoCredito, a['cartao'])
        for n in range(1, 5):
            d = inicio + relativedelta(months=n - 1)
            desc = f'Loja Xyz PARC {n:02d}/04' if n <= 2 else f'Loja Xyz - Parcela {n}/4'
            f = obter_ou_criar_fatura(cartao, d)
            db.session.add(Transacao(descricao=desc, valor=Decimal('50'), tipo='despesa', data=d,
                                     forma_pagamento='cartao_credito', cartao_credito_id=cartao.id,
                                     fatura_id=f.id, conta_id=a['conta'], categoria_id=a['despesa'],
                                     parcelado=True, numero_parcela=n, total_parcelas=4))
            db.session.flush()
            recalcular_fatura(f.id)
        # mesma loja, outra compra 4x começando bem depois: não faz parte da série
        d = date(2031, 8, 10)
        f = obter_ou_criar_fatura(cartao, d)
        db.session.add(Transacao(descricao='Loja Xyz PARC 02/04', valor=Decimal('50'), tipo='despesa', data=d,
                                 forma_pagamento='cartao_credito', cartao_credito_id=cartao.id, fatura_id=f.id,
                                 conta_id=a['conta'], categoria_id=a['despesa'], parcelado=True,
                                 numero_parcela=2, total_parcelas=4))
        db.session.flush(); recalcular_fatura(f.id)
        recalcular_limite(cartao.id)
        db.session.commit()
        segunda = Transacao.query.filter_by(numero_parcela=2, data=date(2031, 2, 10)).first().id
    client_a.post(f'/transacoes/{segunda}/deletar', data={'escopo': 'proximas'})
    restantes = _parcelas(app, a['cartao'], 'Loja Xyz')
    assert [n for _, n in restantes] == [1, 2]          # a 1/4 e a 2/4 da outra compra (agosto)
    assert _limite(app, a['cartao']) == 100


def test_transacao_normal_ignora_escopo(app, usuarios, client_a):
    from app.models import db, Conta
    a, _ = usuarios
    client_a.post('/transacoes/nova', data={'descricao': 'Padaria', 'valor': '30', 'tipo': 'despesa',
                                            'data': date.today().isoformat(), 'conta_id': a['conta'],
                                            'categoria_id': a['despesa'], 'pago': 'on'})
    from app.models import Transacao
    with app.app_context():
        tid = Transacao.query.filter_by(descricao='Padaria').first().id
    client_a.post(f'/transacoes/{tid}/deletar', data={'escopo': 'proximas'})
    with app.app_context():
        assert Transacao.query.filter_by(descricao='Padaria').count() == 0
        assert db.session.get(Conta, a['conta']).saldo_atual == 1000


def test_lista_tem_caixa_de_exclusao(app, usuarios, client_a):
    a, _ = usuarios
    _compra(client_a, a, data=date.today().isoformat())
    html = client_a.get('/transacoes').get_data(as_text=True)
    assert 'id="modalExcluir"' in html and 'Esta e as próximas' in html
    assert 'data-parcela="1" data-total="6"' in html


def test_duas_compras_iguais_no_mesmo_dia_sao_series_diferentes(app, usuarios, client_a):
    """Ex.: duas compras 12x na mesma loja no mesmo dia, uma estornada depois."""
    from app.models import db, CartaoCredito, Transacao
    from app.routes import obter_ou_criar_fatura
    from app.services.saldos import recalcular_fatura, recalcular_limite
    a, _ = usuarios
    with app.app_context():
        cartao = db.session.get(CartaoCredito, a['cartao'])
        def parcela(n, valor, d, pai=None):
            f = obter_ou_criar_fatura(cartao, d)
            t = Transacao(descricao=f'Loja Abc - Parcela {n}/12', valor=Decimal(valor), tipo='despesa', data=d,
                          forma_pagamento='cartao_credito', cartao_credito_id=cartao.id, fatura_id=f.id,
                          conta_id=a['conta'], categoria_id=a['despesa'], parcelado=True, numero_parcela=n,
                          total_parcelas=12, transacao_pai_id=pai)
            db.session.add(t); db.session.flush(); recalcular_fatura(f.id)
            return t
        manter = parcela(1, '136.06', date(2031, 9, 6))
        estornada = parcela(1, '147.83', date(2031, 9, 6))
        segunda = parcela(2, '136.03', date(2031, 10, 1))   # banco varia centavos
        for n in range(3, 13):
            parcela(n, '136.03', date(2031, 9, 1) + relativedelta(months=n - 1), pai=segunda.id)
        recalcular_limite(cartao.id)
        db.session.commit()
        estornada_id, manter_id = estornada.id, manter.id
    client_a.post(f'/transacoes/{estornada_id}/deletar', data={'escopo': 'proximas'})
    with app.app_context():
        restantes = Transacao.query.filter(Transacao.descricao.like('Loja Abc%')).all()
        assert len(restantes) == 12 and manter_id in {t.id for t in restantes}
    client_a.post(f'/transacoes/{manter_id}/deletar', data={'escopo': 'proximas'})
    with app.app_context():
        assert Transacao.query.filter(Transacao.descricao.like('Loja Abc%')).count() == 0
