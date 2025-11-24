"""
Script para adicionar campos de parcelamento ao banco de dados
"""
from app import create_app
from app.models import db

app = create_app()

with app.app_context():
    # Adicionar colunas novas na tabela transacoes
    with db.engine.connect() as conn:
        try:
            # Forma de pagamento
            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS forma_pagamento VARCHAR(20) DEFAULT 'dinheiro'
            """))

            # Cartão de crédito
            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS cartao_credito_id INTEGER REFERENCES cartoes_credito(id)
            """))

            # Parcelamento
            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS parcelado BOOLEAN DEFAULT FALSE
            """))

            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS numero_parcela INTEGER
            """))

            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS total_parcelas INTEGER
            """))

            conn.execute(db.text("""
                ALTER TABLE transacoes
                ADD COLUMN IF NOT EXISTS transacao_pai_id INTEGER
            """))

            conn.commit()
            print("✓ Colunas adicionadas com sucesso!")

        except Exception as e:
            print(f"Erro ao adicionar colunas: {e}")
            conn.rollback()
