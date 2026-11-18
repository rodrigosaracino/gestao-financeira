"""Categoria.natureza: transferência entre contas e pagamento de fatura fora de receitas/despesas

Revision ID: d4b2e9a1c7f3
Revises: c3a1f7d2e8b4
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4b2e9a1c7f3'
down_revision = 'c3a1f7d2e8b4'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if 'natureza' not in {c['name'] for c in insp.get_columns('categorias')}:
        with op.batch_alter_table('categorias') as batch:
            batch.add_column(sa.Column('natureza', sa.String(length=20), nullable=False, server_default='normal'))
    op.execute("UPDATE categorias SET natureza='transferencia' WHERE nome LIKE 'Transfer%ncia % (minhas contas)'")
    op.execute("UPDATE categorias SET natureza='pagamento_cartao' WHERE nome = 'Pagamento de Fatura'")


def downgrade():
    with op.batch_alter_table('categorias') as batch:
        batch.drop_column('natureza')
