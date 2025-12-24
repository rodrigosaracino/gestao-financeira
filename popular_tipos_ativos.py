"""
Script para popular tipos de ativos no banco de dados
"""
from app import create_app
from app.models import db, TipoAtivo

def popular_tipos_ativos():
    """Popula a tabela de tipos de ativos"""
    app = create_app()

    with app.app_context():
        # Verificar se já existem tipos
        if TipoAtivo.query.count() > 0:
            print("✅ Tipos de ativos já existem no banco de dados")
            return

        tipos = [
            {
                'nome': 'Ação',
                'descricao': 'Ações de empresas listadas na B3 (PETR4, VALE3, etc)'
            },
            {
                'nome': 'FII',
                'descricao': 'Fundos de Investimento Imobiliário'
            },
            {
                'nome': 'Tesouro Direto',
                'descricao': 'Títulos públicos do Tesouro Nacional'
            },
            {
                'nome': 'Renda Fixa',
                'descricao': 'CDB, LCI, LCA, Debêntures e outros títulos de renda fixa'
            },
            {
                'nome': 'Criptomoeda',
                'descricao': 'Bitcoin, Ethereum e outras criptomoedas'
            },
            {
                'nome': 'ETF',
                'descricao': 'Exchange Traded Funds'
            },
            {
                'nome': 'BDR',
                'descricao': 'Brazilian Depositary Receipts'
            },
            {
                'nome': 'Fundo de Investimento',
                'descricao': 'Fundos de ações, multimercado, etc'
            }
        ]

        print("Criando tipos de ativos...")
        for tipo_data in tipos:
            tipo = TipoAtivo(**tipo_data)
            db.session.add(tipo)
            print(f"  ✓ {tipo_data['nome']}")

        db.session.commit()
        print("\n✅ Tipos de ativos criados com sucesso!")
        print(f"Total: {TipoAtivo.query.count()} tipos")

if __name__ == '__main__':
    popular_tipos_ativos()
