"""
Módulo de segurança centralizado
"""
import re
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, abort, current_app, session
from flask_login import current_user
import bleach
from collections import defaultdict

# Configurar logging de segurança
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)

# Armazenamento de tentativas de login (em produção, usar Redis)
login_attempts = defaultdict(list)
blocked_ips = {}


def sanitize_input(text, strip=True):
    """
    Sanitiza input do usuário para prevenir XSS

    Args:
        text: Texto a ser sanitizado
        strip: Se deve remover tags HTML completamente (padrão: True)

    Returns:
        Texto sanitizado
    """
    if not text:
        return text

    if strip:
        # Remove todas as tags HTML
        return bleach.clean(text, tags=[], strip=True)
    else:
        # Permite apenas tags seguras
        allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br']
        return bleach.clean(text, tags=allowed_tags, strip=True)


def validate_email(email):
    """
    Valida formato de email

    Args:
        email: Email a ser validado

    Returns:
        True se válido, False caso contrário
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_decimal(value, min_value=None, max_value=None):
    """
    Valida e sanitiza valores decimais

    Args:
        value: Valor a ser validado
        min_value: Valor mínimo permitido
        max_value: Valor máximo permitido

    Returns:
        Decimal sanitizado ou None se inválido
    """
    from decimal import Decimal, InvalidOperation

    try:
        decimal_value = Decimal(str(value))

        if min_value is not None and decimal_value < min_value:
            return None

        if max_value is not None and decimal_value > max_value:
            return None

        return decimal_value
    except (InvalidOperation, ValueError, TypeError):
        return None


def validate_date(date_str, format='%Y-%m-%d'):
    """
    Valida formato de data

    Args:
        date_str: String de data
        format: Formato esperado

    Returns:
        Objeto date se válido, None caso contrário
    """
    from datetime import datetime

    try:
        return datetime.strptime(date_str, format).date()
    except (ValueError, TypeError):
        return None


def check_file_extension(filename, allowed_extensions=None):
    """
    Verifica se a extensão do arquivo é permitida

    Args:
        filename: Nome do arquivo
        allowed_extensions: Set de extensões permitidas

    Returns:
        True se permitido, False caso contrário
    """
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'ofx', 'csv', 'txt'})

    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def get_client_ip():
    """
    Obtém o IP real do cliente, considerando proxies

    Returns:
        IP do cliente
    """
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr


def is_ip_blocked(ip):
    """
    Verifica se um IP está bloqueado

    Args:
        ip: Endereço IP

    Returns:
        True se bloqueado, False caso contrário
    """
    if ip in blocked_ips:
        block_time = blocked_ips[ip]
        if datetime.now() < block_time:
            return True
        else:
            # Desbloqueio automático
            del blocked_ips[ip]
    return False


def block_ip(ip, duration_minutes=15):
    """
    Bloqueia um IP por um período

    Args:
        ip: Endereço IP
        duration_minutes: Duração do bloqueio em minutos
    """
    blocked_ips[ip] = datetime.now() + timedelta(minutes=duration_minutes)
    security_logger.warning(f"IP bloqueado: {ip} até {blocked_ips[ip]}")


def record_login_attempt(ip, success=False):
    """
    Registra tentativa de login

    Args:
        ip: Endereço IP
        success: Se o login foi bem-sucedido

    Returns:
        Número de tentativas falhadas recentes
    """
    now = datetime.now()
    timeout = timedelta(minutes=current_app.config.get('LOGIN_ATTEMPT_TIMEOUT', 900) / 60)

    # Limpar tentativas antigas
    login_attempts[ip] = [
        attempt for attempt in login_attempts[ip]
        if now - attempt['time'] < timeout
    ]

    # Registrar nova tentativa
    login_attempts[ip].append({
        'time': now,
        'success': success
    })

    # Contar falhas
    failed_attempts = sum(1 for a in login_attempts[ip] if not a['success'])

    # Logar tentativa
    if success:
        security_logger.info(f"Login bem-sucedido de {ip}")
    else:
        security_logger.warning(f"Tentativa de login falhada de {ip} ({failed_attempts} falhas recentes)")

    # Bloquear se exceder limite
    max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
    if failed_attempts >= max_attempts:
        block_ip(ip)
        security_logger.error(f"IP bloqueado por excesso de tentativas: {ip}")

    return failed_attempts


def require_ownership(model_class, id_param='id', user_field='user_id'):
    """
    Decorator para verificar se o usuário é dono do recurso

    Args:
        model_class: Classe do modelo a verificar
        id_param: Nome do parâmetro que contém o ID
        user_field: Nome do campo que contém o user_id

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            resource_id = kwargs.get(id_param)
            if not resource_id:
                abort(400)

            resource = model_class.query.get_or_404(resource_id)

            if getattr(resource, user_field) != current_user.id:
                security_logger.warning(
                    f"Tentativa de acesso não autorizado: user {current_user.id} "
                    f"tentou acessar {model_class.__name__} {resource_id}"
                )
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_suspicious_activity(message, level='warning'):
    """
    Registra atividade suspeita

    Args:
        message: Mensagem a ser logada
        level: Nível de log (info, warning, error)
    """
    ip = get_client_ip()
    user_id = current_user.id if current_user.is_authenticated else 'anônimo'

    log_message = f"[{ip}] [User: {user_id}] {message}"

    if level == 'info':
        security_logger.info(log_message)
    elif level == 'warning':
        security_logger.warning(log_message)
    elif level == 'error':
        security_logger.error(log_message)


def validate_csrf_token():
    """
    Valida token CSRF para requisições AJAX

    Returns:
        True se válido, False caso contrário
    """
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError

    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')

    try:
        validate_csrf(token)
        return True
    except ValidationError:
        log_suspicious_activity("Token CSRF inválido", level='warning')
        return False


def check_sql_injection_patterns(text):
    """
    Verifica padrões comuns de SQL injection

    Args:
        text: Texto a ser verificado

    Returns:
        True se padrões suspeitos foram encontrados
    """
    if not text:
        return False

    # Padrões comuns de SQL injection
    sql_patterns = [
        r"(\bUNION\b.*\bSELECT\b)",
        r"(\bSELECT\b.*\bFROM\b)",
        r"(\bINSERT\b.*\bINTO\b)",
        r"(\bUPDATE\b.*\bSET\b)",
        r"(\bDELETE\b.*\bFROM\b)",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(--|\#|\/\*|\*\/)",
        r"(\bOR\b.*=.*)",
        r"(\bAND\b.*=.*)",
        r"(;.*\b(SELECT|INSERT|UPDATE|DELETE|DROP)\b)",
    ]

    text_upper = text.upper()

    for pattern in sql_patterns:
        if re.search(pattern, text_upper, re.IGNORECASE):
            return True

    return False


def sanitize_sql_input(text):
    """
    Sanitiza input para prevenir SQL injection
    Nota: Isso é uma camada extra. Use sempre prepared statements!

    Args:
        text: Texto a ser sanitizado

    Returns:
        Texto sanitizado
    """
    if not text:
        return text

    # Verificar padrões suspeitos
    if check_sql_injection_patterns(text):
        log_suspicious_activity(f"Possível SQL injection detectado: {text[:100]}", level='error')
        return None

    return text


def rate_limit_key():
    """
    Gera chave para rate limiting baseada no IP e usuário

    Returns:
        String chave única
    """
    ip = get_client_ip()
    if current_user.is_authenticated:
        return f"{ip}:{current_user.id}"
    return ip
