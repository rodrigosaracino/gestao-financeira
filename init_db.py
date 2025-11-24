#!/usr/bin/env python3
"""
Script para inicializar o banco de dados com dados de exemplo
"""

from app import create_app
from app.models import db, Conta, Categoria, CartaoCredito
from datetime import datetime

def init_database():
    """Inicializa o banco de dados com categorias padrão"""
    app = create_app()

    with app.app_context():
        # Criar todas as tabelas
        db.create_all()

        # Verificar se já existem categorias
        if Categoria.query.count() > 0:
            print("Banco de dados já contém dados. Pulando inicialização...")
            return

        print("Criando categorias padrão...")
        categorias = [
            # Despesas
            Categoria(nome='Alimentação', tipo='despesa', cor='#e74c3c'),
            Categoria(nome='Transporte', tipo='despesa', cor='#3498db'),
            Categoria(nome='Moradia', tipo='despesa', cor='#2ecc71'),
            Categoria(nome='Lazer', tipo='despesa', cor='#f39c12'),
            Categoria(nome='Saúde', tipo='despesa', cor='#9b59b6'),
            Categoria(nome='Educação', tipo='despesa', cor='#1abc9c'),
            Categoria(nome='Vestuário', tipo='despesa', cor='#34495e'),
            Categoria(nome='Serviços', tipo='despesa', cor='#95a5a6'),
            Categoria(nome='Outros', tipo='despesa', cor='#7f8c8d'),
            # Receitas
            Categoria(nome='Salário', tipo='receita', cor='#27ae60'),
            Categoria(nome='Investimentos', tipo='receita', cor='#16a085'),
            Categoria(nome='Freelance', tipo='receita', cor='#2980b9'),
            Categoria(nome='Outros', tipo='receita', cor='#8e44ad'),
        ]

        db.session.add_all(categorias)
        db.session.commit()
        print(f"✓ {len(categorias)} categorias criadas com sucesso!")

        print("\n" + "="*60)
        print("Banco de dados inicializado com sucesso!")
        print("="*60)
        print("\nCategorias de Despesa criadas:")
        for cat in [c for c in categorias if c.tipo == 'despesa']:
            print(f"  - {cat.nome}")

        print("\nCategorias de Receita criadas:")
        for cat in [c for c in categorias if c.tipo == 'receita']:
            print(f"  - {cat.nome}")

        print("\nPróximos passos:")
        print("1. Execute 'python3 run.py' para iniciar o servidor")
        print("2. Acesse http://localhost:5000 no navegador")
        print("3. Crie suas contas e comece a gerenciar suas finanças!")
        print("="*60)

if __name__ == '__main__':
    init_database()
