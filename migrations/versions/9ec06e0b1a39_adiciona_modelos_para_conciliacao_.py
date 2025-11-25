"""Adiciona modelos para conciliacao bancaria

Revision ID: 9ec06e0b1a39
Revises: 
Create Date: 2025-11-25 15:08:40.278834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9ec06e0b1a39'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Criar tabela de conciliações bancárias
    op.create_table('conciliacoes_bancarias',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('conta_id', sa.Integer(), nullable=False),
        sa.Column('arquivo_nome', sa.String(length=200), nullable=False),
        sa.Column('formato', sa.String(length=10), nullable=False),
        sa.Column('data_upload', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('total_linhas', sa.Integer(), nullable=True),
        sa.Column('linhas_conciliadas', sa.Integer(), nullable=True),
        sa.Column('linhas_importadas', sa.Integer(), nullable=True),
        sa.Column('data_inicio', sa.Date(), nullable=True),
        sa.Column('data_fim', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['conta_id'], ['contas.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Criar tabela de itens de conciliação
    op.create_table('itens_conciliacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conciliacao_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('descricao', sa.String(length=500), nullable=False),
        sa.Column('valor', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('numero_documento', sa.String(length=100), nullable=True),
        sa.Column('saldo_apos', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('transacao_id', sa.Integer(), nullable=True),
        sa.Column('categoria_sugerida_id', sa.Integer(), nullable=True),
        sa.Column('score_matching', sa.Integer(), nullable=True),
        sa.Column('data_processamento', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['categoria_sugerida_id'], ['categorias.id'], ),
        sa.ForeignKeyConstraint(['conciliacao_id'], ['conciliacoes_bancarias.id'], ),
        sa.ForeignKeyConstraint(['transacao_id'], ['transacoes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('itens_conciliacao')
    op.drop_table('conciliacoes_bancarias')
