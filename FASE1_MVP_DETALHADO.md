# 🚀 FASE 1: MVP COMERCIAL - Guia Detalhado de Implementação

**Prazo:** 8-10 semanas
**Investimento:** R$ 15-20k
**Objetivo:** Lançar versão paga funcional e competitiva

---

## 📋 ÍNDICE
1. [Sistema de Pagamento](#1-sistema-de-pagamento)
2. [Orçamentos e Metas](#2-orçamentos-e-metas)
3. [Relatórios Avançados](#3-relatórios-avançados)
4. [Melhorias de UX](#4-melhorias-de-ux)
5. [Landing Page](#5-landing-page)
6. [Segurança](#6-segurança)
7. [Cronograma](#cronograma)

---

## 1. SISTEMA DE PAGAMENTO

### 1.1. Escolha do Gateway

**Recomendação: Stripe**
- ✅ Melhor API do mercado
- ✅ Suporte a subscriptions nativo
- ✅ Webhooks confiáveis
- ✅ PCI compliance automático
- ✅ Dashboard completo
- ❌ Taxa: 3,99% + R$ 0,39

**Alternativa: MercadoPago**
- ✅ Mais conhecido no Brasil
- ✅ Pix integrado
- ✅ Boleto + Cartão
- ❌ API menos robusta
- ❌ Taxa: 4,99% + R$ 0,39

**Escolha Final:** Stripe para cartão + MercadoPago para Pix/Boleto

### 1.2. Implementação Técnica

#### **Novo Modelo: Subscription**

```python
# app/models.py

class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Stripe
    stripe_customer_id = db.Column(db.String(100))
    stripe_subscription_id = db.Column(db.String(100))

    # Plano
    plan = db.Column(db.String(20))  # 'free', 'premium', 'premium_plus'
    status = db.Column(db.String(20))  # 'active', 'canceled', 'past_due', 'trialing'

    # Datas
    trial_ends_at = db.Column(db.DateTime)
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    canceled_at = db.Column(db.DateTime, nullable=True)

    # Valores
    amount = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='BRL')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    user = db.relationship('User', backref='subscription_info')


class Plan(db.Model):
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)  # 'free', 'premium', 'premium_plus'
    display_name = db.Column(db.String(100))
    price_monthly = db.Column(db.Numeric(10, 2))
    price_yearly = db.Column(db.Numeric(10, 2))

    # Limites
    max_accounts = db.Column(db.Integer)  # null = ilimitado
    max_credit_cards = db.Column(db.Integer)
    max_transactions_per_month = db.Column(db.Integer)

    # Features
    has_budgets = db.Column(db.Boolean, default=False)
    has_goals = db.Column(db.Boolean, default=False)
    has_advanced_reports = db.Column(db.Boolean, default=False)
    has_export = db.Column(db.Boolean, default=False)
    has_mobile_app = db.Column(db.Boolean, default=False)
    has_ai_categorization = db.Column(db.Boolean, default=False)
    has_open_finance = db.Column(db.Boolean, default=False)

    stripe_price_id_monthly = db.Column(db.String(100))
    stripe_price_id_yearly = db.Column(db.String(100))

    active = db.Column(db.Boolean, default=True)
```

#### **Atualizar Model User**

```python
# Adicionar ao User model
class User(UserMixin, db.Model):
    # ... campos existentes ...

    # Subscription
    plan = db.Column(db.String(20), default='free')
    subscription_status = db.Column(db.String(20), default='active')
    trial_ends_at = db.Column(db.DateTime, nullable=True)

    def is_premium(self):
        return self.plan in ['premium', 'premium_plus']

    def is_trial(self):
        if self.trial_ends_at:
            return datetime.utcnow() < self.trial_ends_at
        return False

    def can_add_account(self):
        current_plan = Plan.query.filter_by(name=self.plan).first()
        if not current_plan.max_accounts:
            return True
        current_count = Conta.query.filter_by(user_id=self.id).count()
        return current_count < current_plan.max_accounts
```

#### **Rotas de Pagamento**

```python
# app/payment.py

import stripe
from flask import Blueprint, request, jsonify, redirect, url_for

bp = Blueprint('payment', __name__, url_prefix='/payment')

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """Cria sessão de checkout do Stripe"""
    plan = request.form.get('plan')  # 'premium' ou 'premium_plus'
    billing = request.form.get('billing')  # 'monthly' ou 'yearly'

    plan_obj = Plan.query.filter_by(name=plan).first()

    price_id = (plan_obj.stripe_price_id_yearly
                if billing == 'yearly'
                else plan_obj.stripe_price_id_monthly)

    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('payment.success', _external=True),
            cancel_url=url_for('payment.cancel', _external=True),
            metadata={
                'user_id': current_user.id
            }
        )
        return redirect(checkout_session.url)
    except Exception as e:
        flash('Erro ao processar pagamento', 'error')
        return redirect(url_for('main.index'))


@bp.route('/webhook', methods=['POST'])
def webhook():
    """Webhook do Stripe para atualizar status de assinatura"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400

    # Processar eventos
    if event['type'] == 'checkout.session.completed':
        handle_checkout_completed(event['data']['object'])
    elif event['type'] == 'customer.subscription.updated':
        handle_subscription_updated(event['data']['object'])
    elif event['type'] == 'customer.subscription.deleted':
        handle_subscription_deleted(event['data']['object'])

    return jsonify({'status': 'success'}), 200


@bp.route('/portal')
@login_required
def customer_portal():
    """Redireciona para portal do cliente Stripe"""
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()

    if not subscription or not subscription.stripe_customer_id:
        flash('Você não possui uma assinatura ativa', 'warning')
        return redirect(url_for('main.index'))

    session = stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=url_for('main.index', _external=True)
    )

    return redirect(session.url)
```

#### **Decorator para Premium**

```python
# app/decorators.py

from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.is_premium():
            flash('Esta funcionalidade é exclusiva para assinantes Premium', 'warning')
            return redirect(url_for('payment.plans'))

        return f(*args, **kwargs)
    return decorated_function
```

**Tempo:** 2 semanas

---

## 2. ORÇAMENTOS E METAS

### 2.1. Modelos de Dados

```python
# app/models.py

class Orcamento(db.Model):
    __tablename__ = 'orcamentos'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)

    # Período
    mes = db.Column(db.Integer, nullable=False)  # 1-12
    ano = db.Column(db.Integer, nullable=False)  # 2024, 2025...

    # Valor limite
    valor_limite = db.Column(db.Numeric(10, 2), nullable=False)

    # Alertas
    alerta_em_percentual = db.Column(db.Integer, default=80)  # Avisar ao atingir 80%

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    user = db.relationship('User', backref='orcamentos')
    categoria = db.relationship('Categoria')

    def valor_gasto(self):
        """Calcula quanto já foi gasto nesta categoria no período"""
        from sqlalchemy import extract, func

        total = db.session.query(func.sum(Transacao.valor)).join(Conta).filter(
            Transacao.categoria_id == self.categoria_id,
            Conta.user_id == self.user_id,
            Transacao.tipo == 'despesa',
            extract('month', Transacao.data) == self.mes,
            extract('year', Transacao.data) == self.ano
        ).scalar()

        return total or Decimal('0.00')

    def percentual_gasto(self):
        """Retorna percentual gasto do orçamento (0-100)"""
        if self.valor_limite == 0:
            return 0
        return float((self.valor_gasto() / self.valor_limite) * 100)

    def esta_no_limite(self):
        """Verifica se atingiu o alerta"""
        return self.percentual_gasto() >= self.alerta_em_percentual


class Meta(db.Model):
    __tablename__ = 'metas'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Detalhes
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)

    # Valores
    valor_alvo = db.Column(db.Numeric(10, 2), nullable=False)
    valor_inicial = db.Column(db.Numeric(10, 2), default=0)
    valor_mensal = db.Column(db.Numeric(10, 2))  # Quanto guardar por mês

    # Prazos
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    data_conclusao = db.Column(db.Date, nullable=True)

    # Status
    status = db.Column(db.String(20), default='ativa')  # ativa, concluida, cancelada

    # Conta vinculada (onde o dinheiro está guardado)
    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    user = db.relationship('User', backref='metas')
    conta = db.relationship('Conta')
    depositos = db.relationship('DepositoMeta', backref='meta', cascade='all, delete-orphan')

    def valor_acumulado(self):
        """Valor total acumulado na meta"""
        total_depositos = sum(d.valor for d in self.depositos)
        return self.valor_inicial + total_depositos

    def percentual_concluido(self):
        """Percentual da meta concluído (0-100)"""
        if self.valor_alvo == 0:
            return 0
        return float((self.valor_acumulado() / self.valor_alvo) * 100)

    def meses_restantes(self):
        """Quantidade de meses até o prazo"""
        hoje = date.today()
        if hoje >= self.data_fim:
            return 0
        return ((self.data_fim.year - hoje.year) * 12 +
                (self.data_fim.month - hoje.month))


class DepositoMeta(db.Model):
    __tablename__ = 'depositos_meta'

    id = db.Column(db.Integer, primary_key=True)
    meta_id = db.Column(db.Integer, db.ForeignKey('metas.id'), nullable=False)

    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    observacao = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### 2.2. Rotas e Views

```python
# app/routes.py

@bp.route('/orcamentos')
@login_required
@premium_required
def listar_orcamentos():
    """Lista orçamentos do mês atual"""
    mes = request.args.get('mes', type=int) or datetime.now().month
    ano = request.args.get('ano', type=int) or datetime.now().year

    orcamentos = Orcamento.query.filter_by(
        user_id=current_user.id,
        mes=mes,
        ano=ano
    ).all()

    return render_template('orcamentos/listar.html',
                         orcamentos=orcamentos,
                         mes=mes, ano=ano)


@bp.route('/metas')
@login_required
@premium_required
def listar_metas():
    """Lista todas as metas"""
    metas_ativas = Meta.query.filter_by(
        user_id=current_user.id,
        status='ativa'
    ).order_by(Meta.data_fim).all()

    metas_concluidas = Meta.query.filter_by(
        user_id=current_user.id,
        status='concluida'
    ).order_by(Meta.data_conclusao.desc()).limit(5).all()

    return render_template('metas/listar.html',
                         metas_ativas=metas_ativas,
                         metas_concluidas=metas_concluidas)
```

**Tempo:** 3 semanas

---

## 3. RELATÓRIOS AVANÇADOS

### 3.1. Exportação PDF

```python
# requirements.txt
weasyprint==60.1

# app/reports.py
from weasyprint import HTML
from flask import render_template

def gerar_relatorio_pdf(user_id, mes, ano):
    """Gera relatório mensal em PDF"""

    # Buscar dados
    transacoes = Transacao.query.join(Conta).filter(
        Conta.user_id == user_id,
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).all()

    # Calcular totais
    total_receitas = sum(t.valor for t in transacoes if t.tipo == 'receita')
    total_despesas = sum(t.valor for t in transacoes if t.tipo == 'despesa')

    # Gastos por categoria
    gastos_categoria = db.session.query(
        Categoria.nome,
        func.sum(Transacao.valor)
    ).join(Transacao).join(Conta).filter(
        Conta.user_id == user_id,
        Transacao.tipo == 'despesa',
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).group_by(Categoria.nome).all()

    # Renderizar HTML
    html_string = render_template('relatorios/pdf_mensal.html',
                                 mes=mes,
                                 ano=ano,
                                 transacoes=transacoes,
                                 total_receitas=total_receitas,
                                 total_despesas=total_despesas,
                                 gastos_categoria=gastos_categoria)

    # Converter para PDF
    pdf = HTML(string=html_string).write_pdf()

    return pdf
```

### 3.2. Exportação Excel

```python
# requirements.txt
openpyxl==3.1.2

# app/reports.py
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from io import BytesIO

def gerar_relatorio_excel(user_id, mes, ano):
    """Gera relatório mensal em Excel"""

    wb = Workbook()
    ws = wb.active
    ws.title = f"Finanças {mes}-{ano}"

    # Cabeçalho
    headers = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Conta', 'Pago']
    ws.append(headers)

    # Estilizar cabeçalho
    header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font

    # Buscar transações
    transacoes = Transacao.query.join(Conta).filter(
        Conta.user_id == user_id,
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).order_by(Transacao.data).all()

    # Adicionar dados
    for t in transacoes:
        ws.append([
            t.data.strftime('%d/%m/%Y'),
            t.descricao,
            t.categoria.nome,
            t.tipo.upper(),
            float(t.valor),
            t.conta.nome,
            'Sim' if t.pago else 'Não'
        ])

    # Totais
    ws.append([])
    ws.append(['TOTAIS'])

    total_receitas = sum(t.valor for t in transacoes if t.tipo == 'receita')
    total_despesas = sum(t.valor for t in transacoes if t.tipo == 'despesa')
    saldo = total_receitas - total_despesas

    ws.append(['Total Receitas', '', '', '', float(total_receitas)])
    ws.append(['Total Despesas', '', '', '', float(total_despesas)])
    ws.append(['Saldo', '', '', '', float(saldo)])

    # Salvar em BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


@bp.route('/relatorios/exportar/<formato>')
@login_required
@premium_required
def exportar_relatorio(formato):
    """Exporta relatório em PDF ou Excel"""
    mes = request.args.get('mes', type=int) or datetime.now().month
    ano = request.args.get('ano', type=int) or datetime.now().year

    if formato == 'pdf':
        pdf = gerar_relatorio_pdf(current_user.id, mes, ano)
        return send_file(
            BytesIO(pdf),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'relatorio_{mes}_{ano}.pdf'
        )
    elif formato == 'excel':
        excel = gerar_relatorio_excel(current_user.id, mes, ano)
        return send_file(
            excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'relatorio_{mes}_{ano}.xlsx'
        )
```

**Tempo:** 2 semanas

---

## 4. MELHORIAS DE UX

### 4.1. Onboarding

```python
# app/models.py - adicionar ao User
class User(UserMixin, db.Model):
    # ... campos existentes ...

    onboarding_completed = db.Column(db.Boolean, default=False)
    onboarding_step = db.Column(db.Integer, default=0)


# app/routes.py
@bp.route('/onboarding/<int:step>')
@login_required
def onboarding(step):
    """Wizard de onboarding em 5 passos"""
    if current_user.onboarding_completed:
        return redirect(url_for('main.index'))

    steps = {
        1: 'onboarding/step1_welcome.html',  # Bem-vindo
        2: 'onboarding/step2_account.html',  # Criar primeira conta
        3: 'onboarding/step3_categories.html',  # Escolher categorias
        4: 'onboarding/step4_first_transaction.html',  # Primeira transação
        5: 'onboarding/step5_done.html',  # Pronto!
    }

    if step not in steps:
        return redirect(url_for('main.onboarding', step=1))

    current_user.onboarding_step = step
    db.session.commit()

    return render_template(steps[step], step=step)
```

### 4.2. Dark Mode

```css
/* app/static/css/dark-mode.css */

:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f5f7fa;
    --text-primary: #0f1419;
    --text-secondary: #8b98a5;
    --border-color: #e8ecf0;
}

[data-theme="dark"] {
    --bg-primary: #15202b;
    --bg-secondary: #192734;
    --text-primary: #ffffff;
    --text-secondary: #8b98a5;
    --border-color: #38444d;
}

body {
    background-color: var(--bg-primary);
    color: var(--text-primary);
}

.card {
    background-color: var(--bg-secondary);
    border-color: var(--border-color);
}
```

```javascript
// app/static/js/dark-mode.js

// Detectar preferência do sistema
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const currentTheme = localStorage.getItem('theme') || (prefersDark ? 'dark' : 'light');

// Aplicar tema
document.documentElement.setAttribute('data-theme', currentTheme);

// Toggle
function toggleTheme() {
    const theme = document.documentElement.getAttribute('data-theme');
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}
```

**Tempo:** 2 semanas

---

## 5. LANDING PAGE

### 5.1. Estrutura

```
landing/
  ├── hero.html           # Seção principal
  ├── features.html       # Funcionalidades
  ├── pricing.html        # Preços
  ├── testimonials.html   # Depoimentos
  ├── faq.html           # Perguntas frequentes
  ├── cta.html           # Call-to-action
  └── footer.html        # Rodapé
```

### 5.2. Conteúdo Essencial

**Hero:**
- Título: "Organize suas finanças e alcance seus objetivos"
- Subtítulo: "Sistema completo de gestão financeira pessoal"
- CTA: "Comece grátis por 7 dias"
- Screenshot do dashboard

**Features (6 principais):**
1. Gestão completa de contas e cartões
2. Orçamentos inteligentes
3. Metas de economia
4. Relatórios detalhados
5. App mobile (iOS e Android)
6. 100% seguro e privado

**Pricing:**
- Free vs Premium (tabela comparativa)
- Destaque para Premium (R$ 14,90/mês)
- Badge "Mais popular"
- "Cancele quando quiser"

**Social Proof:**
- 5 depoimentos de beta users
- Nota 4.8/5 estrelas
- "+500 usuários confiam"

**FAQ (10 perguntas):**
1. Como funciona o trial?
2. Posso cancelar a qualquer momento?
3. Meus dados estão seguros?
4. Funciona offline?
5. Tem app mobile?
6. Posso importar do banco?
7. Quantas contas posso ter?
8. Como faço backup?
9. Tem suporte?
10. Aceita Pix?

**Tempo:** 1 semana (com designer)

---

## 6. SEGURANÇA

### 6.1. Checklist de Segurança

```python
# config.py - Produção

class ProductionConfig:
    # HTTPS obrigatório
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Senha forte
    MIN_PASSWORD_LENGTH = 8
    REQUIRE_PASSWORD_UPPERCASE = True
    REQUIRE_PASSWORD_LOWERCASE = True
    REQUIRE_PASSWORD_DIGIT = True

    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = 'redis://localhost:6379'
```

```python
# app/__init__.py

from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def create_app():
    app = Flask(__name__)

    # HTTPS forçado
    Talisman(app, force_https=True)

    # Rate limiting
    limiter = Limiter(
        app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )

    # Criptografia de dados sensíveis
    from cryptography.fernet import Fernet
    app.config['ENCRYPTION_KEY'] = os.getenv('ENCRYPTION_KEY')

    return app
```

### 6.2. LGPD Compliance

```python
# app/models.py

class DataExportRequest(db.Model):
    """Solicitação de exportação de dados (LGPD)"""
    __tablename__ = 'data_export_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    status = db.Column(db.String(20), default='pending')  # pending, processing, completed
    file_path = db.Column(db.String(500))

    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


class DataDeletionRequest(db.Model):
    """Solicitação de exclusão de dados (LGPD)"""
    __tablename__ = 'data_deletion_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')

    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)


@bp.route('/settings/export-data', methods=['POST'])
@login_required
def export_my_data():
    """Exportar todos os dados do usuário (LGPD)"""
    request_obj = DataExportRequest(user_id=current_user.id)
    db.session.add(request_obj)
    db.session.commit()

    # Processar em background (Celery)
    flash('Sua solicitação foi recebida. Você receberá um email em até 48h.', 'info')
    return redirect(url_for('main.settings'))


@bp.route('/settings/delete-account', methods=['POST'])
@login_required
def delete_my_account():
    """Solicitar exclusão da conta (LGPD)"""
    reason = request.form.get('reason')

    request_obj = DataDeletionRequest(
        user_id=current_user.id,
        reason=reason
    )
    db.session.add(request_obj)
    db.session.commit()

    flash('Sua conta será excluída em 30 dias. Você pode cancelar essa solicitação.', 'warning')
    return redirect(url_for('main.settings'))
```

**Tempo:** 1 semana

---

## CRONOGRAMA DETALHADO

### Semana 1-2: Pagamento
- [ ] Configurar Stripe
- [ ] Criar modelos Subscription e Plan
- [ ] Implementar checkout
- [ ] Configurar webhooks
- [ ] Portal do cliente
- [ ] Testes de pagamento

### Semana 3-4: Orçamentos
- [ ] Criar modelos Orcamento
- [ ] CRUD de orçamentos
- [ ] Dashboard de orçamentos
- [ ] Alertas de limite
- [ ] Notificações

### Semana 5: Metas
- [ ] Criar modelos Meta e DepositoMeta
- [ ] CRUD de metas
- [ ] Dashboard de metas
- [ ] Gráficos de progresso

### Semana 6: Relatórios
- [ ] Implementar exportação PDF
- [ ] Implementar exportação Excel
- [ ] Relatório comparativo mensal
- [ ] Testes de performance

### Semana 7: UX
- [ ] Criar onboarding
- [ ] Implementar dark mode
- [ ] Tours interativos
- [ ] Melhorias de performance

### Semana 8: Landing + Segurança
- [ ] Desenvolver landing page
- [ ] Gravar vídeo demo
- [ ] Implementar HTTPS
- [ ] LGPD compliance
- [ ] Backup automático

### Semana 9-10: Testes e Lançamento
- [ ] Beta testing (20 usuários)
- [ ] Correção de bugs
- [ ] Documentação
- [ ] Deploy em produção
- [ ] Lançamento público

---

## INVESTIMENTO NECESSÁRIO

### Desenvolvimento (R$ 12.000 - R$ 15.000)
- 80-100 horas de desenvolvimento
- Taxa horária: R$ 120-150/h

### Design (R$ 2.000 - R$ 3.000)
- Landing page profissional
- Templates de email
- Materiais de marketing

### Infraestrutura (R$ 500/mês)
- Servidor VPS (R$ 200)
- Domínio e SSL (R$ 50)
- Stripe fees (R$ 100)
- Backup e monitoramento (R$ 150)

### Marketing Inicial (R$ 2.000)
- Google Ads (R$ 1.000)
- Social Media Ads (R$ 500)
- Influencers (R$ 500)

**TOTAL INICIAL: R$ 16.500 - R$ 20.500**

---

## MÉTRICAS DE SUCESSO

### Lançamento (Mês 1)
- [ ] 100 signups (usuários free)
- [ ] 10 assinantes pagos
- [ ] NPS > 40
- [ ] Churn < 20%

### Crescimento (Mês 3)
- [ ] 300 signups
- [ ] 50 assinantes pagos
- [ ] MRR: R$ 750
- [ ] CAC < R$ 50

### Sustentabilidade (Mês 6)
- [ ] 1.000 signups
- [ ] 150 assinantes pagos
- [ ] MRR: R$ 2.200
- [ ] Break-even operacional

---

## CONCLUSÃO

Com este plano detalhado, em **8-10 semanas** teremos um MVP comercial completo e competitivo, pronto para começar a gerar receita recorrente.

**Próximo passo:** Aprovar o plano e iniciar desenvolvimento! 🚀
