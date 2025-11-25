"""
Rotas de autenticação (login, logout, registro)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    # Se já estiver autenticado, redirecionar para o dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        lembrar = 'lembrar' in request.form

        # Validar campos
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'error')
            return redirect(url_for('auth.login'))

        # Buscar usuário
        user = User.query.filter_by(email=email).first()

        # Verificar se usuário existe e senha está correta
        if not user or not user.check_password(senha):
            flash('Email ou senha incorretos.', 'error')
            return redirect(url_for('auth.login'))

        # Verificar se usuário está ativo
        if not user.ativo:
            flash('Sua conta está desativada. Entre em contato com o administrador.', 'error')
            return redirect(url_for('auth.login'))

        # Fazer login
        login_user(user, remember=lembrar)
        flash(f'Bem-vindo, {user.nome}!', 'success')

        # Redirecionar para a página solicitada ou dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('main.index'))

    return render_template('auth/login.html')


@auth.route('/registro', methods=['GET', 'POST'])
def registro():
    """Página de registro de novo usuário"""
    # Se já estiver autenticado, redirecionar para o dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        confirmar_senha = request.form.get('confirmar_senha')

        # Validar campos
        if not nome or not email or not senha or not confirmar_senha:
            flash('Por favor, preencha todos os campos.', 'error')
            return redirect(url_for('auth.registro'))

        # Validar email
        if '@' not in email or '.' not in email:
            flash('Por favor, insira um email válido.', 'error')
            return redirect(url_for('auth.registro'))

        # Validar senha
        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'error')
            return redirect(url_for('auth.registro'))

        if senha != confirmar_senha:
            flash('As senhas não coincidem.', 'error')
            return redirect(url_for('auth.registro'))

        # Verificar se email já existe
        user_existente = User.query.filter_by(email=email).first()
        if user_existente:
            flash('Este email já está cadastrado.', 'error')
            return redirect(url_for('auth.registro'))

        # Criar novo usuário
        novo_user = User(
            nome=nome,
            email=email
        )
        novo_user.set_password(senha)

        db.session.add(novo_user)
        db.session.commit()

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
