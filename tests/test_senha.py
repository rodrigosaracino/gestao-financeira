"""Troca de senha (tela) e redefinição (CLI)."""
from tests.conftest import login


def _post(c, atual, nova, confirmar=None):
    return c.post('/alterar-senha', data={'senha_atual': atual, 'nova_senha': nova,
                                           'confirmar_senha': nova if confirmar is None else confirmar})


def _senha_ok(app, uid, senha):
    from app.models import db, User
    with app.app_context():
        return db.session.get(User, uid).check_password(senha)


def test_pagina_alterar_senha_abre(client_a):
    assert client_a.get('/alterar-senha').status_code == 200


def test_alterar_senha_com_sucesso(app, usuarios, client_a):
    a, _ = usuarios
    assert _post(client_a, a['senha'], 'NovaSenha456').status_code == 302
    assert _senha_ok(app, a['user'], 'NovaSenha456')
    c = app.test_client()
    assert c.post('/login', data={'email': a['email'], 'senha': 'NovaSenha456'}).status_code == 302
    assert c.get('/transacoes').status_code == 200


def test_senha_atual_errada_nao_altera(app, usuarios, client_a):
    a, _ = usuarios
    _post(client_a, 'errada', 'NovaSenha456')
    assert _senha_ok(app, a['user'], a['senha'])


def test_senha_fraca_ou_diferente_nao_altera(app, usuarios, client_a):
    a, _ = usuarios
    _post(client_a, a['senha'], 'fraca')
    _post(client_a, a['senha'], 'NovaSenha456', 'OutraSenha789')
    assert _senha_ok(app, a['user'], a['senha'])


def test_alterar_senha_exige_login(app):
    resp = app.test_client().get('/alterar-senha')
    assert resp.status_code == 302 and '/login' in resp.headers['Location']


def test_cli_redefinir_senha(app, usuarios):
    a, b = usuarios
    runner = app.test_cli_runner()
    r = runner.invoke(args=['redefinir-senha', '--usuario', b['email']], input='Recuperada123\nRecuperada123\n')
    assert r.exit_code == 0, r.output
    assert 'Recuperada123' not in r.output  # senha nunca aparece na saída
    assert _senha_ok(app, b['user'], 'Recuperada123')


def test_cli_redefinir_senha_rejeita_fraca_e_inativo(app, usuarios):
    from app.models import db, User
    a, b = usuarios
    runner = app.test_cli_runner()
    r = runner.invoke(args=['redefinir-senha', '--usuario', b['email']], input='fraca\nfraca\n')
    assert r.exit_code != 0 and _senha_ok(app, b['user'], b['senha'])
    with app.app_context():
        db.session.get(User, a['user']).ativo = False
        db.session.commit()
    r = runner.invoke(args=['redefinir-senha', '--usuario', a['email']], input='Recuperada123\nRecuperada123\n')
    assert r.exit_code != 0
