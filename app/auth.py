"""
Rotas de autenticação (login, logout, registro)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, Categoria
from app.security import (
    sanitize_input, validate_email, get_client_ip,
    record_login_attempt, is_ip_blocked, log_suspicious_activity
)
from app import limiter

# Categorias padrão criadas automaticamente para novos usuários
CATEGORIAS_PADRAO = {
    'despesa': [
        {'nome': 'Alimentação', 'cor': '#e74c3c'},
        {'nome': 'Transporte', 'cor': '#3498db'},
        {'nome': 'Moradia', 'cor': '#9b59b6'},
        {'nome': 'Saúde', 'cor': '#2ecc71'},
        {'nome': 'Educação', 'cor': '#f39c12'},
        {'nome': 'Lazer e Entretenimento', 'cor': '#1abc9c'},
        {'nome': 'Vestuário', 'cor': '#e67e22'},
        {'nome': 'Contas e Serviços', 'cor': '#34495e'},
        {'nome': 'Mercado', 'cor': '#c0392b'},
        {'nome': 'Combustível', 'cor': '#16a085'},
        {'nome': 'Restaurantes', 'cor': '#d35400'},
        {'nome': 'Academia e Esportes', 'cor': '#27ae60'},
        {'nome': 'Farmácia', 'cor': '#8e44ad'},
        {'nome': 'Beleza e Cuidados Pessoais', 'cor': '#f368e0'},
        {'nome': 'Internet e Telefone', 'cor': '#2c3e50'},
        {'nome': 'Streaming e Assinaturas', 'cor': '#6c5ce7'},
        {'nome': 'Viagens', 'cor': '#00b894'},
        {'nome': 'Presentes e Doações', 'cor': '#fd79a8'},
        {'nome': 'Impostos e Taxas', 'cor': '#636e72'},
        {'nome': 'Seguros', 'cor': '#2d3436'},
        {'nome': 'Pets', 'cor': '#a29bfe'},
        {'nome': 'Manutenção e Reparos', 'cor': '#fab1a0'},
        {'nome': 'Outros', 'cor': '#95a5a6'},
    ],
    'receita': [
        {'nome': 'Salário', 'cor': '#27ae60'},
        {'nome': 'Freelance', 'cor': '#16a085'},
        {'nome': 'Investimentos', 'cor': '#2ecc71'},
        {'nome': 'Aluguel Recebido', 'cor': '#1abc9c'},
        {'nome': 'Bonificações', 'cor': '#3498db'},
        {'nome': 'Restituição de Impostos', 'cor': '#9b59b6'},
        {'nome': 'Vendas', 'cor': '#f39c12'},
        {'nome': 'Presentes Recebidos', 'cor': '#fd79a8'},
        {'nome': 'Outras Receitas', 'cor': '#95a5a6'},
    ]
}


def criar_categorias_padrao(user_id):
    """
    Cria categorias padrão para um novo usuário.

    Args:
        user_id: ID do usuário
    """
    for tipo, categorias in CATEGORIAS_PADRAO.items():
        for cat_data in categorias:
            categoria = Categoria(
                nome=cat_data['nome'],
                tipo=tipo,
                cor=cat_data['cor'],
                user_id=user_id
            )
            db.session.add(categoria)

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Página de login com proteção contra força bruta"""
    # Se já estiver autenticado, redirecionar para o dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        client_ip = get_client_ip()

        # Verificar se IP está bloqueado
        if is_ip_blocked(client_ip):
            log_suspicious_activity("Tentativa de login de IP bloqueado", level='warning')
            flash('Muitas tentativas falhadas. Tente novamente mais tarde.', 'error')
            return redirect(url_for('auth.login'))

        email = sanitize_input(request.form.get('email', ''))
        senha = request.form.get('senha', '')
        lembrar = 'lembrar' in request.form

        # Validar campos
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'error')
            return redirect(url_for('auth.login'))

        # Validar formato de email
        if not validate_email(email):
            log_suspicious_activity(f"Tentativa de login com email inválido: {email}", level='warning')
            flash('Email ou senha incorretos.', 'error')
            record_login_attempt(client_ip, success=False)
            return redirect(url_for('auth.login'))

        # Buscar usuário
        user = User.query.filter_by(email=email).first()

        # Verificar se usuário existe e senha está correta
        if not user or not user.check_password(senha):
            flash('Email ou senha incorretos.', 'error')
            record_login_attempt(client_ip, success=False)
            log_suspicious_activity(f"Tentativa de login falhada para: {email}", level='warning')
            return redirect(url_for('auth.login'))

        # Verificar se usuário está ativo
        if not user.ativo:
            flash('Sua conta está desativada. Entre em contato com o administrador.', 'error')
            log_suspicious_activity(f"Tentativa de login em conta desativada: {email}", level='warning')
            return redirect(url_for('auth.login'))

        # Login bem-sucedido
        login_user(user, remember=lembrar)
        record_login_attempt(client_ip, success=True)
        log_suspicious_activity(f"Login bem-sucedido: {email}", level='info')
        flash(f'Bem-vindo, {user.nome}!', 'success')

        # Redirecionar para a página solicitada ou dashboard
        next_page = request.args.get('next')
        if next_page:
            # Validar que next_page é uma URL local (prevenir open redirect)
            if next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
        return redirect(url_for('main.index'))

    return render_template('auth/login.html')


@auth.route('/registro', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def registro():
    """Página de registro de novo usuário com validações de segurança"""
    # Se já estiver autenticado, redirecionar para o dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        nome = sanitize_input(request.form.get('nome', ''))
        email = sanitize_input(request.form.get('email', ''))
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        # Validar campos
        if not nome or not email or not senha or not confirmar_senha:
            flash('Por favor, preencha todos os campos.', 'error')
            return redirect(url_for('auth.registro'))

        # Validar tamanho do nome
        if len(nome) < 2 or len(nome) > 100:
            flash('O nome deve ter entre 2 e 100 caracteres.', 'error')
            return redirect(url_for('auth.registro'))

        # Validar email
        if not validate_email(email):
            flash('Por favor, insira um email válido.', 'error')
            return redirect(url_for('auth.registro'))

        # Validar senha forte
        if len(senha) < 8:
            flash('A senha deve ter pelo menos 8 caracteres.', 'error')
            return redirect(url_for('auth.registro'))

        # Verificar complexidade da senha
        has_upper = any(c.isupper() for c in senha)
        has_lower = any(c.islower() for c in senha)
        has_digit = any(c.isdigit() for c in senha)

        if not (has_upper and has_lower and has_digit):
            flash('A senha deve conter letras maiúsculas, minúsculas e números.', 'error')
            return redirect(url_for('auth.registro'))

        if senha != confirmar_senha:
            flash('As senhas não coincidem.', 'error')
            return redirect(url_for('auth.registro'))

        # Verificar se email já existe
        user_existente = User.query.filter_by(email=email).first()
        if user_existente:
            flash('Este email já está cadastrado.', 'error')
            log_suspicious_activity(f"Tentativa de registro com email existente: {email}", level='warning')
            return redirect(url_for('auth.registro'))

        # Criar novo usuário
        novo_user = User(
            nome=nome,
            email=email
        )
        novo_user.set_password(senha)

        db.session.add(novo_user)
        db.session.flush()  # Para obter o ID do usuário

        # Criar categorias padrão para o novo usuário
        criar_categorias_padrao(novo_user.id)

        db.session.commit()

        log_suspicious_activity(f"Novo usuário registrado: {email}", level='info')
        flash('Conta criada com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/registro.html')


@auth.route('/logout')
@login_required
def logout():
    """Fazer logout"""
    logout_user()
    flash('Você saiu da sua conta.', 'success')
    return redirect(url_for('auth.login'))
