from flask import Flask, request, abort
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from app.models import db
import logging
from logging.handlers import RotatingFileHandler
import os

migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Confiar apenas no proxy reverso (Traefik) para IP/protocolo do cliente.
    # Assim request.remote_addr passa a ser o IP real e X-Forwarded-For
    # forjado pelo cliente é ignorado.
    proxies = app.config.get('TRUSTED_PROXIES', 1)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    # Inicializar extensões de segurança
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    # Configurar Talisman (HTTPS e Security Headers)
    if app.config.get('IS_PRODUCTION') and not app.config.get('TESTING'):
        Talisman(app,
                force_https=app.config.get('TALISMAN_FORCE_HTTPS', True),
                strict_transport_security=app.config.get('TALISMAN_STRICT_TRANSPORT_SECURITY', True),
                content_security_policy=app.config.get('TALISMAN_CONTENT_SECURITY_POLICY'),
                session_cookie_secure=True)

    # Configurar logging de segurança
    if not app.debug and not app.config.get('TESTING'):
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # Log de aplicação
        file_handler = RotatingFileHandler('logs/gestao_financeira.log',
                                          maxBytes=10240000, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Sistema de Gestão Financeira iniciado')

        # Log de segurança
        security_handler = RotatingFileHandler('logs/security.log',
                                              maxBytes=10240000, backupCount=10)
        security_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        security_logger = logging.getLogger('security')
        security_logger.addHandler(security_handler)
        security_logger.setLevel(logging.INFO)

    # Configurar Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # Middleware de segurança
    @app.before_request
    def security_checks():
        from app.security import get_client_ip, is_ip_blocked, log_suspicious_activity

        # Verificar IP bloqueado
        client_ip = get_client_ip()
        if is_ip_blocked(client_ip):
            log_suspicious_activity(f"Tentativa de acesso de IP bloqueado: {client_ip}", level='warning')
            abort(403)

        # Verificar tamanho do conteúdo
        if request.content_length:
            max_size = app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
            if request.content_length > max_size:
                log_suspicious_activity(f"Requisição muito grande rejeitada: {request.content_length} bytes", level='warning')
                abort(413)

    # Headers de segurança adicionais
    @app.after_request
    def set_security_headers(response):
        # Prevenir MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # Prevenir clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions Policy
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        return response

    # Registrar blueprints
    from app import routes, auth, investimentos
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.auth)
    app.register_blueprint(investimentos.investimentos_bp)

    return app
