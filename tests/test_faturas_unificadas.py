"""Tela de faturas: todos os cartões juntos, por mês de vencimento."""
from datetime import date
from decimal import Decimal


def _fatura(cartao, mes, ano, fecha, vence, total, pago='0', status='aberta'):
    from app.models import Fatura
    return Fatura(cartao_id=cartao, mes_referencia=mes, ano_referencia=ano, data_fechamento=fecha,
                  data_vencimento=vence, valor_total=Decimal(total), valor_pago=Decimal(pago), status=status)


def _cenario(app, a):
    """Hoje = 15/11/2026. Dois cartões: A (fecha 31, vence 8) e B (fecha 3, vence 10)."""
    from app.models import db, CartaoCredito, Transacao
    with app.app_context():
        b = CartaoCredito(nome='Cartão B', limite=Decimal('2000'), limite_utilizado=Decimal('0'),
                          dia_fechamento=3, dia_vencimento=10, user_id=a['user'])
        db.session.add(b); db.session.flush()
        fs = [
            _fatura(a['cartao'], 9, 2026, date(2026, 9, 30), date(2026, 10, 8), '300', '300', 'paga'),
            _fatura(a['cartao'], 10, 2026, date(2026, 10, 31), date(2026, 11, 8), '200'),          # vencida
            _fatura(a['cartao'], 11, 2026, date(2026, 11, 30), date(2026, 12, 8), '500', '100'),   # atual
            _fatura(b.id, 11, 2026, date(2026, 11, 3), date(2026, 12, 10), '150'),                # fechada
            _fatura(b.id, 12, 2026, date(2026, 12, 3), date(2027, 1, 10), '80'),                  # atual de B
            _fatura(a['cartao'], 12, 2026, date(2026, 12, 31), date(2027, 1, 8), '120'),           # próxima de A
            _fatura(b.id, 1, 2027, date(2027, 1, 3), date(2027, 2, 10), '0'),                     # vazia: some
        ]
        db.session.add_all(fs); db.session.flush()
        db.session.add_all([
            Transacao(descricao='Mercado', valor=Decimal('520'), tipo='despesa', data=date(2026, 11, 10),
                      forma_pagamento='cartao_credito', cartao_credito_id=a['cartao'], fatura_id=fs[2].id,
                      conta_id=a['conta'], categoria_id=a['despesa']),
            Transacao(descricao='Estorno loja', valor=Decimal('20'), tipo='receita', data=date(2026, 11, 12),
                      forma_pagamento='cartao_credito', cartao_credito_id=a['cartao'], fatura_id=fs[2].id,
                      conta_id=a['conta'], categoria_id=a['receita']),
        ])
        db.session.commit()
        return b.id


def test_agrupa_por_vencimento_com_situacao(app, usuarios):
    from app.routes import faturas_por_vencimento
    a, _ = usuarios
    _cenario(app, a)
    with app.app_context():
        v = faturas_por_vencimento(a['user'], hoje=date(2026, 11, 15))
        grupos = [(g['chave'], [(l['fatura'].cartao.nome, l['situacao']) for l in g['faturas']], g['falta'])
                  for g in v['grupos']]
        assert grupos == [
            ((2026, 11), [('Cartão Atacante', 'vencida')], 200),
            ((2026, 12), [('Cartão Atacante', 'atual'), ('Cartão B', 'fechada')], 550),   # 400 + 150
            ((2027, 1), [('Cartão Atacante', 'proxima'), ('Cartão B', 'atual')], 200),
        ]
        assert v['total_em_aberto'] == 950
        assert v['proximo_mes']['chave'] == (2026, 11)
        assert [l['fatura'].mes_referencia for l in v['pagas']] == [9]
        atual = v['grupos'][1]['faturas'][0]
        assert [t.descricao for t in atual['itens']] == ['Mercado', 'Estorno loja']


def test_tela_de_faturas(app, usuarios, client_a):
    a, b = usuarios
    _cenario(app, a)
    html = client_a.get('/faturas').get_data(as_text=True)
    assert 'Todos os cartões juntos' in html and 'Cartão B' in html
    assert 'Estorno loja' in html and 'Faturas pagas' in html
    assert 'Cartão Vitima' not in html          # só os cartões do próprio usuário


def test_compra_depois_do_fechamento_vai_para_proxima_fatura(app, usuarios, client_a):
    from app.models import db, CartaoCredito, Fatura, Transacao
    a, _ = usuarios
    with app.app_context():
        c = db.session.get(CartaoCredito, a['cartao'])
        c.dia_fechamento, c.dia_vencimento = 8, 13
        db.session.commit()
    for dia in ('2031-03-05', '2031-03-20'):
        client_a.post('/transacoes/nova', data={
            'descricao': 'Compra', 'valor': '100', 'tipo': 'despesa', 'data': dia, 'conta_id': a['conta'],
            'categoria_id': a['despesa'], 'forma_pagamento': 'cartao_credito',
            'cartao_credito_id': a['cartao'], 'total_parcelas': '1'})
    with app.app_context():
        faturas = {t.data.day: db.session.get(Fatura, t.fatura_id)
                   for t in Transacao.query.filter_by(cartao_credito_id=a['cartao']).all()}
        assert faturas[5].data_vencimento == date(2031, 3, 13)    # antes do fechamento (8/3)
        assert faturas[20].data_vencimento == date(2031, 4, 13)   # depois: fatura seguinte
