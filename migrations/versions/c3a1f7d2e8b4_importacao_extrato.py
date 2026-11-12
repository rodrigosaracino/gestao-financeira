"""Importação de extrato: deduplicação (id_externo), fatura de cartão e saldo do banco

Revision ID: c3a1f7d2e8b4
Revises: 5b19b8709657
Create Date: 2026-11-12

Idempotente: só adiciona colunas/índices que ainda não existem (o banco de
produção pode ter sido criado via db.create_all()).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3a1f7d2e8b4'
down_revision = '5b19b8709657'
branch_labels = None
depends_on = None


COLUNAS = [
    ('contas', sa.Column('id_banco', sa.String(length=50), nullable=True)),
    ('transacoes', sa.Column('id_externo', sa.String(length=64), nullable=True)),
    ('transacoes', sa.Column('conciliacao_origem_id', sa.Integer(), nullable=True)),
    ('conciliacoes_bancarias', sa.Column('cartao_credito_id', sa.Integer(), nullable=True)),
    ('conciliacoes_bancarias', sa.Column('hash_arquivo', sa.String(length=64), nullable=True)),
    ('conciliacoes_bancarias', sa.Column('saldo_extrato', sa.Numeric(12, 2), nullable=True)),
    ('itens_conciliacao', sa.Column('id_externo', sa.String(length=64), nullable=True)),
    ('itens_conciliacao', sa.Column('numero_parcela', sa.Integer(), nullable=True)),
    ('itens_conciliacao', sa.Column('total_parcelas', sa.Integer(), nullable=True)),
    ('itens_conciliacao', sa.Column('acao_sugerida', sa.String(length=20), nullable=True)),
]

INDICES = [
    ('ix_transacoes_id_externo', 'transacoes', ['id_externo']),
    ('ix_transacoes_conciliacao_origem_id', 'transacoes', ['conciliacao_origem_id']),
    ('ix_conciliacoes_bancarias_hash_arquivo', 'conciliacoes_bancarias', ['hash_arquivo']),
]


def _colunas(insp, tabela):
    return {c['name'] for c in insp.get_columns(tabela)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    for tabela, coluna in COLUNAS:
        if coluna.name not in _colunas(insp, tabela):
            with op.batch_alter_table(tabela) as batch:
                batch.add_column(coluna)
    insp = sa.inspect(op.get_bind())
    for nome, tabela, cols in INDICES:
        if nome not in {i['name'] for i in insp.get_indexes(tabela)}:
            op.create_index(nome, tabela, cols)


def downgrade():
    insp = sa.inspect(op.get_bind())
    for nome, tabela, _ in INDICES:
        if nome in {i['name'] for i in insp.get_indexes(tabela)}:
            op.drop_index(nome, table_name=tabela)
    for tabela, coluna in reversed(COLUNAS):
        if coluna.name in _colunas(insp, tabela):
            with op.batch_alter_table(tabela) as batch:
                batch.drop_column(coluna.name)
