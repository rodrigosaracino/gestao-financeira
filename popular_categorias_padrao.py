#!/usr/bin/env python3
"""
Script para popular categorias padrão no sistema.
Estas categorias são criadas automaticamente para novos usuários.
"""

from app import create_app, db
from app.models import Categoria, User

# Categorias padrão que fazem sentido para a maior parte das pessoas
CATEGORIAS_PADRAO = {
    'despesa': [
        {'nome': 'Alimentação', 'cor': '#e74c3c'},
        {'nome': 'Transporte', 'cor': '#3498db'},
        {'nome': 'Moradia', 'cor': '#9b59b6'},
        {'nome': 'Saúde', 'cor': '#2ecc71'},
        {'nome': 'Educação', 'cor': '#f39c12'},
        {'nome': 'Lazer e Entretenimento', 'cor': '#1abc9c'},
        {'nome': 'Vestuário', 'cor': '#e67e22'},
        {'nome': 'Contas e Serviços', 'cor': '#34495e'},
        {'nome': 'Mercado', 'cor': '#c0392b'},
        {'nome': 'Combustível', 'cor': '#16a085'},
        {'nome': 'Restaurantes', 'cor': '#d35400'},
        {'nome': 'Academia e Esportes', 'cor': '#27ae60'},
        {'nome': 'Farmácia', 'cor': '#8e44ad'},
        {'nome': 'Beleza e Cuidados Pessoais', 'cor': '#f368e0'},
        {'nome': 'Internet e Telefone', 'cor': '#2c3e50'},
        {'nome': 'Streaming e Assinaturas', 'cor': '#6c5ce7'},
        {'nome': 'Viagens', 'cor': '#00b894'},
        {'nome': 'Presentes e Doações', 'cor': '#fd79a8'},
        {'nome': 'Impostos e Taxas', 'cor': '#636e72'},
        {'nome': 'Seguros', 'cor': '#2d3436'},
        {'nome': 'Pets', 'cor': '#a29bfe'},
        {'nome': 'Manutenção e Reparos', 'cor': '#fab1a0'},
        {'nome': 'Outros', 'cor': '#95a5a6'},
    ],
    'receita': [
        {'nome': 'Salário', 'cor': '#27ae60'},
        {'nome': 'Freelance', 'cor': '#16a085'},
        {'nome': 'Investimentos', 'cor': '#2ecc71'},
        {'nome': 'Aluguel Recebido', 'cor': '#1abc9c'},
        {'nome': 'Bonificações', 'cor': '#3498db'},
        {'nome': 'Restituição de Impostos', 'cor': '#9b59b6'},
        {'nome': 'Vendas', 'cor': '#f39c12'},
        {'nome': 'Presentes Recebidos', 'cor': '#fd79a8'},
        {'nome': 'Outras Receitas', 'cor': '#95a5a6'},
    ]
}


def criar_categorias_para_usuario(user_id):
    """
    Cria as categorias padrão para um usuário específico.

    Args:
        user_id: ID do usuário

    Returns:
        Número de categorias criadas
    """
    total_criadas = 0

    for tipo, categorias in CATEGORIAS_PADRAO.items():
        for cat_data in categorias:
            # Verificar se categoria já existe para este usuário
            categoria_existente = Categoria.query.filter_by(
                user_id=user_id,
                nome=cat_data['nome'],
                tipo=tipo
            ).first()

            if not categoria_existente:
                categoria = Categoria(
                    nome=cat_data['nome'],
                    tipo=tipo,
                    cor=cat_data['cor'],
                    user_id=user_id
                )
                db.session.add(categoria)
                total_criadas += 1

    db.session.commit()
    return total_criadas


def popular_para_todos_usuarios():
    """
    Popula categorias padrão para todos os usuários que não têm categorias.
    """
    app = create_app()

    with app.app_context():
        usuarios = User.query.all()

        print(f"Encontrados {len(usuarios)} usuários no sistema")

        for usuario in usuarios:
            # Verificar se usuário já tem categorias
            categorias_existentes = Categoria.query.filter_by(user_id=usuario.id).count()

            if categorias_existentes == 0:
                print(f"\nCriando categorias para: {usuario.email}")
                total = criar_categorias_para_usuario(usuario.id)
                print(f"  ✓ {total} categorias criadas")
            else:
                print(f"\n{usuario.email} já possui {categorias_existentes} categorias")

        print("\n✓ Processo concluído!")


def popular_para_usuario_especifico(email):
    """
    Popula categorias padrão para um usuário específico.

    Args:
        email: Email do usuário
    """
    app = create_app()

    with app.app_context():
        usuario = User.query.filter_by(email=email).first()

        if not usuario:
            print(f"❌ Usuário {email} não encontrado!")
            return

        print(f"Criando categorias para: {usuario.email}")
        total = criar_categorias_para_usuario(usuario.id)
        print(f"✓ {total} categorias criadas com sucesso!")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        # Criar para usuário específico
        email = sys.argv[1]
        popular_para_usuario_especifico(email)
    else:
        # Criar para todos os usuários que não têm categorias
        popular_para_todos_usuarios()
