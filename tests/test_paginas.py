"""Smoke test: todas as páginas GET principais abrem sem erro para um usuário logado."""
import pytest

PAGINAS = [
    '/', '/contas', '/contas/nova', '/transacoes', '/transacoes/nova', '/categorias',
    '/categorias/nova', '/cartoes', '/cartoes/novo', '/faturas', '/relatorios',
    '/conciliacao', '/conciliacao/nova', '/orcamentos', '/orcamentos/novo', '/metas',
    '/metas/nova', '/investimentos/', '/api/top-categorias', '/api/comparacao-periodos?quantidade=9999',
]


@pytest.mark.parametrize('url', PAGINAS)
def test_pagina_abre(client_a, url):
    resp = client_a.get(url)
    assert resp.status_code in (200, 302), (url, resp.status_code)


def test_pagina_exige_login(app):
    resp = app.test_client().get('/transacoes')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
