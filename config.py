import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Segurança
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY deve ser configurada nas variáveis de ambiente!")

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://localhost/gestao_financeira'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Session Security
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hora

    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_ENABLED = True

    # Security Headers (Talisman)
    TALISMAN_FORCE_HTTPS = os.environ.get('FLASK_ENV') == 'production'
    TALISMAN_STRICT_TRANSPORT_SECURITY = True
    TALISMAN_CONTENT_SECURITY_POLICY = {
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'", 'cdn.jsdelivr.net', 'code.jquery.com', 'cdn.plot.ly'],
        'style-src': ["'self'", "'unsafe-inline'", 'cdn.jsdelivr.net', 'fonts.googleapis.com'],
        'font-src': ["'self'", 'fonts.gstatic.com', 'cdn.jsdelivr.net'],
        'img-src': ["'self'", 'data:', 'https:'],
    }

    # Upload Security
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'ofx', 'csv', 'txt'}

    # Login Security
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_ATTEMPT_TIMEOUT = 900  # 15 minutos
