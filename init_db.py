#!/usr/bin/env python3
"""
Script para inicializar o banco de dados com dados de exemplo
"""

from app import create_app
from app.models import db, Conta, Categoria, CartaoCredito
from datetime import datetime

def init_database():
    """Inicializa o banco de dados criando as tabelas"""
    app = create_app()

    with app.app_context():
        # Criar todas as tabelas
        db.create_all()

        print("\n" + "="*60)
        print("Banco de dados inicializado com sucesso!")
        print("="*60)
        print("\nPróximos passos:")
        print("1. Registre um novo usuário")
        print("2. Crie suas categorias personalizadas")
        print("3. Crie suas contas e comece a gerenciar suas finanças!")
        print("="*60)

if __name__ == '__main__':
    init_database()
