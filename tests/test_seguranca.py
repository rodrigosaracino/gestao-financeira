"""Testes de segurança: isolamento entre usuários, CSRF, redirect, XSS."""
from decimal import Decimal

from tests.conftest import HOJE, login


def _saldo(app, conta_id):
    from app.models import db, Conta
    with app.app_context():
        return db.session.get(Conta, conta_id).saldo_atual


def _qtd_transacoes(app, conta_id):
    from app.models import Transacao
    with app.app_context():
        return Transacao.query.filter_by(conta_id=conta_id).count()


# ---------- IDOR (um usuário mexendo nos dados de outro) ----------

def test_nova_transacao_em_conta_de_outro_usuario_e_bloqueada(app, usuarios, client_a):
    a, b = usuarios
    resp = client_a.post('/transacoes/nova', data={
        'descricao': 'ataque', 'valor': '500', 'tipo': 'despesa', 'data': HOJE,
        'conta_id': b['conta'], 'categoria_id': a['despesa'], 'pago': 'on',
    })
    assert resp.status_code == 404
    assert _saldo(app, b['conta']) == Decimal('1000')
    assert _qtd_transacoes(app, b['conta']) == 0


def test_nova_transacao_com_categoria_de_outro_usuario_e_bloqueada(app, usuarios, client_a):
    a, b = usuarios
    resp = client_a.post('/transacoes/nova', data={
        'descricao': 'x', 'valor': '10', 'tipo': 'despesa', 'data': HOJE,
        'conta_id': a['conta'], 'categoria_id': b['despesa'],
    })
    assert resp.status_code == 404


def test_nova_transacao_propria_funciona_e_atualiza_saldo(app, usuarios, client_a):
    a, _ = usuarios
    resp = client_a.post('/transacoes/nova', data={
        'descricao': 'mercado', 'valor': '100', 'tipo': 'despesa', 'data': HOJE,
        'conta_id': a['conta'], 'categoria_id': a['despesa'], 'pago': 'on',
    })
    assert resp.status_code == 302
    assert _saldo(app, a['conta']) == Decimal('900')


def test_tipo_invalido_e_rejeitado(app, usuarios, client_a):
    a, _ = usuarios
    resp = client_a.post('/transacoes/nova', data={
        'descricao': 'x', 'valor': '10', 'tipo': 'hack', 'data': HOJE,
        'conta_id': a['conta'], 'categoria_id': a['despesa'],
    })
    assert resp.status_code == 400


def test_editar_transacao_movendo_para_conta_de_outro_e_bloqueado(app, usuarios, client_a):
    from app.models import db, Transacao
    a, b = usuarios
    with app.app_context():
        t = Transacao(descricao='minha', valor=Decimal('50'), tipo='receita', data=__import__('datetime').date.today(),
                      conta_id=a['conta'], categoria_id=a['receita'], pago=True)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client_a.post(f'/transacoes/{tid}/editar', data={
        'descricao': 'minha', 'valor': '999999', 'tipo': 'receita', 'data': HOJE,
        'conta_id': b['conta'], 'categoria_id': a['receita'], 'pago': 'on',
    })
    assert resp.status_code == 404
    assert _saldo(app, b['conta']) == Decimal('1000')


def test_toggle_pago_de_transacao_alheia_retorna_404(app, usuarios, client_a):
    from app.models import db, Transacao
    a, b = usuarios
    with app.app_context():
        t = Transacao(descricao='da vitima', valor=Decimal('50'), tipo='despesa',
                      data=__import__('datetime').date.today(),
                      conta_id=b['conta'], categoria_id=b['despesa'], pago=False)
        db.session.add(t)
        db.session.commit()
        tid = t.id
    assert client_a.post(f'/transacoes/{tid}/toggle-pago').status_code == 404


def test_criar_inline_com_categoria_alheia_e_bloqueado(app, usuarios, client_a):
    a, b = usuarios
    resp = client_a.post('/transacoes/criar-inline', json={
        'descricao': 'x', 'valor': 10, 'tipo': 'despesa', 'data': HOJE,
        'categoria_id': b['despesa'], 'conta_id': a['conta'],
    })
    assert resp.status_code == 404


def test_pagar_fatura_debitando_conta_de_outro_e_bloqueado(app, usuarios, client_a):
    from app.models import db, Fatura
    from datetime import date
    a, b = usuarios
    with app.app_context():
        f = Fatura(cartao_id=a['cartao'], mes_referencia=1, ano_referencia=2026,
                   data_fechamento=date(2026, 1, 5), data_vencimento=date(2026, 1, 15),
                   valor_total=Decimal('300'), valor_pago=Decimal('0'))
        db.session.add(f)
        db.session.commit()
        fid = f.id
    resp = client_a.post(f'/faturas/{fid}/pagar', data={'valor_pago': '300', 'conta_id': b['conta']})
    assert resp.status_code == 404
    assert _saldo(app, b['conta']) == Decimal('1000')


def test_orcamento_com_categoria_alheia_e_bloqueado(app, usuarios, client_a):
    a, b = usuarios
    resp = client_a.post('/orcamentos/novo', data={
        'categoria_id': b['despesa'], 'mes': '1', 'ano': '2026', 'valor_limite': '100',
    })
    assert resp.status_code == 404


def test_meta_com_conta_alheia_e_bloqueada(app, usuarios, client_a):
    a, b = usuarios
    resp = client_a.post('/metas/nova', data={
        'titulo': 'x', 'valor_alvo': '100', 'data_inicio': '2026-01-01', 'data_fim': '2026-12-31',
        'conta_id': b['conta'],
    })
    assert resp.status_code == 404


def test_parcelas_sao_limitadas(app, usuarios, client_a):
    from app.models import Transacao
    a, _ = usuarios
    client_a.post('/transacoes/nova', data={
        'descricao': 'tv', 'valor': '720', 'tipo': 'despesa', 'data': HOJE,
        'forma_pagamento': 'cartao_credito', 'cartao_credito_id': a['cartao'],
        'categoria_id': a['despesa'], 'conta_id': a['conta'], 'total_parcelas': '1000000',
    })
    with app.app_context():
        assert Transacao.query.filter_by(cartao_credito_id=a['cartao']).count() <= 72


# ---------- Autenticação / sessão ----------

def test_logout_exige_post(app, usuarios, client_a):
    assert client_a.get('/logout').status_code == 405
    assert client_a.post('/logout').status_code == 302


def test_redirect_externo_apos_login_e_ignorado(app, usuarios):
    c = app.test_client()
    resp = c.post('/login?next=/\\evil.com', data={'email': usuarios[0]['email'], 'senha': usuarios[0]['senha']})
    assert resp.status_code == 302
    assert 'evil.com' not in resp.headers['Location']


def test_is_safe_redirect():
    from app.security import is_safe_redirect
    assert is_safe_redirect('/transacoes')
    for ruim in ['//evil.com', '/\\evil.com', 'https://evil.com', 'javascript:alert(1)', '', None, '/a\r\nb']:
        assert not is_safe_redirect(ruim)


def test_mask_email():
    from app.security import mask_email
    assert mask_email('rodrigo@gmail.com') == 'ro***@gmail.com'
    assert '\n' not in mask_email('a\nb@x.com')


def test_cor_de_categoria_invalida_e_substituida(app, usuarios, client_a):
    from app.models import Categoria
    client_a.post('/categorias/nova', data={
        'nome': 'Teste', 'tipo': 'despesa', 'cor': 'red;background:url(javascript:alert(1))'})
    with app.app_context():
        cat = Categoria.query.filter_by(nome='Teste').first()
        assert cat.cor == '#3498db'


def test_ip_nao_vem_de_x_forwarded_for_sem_proxy(app):
    from app.security import get_client_ip
    with app.test_request_context('/', headers={'X-Forwarded-For': '6.6.6.6'},
                                  environ_base={'REMOTE_ADDR': '10.0.0.1'}):
        assert get_client_ip() == '10.0.0.1'


# ---------- CSRF ----------

def test_csrf_bloqueia_post_sem_token(csrf_app):
    from tests.conftest import criar_usuario
    with csrf_app.app_context():
        a = criar_usuario('A', 'a@exemplo.com')
    c = csrf_app.test_client()
    resp = c.post('/login', data={'email': a['email'], 'senha': a['senha']})
    assert resp.status_code == 400


def test_formularios_renderizam_token_csrf(csrf_app):
    import re
    from tests.conftest import criar_usuario
    with csrf_app.app_context():
        a = criar_usuario('A', 'a@exemplo.com')
    c = csrf_app.test_client()
    html = c.get('/login').get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    assert c.post('/login', data={'email': a['email'], 'senha': a['senha'], 'csrf_token': token}).status_code == 302
    for url in ['/contas/nova', '/categorias/nova', '/cartoes/novo', '/conciliacao/nova', '/transacoes']:
        pagina = c.get(url)
        assert pagina.status_code == 200, url
        corpo = pagina.get_data(as_text=True)
        if 'method="POST"' in corpo or "method='POST'" in corpo:
            assert 'name="csrf_token"' in corpo, url


def test_templates_post_tem_csrf():
    """Nenhum <form method=POST> nos templates pode ficar sem csrf_token."""
    import glob
    import os
    import re
    base = os.path.join(os.path.dirname(__file__), '..', 'app', 'templates')
    faltando = []
    for f in glob.glob(os.path.join(base, '**', '*.html'), recursive=True):
        s = open(f, encoding='utf-8').read()
        for m in re.finditer(r'<form\b[^>]*>', s, re.I):
            if re.search(r'method\s*=\s*["\']?post', m.group(0), re.I):
                fim = s.find('</form>', m.end())
                if 'csrf_token' not in s[m.end():fim]:
                    faltando.append(os.path.relpath(f, base))
    assert not faltando, faltando
