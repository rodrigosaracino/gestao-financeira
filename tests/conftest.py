import os
import sys

# Variáveis mínimas antes de importar config.py (que exige SECRET_KEY)
os.environ.setdefault('SECRET_KEY', 'chave-somente-para-testes')
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ['FLASK_ENV'] = 'testing'
os.environ['TRUSTED_PROXIES'] = '0'

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.pool import StaticPool

from config import Config


class TestConfig(Config):
    TESTING = True
    IS_PRODUCTION = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': StaticPool,
        'connect_args': {'check_same_thread': False},
    }
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    TRUSTED_PROXIES = 0


class CsrfConfig(TestConfig):
    WTF_CSRF_ENABLED = True


def _make_app(config):
    from app import create_app
    from app.models import db
    app = create_app(config)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def app():
    from app.models import db
    app = _make_app(TestConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_app():
    from app.models import db
    app = _make_app(CsrfConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def criar_usuario(nome, email, senha='SenhaForte123'):
    from app.models import db, User, Conta, Categoria, CartaoCredito
    u = User(nome=nome, email=email)
    u.set_password(senha)
    db.session.add(u)
    db.session.flush()
    conta = Conta(nome=f'Conta {nome}', tipo='corrente', saldo_inicial=Decimal('1000'),
                  saldo_atual=Decimal('1000'), user_id=u.id)
    desp = Categoria(nome='Outros', tipo='despesa', cor='#95a5a6', user_id=u.id)
    rec = Categoria(nome='Outras Receitas', tipo='receita', cor='#95a5a6', user_id=u.id)
    cartao = CartaoCredito(nome=f'Cartão {nome}', limite=Decimal('5000'), limite_utilizado=Decimal('0'),
                           dia_fechamento=5, dia_vencimento=15, user_id=u.id)
    db.session.add_all([conta, desp, rec, cartao])
    db.session.commit()
    return {'user': u.id, 'conta': conta.id, 'despesa': desp.id, 'receita': rec.id,
            'cartao': cartao.id, 'email': email, 'senha': senha}


@pytest.fixture
def usuarios(app):
    """Dois usuários: 'atacante' (A) e 'vitima' (B)."""
    with app.app_context():
        a = criar_usuario('Atacante', 'atacante@exemplo.com')
        b = criar_usuario('Vitima', 'vitima@exemplo.com')
    return a, b


def login(client, dados):
    return client.post('/login', data={'email': dados['email'], 'senha': dados['senha']})


@pytest.fixture
def client_a(app, usuarios):
    c = app.test_client()
    resp = login(c, usuarios[0])
    assert resp.status_code == 302
    return c


HOJE = date.today().strftime('%Y-%m-%d')
