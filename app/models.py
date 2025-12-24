from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Modelo para usuários do sistema"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    ativo = db.Column(db.Boolean, default=True)

    # Relacionamentos
    contas = db.relationship('Conta', backref='usuario', lazy=True, cascade='all, delete-orphan')
    categorias = db.relationship('Categoria', backref='usuario', lazy=True, cascade='all, delete-orphan')
    cartoes = db.relationship('CartaoCredito', backref='usuario', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        """Define a senha do usuário (criptografada)"""
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha está correta"""
        return check_password_hash(self.senha_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

class Conta(db.Model):
    """Modelo para contas bancárias"""
    __tablename__ = 'contas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # corrente, poupanca, investimento
    saldo_inicial = db.Column(db.Numeric(10, 2), default=0.00)
    saldo_atual = db.Column(db.Numeric(10, 2), default=0.00)
    ativa = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    transacoes = db.relationship('Transacao', backref='conta', lazy=True)

    def __repr__(self):
        return f'<Conta {self.nome}>'


class Categoria(db.Model):
    """Modelo para categorias de gastos"""
    __tablename__ = 'categorias'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # receita, despesa
    cor = db.Column(db.String(7))  # código hexadecimal da cor
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    transacoes = db.relationship('Transacao', backref='categoria', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('nome', 'user_id', name='unique_categoria_per_user'),
    )

    def __repr__(self):
        return f'<Categoria {self.nome}>'


class Transacao(db.Model):
    """Modelo para transações (receitas e despesas)"""
    __tablename__ = 'transacoes'

    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # receita, despesa
    data = db.Column(db.Date, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # Campos para pagamento
    forma_pagamento = db.Column(db.String(20), default='dinheiro')  # dinheiro, cartao_credito
    cartao_credito_id = db.Column(db.Integer, db.ForeignKey('cartoes_credito.id'), nullable=True)
    pago = db.Column(db.Boolean, default=False)  # Se foi pago (despesa) ou recebido (receita)

    # Campos para parcelamento
    parcelado = db.Column(db.Boolean, default=False)
    numero_parcela = db.Column(db.Integer, nullable=True)  # Ex: 1 (se for parcela 1 de 12)
    total_parcelas = db.Column(db.Integer, nullable=True)  # Ex: 12 (total de parcelas)
    transacao_pai_id = db.Column(db.Integer, nullable=True)  # ID da transação original (para parcelas)

    # Campos para recorrência
    recorrente = db.Column(db.Boolean, default=False)
    frequencia_recorrencia = db.Column(db.String(20), nullable=True)  # mensal, semanal, quinzenal, anual
    data_inicio_recorrencia = db.Column(db.Date, nullable=True)
    data_fim_recorrencia = db.Column(db.Date, nullable=True)  # Mantido para compatibilidade
    quantidade_recorrencias = db.Column(db.Integer, nullable=True)  # Número de vezes que deve ocorrer
    transacao_recorrente_pai_id = db.Column(db.Integer, nullable=True)  # ID da transação recorrente original

    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    fatura_id = db.Column(db.Integer, db.ForeignKey('faturas.id'), nullable=True)

    def pode_marcar_pago(self):
        """Verifica se a transação pode ser marcada como paga"""
        # Transações de cartão de crédito não podem ser marcadas individualmente
        return self.forma_pagamento != 'cartao_credito'

    def __repr__(self):
        return f'<Transacao {self.descricao} - R$ {self.valor}>'


class CartaoCredito(db.Model):
    """Modelo para cartões de crédito"""
    __tablename__ = 'cartoes_credito'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    bandeira = db.Column(db.String(50))  # Visa, Mastercard, etc
    banco_emissor = db.Column(db.String(100))  # Banco que emitiu o cartão
    numero_cartao = db.Column(db.String(4))  # Últimos 4 dígitos do cartão
    limite = db.Column(db.Numeric(10, 2), nullable=False)
    limite_utilizado = db.Column(db.Numeric(10, 2), default=0.00)
    dia_fechamento = db.Column(db.Integer, nullable=False)  # 1-31
    dia_vencimento = db.Column(db.Integer, nullable=False)  # 1-31
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    faturas = db.relationship('Fatura', backref='cartao', lazy=True)

    def limite_disponivel(self):
        """Calcula o limite disponível"""
        return self.limite - self.limite_utilizado

    def percentual_utilizado(self):
        """Calcula o percentual do limite utilizado"""
        if self.limite > 0:
            return (self.limite_utilizado / self.limite) * 100
        return 0

    def __repr__(self):
        return f'<CartaoCredito {self.nome}>'


class Fatura(db.Model):
    """Modelo para faturas de cartão de crédito"""
    __tablename__ = 'faturas'

    id = db.Column(db.Integer, primary_key=True)
    cartao_id = db.Column(db.Integer, db.ForeignKey('cartoes_credito.id'), nullable=False)
    mes_referencia = db.Column(db.Integer, nullable=False)  # 1-12
    ano_referencia = db.Column(db.Integer, nullable=False)
    data_fechamento = db.Column(db.Date, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    valor_total = db.Column(db.Numeric(10, 2), default=0.00)
    valor_pago = db.Column(db.Numeric(10, 2), default=0.00)
    status = db.Column(db.String(20), default='aberta')  # aberta, fechada, paga, vencida
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    transacoes = db.relationship('Transacao', backref='fatura', lazy=True)

    def __repr__(self):
        return f'<Fatura {self.mes_referencia}/{self.ano_referencia} - {self.cartao.nome}>'


class ConciliacaoBancaria(db.Model):
    """Modelo para conciliações bancárias"""
    __tablename__ = 'conciliacoes_bancarias'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=False)

    # Informações do arquivo
    arquivo_nome = db.Column(db.String(200), nullable=False)
    formato = db.Column(db.String(10), nullable=False)  # OFX, CSV

    # Status e estatísticas
    data_upload = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='processando')  # processando, pendente_revisao, concluida, erro
    total_linhas = db.Column(db.Integer, default=0)
    linhas_conciliadas = db.Column(db.Integer, default=0)
    linhas_importadas = db.Column(db.Integer, default=0)

    # Data range do arquivo
    data_inicio = db.Column(db.Date, nullable=True)
    data_fim = db.Column(db.Date, nullable=True)

    # Relacionamentos
    usuario = db.relationship('User', backref='conciliacoes')
    conta = db.relationship('Conta', backref='conciliacoes')
    itens = db.relationship('ItemConciliacao', backref='conciliacao', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ConciliacaoBancaria {self.arquivo_nome} - {self.conta.nome}>'


class ItemConciliacao(db.Model):
    """Modelo para itens individuais de uma conciliação"""
    __tablename__ = 'itens_conciliacao'

    id = db.Column(db.Integer, primary_key=True)
    conciliacao_id = db.Column(db.Integer, db.ForeignKey('conciliacoes_bancarias.id'), nullable=False)

    # Dados do item do extrato
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(500), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # receita, despesa

    # Dados extras do arquivo
    numero_documento = db.Column(db.String(100), nullable=True)
    saldo_apos = db.Column(db.Numeric(10, 2), nullable=True)

    # Status de conciliação
    status = db.Column(db.String(20), default='pendente')  # pendente, conciliado, importado, ignorado
    transacao_id = db.Column(db.Integer, db.ForeignKey('transacoes.id'), nullable=True)  # Se foi conciliado com transação existente
    categoria_sugerida_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=True)

    # Score de matching (0-100)
    score_matching = db.Column(db.Integer, nullable=True)

    data_processamento = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    transacao = db.relationship('Transacao', backref='itens_conciliacao')
    categoria_sugerida = db.relationship('Categoria', backref='itens_conciliacao_sugeridos')

    def __repr__(self):
        return f'<ItemConciliacao {self.descricao} - R$ {self.valor}>'


class Orcamento(db.Model):
    """Modelo para orçamentos mensais por categoria"""
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
    usuario = db.relationship('User', backref='orcamentos')
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

        return total or 0

    def percentual_gasto(self):
        """Retorna percentual gasto do orçamento (0-100)"""
        if self.valor_limite == 0:
            return 0
        return float((self.valor_gasto() / self.valor_limite) * 100)

    def esta_no_limite(self):
        """Verifica se atingiu o alerta"""
        return self.percentual_gasto() >= self.alerta_em_percentual

    def saldo_restante(self):
        """Retorna o saldo restante do orçamento"""
        return self.valor_limite - self.valor_gasto()

    def __repr__(self):
        return f'<Orcamento {self.categoria.nome} - {self.mes}/{self.ano}>'


class Meta(db.Model):
    """Modelo para metas de economia"""
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
    usuario = db.relationship('User', backref='metas')
    conta = db.relationship('Conta')
    depositos = db.relationship('DepositoMeta', backref='meta', cascade='all, delete-orphan')

    def valor_acumulado(self):
        """Valor total acumulado na meta"""
        from decimal import Decimal
        total_depositos = sum(d.valor for d in self.depositos)
        return Decimal(str(self.valor_inicial)) + Decimal(str(total_depositos))

    def percentual_concluido(self):
        """Percentual da meta concluído (0-100)"""
        if self.valor_alvo == 0:
            return 0
        return float((self.valor_acumulado() / self.valor_alvo) * 100)

    def meses_restantes(self):
        """Quantidade de meses até o prazo"""
        from datetime import date
        from dateutil.relativedelta import relativedelta

        hoje = date.today()
        if hoje >= self.data_fim:
            return 0

        delta = relativedelta(self.data_fim, hoje)
        return delta.years * 12 + delta.months

    def saldo_faltante(self):
        """Retorna quanto ainda falta para atingir a meta"""
        return self.valor_alvo - self.valor_acumulado()

    def __repr__(self):
        return f'<Meta {self.titulo}>'


class DepositoMeta(db.Model):
    """Modelo para depósitos realizados em uma meta"""
    __tablename__ = 'depositos_meta'

    id = db.Column(db.Integer, primary_key=True)
    meta_id = db.Column(db.Integer, db.ForeignKey('metas.id'), nullable=False)

    valor = db.Column(db.Numeric(10, 2), nullable=False)
    data = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    observacao = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DepositoMeta R$ {self.valor} - {self.data}>'


class TipoAtivo(db.Model):
    """Modelo para tipos de ativos (ações, FIIs, Tesouro Direto, etc)"""
    __tablename__ = 'tipos_ativos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)  # Ação, FII, Tesouro Direto, Renda Fixa, Cripto
    descricao = db.Column(db.String(200))

    # Relacionamentos
    ativos = db.relationship('Ativo', backref='tipo', lazy=True)

    def __repr__(self):
        return f'<TipoAtivo {self.nome}>'


class Ativo(db.Model):
    """Modelo para ativos financeiros (ações, FIIs, etc)"""
    __tablename__ = 'ativos'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_ativo_id = db.Column(db.Integer, db.ForeignKey('tipos_ativos.id'), nullable=False)

    # Identificação
    ticker = db.Column(db.String(20), nullable=False)  # PETR4, BBAS3, MXRF11
    nome = db.Column(db.String(200))  # Petrobras PN, Banco do Brasil ON, Maxi Renda FII
    instituicao = db.Column(db.String(200))  # Corretora/Banco onde está investido

    # Dados de aquisição
    quantidade = db.Column(db.Numeric(10, 4), nullable=False, default=0)  # Permite fracionadas
    preco_medio = db.Column(db.Numeric(10, 2), nullable=False)  # Preço médio de compra

    # Cache da última cotação (para economizar API calls)
    ultimo_preco = db.Column(db.Numeric(10, 2))
    ultima_atualizacao = db.Column(db.DateTime)  # Quando foi atualizado
    variacao_dia = db.Column(db.Numeric(10, 2))  # % de variação no dia

    # Status
    ativo = db.Column(db.Boolean, default=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    usuario = db.relationship('User', backref='ativos')
    transacoes_ativo = db.relationship('TransacaoAtivo', backref='ativo', cascade='all, delete-orphan')
    dividendos = db.relationship('Dividendo', backref='ativo', cascade='all, delete-orphan')

    def valor_investido(self):
        """Retorna o valor total investido"""
        from decimal import Decimal
        return Decimal(str(self.quantidade)) * Decimal(str(self.preco_medio))

    def valor_atual(self):
        """Retorna o valor atual do ativo"""
        from decimal import Decimal
        if self.ultimo_preco:
            return Decimal(str(self.quantidade)) * Decimal(str(self.ultimo_preco))
        return self.valor_investido()

    def rentabilidade_percentual(self):
        """Retorna a rentabilidade em %"""
        investido = self.valor_investido()
        if investido == 0:
            return 0
        atual = self.valor_atual()
        return float(((atual - investido) / investido) * 100)

    def rentabilidade_reais(self):
        """Retorna a rentabilidade em R$"""
        return self.valor_atual() - self.valor_investido()

    def precisa_atualizar(self):
        """Verifica se precisa atualizar cotação (cache > 15 min)"""
        from datetime import timedelta
        if not self.ultima_atualizacao:
            return True
        return datetime.utcnow() - self.ultima_atualizacao > timedelta(minutes=15)

    def __repr__(self):
        return f'<Ativo {self.ticker} - {self.quantidade}>'


class TransacaoAtivo(db.Model):
    """Modelo para transações de compra/venda de ativos"""
    __tablename__ = 'transacoes_ativos'

    id = db.Column(db.Integer, primary_key=True)
    ativo_id = db.Column(db.Integer, db.ForeignKey('ativos.id'), nullable=False)

    # Tipo de operação
    tipo = db.Column(db.String(20), nullable=False)  # compra, venda

    # Dados da transação
    quantidade = db.Column(db.Numeric(10, 4), nullable=False)
    preco_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    taxa_corretagem = db.Column(db.Numeric(10, 2), default=0)
    outros_custos = db.Column(db.Numeric(10, 2), default=0)

    # Data
    data_operacao = db.Column(db.Date, nullable=False)

    # Observações
    observacao = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def valor_total(self):
        """Valor total da operação (quantidade * preço + custos)"""
        from decimal import Decimal
        valor_base = Decimal(str(self.quantidade)) * Decimal(str(self.preco_unitario))
        custos = Decimal(str(self.taxa_corretagem)) + Decimal(str(self.outros_custos))
        return valor_base + custos

    def __repr__(self):
        return f'<TransacaoAtivo {self.tipo} {self.quantidade} - {self.data_operacao}>'


class Dividendo(db.Model):
    """Modelo para dividendos recebidos"""
    __tablename__ = 'dividendos'

    id = db.Column(db.Integer, primary_key=True)
    ativo_id = db.Column(db.Integer, db.ForeignKey('ativos.id'), nullable=False)

    # Tipo de provento
    tipo = db.Column(db.String(20), nullable=False)  # dividendo, jcp, rendimento

    # Valores
    valor_por_acao = db.Column(db.Numeric(10, 4), nullable=False)
    quantidade_acoes = db.Column(db.Numeric(10, 4), nullable=False)
    valor_total = db.Column(db.Numeric(10, 2), nullable=False)

    # Datas
    data_com = db.Column(db.Date)  # Data COM (último dia para ter direito)
    data_pagamento = db.Column(db.Date, nullable=False)

    # Status
    recebido = db.Column(db.Boolean, default=False)

    # Observações
    observacao = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Dividendo {self.ativo.ticker} - R$ {self.valor_total}>'
