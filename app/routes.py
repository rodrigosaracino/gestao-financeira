from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, Conta, Categoria, Transacao, CartaoCredito, Fatura, ConciliacaoBancaria, ItemConciliacao
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func, extract
from dateutil.relativedelta import relativedelta
from werkzeug.utils import secure_filename
from app.parsers import parse_file, detect_format
from app.matching import processar_matching, estatisticas_matching
from calendar import monthrange
from collections import defaultdict
import calendar

bp = Blueprint('main', __name__)

# ==================== ROTAS PRINCIPAIS ====================

@bp.route('/')
@login_required
def index():
    """Dashboard principal com projeção de fluxo de caixa"""
    # Obter mês e ano dos parâmetros ou usar valores atuais
    mes_filtro = request.args.get('mes', type=int) or datetime.now().month
    ano_filtro = request.args.get('ano', type=int) or datetime.now().year

    # Calcular saldo total de todas as contas do usuário logado
    contas = Conta.query.filter_by(ativa=True, user_id=current_user.id).all()
    saldo_total = sum(conta.saldo_atual for conta in contas)

    # Determinar primeiro e último dia do mês
    primeiro_dia = date(ano_filtro, mes_filtro, 1)
    ultimo_dia = date(ano_filtro, mes_filtro, calendar.monthrange(ano_filtro, mes_filtro)[1])
    hoje = date.today()

    # Buscar todas as transações do mês (realizadas e futuras) do usuário logado
    transacoes_mes = Transacao.query.join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.data >= primeiro_dia,
        Transacao.data <= ultimo_dia
    ).order_by(Transacao.data).all()

    # Buscar faturas com vencimento no mês do usuário logado
    faturas_mes = Fatura.query.join(CartaoCredito).filter(
        CartaoCredito.user_id == current_user.id,
        Fatura.data_vencimento >= primeiro_dia,
        Fatura.data_vencimento <= ultimo_dia,
        Fatura.status.in_(['aberta', 'fechada'])
    ).all()

    # Organizar transações por dia
    transacoes_por_dia = defaultdict(lambda: {'receitas': Decimal('0.00'), 'despesas': Decimal('0.00')})

    for transacao in transacoes_mes:
        dia_key = transacao.data
        if transacao.tipo == 'receita':
            transacoes_por_dia[dia_key]['receitas'] += transacao.valor
        else:
            transacoes_por_dia[dia_key]['despesas'] += transacao.valor

    # Adicionar faturas como despesas futuras
    for fatura in faturas_mes:
        dia_key = fatura.data_vencimento
        valor_pendente = fatura.valor_total - fatura.valor_pago
        if valor_pendente > 0:
            transacoes_por_dia[dia_key]['despesas'] += valor_pendente

    # Calcular projeção dia a dia do saldo
    projecao_fluxo = []
    saldo_acumulado = float(saldo_total)

    # Gerar dados para cada dia do mês
    dia_atual = primeiro_dia
    while dia_atual <= ultimo_dia:
        if dia_atual in transacoes_por_dia:
            receitas_dia = float(transacoes_por_dia[dia_atual]['receitas'])
            despesas_dia = float(transacoes_por_dia[dia_atual]['despesas'])
            saldo_acumulado += receitas_dia - despesas_dia

        projecao_fluxo.append({
            'data': dia_atual.strftime('%Y-%m-%d'),
            'dia': dia_atual.day,
            'saldo': round(saldo_acumulado, 2),
            'is_hoje': dia_atual == hoje,
            'is_futuro': dia_atual > hoje
        })

        dia_atual += relativedelta(days=1)

    # Calcular totais do mês
    total_receitas_mes = sum(float(d['receitas']) for d in transacoes_por_dia.values())
    total_despesas_mes = sum(float(d['despesas']) for d in transacoes_por_dia.values())
    saldo_previsto_fim_mes = float(saldo_total) + total_receitas_mes - total_despesas_mes

    # Separar receitas e despesas realizadas vs futuras
    receitas_realizadas = sum(
        float(t.valor) for t in transacoes_mes
        if t.tipo == 'receita' and t.data <= hoje
    )
    despesas_realizadas = sum(
        float(t.valor) for t in transacoes_mes
        if t.tipo == 'despesa' and t.data <= hoje
    )

    # Próximos pagamentos (despesas futuras + faturas)
    proximos_pagamentos = []

    # Despesas futuras
    despesas_futuras = [t for t in transacoes_mes if t.tipo == 'despesa' and t.data > hoje]
    for despesa in despesas_futuras[:10]:
        proximos_pagamentos.append({
            'tipo': 'despesa',
            'id': despesa.id,
            'descricao': despesa.descricao,
            'valor': float(despesa.valor),
            'data': despesa.data,
            'categoria': despesa.categoria.nome,
            'pago': despesa.pago
        })

    # Faturas pendentes (incluindo as com vencimento futuro e atual)
    faturas_pendentes = Fatura.query.filter(
        Fatura.status.in_(['aberta', 'fechada']),
        Fatura.data_vencimento >= hoje
    ).join(CartaoCredito).filter(
        CartaoCredito.user_id == current_user.id
    ).all()

    for fatura in faturas_pendentes:
        valor_pendente = float(fatura.valor_total - fatura.valor_pago)
        if valor_pendente > 0:
            proximos_pagamentos.append({
                'tipo': 'fatura',
                'id': fatura.id,
                'descricao': f'Fatura {fatura.cartao.nome}',
                'valor': valor_pendente,
                'data': fatura.data_vencimento,
                'categoria': 'Cartão de Crédito',
                'pago': False  # Faturas não têm campo 'pago' diretamente
            })

    # Ordenar por data
    proximos_pagamentos.sort(key=lambda x: x['data'])
    proximos_pagamentos = proximos_pagamentos[:5]

    # Próximas receitas
    proximas_receitas = []
    receitas_futuras = [t for t in transacoes_mes if t.tipo == 'receita' and t.data > hoje]
    for receita in receitas_futuras[:5]:
        proximas_receitas.append({
            'id': receita.id,
            'descricao': receita.descricao,
            'valor': float(receita.valor),
            'data': receita.data,
            'categoria': receita.categoria.nome,
            'pago': receita.pago
        })

    proximas_receitas.sort(key=lambda x: x['data'])

    # Faturas pendentes (todas) do usuário logado
    faturas_abertas = Fatura.query.join(CartaoCredito).filter(
        CartaoCredito.user_id == current_user.id,
        Fatura.status.in_(['aberta', 'fechada'])
    ).all()
    total_faturas = sum(fatura.valor_total for fatura in faturas_abertas)

    return render_template('index.html',
                         contas=contas,
                         saldo_total=saldo_total,
                         receitas_mes=total_receitas_mes,
                         despesas_mes=total_despesas_mes,
                         receitas_realizadas=receitas_realizadas,
                         despesas_realizadas=despesas_realizadas,
                         saldo_previsto=saldo_previsto_fim_mes,
                         faturas_abertas=faturas_abertas,
                         total_faturas=total_faturas,
                         mes_filtro=mes_filtro,
                         ano_filtro=ano_filtro,
                         projecao_fluxo=projecao_fluxo,
                         proximos_pagamentos=proximos_pagamentos,
                         proximas_receitas=proximas_receitas)


# ==================== CONTAS ====================

@bp.route('/contas')
@login_required
def listar_contas():
    """Lista todas as contas do usuário"""
    contas = Conta.query.filter_by(user_id=current_user.id).all()
    return render_template('contas/listar.html', contas=contas)


@bp.route('/contas/nova', methods=['GET', 'POST'])
@login_required
def nova_conta():
    """Criar nova conta"""
    if request.method == 'POST':
        conta = Conta(
            nome=request.form['nome'],
            tipo=request.form['tipo'],
            saldo_inicial=Decimal(request.form['saldo_inicial']),
            saldo_atual=Decimal(request.form['saldo_inicial']),
            user_id=current_user.id
        )
        db.session.add(conta)
        db.session.commit()
        flash('Conta criada com sucesso!', 'success')
        return redirect(url_for('main.listar_contas'))

    return render_template('contas/form.html')


@bp.route('/contas/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_conta(id):
    """Editar conta existente"""
    conta = Conta.query.filter_by(id=id, user_id=current_user.id).first_or_404()

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
@login_required
def listar_transacoes():
    """Lista todas as transações com filtros e navegação por mês"""
    page = request.args.get('page', 1, type=int)

    # Obter mês e ano da query string ou usar mês/ano atual
    mes_atual = request.args.get('mes', datetime.now().month, type=int)
    ano_atual = request.args.get('ano', datetime.now().year, type=int)

    # Calcular mês anterior e próximo
    if mes_atual == 1:
        mes_anterior = 12
        ano_anterior = ano_atual - 1
    else:
        mes_anterior = mes_atual - 1
        ano_anterior = ano_atual

    if mes_atual == 12:
        mes_proximo = 1
        ano_proximo = ano_atual + 1
    else:
        mes_proximo = mes_atual + 1
        ano_proximo = ano_atual

    # Calcular primeiro e último dia do mês
    primeiro_dia = date(ano_atual, mes_atual, 1)
    ultimo_dia = date(ano_atual, mes_atual, monthrange(ano_atual, mes_atual)[1])

    # Obter outros filtros da query string
    filtro_tipo = request.args.get('tipo', '')
    filtro_conta = request.args.get('conta_id', '')
    filtro_categoria = request.args.get('categoria_id', '')

    # Construir query com filtros - incluir apenas transações do usuário logado
    query = Transacao.query.join(Conta).filter(Conta.user_id == current_user.id)

    # Filtrar por mês/ano por padrão
    query = query.filter(Transacao.data >= primeiro_dia, Transacao.data <= ultimo_dia)

    if filtro_tipo:
        query = query.filter(Transacao.tipo == filtro_tipo)

    if filtro_conta:
        query = query.filter(Transacao.conta_id == int(filtro_conta))

    if filtro_categoria:
        query = query.filter(Transacao.categoria_id == int(filtro_categoria))

    # Ordenar e paginar
    transacoes = query.order_by(Transacao.data.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    # Calcular totais do mês do usuário logado
    total_receitas = db.session.query(func.sum(Transacao.valor)).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.tipo == 'receita',
        Transacao.data >= primeiro_dia,
        Transacao.data <= ultimo_dia
    ).scalar() or Decimal('0.00')

    total_despesas = db.session.query(func.sum(Transacao.valor)).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.tipo == 'despesa',
        Transacao.data >= primeiro_dia,
        Transacao.data <= ultimo_dia
    ).scalar() or Decimal('0.00')

    saldo_mes = total_receitas - total_despesas

    # Dados para os filtros - apenas do usuário logado
    contas_filtro = Conta.query.filter_by(ativa=True, user_id=current_user.id).all()
    categorias_filtro = Categoria.query.filter_by(user_id=current_user.id).all()

    # Nome do mês em português
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }

    return render_template('transacoes/listar.html',
                         transacoes=transacoes,
                         contas_filtro=contas_filtro,
                         categorias_filtro=categorias_filtro,
                         filtro_tipo=filtro_tipo,
                         filtro_conta=filtro_conta,
                         filtro_categoria=filtro_categoria,
                         mes_atual=mes_atual,
                         ano_atual=ano_atual,
                         mes_anterior=mes_anterior,
                         ano_anterior=ano_anterior,
                         mes_proximo=mes_proximo,
                         ano_proximo=ano_proximo,
                         nome_mes=meses_pt[mes_atual],
                         total_receitas=total_receitas,
                         total_despesas=total_despesas,
                         saldo_mes=saldo_mes,
                         mes_sistema=datetime.now().month,
                         ano_sistema=datetime.now().year)


@bp.route('/transacoes/nova', methods=['GET', 'POST'])
@login_required
def nova_transacao():
    """Criar nova transação"""
    if request.method == 'POST':
        forma_pagamento = request.form.get('forma_pagamento', 'dinheiro')

        # Validar valor da transação
        try:
            valor = Decimal(request.form['valor'])
            if valor <= 0:
                flash('O valor deve ser maior que zero!', 'error')
                return redirect(url_for('main.nova_transacao'))
        except (ValueError, KeyError):
            flash('Valor inválido!', 'error')
            return redirect(url_for('main.nova_transacao'))

        if forma_pagamento == 'cartao_credito':
            # Pagamento com cartão de crédito
            cartao_id = request.form.get('cartao_credito_id')
            total_parcelas = int(request.form.get('total_parcelas', 1))
            valor_total = Decimal(request.form['valor'])
            valor_parcela = valor_total / total_parcelas
            data_compra = datetime.strptime(request.form['data'], '%Y-%m-%d').date()

            cartao = CartaoCredito.query.filter_by(id=cartao_id, user_id=current_user.id).first()
            if not cartao:
                flash('Cartão de crédito não encontrado ou acesso negado!', 'error')
                return redirect(url_for('main.nova_transacao'))

            # Validar se não ultrapassa o limite do cartão
            if (cartao.limite_utilizado + valor_total) > cartao.limite:
                flash(f'Limite do cartão insuficiente! Disponível: R$ {cartao.limite_disponivel():.2f}', 'error')
                return redirect(url_for('main.nova_transacao'))

            # Obter conta (usar primeira conta ativa se não especificada)
            conta_id_form = request.form.get('conta_id')
            if not conta_id_form or conta_id_form == '':
                conta = Conta.query.filter_by(ativa=True, user_id=current_user.id).first()
                if conta:
                    conta_id_form = int(conta.id)
                else:
                    flash('Nenhuma conta ativa encontrada!', 'error')
                    return redirect(url_for('main.nova_transacao'))
            else:
                conta_id_form = int(conta_id_form)
                # Verificar se a conta pertence ao usuário
                conta_validacao = Conta.query.filter_by(id=conta_id_form, user_id=current_user.id).first()
                if not conta_validacao:
                    flash('Conta não encontrada ou acesso negado!', 'error')
                    return redirect(url_for('main.nova_transacao'))

            # CORREÇÃO: Criar APENAS as parcelas, não a transação pai
            # A transação pai causava duplicação de valores
            primeira_transacao_id = None  # Para vincular as parcelas entre si

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
                    transacao_pai_id=primeira_transacao_id,  # Vincula à primeira parcela
                    conta_id=conta_id_form,
                    categoria_id=request.form['categoria_id'],
                    fatura_id=fatura.id
                )
                db.session.add(transacao_parcela)

                # Guardar ID da primeira parcela para vincular as demais
                if i == 1:
                    db.session.flush()
                    primeira_transacao_id = transacao_parcela.id

                # Atualizar valor da fatura
                fatura.valor_total += valor_parcela

            # Atualizar limite utilizado do cartão
            cartao.limite_utilizado += valor_total

            db.session.commit()
            msg = f'Compra parcelada em {total_parcelas}x adicionada com sucesso!'
            flash(msg, 'success')
            return redirect(url_for('main.listar_transacoes'))

        else:
            # Pagamento em dinheiro/débito
            recorrente = 'recorrente' in request.form
            pago = 'pago' in request.form

            transacao = Transacao(
                descricao=request.form['descricao'],
                valor=Decimal(request.form['valor']),
                tipo=request.form['tipo'],
                data=datetime.strptime(request.form['data'], '%Y-%m-%d').date(),
                forma_pagamento='dinheiro',
                conta_id=request.form['conta_id'],
                categoria_id=request.form['categoria_id'],
                recorrente=recorrente,
                pago=pago
            )

            # Se for recorrente, adicionar informações de recorrência
            if recorrente:
                frequencia = request.form.get('frequencia_recorrencia')
                data_inicio = datetime.strptime(request.form['data_inicio_recorrencia'], '%Y-%m-%d').date()
                quantidade = int(request.form.get('quantidade_recorrencias', 12))

                transacao.frequencia_recorrencia = frequencia
                transacao.data_inicio_recorrencia = data_inicio
                transacao.quantidade_recorrencias = quantidade

            # Atualizar saldo da conta apenas se a transação estiver marcada como paga
            # e a data for hoje ou no passado
            if pago and transacao.data <= date.today():
                conta = Conta.query.get(transacao.conta_id)
                if transacao.tipo == 'receita':
                    conta.saldo_atual += transacao.valor
                else:
                    conta.saldo_atual -= transacao.valor

            db.session.add(transacao)
            db.session.flush()  # Para obter o ID da transação

            # Se for recorrente, gerar transações futuras
            if recorrente:
                try:
                    transacoes_geradas = gerar_transacoes_recorrentes(
                        transacao,
                        frequencia,
                        data_inicio,
                        quantidade,
                        pago_inicial=pago
                    )

                    # Atualizar saldo para transações passadas que foram marcadas como pagas
                    if pago:
                        conta = Conta.query.get(transacao.conta_id)
                        for trans in transacoes_geradas:
                            if trans.pago and trans.data <= date.today():
                                if trans.tipo == 'receita':
                                    conta.saldo_atual += trans.valor
                                else:
                                    conta.saldo_atual -= trans.valor

                    db.session.commit()

                    total_geradas = len(transacoes_geradas)
                    flash(f'Transação recorrente criada com sucesso! {total_geradas} transações foram geradas.', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao gerar transações recorrentes: {str(e)}', 'error')
                    return redirect(url_for('main.nova_transacao'))
            else:
                db.session.commit()
                flash('Transação adicionada com sucesso!', 'success')

        return redirect(url_for('main.listar_transacoes'))

    contas = Conta.query.filter_by(ativa=True, user_id=current_user.id).all()
    categorias = Categoria.query.filter_by(user_id=current_user.id).all()
    cartoes = CartaoCredito.query.filter_by(ativo=True, user_id=current_user.id).all()
    data_hoje = date.today().strftime('%Y-%m-%d')
    return render_template('transacoes/form.html', contas=contas, categorias=categorias, cartoes=cartoes, data_hoje=data_hoje)


@bp.route('/transacoes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_transacao(id):
    """Editar uma transação existente"""
    transacao = Transacao.query.join(Conta).filter(
        Transacao.id == id,
        Conta.user_id == current_user.id
    ).first_or_404()

    if request.method == 'POST':
        # Reverter o efeito da transação anterior no saldo
        conta_anterior = Conta.query.get(transacao.conta_id)
        if transacao.tipo == 'receita':
            conta_anterior.saldo_atual -= transacao.valor
        else:
            conta_anterior.saldo_atual += transacao.valor

        # Atualizar os dados da transação
        transacao.descricao = request.form['descricao']
        transacao.valor = Decimal(request.form['valor'])
        transacao.tipo = request.form['tipo']
        transacao.data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
        transacao.categoria_id = request.form['categoria_id']

        # Atualizar forma de pagamento
        transacao.forma_pagamento = request.form.get('forma_pagamento', 'dinheiro')

        # Atualizar cartão de crédito (se aplicável)
        if transacao.forma_pagamento == 'cartao_credito':
            transacao.cartao_credito_id = request.form.get('cartao_credito_id')
        else:
            transacao.cartao_credito_id = None
            # Atualizar status de pago (apenas para não-cartão)
            transacao.pago = 'pago' in request.form

        # Atualizar conta se foi alterada
        nova_conta_id = int(request.form['conta_id'])
        if nova_conta_id != transacao.conta_id:
            transacao.conta_id = nova_conta_id

        # Aplicar o novo efeito no saldo
        conta_nova = Conta.query.get(transacao.conta_id)
        if transacao.tipo == 'receita':
            conta_nova.saldo_atual += transacao.valor
        else:
            conta_nova.saldo_atual -= transacao.valor

        db.session.commit()
        flash('Transação atualizada com sucesso!', 'success')
        return redirect(url_for('main.listar_transacoes'))

    contas = Conta.query.filter_by(ativa=True, user_id=current_user.id).all()
    categorias = Categoria.query.filter_by(user_id=current_user.id).all()
    cartoes = CartaoCredito.query.filter_by(ativo=True, user_id=current_user.id).all()
    return render_template('transacoes/editar.html',
                         transacao=transacao,
                         contas=contas,
                         categorias=categorias,
                         cartoes=cartoes)


@bp.route('/transacoes/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_transacao(id):
    """Deletar uma transação"""
    transacao = Transacao.query.join(Conta).filter(
        Transacao.id == id,
        Conta.user_id == current_user.id
    ).first_or_404()

    # Reverter o efeito da transação no saldo (apenas se estava marcada como paga)
    if transacao.pago:
        conta = Conta.query.get(transacao.conta_id)
        if transacao.tipo == 'receita':
            conta.saldo_atual -= transacao.valor
        else:
            conta.saldo_atual += transacao.valor

    # Se for transação de cartão de crédito, atualizar fatura e limite
    if transacao.forma_pagamento == 'cartao_credito':
        # Atualizar valor da fatura
        if transacao.fatura_id:
            fatura = Fatura.query.get(transacao.fatura_id)
            if fatura:
                fatura.valor_total -= transacao.valor

        # Atualizar limite utilizado do cartão (se for transação parcelada)
        if transacao.cartao_credito_id and transacao.parcelado:
            cartao = CartaoCredito.query.get(transacao.cartao_credito_id)
            if cartao:
                # Se for a primeira parcela ou transação pai, descontar o valor total
                # Caso contrário, descontar apenas o valor da parcela
                if transacao.numero_parcela == 1 or transacao.numero_parcela is None:
                    # Calcular valor total do parcelamento
                    valor_total_parcelamento = transacao.valor * transacao.total_parcelas
                    cartao.limite_utilizado -= valor_total_parcelamento

                    # Garantir que não fique negativo
                    if cartao.limite_utilizado < 0:
                        cartao.limite_utilizado = 0

    # Deletar a transação
    db.session.delete(transacao)
    db.session.commit()
    flash('Transação deletada com sucesso!', 'success')
    return redirect(url_for('main.listar_transacoes'))


@bp.route('/transacoes/<int:id>/toggle-pago', methods=['POST'])
@login_required
def toggle_pago_transacao(id):
    """Marcar/desmarcar transação como paga/recebida"""
    transacao = Transacao.query.get_or_404(id)

    # Verificar se a transação pertence ao usuário logado
    if transacao.conta.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403

    # Verificar se a transação pode ser marcada como paga
    if not transacao.pode_marcar_pago():
        return jsonify({'success': False, 'message': 'Transações de cartão de crédito não podem ser marcadas individualmente'}), 400

    # Obter a conta
    conta = Conta.query.get(transacao.conta_id)

    # Se está marcando como pago agora
    if not transacao.pago:
        # Atualizar saldo da conta
        if transacao.tipo == 'receita':
            conta.saldo_atual += transacao.valor
        else:  # despesa
            conta.saldo_atual -= transacao.valor

        transacao.pago = True
        status_text = 'pago' if transacao.tipo == 'despesa' else 'recebido'
        message = f'Transação marcada como {status_text}!'
    else:
        # Se está desmarcando como pago
        # Reverter o efeito no saldo
        if transacao.tipo == 'receita':
            conta.saldo_atual -= transacao.valor
        else:  # despesa
            conta.saldo_atual += transacao.valor

        transacao.pago = False
        message = 'Status de pagamento removido'

    db.session.commit()

    return jsonify({
        'success': True,
        'pago': transacao.pago,
        'message': message
    })


@bp.route('/transacoes/criar-inline', methods=['POST'])
@login_required
def criar_transacao_inline():
    """Criar transação rapidamente via inserção inline"""
    try:
        data = request.get_json()

        # Validar dados obrigatórios
        if not all(key in data for key in ['descricao', 'valor', 'tipo', 'data', 'categoria_id', 'conta_id']):
            return jsonify({'success': False, 'message': 'Dados incompletos'}), 400

        # Verificar se a conta pertence ao usuário
        conta = Conta.query.filter_by(id=int(data['conta_id']), user_id=current_user.id).first()
        if not conta:
            return jsonify({'success': False, 'message': 'Conta não encontrada ou acesso negado'}), 403

        # Criar transação
        transacao = Transacao(
            descricao=data['descricao'],
            valor=Decimal(str(data['valor'])),
            tipo=data['tipo'],
            data=datetime.strptime(data['data'], '%Y-%m-%d').date(),
            categoria_id=int(data['categoria_id']),
            conta_id=int(data['conta_id']),
            forma_pagamento='dinheiro',
            pago=data.get('pago', False)
        )

        # Atualizar saldo da conta
        if transacao.tipo == 'receita':
            conta.saldo_atual += transacao.valor
        else:
            conta.saldo_atual -= transacao.valor

        db.session.add(transacao)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Transação criada com sucesso!',
            'transacao_id': transacao.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


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


def recalcular_valor_fatura(fatura_id):
    """
    Recalcula o valor total de uma fatura baseado nas transações vinculadas.

    Args:
        fatura_id: ID da fatura a ser recalculada

    Returns:
        O novo valor total da fatura
    """
    fatura = Fatura.query.get(fatura_id)
    if not fatura:
        return None

    # Somar todas as transações desta fatura
    transacoes = Transacao.query.filter_by(fatura_id=fatura_id).all()
    valor_total = sum(transacao.valor for transacao in transacoes)

    # Atualizar valor da fatura
    fatura.valor_total = valor_total

    return valor_total


def gerar_transacoes_recorrentes(transacao_base, frequencia, data_inicio, quantidade, pago_inicial=False):
    """
    Gera transações recorrentes baseadas em uma transação modelo.

    Args:
        transacao_base: Transação que servirá como modelo
        frequencia: 'semanal', 'quinzenal', 'mensal', 'bimestral', 'trimestral', 'semestral', 'anual'
        data_inicio: Data da primeira transação
        quantidade: Número de vezes que a transação deve se repetir
        pago_inicial: Se as transações devem ser marcadas como pagas

    Returns:
        Lista de transações criadas
    """
    transacoes_criadas = []

    # Validar quantidade
    if quantidade < 1 or quantidade > 100:
        raise ValueError('A quantidade deve estar entre 1 e 100')

    # Determinar o intervalo baseado na frequência
    intervalos = {
        'semanal': relativedelta(weeks=1),
        'quinzenal': relativedelta(weeks=2),
        'mensal': relativedelta(months=1),
        'bimestral': relativedelta(months=2),
        'trimestral': relativedelta(months=3),
        'semestral': relativedelta(months=6),
        'anual': relativedelta(years=1)
    }

    if frequencia not in intervalos:
        raise ValueError(f'Frequência inválida: {frequencia}')

    intervalo = intervalos[frequencia]
    # Começar da segunda ocorrência, pois a primeira já é a transacao_base
    data_atual = data_inicio + intervalo

    # Gerar a quantidade especificada de transações (menos 1, pois a primeira já existe)
    for i in range(quantidade - 1):
        # Determinar se esta transação específica deve ser marcada como paga
        # Apenas transações passadas devem ser marcadas como pagas
        transacao_paga = pago_inicial and data_atual <= date.today()

        # Criar nova transação
        nova_transacao = Transacao(
            descricao=transacao_base.descricao,
            valor=transacao_base.valor,
            tipo=transacao_base.tipo,
            data=data_atual,
            forma_pagamento=transacao_base.forma_pagamento,
            conta_id=transacao_base.conta_id,
            categoria_id=transacao_base.categoria_id,
            recorrente=True,
            frequencia_recorrencia=frequencia,
            data_inicio_recorrencia=data_inicio,
            quantidade_recorrencias=quantidade,
            transacao_recorrente_pai_id=transacao_base.id,
            pago=transacao_paga
        )

        db.session.add(nova_transacao)
        transacoes_criadas.append(nova_transacao)

        # Avançar para a próxima data
        data_atual += intervalo

    return transacoes_criadas


# ==================== CATEGORIAS ====================

@bp.route('/categorias')
@login_required
def listar_categorias():
    """Lista todas as categorias"""
    categorias = Categoria.query.filter_by(user_id=current_user.id).all()
    return render_template('categorias/listar.html', categorias=categorias)


@bp.route('/categorias/nova', methods=['GET', 'POST'])
@login_required
def nova_categoria():
    """Criar nova categoria"""
    if request.method == 'POST':
        categoria = Categoria(
            nome=request.form['nome'],
            tipo=request.form['tipo'],
            cor=request.form.get('cor', '#3498db'),
            user_id=current_user.id
        )
        db.session.add(categoria)
        db.session.commit()
        flash('Categoria criada com sucesso!', 'success')
        return redirect(url_for('main.listar_categorias'))

    return render_template('categorias/form.html')


@bp.route('/api/categorias', methods=['POST'])
@login_required
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

        # Verificar se categoria já existe para este usuário
        categoria_existente = Categoria.query.filter_by(nome=nome, user_id=current_user.id).first()
        if categoria_existente:
            return jsonify({'erro': 'Já existe uma categoria com este nome'}), 400

        # Criar nova categoria
        categoria = Categoria(
            nome=nome,
            tipo=tipo,
            cor=cor,
            user_id=current_user.id
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
@login_required
def listar_cartoes():
    """Lista todos os cartões de crédito"""
    cartoes = CartaoCredito.query.filter_by(user_id=current_user.id).all()
    return render_template('cartoes/listar.html', cartoes=cartoes)


@bp.route('/cartoes/novo', methods=['GET', 'POST'])
@login_required
def novo_cartao():
    """Criar novo cartão de crédito"""
    if request.method == 'POST':
        # Validações
        limite = Decimal(request.form['limite'])
        dia_fechamento = int(request.form['dia_fechamento'])
        dia_vencimento = int(request.form['dia_vencimento'])

        if limite <= 0:
            flash('O limite deve ser maior que zero!', 'error')
            return redirect(url_for('main.novo_cartao'))

        if dia_fechamento < 1 or dia_fechamento > 31:
            flash('Dia de fechamento deve estar entre 1 e 31!', 'error')
            return redirect(url_for('main.novo_cartao'))

        if dia_vencimento < 1 or dia_vencimento > 31:
            flash('Dia de vencimento deve estar entre 1 e 31!', 'error')
            return redirect(url_for('main.novo_cartao'))

        cartao = CartaoCredito(
            nome=request.form['nome'],
            bandeira=request.form['bandeira'],
            banco_emissor=request.form.get('banco_emissor'),
            numero_cartao=request.form.get('numero_cartao'),
            limite=limite,
            dia_fechamento=dia_fechamento,
            dia_vencimento=dia_vencimento,
            user_id=current_user.id
        )
        db.session.add(cartao)
        db.session.commit()
        flash('Cartão de crédito criado com sucesso!', 'success')
        return redirect(url_for('main.listar_cartoes'))

    return render_template('cartoes/form.html')


@bp.route('/cartoes/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cartao(id):
    """Editar cartão de crédito"""
    cartao = CartaoCredito.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        cartao.nome = request.form['nome']
        cartao.bandeira = request.form['bandeira']
        cartao.banco_emissor = request.form.get('banco_emissor')
        cartao.numero_cartao = request.form.get('numero_cartao')
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
@login_required
def listar_faturas():
    """Lista todas as faturas"""
    faturas = Fatura.query.join(CartaoCredito).filter(
        CartaoCredito.user_id == current_user.id
    ).order_by(Fatura.ano_referencia.desc(), Fatura.mes_referencia.desc()).all()
    return render_template('faturas/listar.html', faturas=faturas)


@bp.route('/faturas/nova', methods=['GET', 'POST'])
@login_required
def nova_fatura():
    """Criar nova fatura"""
    if request.method == 'POST':
        # Verificar se o cartão pertence ao usuário
        cartao = CartaoCredito.query.filter_by(id=request.form['cartao_id'], user_id=current_user.id).first()
        if not cartao:
            flash('Cartão não encontrado ou acesso negado!', 'error')
            return redirect(url_for('main.listar_faturas'))

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

    cartoes = CartaoCredito.query.filter_by(ativo=True, user_id=current_user.id).all()
    return render_template('faturas/form.html', cartoes=cartoes)


@bp.route('/faturas/<int:id>')
@login_required
def ver_fatura(id):
    """Ver detalhes de uma fatura"""
    fatura = Fatura.query.join(CartaoCredito).filter(
        Fatura.id == id,
        CartaoCredito.user_id == current_user.id
    ).first_or_404()
    transacoes = Transacao.query.filter_by(fatura_id=id).all()
    contas = Conta.query.filter_by(ativa=True, user_id=current_user.id).all()
    return render_template('faturas/detalhes.html', fatura=fatura, transacoes=transacoes, contas=contas)


@bp.route('/faturas/<int:id>/pagar', methods=['POST'])
@login_required
def pagar_fatura(id):
    """Marcar fatura como paga"""
    fatura = Fatura.query.join(CartaoCredito).filter(
        Fatura.id == id,
        CartaoCredito.user_id == current_user.id
    ).first_or_404()
    valor_pago = Decimal(request.form.get('valor_pago', fatura.valor_total))

    fatura.valor_pago = valor_pago
    if valor_pago >= fatura.valor_total:
        fatura.status = 'paga'
        # Liberar limite do cartão quando fatura é totalmente paga
        cartao = fatura.cartao
        cartao.limite_utilizado -= fatura.valor_total

    # Criar transação de pagamento na conta
    if 'conta_id' in request.form:
        # Obter ou criar categoria para pagamento de fatura do usuário logado
        categoria_fatura = Categoria.query.filter_by(nome='Pagamento de Fatura', user_id=current_user.id).first()
        if not categoria_fatura:
            categoria_fatura = Categoria(nome='Pagamento de Fatura', tipo='despesa', cor='#ff3b57', user_id=current_user.id)
            db.session.add(categoria_fatura)
            db.session.flush()

        transacao = Transacao(
            descricao=f'Pagamento fatura {fatura.cartao.nome} {fatura.mes_referencia}/{fatura.ano_referencia}',
            valor=valor_pago,
            tipo='despesa',
            data=date.today(),
            conta_id=request.form['conta_id'],
            categoria_id=categoria_fatura.id,
            pago=True  # Marcar como pago automaticamente
        )

        conta = Conta.query.get(request.form['conta_id'])
        conta.saldo_atual -= valor_pago

        db.session.add(transacao)

    db.session.commit()
    flash('Fatura marcada como paga!', 'success')
    return redirect(url_for('main.ver_fatura', id=id))


# ==================== RELATÓRIOS ====================

@bp.route('/relatorios')
@login_required
def relatorios():
    """Página de relatórios e gráficos"""
    return render_template('relatorios/index.html')


@bp.route('/api/gastos-por-categoria')
@login_required
def api_gastos_por_categoria():
    """API: Gastos por categoria (para gráficos)"""
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)

    resultados = db.session.query(
        Categoria.nome,
        func.sum(Transacao.valor).label('total')
    ).join(Transacao).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.tipo == 'despesa',
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).group_by(Categoria.nome).all()

    return jsonify({
        'categorias': [r[0] for r in resultados],
        'valores': [float(r[1]) for r in resultados]
    })


@bp.route('/api/fluxo-caixa')
@login_required
def api_fluxo_caixa():
    """API: Fluxo de caixa mensal (para gráficos)"""
    ano = request.args.get('ano', datetime.now().year, type=int)

    receitas = db.session.query(
        extract('month', Transacao.data).label('mes'),
        func.sum(Transacao.valor).label('total')
    ).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.tipo == 'receita',
        extract('year', Transacao.data) == ano
    ).group_by('mes').all()

    despesas = db.session.query(
        extract('month', Transacao.data).label('mes'),
        func.sum(Transacao.valor).label('total')
    ).join(Conta).filter(
        Conta.user_id == current_user.id,
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


# ==================== ROTAS DE CONCILIAÇÃO BANCÁRIA ====================

@bp.route('/conciliacao')
@login_required
def conciliacao_lista():
    """Lista de conciliações bancárias"""
    conciliacoes = ConciliacaoBancaria.query.filter_by(
        user_id=current_user.id
    ).order_by(ConciliacaoBancaria.data_upload.desc()).all()

    return render_template('conciliacao/lista.html', conciliacoes=conciliacoes)


@bp.route('/conciliacao/nova', methods=['GET', 'POST'])
@login_required
def conciliacao_nova():
    """Upload de arquivo para conciliação"""
    if request.method == 'POST':
        # Validar se arquivo foi enviado
        if 'arquivo' not in request.files:
            flash('Nenhum arquivo foi enviado', 'danger')
            return redirect(request.url)

        arquivo = request.files['arquivo']
        if arquivo.filename == '':
            flash('Nenhum arquivo foi selecionado', 'danger')
            return redirect(request.url)

        # Obter conta selecionada
        conta_id = request.form.get('conta_id', type=int)
        if not conta_id:
            flash('Selecione uma conta', 'danger')
            return redirect(request.url)

        # Verificar se conta pertence ao usuário
        conta = Conta.query.filter_by(id=conta_id, user_id=current_user.id).first()
        if not conta:
            flash('Conta inválida', 'danger')
            return redirect(url_for('main.conciliacao_nova'))

        try:
            # Ler conteúdo do arquivo
            arquivo_content = arquivo.read()
            arquivo_nome = secure_filename(arquivo.filename)

            # Detectar formato
            formato = detect_format(arquivo_content)
            if formato == 'UNKNOWN':
                flash('Formato de arquivo não reconhecido. Use OFX ou CSV.', 'danger')
                return redirect(request.url)

            # Parsear arquivo
            resultado = parse_file(arquivo_content, formato)

            if resultado['total'] == 0:
                flash('Nenhuma transação encontrada no arquivo', 'warning')
                return redirect(request.url)

            # Criar conciliação
            conciliacao = ConciliacaoBancaria(
                user_id=current_user.id,
                conta_id=conta_id,
                arquivo_nome=arquivo_nome,
                formato=formato,
                status='processando',
                total_linhas=resultado['total'],
                data_inicio=resultado['date_range'][0],
                data_fim=resultado['date_range'][1]
            )
            db.session.add(conciliacao)
            db.session.flush()  # Para obter o ID

            # Processar matching
            itens_processados = processar_matching(
                resultado['transactions'],
                conta_id,
                current_user.id
            )

            # Criar itens de conciliação
            for item in itens_processados:
                melhor_match = item.get('melhor_match')
                item_conciliacao = ItemConciliacao(
                    conciliacao_id=conciliacao.id,
                    data=item['data'],
                    descricao=item['descricao'],
                    valor=item['valor'],
                    tipo=item['tipo'],
                    numero_documento=item.get('numero_documento'),
                    saldo_apos=item.get('saldo_apos'),
                    status='pendente',
                    transacao_id=melhor_match[0].id if melhor_match else None,
                    categoria_sugerida_id=item['categoria_sugerida'].id if item['categoria_sugerida'] else None,
                    score_matching=item['score_matching']
                )
                db.session.add(item_conciliacao)

            # Atualizar status
            conciliacao.status = 'pendente_revisao'
            db.session.commit()

            flash(f'Arquivo processado com sucesso! {resultado["total"]} transações encontradas.', 'success')
            return redirect(url_for('main.conciliacao_revisar', id=conciliacao.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar arquivo: {str(e)}', 'danger')
            return redirect(request.url)

    # GET: Mostrar formulário
    contas = Conta.query.filter_by(user_id=current_user.id, ativa=True).all()
    return render_template('conciliacao/nova.html', contas=contas)


@bp.route('/conciliacao/<int:id>/revisar')
@login_required
def conciliacao_revisar(id):
    """Revisar itens da conciliação e confirmar matches"""
    conciliacao = ConciliacaoBancaria.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    # Buscar itens
    itens = ItemConciliacao.query.filter_by(
        conciliacao_id=conciliacao.id
    ).order_by(ItemConciliacao.data.desc()).all()

    # Estatísticas
    stats = {
        'total': len(itens),
        'com_match_forte': sum(1 for item in itens if item.score_matching and item.score_matching >= 90),
        'com_match_medio': sum(1 for item in itens if item.score_matching and 70 <= item.score_matching < 90),
        'sem_match': sum(1 for item in itens if not item.score_matching or item.score_matching < 70)
    }

    # Buscar todas as categorias para seleção
    categorias = Categoria.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'conciliacao/revisar.html',
        conciliacao=conciliacao,
        itens=itens,
        stats=stats,
        categorias=categorias
    )


@bp.route('/conciliacao/<int:id>/processar', methods=['POST'])
@login_required
def conciliacao_processar(id):
    """Processar ações da conciliação (conciliar, importar, ignorar)"""
    conciliacao = ConciliacaoBancaria.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    try:
        # Obter ações do formulário
        acoes = request.form.getlist('acao')  # Lista de ações no formato "item_id:acao:transacao_id"

        linhas_conciliadas = 0
        linhas_importadas = 0

        for acao_str in acoes:
            partes = acao_str.split(':')
            if len(partes) < 2:
                continue

            item_id = int(partes[0])
            acao = partes[1]

            item = ItemConciliacao.query.filter_by(
                id=item_id,
                conciliacao_id=conciliacao.id
            ).first()

            if not item:
                continue

            if acao == 'conciliar':
                # Conciliar com transação existente
                if len(partes) >= 3:
                    transacao_id = int(partes[2])
                else:
                    transacao_id = item.transacao_id

                if transacao_id:
                    item.transacao_id = transacao_id
                    item.status = 'conciliado'
                    linhas_conciliadas += 1

            elif acao == 'importar':
                # Importar como nova transação
                categoria_id = request.form.get(f'categoria_{item_id}', type=int)
                if not categoria_id:
                    categoria_id = item.categoria_sugerida_id

                nova_transacao = Transacao(
                    descricao=item.descricao,
                    valor=item.valor,
                    tipo=item.tipo,
                    data=item.data,
                    conta_id=conciliacao.conta_id,
                    categoria_id=categoria_id,
                    pago=True,  # Transações do extrato já foram pagas
                    forma_pagamento='dinheiro'
                )
                db.session.add(nova_transacao)
                db.session.flush()

                item.transacao_id = nova_transacao.id
                item.status = 'importado'
                linhas_importadas += 1

            elif acao == 'ignorar':
                # Ignorar item
                item.status = 'ignorado'

        # Atualizar estatísticas da conciliação
        conciliacao.linhas_conciliadas = linhas_conciliadas
        conciliacao.linhas_importadas = linhas_importadas
        conciliacao.status = 'concluida'

        db.session.commit()

        flash(f'Conciliação concluída! {linhas_conciliadas} conciliadas, {linhas_importadas} importadas.', 'success')
        return redirect(url_for('main.conciliacao_lista'))

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao processar conciliação: {str(e)}', 'danger')
        return redirect(url_for('main.conciliacao_revisar', id=id))


@bp.route('/conciliacao/<int:id>/excluir', methods=['POST'])
@login_required
def conciliacao_excluir(id):
    """Excluir uma conciliação"""
    conciliacao = ConciliacaoBancaria.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    try:
        db.session.delete(conciliacao)
        db.session.commit()
        flash('Conciliação excluída com sucesso', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir conciliação: {str(e)}', 'danger')

    return redirect(url_for('main.conciliacao_lista'))
