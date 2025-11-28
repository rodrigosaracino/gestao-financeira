#!/usr/bin/env python3
"""
Script para popular banco de dados com dados fictícios
para o usuário teste@teste.com
"""

from app import create_app
from app.models import db, User, Conta, Categoria, Transacao, CartaoCredito, Fatura, Orcamento, Meta, DepositoMeta
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import random

app = create_app()

def criar_ou_buscar_usuario():
    """Cria ou busca o usuário teste@teste.com"""
    with app.app_context():
        user = User.query.filter_by(email='teste@teste.com').first()

        if not user:
            user = User(
                nome='Usuário Teste',
                email='teste@teste.com',
                ativo=True
            )
            user.set_password('teste123')
            db.session.add(user)
            db.session.commit()
            print(f"✅ Usuário criado: {user.email}")
        else:
            print(f"✅ Usuário encontrado: {user.email}")

        return user.id

def limpar_dados_usuario(user_id):
    """Remove todos os dados existentes do usuário"""
    with app.app_context():
        # Buscar IDs das contas do usuário
        contas_ids = [c.id for c in Conta.query.filter_by(user_id=user_id).all()]

        # Deletar transações das contas
        if contas_ids:
            Transacao.query.filter(Transacao.conta_id.in_(contas_ids)).delete(synchronize_session=False)

        # Buscar IDs das metas
        metas_ids = [m.id for m in Meta.query.filter_by(user_id=user_id).all()]

        # Deletar depósitos das metas
        if metas_ids:
            DepositoMeta.query.filter(DepositoMeta.meta_id.in_(metas_ids)).delete(synchronize_session=False)

        # Deletar metas
        Meta.query.filter_by(user_id=user_id).delete()

        # Deletar orçamentos
        Orcamento.query.filter_by(user_id=user_id).delete()

        # Buscar IDs dos cartões
        cartoes_ids = [c.id for c in CartaoCredito.query.filter_by(user_id=user_id).all()]

        # Deletar faturas dos cartões
        if cartoes_ids:
            Fatura.query.filter(Fatura.cartao_id.in_(cartoes_ids)).delete(synchronize_session=False)

        # Deletar cartões
        CartaoCredito.query.filter_by(user_id=user_id).delete()

        # Deletar categorias
        Categoria.query.filter_by(user_id=user_id).delete()

        # Deletar contas
        Conta.query.filter_by(user_id=user_id).delete()

        db.session.commit()
        print("🗑️  Dados anteriores limpos")

def criar_contas(user_id):
    """Cria contas bancárias"""
    with app.app_context():
        contas = [
            Conta(nome='Conta Corrente Nubank', tipo='corrente', saldo_inicial=Decimal('5000.00'), saldo_atual=Decimal('5000.00'), user_id=user_id, ativa=True),
            Conta(nome='Poupança Banco do Brasil', tipo='poupanca', saldo_inicial=Decimal('15000.00'), saldo_atual=Decimal('15000.00'), user_id=user_id, ativa=True),
            Conta(nome='Investimentos XP', tipo='investimento', saldo_inicial=Decimal('30000.00'), saldo_atual=Decimal('30000.00'), user_id=user_id, ativa=True),
        ]

        for conta in contas:
            db.session.add(conta)

        db.session.commit()
        print(f"✅ {len(contas)} contas criadas")
        return Conta.query.filter_by(user_id=user_id).all()

def criar_categorias(user_id):
    """Cria categorias de receitas e despesas"""
    with app.app_context():
        categorias = [
            # Despesas
            Categoria(nome='Alimentação', tipo='despesa', cor='#e74c3c', user_id=user_id),
            Categoria(nome='Transporte', tipo='despesa', cor='#3498db', user_id=user_id),
            Categoria(nome='Moradia', tipo='despesa', cor='#9b59b6', user_id=user_id),
            Categoria(nome='Saúde', tipo='despesa', cor='#1abc9c', user_id=user_id),
            Categoria(nome='Educação', tipo='despesa', cor='#f39c12', user_id=user_id),
            Categoria(nome='Lazer', tipo='despesa', cor='#e67e22', user_id=user_id),
            Categoria(nome='Assinaturas', tipo='despesa', cor='#34495e', user_id=user_id),
            Categoria(nome='Vestuário', tipo='despesa', cor='#16a085', user_id=user_id),
            Categoria(nome='Outros', tipo='despesa', cor='#95a5a6', user_id=user_id),

            # Receitas
            Categoria(nome='Salário', tipo='receita', cor='#2ecc71', user_id=user_id),
            Categoria(nome='Freelance', tipo='receita', cor='#27ae60', user_id=user_id),
            Categoria(nome='Investimentos', tipo='receita', cor='#16a085', user_id=user_id),
        ]

        for cat in categorias:
            db.session.add(cat)

        db.session.commit()
        print(f"✅ {len(categorias)} categorias criadas")
        return Categoria.query.filter_by(user_id=user_id).all()

def criar_cartoes(user_id):
    """Cria cartões de crédito"""
    with app.app_context():
        cartoes = [
            CartaoCredito(
                nome='Nubank Mastercard',
                bandeira='Mastercard',
                banco_emissor='Nubank',
                numero_cartao='1234',
                limite=Decimal('8000.00'),
                limite_utilizado=Decimal('2400.00'),
                dia_fechamento=15,
                dia_vencimento=25,
                user_id=user_id,
                ativo=True
            ),
            CartaoCredito(
                nome='Inter Visa Gold',
                bandeira='Visa',
                banco_emissor='Banco Inter',
                numero_cartao='5678',
                limite=Decimal('5000.00'),
                limite_utilizado=Decimal('1200.00'),
                dia_fechamento=10,
                dia_vencimento=20,
                user_id=user_id,
                ativo=True
            ),
        ]

        for cartao in cartoes:
            db.session.add(cartao)

        db.session.commit()
        print(f"✅ {len(cartoes)} cartões criados")
        return CartaoCredito.query.filter_by(user_id=user_id).all()

def criar_transacoes(user_id, contas, categorias):
    """Cria transações dos últimos 12 meses"""
    with app.app_context():
        hoje = date.today()

        # Categorias por tipo
        cats_despesa = [c for c in categorias if c.tipo == 'despesa']
        cats_receita = [c for c in categorias if c.tipo == 'receita']

        cat_salario = next(c for c in cats_receita if c.nome == 'Salário')
        cat_alimentacao = next(c for c in cats_despesa if c.nome == 'Alimentação')
        cat_transporte = next(c for c in cats_despesa if c.nome == 'Transporte')
        cat_moradia = next(c for c in cats_despesa if c.nome == 'Moradia')
        cat_lazer = next(c for c in cats_despesa if c.nome == 'Lazer')
        cat_assinaturas = next(c for c in cats_despesa if c.nome == 'Assinaturas')

        conta_corrente = contas[0]
        transacoes = []

        # Gerar transações para os últimos 12 meses
        for mes_offset in range(12, 0, -1):
            data_mes = hoje - relativedelta(months=mes_offset)
            primeiro_dia = date(data_mes.year, data_mes.month, 1)

            # Salário mensal (dia 5)
            if mes_offset <= 12:
                transacoes.append(Transacao(
                    descricao='Salário Empresa XYZ',
                    valor=Decimal('6500.00'),
                    tipo='receita',
                    data=date(data_mes.year, data_mes.month, 5),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_salario.id,
                    pago=True,
                    forma_pagamento='dinheiro'
                ))

            # Despesas fixas mensais
            # Aluguel
            transacoes.append(Transacao(
                descricao='Aluguel Apartamento',
                valor=Decimal('1800.00'),
                tipo='despesa',
                data=date(data_mes.year, data_mes.month, 10),
                conta_id=conta_corrente.id,
                categoria_id=cat_moradia.id,
                pago=True,
                forma_pagamento='dinheiro',
                recorrente=True
            ))

            # Assinaturas
            assinaturas = [
                ('Netflix', Decimal('55.90'), 15),
                ('Spotify', Decimal('21.90'), 18),
                ('Amazon Prime', Decimal('14.90'), 20),
            ]

            for desc, valor, dia in assinaturas:
                transacoes.append(Transacao(
                    descricao=desc,
                    valor=valor,
                    tipo='despesa',
                    data=date(data_mes.year, data_mes.month, dia),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_assinaturas.id,
                    pago=True,
                    forma_pagamento='dinheiro',
                    recorrente=True
                ))

            # Despesas variáveis
            # Supermercado (2-4x por mês)
            num_compras = random.randint(2, 4)
            for _ in range(num_compras):
                dia = random.randint(1, 28)
                transacoes.append(Transacao(
                    descricao='Supermercado',
                    valor=Decimal(random.uniform(150, 400)),
                    tipo='despesa',
                    data=date(data_mes.year, data_mes.month, dia),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_alimentacao.id,
                    pago=True,
                    forma_pagamento='dinheiro'
                ))

            # Restaurantes
            num_restaurantes = random.randint(3, 6)
            for _ in range(num_restaurantes):
                dia = random.randint(1, 28)
                transacoes.append(Transacao(
                    descricao='Restaurante',
                    valor=Decimal(random.uniform(40, 120)),
                    tipo='despesa',
                    data=date(data_mes.year, data_mes.month, dia),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_alimentacao.id,
                    pago=True,
                    forma_pagamento='dinheiro'
                ))

            # Uber/99
            num_corridas = random.randint(8, 15)
            for _ in range(num_corridas):
                dia = random.randint(1, 28)
                transacoes.append(Transacao(
                    descricao='Uber/99',
                    valor=Decimal(random.uniform(15, 45)),
                    tipo='despesa',
                    data=date(data_mes.year, data_mes.month, dia),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_transporte.id,
                    pago=True,
                    forma_pagamento='dinheiro'
                ))

            # Lazer
            num_lazer = random.randint(2, 4)
            for _ in range(num_lazer):
                dia = random.randint(1, 28)
                atividades = ['Cinema', 'Bar', 'Shopping', 'Show', 'Teatro']
                transacoes.append(Transacao(
                    descricao=random.choice(atividades),
                    valor=Decimal(random.uniform(50, 200)),
                    tipo='despesa',
                    data=date(data_mes.year, data_mes.month, dia),
                    conta_id=conta_corrente.id,
                    categoria_id=cat_lazer.id,
                    pago=True,
                    forma_pagamento='dinheiro'
                ))

        # Adicionar transações futuras (próximo mês)
        proximo_mes = hoje + relativedelta(months=1)

        # Salário próximo mês
        transacoes.append(Transacao(
            descricao='Salário Empresa XYZ',
            valor=Decimal('6500.00'),
            tipo='receita',
            data=date(proximo_mes.year, proximo_mes.month, 5),
            conta_id=conta_corrente.id,
            categoria_id=cat_salario.id,
            pago=False,
            forma_pagamento='dinheiro'
        ))

        # Despesas futuras
        transacoes.append(Transacao(
            descricao='Aluguel Apartamento',
            valor=Decimal('1800.00'),
            tipo='despesa',
            data=date(proximo_mes.year, proximo_mes.month, 10),
            conta_id=conta_corrente.id,
            categoria_id=cat_moradia.id,
            pago=False,
            forma_pagamento='dinheiro'
        ))

        for trans in transacoes:
            db.session.add(trans)

        db.session.commit()
        print(f"✅ {len(transacoes)} transações criadas")

def criar_orcamentos(user_id, categorias):
    """Cria orçamentos para o mês atual"""
    with app.app_context():
        hoje = date.today()

        orcamentos_data = [
            ('Alimentação', Decimal('1500.00'), 80),
            ('Transporte', Decimal('600.00'), 80),
            ('Moradia', Decimal('2000.00'), 90),
            ('Lazer', Decimal('500.00'), 75),
            ('Assinaturas', Decimal('150.00'), 80),
        ]

        orcamentos = []
        for nome_cat, valor_limite, alerta in orcamentos_data:
            cat = next((c for c in categorias if c.nome == nome_cat), None)
            if cat:
                orcamentos.append(Orcamento(
                    user_id=user_id,
                    categoria_id=cat.id,
                    mes=hoje.month,
                    ano=hoje.year,
                    valor_limite=valor_limite,
                    alerta_em_percentual=alerta
                ))

        for orc in orcamentos:
            db.session.add(orc)

        db.session.commit()
        print(f"✅ {len(orcamentos)} orçamentos criados")

def criar_metas(user_id, contas):
    """Cria metas de economia"""
    with app.app_context():
        hoje = date.today()

        metas = [
            Meta(
                user_id=user_id,
                titulo='Viagem para Europa',
                descricao='Viagem de férias para França e Itália',
                valor_alvo=Decimal('25000.00'),
                valor_inicial=Decimal('5000.00'),
                valor_mensal=Decimal('1500.00'),
                data_inicio=hoje - relativedelta(months=3),
                data_fim=hoje + relativedelta(months=10),
                status='ativa',
                conta_id=contas[1].id  # Poupança
            ),
            Meta(
                user_id=user_id,
                titulo='Reserva de Emergência',
                descricao='6 meses de despesas (R$ 4.000/mês)',
                valor_alvo=Decimal('24000.00'),
                valor_inicial=Decimal('8000.00'),
                valor_mensal=Decimal('2000.00'),
                data_inicio=hoje - relativedelta(months=6),
                data_fim=hoje + relativedelta(months=6),
                status='ativa',
                conta_id=contas[1].id
            ),
            Meta(
                user_id=user_id,
                titulo='Notebook Novo',
                descricao='MacBook Pro para trabalho',
                valor_alvo=Decimal('12000.00'),
                valor_inicial=Decimal('3000.00'),
                valor_mensal=Decimal('1000.00'),
                data_inicio=hoje - relativedelta(months=2),
                data_fim=hoje + relativedelta(months=7),
                status='ativa',
                conta_id=contas[2].id  # Investimentos
            ),
        ]

        for meta in metas:
            db.session.add(meta)

        db.session.flush()

        # Adicionar alguns depósitos
        for meta in metas:
            # Depósitos mensais
            num_depositos = random.randint(2, 4)
            for i in range(num_depositos):
                deposito = DepositoMeta(
                    meta_id=meta.id,
                    valor=Decimal(random.uniform(500, 2000)),
                    data=hoje - relativedelta(months=num_depositos-i),
                    observacao=f'Depósito mensal {i+1}'
                )
                db.session.add(deposito)

        db.session.commit()
        print(f"✅ {len(metas)} metas criadas com depósitos")

def atualizar_saldos_contas(user_id):
    """Atualiza os saldos das contas baseado nas transações"""
    with app.app_context():
        contas = Conta.query.filter_by(user_id=user_id).all()

        for conta in contas:
            # Somar receitas pagas
            receitas = db.session.query(db.func.sum(Transacao.valor)).filter(
                Transacao.conta_id == conta.id,
                Transacao.tipo == 'receita',
                Transacao.pago == True
            ).scalar() or Decimal('0')

            # Somar despesas pagas
            despesas = db.session.query(db.func.sum(Transacao.valor)).filter(
                Transacao.conta_id == conta.id,
                Transacao.tipo == 'despesa',
                Transacao.pago == True
            ).scalar() or Decimal('0')

            conta.saldo_atual = conta.saldo_inicial + receitas - despesas

        db.session.commit()
        print("✅ Saldos das contas atualizados")

def main():
    """Função principal"""
    print("\n" + "="*60)
    print("🚀 POPULANDO BANCO DE DADOS COM DADOS FICTÍCIOS")
    print("="*60 + "\n")

    # 1. Criar ou buscar usuário
    user_id = criar_ou_buscar_usuario()

    # 2. Limpar dados anteriores
    limpar_dados_usuario(user_id)

    # 3. Criar estrutura
    contas = criar_contas(user_id)
    categorias = criar_categorias(user_id)
    cartoes = criar_cartoes(user_id)

    # 4. Criar dados
    criar_transacoes(user_id, contas, categorias)
    criar_orcamentos(user_id, categorias)
    criar_metas(user_id, contas)

    # 5. Atualizar saldos
    atualizar_saldos_contas(user_id)

    print("\n" + "="*60)
    print("✅ BANCO DE DADOS POPULADO COM SUCESSO!")
    print("="*60)
    print("\n📧 Email: teste@teste.com")
    print("🔑 Senha: teste123")
    print(f"\n💰 {len(contas)} contas | 📊 {len(categorias)} categorias")
    print(f"💳 {len(cartoes)} cartões de crédito")
    print(f"📈 ~300+ transações dos últimos 12 meses")
    print(f"🎯 3 metas ativas | 💵 Orçamentos configurados")
    print("\n🌐 Acesse: http://127.0.0.1:8000/login")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
