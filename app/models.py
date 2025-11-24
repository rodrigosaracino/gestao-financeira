from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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

    transacoes = db.relationship('Transacao', backref='conta', lazy=True)

    def __repr__(self):
        return f'<Conta {self.nome}>'


class Categoria(db.Model):
    """Modelo para categorias de gastos"""
    __tablename__ = 'categorias'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    tipo = db.Column(db.String(20), nullable=False)  # receita, despesa
    cor = db.Column(db.String(7))  # código hexadecimal da cor

    transacoes = db.relationship('Transacao', backref='categoria', lazy=True)

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

    # Campos para parcelamento
    parcelado = db.Column(db.Boolean, default=False)
    numero_parcela = db.Column(db.Integer, nullable=True)  # Ex: 1 (se for parcela 1 de 12)
    total_parcelas = db.Column(db.Integer, nullable=True)  # Ex: 12 (total de parcelas)
    transacao_pai_id = db.Column(db.Integer, nullable=True)  # ID da transação original (para parcelas)

    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'), nullable=False)
    fatura_id = db.Column(db.Integer, db.ForeignKey('faturas.id'), nullable=True)

    def __repr__(self):
        return f'<Transacao {self.descricao} - R$ {self.valor}>'


class CartaoCredito(db.Model):
    """Modelo para cartões de crédito"""
    __tablename__ = 'cartoes_credito'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    bandeira = db.Column(db.String(50))  # Visa, Mastercard, etc
    limite = db.Column(db.Numeric(10, 2), nullable=False)
    dia_fechamento = db.Column(db.Integer, nullable=False)  # 1-31
    dia_vencimento = db.Column(db.Integer, nullable=False)  # 1-31
    ativo = db.Column(db.Boolean, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    faturas = db.relationship('Fatura', backref='cartao', lazy=True)

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
