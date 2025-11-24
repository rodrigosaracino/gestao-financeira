from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, Conta, Categoria, Transacao, CartaoCredito, Fatura
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func, extract
from dateutil.relativedelta import relativedelta

bp = Blueprint('main', __name__)

# ==================== ROTAS PRINCIPAIS ====================

@bp.route('/')
def index():
    """Dashboard principal com resumo financeiro"""
    # Calcular saldo total de todas as contas
    contas = Conta.query.filter_by(ativa=True).all()
    saldo_total = sum(conta.saldo_atual for conta in contas)

    # Receitas e despesas do mês atual
    mes_atual = datetime.now().month
    ano_atual = datetime.now().year

    receitas_mes = db.session.query(func.sum(Transacao.valor)).filter(
        Transacao.tipo == 'receita',
        extract('month', Transacao.data) == mes_atual,
        extract('year', Transacao.data) == ano_atual
    ).scalar() or Decimal('0.00')

    despesas_mes = db.session.query(func.sum(Transacao.valor)).filter(
        Transacao.tipo == 'despesa',
        extract('month', Transacao.data) == mes_atual,
        extract('year', Transacao.data) == ano_atual
    ).scalar() or Decimal('0.00')

    # Faturas pendentes
    faturas_abertas = Fatura.query.filter(
        Fatura.status.in_(['aberta', 'fechada'])
    ).all()

    total_faturas = sum(fatura.valor_total for fatura in faturas_abertas)

    return render_template('index.html',
                         contas=contas,
                         saldo_total=saldo_total,
                         receitas_mes=receitas_mes,
                         despesas_mes=despesas_mes,
                         faturas_abertas=faturas_abertas,
                         total_faturas=total_faturas)


# ==================== CONTAS ====================

@bp.route('/contas')
def listar_contas():
    """Lista todas as contas"""
    contas = Conta.query.all()
    return render_template('contas/listar.html', contas=contas)


@bp.route('/contas/nova', methods=['GET', 'POST'])
def nova_conta():
    """Criar nova conta"""
    if request.method == 'POST':
        conta = Conta(
            nome=request.form['nome'],
            tipo=request.form['tipo'],
            saldo_inicial=Decimal(request.form['saldo_inicial']),
            saldo_atual=Decimal(request.form['saldo_inicial'])
        )
        db.session.add(conta)
        db.session.commit()
        flash('Conta criada com sucesso!', 'success')
        return redirect(url_for('main.listar_contas'))

    return render_template('contas/form.html')


@bp.route('/contas/<int:id>/editar', methods=['GET', 'POST'])
def editar_conta(id):
    """Editar conta existente"""
    conta = Conta.query.get_or_404(id)

    if request.method == 'POST':
        conta.nome = request.form['nome']
        conta.tipo = request.form['tipo']
        conta.ativa = 'ativa' in request.form
        db.session.commit()
        flash('Conta atualizada com sucesso!', 'success')
        return redirect(url_for('main.listar_contas'))

    return render_template('contas/form.html', conta=conta)


# ==================== TRANSAÇÕES ====================

@bp.route('/transacoes')
def listar_transacoes():
    """Lista todas as transações"""
    page = request.args.get('page', 1, type=int)
    transacoes = Transacao.query.order_by(Transacao.data.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('transacoes/listar.html', transacoes=transacoes)


@bp.route('/transacoes/nova', methods=['GET', 'POST'])
def nova_transacao():
    """Criar nova transação"""
    if request.method == 'POST':
        forma_pagamento = request.form.get('forma_pagamento', 'dinheiro')

        if forma_pagamento == 'cartao_credito':
            # Pagamento com cartão de crédito
            cartao_id = request.form.get('cartao_credito_id')
            total_parcelas = int(request.form.get('total_parcelas', 1))
            valor_total = Decimal(request.form['valor'])
            valor_parcela = valor_total / total_parcelas
            data_compra = datetime.strptime(request.form['data'], '%Y-%m-%d').date()

            cartao = CartaoCredito.query.get(cartao_id)
            if not cartao:
                flash('Cartão de crédito não encontrado!', 'error')
                return redirect(url_for('main.nova_transacao'))

            # Obter conta (usar primeira conta ativa se não especificada)
            conta_id_form = request.form.get('conta_id')
            if not conta_id_form or conta_id_form == '':
                conta = Conta.query.filter_by(ativa=True).first()
                if conta:
                    conta_id_form = int(conta.id)
                else:
                    flash('Nenhuma conta ativa encontrada!', 'error')
                    return redirect(url_for('main.nova_transacao'))
            else:
                conta_id_form = int(conta_id_form)

            # Criar transação pai (registro da compra)
            transacao_pai = Transacao(
                descricao=request.form['descricao'],
                valor=valor_total,
                tipo='despesa',
                data=data_compra,
                forma_pagamento='cartao_credito',
                cartao_credito_id=cartao_id,
                parcelado=(total_parcelas > 1),
                total_parcelas=total_parcelas,
                conta_id=conta_id_form,
                categoria_id=request.form['categoria_id']
            )
            db.session.add(transacao_pai)
            db.session.flush()  # Para obter o ID

            # Criar parcelas
            from dateutil.relativedelta import relativedelta
            for i in range(1, total_parcelas + 1):
                # Calcular a data da parcela (mês seguinte)
                data_parcela = data_compra + relativedelta(months=i-1)

                # Obter ou criar fatura do mês
                fatura = obter_ou_criar_fatura(cartao, data_parcela)

                # Criar transação da parcela
                descricao_parcela = f"{request.form['descricao']} ({i}/{total_parcelas})"
                transacao_parcela = Transacao(
                    descricao=descricao_parcela,
                    valor=valor_parcela,
                    tipo='despesa',
                    data=data_parcela,
                    forma_pagamento='cartao_credito',
                    cartao_credito_id=cartao_id,
                    parcelado=True,
                    numero_parcela=i,
                    total_parcelas=total_parcelas,
                    transacao_pai_id=transacao_pai.id,
                    conta_id=conta_id_form,
                    categoria_id=request.form['categoria_id'],
                    fatura_id=fatura.id
                )
                db.session.add(transacao_parcela)

                # Atualizar valor da fatura
                fatura.valor_total += valor_parcela

            db.session.commit()
            msg = f'Compra parcelada em {total_parcelas}x adicionada com sucesso!'
            flash(msg, 'success')

        else:
            # Pagamento em dinheiro/débito
            transacao = Transacao(
                descricao=request.form['descricao'],
                valor=Decimal(request.form['valor']),
                tipo=request.form['tipo'],
                data=datetime.strptime(request.form['data'], '%Y-%m-%d').date(),
                forma_pagamento='dinheiro',
                conta_id=request.form['conta_id'],
                categoria_id=request.form['categoria_id']
            )

            # Atualizar saldo da conta
            conta = Conta.query.get(transacao.conta_id)
            if transacao.tipo == 'receita':
                conta.saldo_atual += transacao.valor
            else:
                conta.saldo_atual -= transacao.valor

            db.session.add(transacao)
            db.session.commit()
            flash('Transação adicionada com sucesso!', 'success')

        return redirect(url_for('main.listar_transacoes'))

    contas = Conta.query.filter_by(ativa=True).all()
    categorias = Categoria.query.all()
    cartoes = CartaoCredito.query.filter_by(ativo=True).all()
    data_hoje = date.today().strftime('%Y-%m-%d')
    return render_template('transacoes/form.html', contas=contas, categorias=categorias, cartoes=cartoes, data_hoje=data_hoje)


def obter_ou_criar_fatura(cartao, data_referencia):
    """Obtém ou cria uma fatura para o cartão no mês de referência"""
    mes = data_referencia.month
    ano = data_referencia.year

    # Tentar encontrar fatura existente
    fatura = Fatura.query.filter_by(
        cartao_id=cartao.id,
        mes_referencia=mes,
        ano_referencia=ano
    ).first()

    if fatura:
        return fatura

    # Criar nova fatura
    from calendar import monthrange

    # Calcular data de fechamento
    ultimo_dia_mes = monthrange(ano, mes)[1]
    if cartao.dia_fechamento > ultimo_dia_mes:
        data_fechamento = date(ano, mes, ultimo_dia_mes)
    else:
        data_fechamento = date(ano, mes, cartao.dia_fechamento)

    # Calcular data de vencimento (mês seguinte)
    if mes == 12:
        mes_vencimento = 1
        ano_vencimento = ano + 1
    else:
        mes_vencimento = mes + 1
        ano_vencimento = ano

    ultimo_dia_vencimento = monthrange(ano_vencimento, mes_vencimento)[1]
    if cartao.dia_vencimento > ultimo_dia_vencimento:
        data_vencimento = date(ano_vencimento, mes_vencimento, ultimo_dia_vencimento)
    else:
        data_vencimento = date(ano_vencimento, mes_vencimento, cartao.dia_vencimento)

    fatura = Fatura(
        cartao_id=cartao.id,
        mes_referencia=mes,
        ano_referencia=ano,
        data_fechamento=data_fechamento,
        data_vencimento=data_vencimento,
        valor_total=Decimal('0.00'),
        valor_pago=Decimal('0.00'),
        status='aberta'
    )

    db.session.add(fatura)
    db.session.flush()

    return fatura


# ==================== CATEGORIAS ====================

@bp.route('/categorias')
def listar_categorias():
    """Lista todas as categorias"""
    categorias = Categoria.query.all()
    return render_template('categorias/listar.html', categorias=categorias)


@bp.route('/categorias/nova', methods=['GET', 'POST'])
def nova_categoria():
    """Criar nova categoria"""
    if request.method == 'POST':
        categoria = Categoria(
            nome=request.form['nome'],
            tipo=request.form['tipo'],
            cor=request.form.get('cor', '#3498db')
        )
        db.session.add(categoria)
        db.session.commit()
        flash('Categoria criada com sucesso!', 'success')
        return redirect(url_for('main.listar_categorias'))

    return render_template('categorias/form.html')


@bp.route('/api/categorias', methods=['POST'])
def api_criar_categoria():
    """API para criar categoria via AJAX"""
    try:
        data = request.get_json()

        nome = data.get('nome', '').strip()
        tipo = data.get('tipo', '').strip()
        cor = data.get('cor', '#3498db')

        if not nome or not tipo:
            return jsonify({'erro': 'Nome e tipo são obrigatórios'}), 400

        if tipo not in ['receita', 'despesa']:
            return jsonify({'erro': 'Tipo deve ser "receita" ou "despesa"'}), 400

        # Verificar se categoria já existe
        categoria_existente = Categoria.query.filter_by(nome=nome).first()
        if categoria_existente:
            return jsonify({'erro': 'Já existe uma categoria com este nome'}), 400

        # Criar nova categoria
        categoria = Categoria(
            nome=nome,
            tipo=tipo,
            cor=cor
        )
        db.session.add(categoria)
        db.session.commit()

        return jsonify({
            'id': categoria.id,
            'nome': categoria.nome,
            'tipo': categoria.tipo,
            'cor': categoria.cor
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# ==================== CARTÕES DE CRÉDITO ====================

@bp.route('/cartoes')
def listar_cartoes():
    """Lista todos os cartões de crédito"""
    cartoes = CartaoCredito.query.all()
    return render_template('cartoes/listar.html', cartoes=cartoes)


@bp.route('/cartoes/novo', methods=['GET', 'POST'])
def novo_cartao():
    """Criar novo cartão de crédito"""
    if request.method == 'POST':
        cartao = CartaoCredito(
            nome=request.form['nome'],
            bandeira=request.form['bandeira'],
            limite=Decimal(request.form['limite']),
            dia_fechamento=int(request.form['dia_fechamento']),
            dia_vencimento=int(request.form['dia_vencimento'])
        )
        db.session.add(cartao)
        db.session.commit()
        flash('Cartão de crédito criado com sucesso!', 'success')
        return redirect(url_for('main.listar_cartoes'))

    return render_template('cartoes/form.html')


@bp.route('/cartoes/<int:id>/editar', methods=['GET', 'POST'])
def editar_cartao(id):
    """Editar cartão de crédito"""
    cartao = CartaoCredito.query.get_or_404(id)

    if request.method == 'POST':
        cartao.nome = request.form['nome']
        cartao.bandeira = request.form['bandeira']
        cartao.limite = Decimal(request.form['limite'])
        cartao.dia_fechamento = int(request.form['dia_fechamento'])
        cartao.dia_vencimento = int(request.form['dia_vencimento'])
        cartao.ativo = 'ativo' in request.form
        db.session.commit()
        flash('Cartão atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_cartoes'))

    return render_template('cartoes/form.html', cartao=cartao)


# ==================== FATURAS ====================

@bp.route('/faturas')
def listar_faturas():
    """Lista todas as faturas"""
    faturas = Fatura.query.order_by(Fatura.ano_referencia.desc(), Fatura.mes_referencia.desc()).all()
    return render_template('faturas/listar.html', faturas=faturas)


@bp.route('/faturas/nova', methods=['GET', 'POST'])
def nova_fatura():
    """Criar nova fatura"""
    if request.method == 'POST':
        fatura = Fatura(
            cartao_id=request.form['cartao_id'],
            mes_referencia=int(request.form['mes_referencia']),
            ano_referencia=int(request.form['ano_referencia']),
            data_fechamento=datetime.strptime(request.form['data_fechamento'], '%Y-%m-%d').date(),
            data_vencimento=datetime.strptime(request.form['data_vencimento'], '%Y-%m-%d').date()
        )
        db.session.add(fatura)
        db.session.commit()
        flash('Fatura criada com sucesso!', 'success')
        return redirect(url_for('main.listar_faturas'))

    cartoes = CartaoCredito.query.filter_by(ativo=True).all()
    return render_template('faturas/form.html', cartoes=cartoes)


@bp.route('/faturas/<int:id>')
def ver_fatura(id):
    """Ver detalhes de uma fatura"""
    fatura = Fatura.query.get_or_404(id)
    transacoes = Transacao.query.filter_by(fatura_id=id).all()
    return render_template('faturas/detalhes.html', fatura=fatura, transacoes=transacoes)


@bp.route('/faturas/<int:id>/pagar', methods=['POST'])
def pagar_fatura(id):
    """Marcar fatura como paga"""
    fatura = Fatura.query.get_or_404(id)
    valor_pago = Decimal(request.form.get('valor_pago', fatura.valor_total))

    fatura.valor_pago = valor_pago
    if valor_pago >= fatura.valor_total:
        fatura.status = 'paga'

    # Criar transação de pagamento na conta
    if 'conta_id' in request.form:
        transacao = Transacao(
            descricao=f'Pagamento fatura {fatura.cartao.nome} {fatura.mes_referencia}/{fatura.ano_referencia}',
            valor=valor_pago,
            tipo='despesa',
            data=date.today(),
            conta_id=request.form['conta_id'],
            categoria_id=request.form.get('categoria_id', 1)
        )

        conta = Conta.query.get(request.form['conta_id'])
        conta.saldo_atual -= valor_pago

        db.session.add(transacao)

    db.session.commit()
    flash('Fatura marcada como paga!', 'success')
    return redirect(url_for('main.ver_fatura', id=id))


# ==================== RELATÓRIOS ====================

@bp.route('/relatorios')
def relatorios():
    """Página de relatórios e gráficos"""
    return render_template('relatorios/index.html')


@bp.route('/api/gastos-por-categoria')
def api_gastos_por_categoria():
    """API: Gastos por categoria (para gráficos)"""
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)

    resultados = db.session.query(
        Categoria.nome,
        func.sum(Transacao.valor).label('total')
    ).join(Transacao).filter(
        Transacao.tipo == 'despesa',
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).group_by(Categoria.nome).all()

    return jsonify({
        'categorias': [r[0] for r in resultados],
        'valores': [float(r[1]) for r in resultados]
    })


@bp.route('/api/fluxo-caixa')
def api_fluxo_caixa():
    """API: Fluxo de caixa mensal (para gráficos)"""
    ano = request.args.get('ano', datetime.now().year, type=int)

    receitas = db.session.query(
        extract('month', Transacao.data).label('mes'),
        func.sum(Transacao.valor).label('total')
    ).filter(
        Transacao.tipo == 'receita',
        extract('year', Transacao.data) == ano
    ).group_by('mes').all()

    despesas = db.session.query(
        extract('month', Transacao.data).label('mes'),
        func.sum(Transacao.valor).label('total')
    ).filter(
        Transacao.tipo == 'despesa',
        extract('year', Transacao.data) == ano
    ).group_by('mes').all()

    # Converter para dicionários para facilitar o merge
    receitas_dict = {int(r[0]): float(r[1]) for r in receitas}
    despesas_dict = {int(d[0]): float(d[1]) for d in despesas}

    meses = list(range(1, 13))
    dados_receitas = [receitas_dict.get(m, 0) for m in meses]
    dados_despesas = [despesas_dict.get(m, 0) for m in meses]

    return jsonify({
        'meses': ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'],
        'receitas': dados_receitas,
        'despesas': dados_despesas
    })
