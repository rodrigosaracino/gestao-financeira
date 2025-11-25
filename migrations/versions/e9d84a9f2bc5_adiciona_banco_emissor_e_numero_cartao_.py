"""Adiciona banco_emissor e numero_cartao ao CartaoCredito

Revision ID: e9d84a9f2bc5
Revises: 9ec06e0b1a39
Create Date: 2025-11-25 16:09:34.693967

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9d84a9f2bc5'
down_revision = '9ec06e0b1a39'
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar coluna banco_emissor
    op.add_column('cartoes_credito', sa.Column('banco_emissor', sa.String(length=100), nullable=True))

    # Adicionar coluna numero_cartao (últimos 4 dígitos)
    op.add_column('cartoes_credito', sa.Column('numero_cartao', sa.String(length=4), nullable=True))


def downgrade():
    # Remover colunas adicionadas
    op.drop_column('cartoes_credito', 'numero_cartao')
    op.drop_column('cartoes_credito', 'banco_emissor')
