from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app.models import db, Conta, Categoria, Transacao, CartaoCredito, Fatura, ConciliacaoBancaria, ItemConciliacao, Orcamento, Meta, DepositoMeta
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
        receitas_dia = 0.0
        despesas_dia = 0.0

        if dia_atual in transacoes_por_dia:
            receitas_dia = float(transacoes_por_dia[dia_atual]['receitas'])
            despesas_dia = float(transacoes_por_dia[dia_atual]['despesas'])
            saldo_acumulado += receitas_dia - despesas_dia

        projecao_fluxo.append({
            'data': dia_atual.strftime('%Y-%m-%d'),
            'dia': dia_atual.day,
            'saldo': round(saldo_acumulado, 2),
            'receitas': round(receitas_dia, 2),
            'despesas': round(despesas_dia, 2),
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

    # LEMBRETES DE METAS - Metas ativas que precisam de aporte
    metas_ativas = Meta.query.filter_by(
        user_id=current_user.id,
        status='ativa'
    ).order_by(Meta.data_fim).limit(5).all()

    # Processar metas para calcular status
    lembretes_metas = []
    for meta in metas_ativas:
        acumulado = meta.valor_acumulado()
        alvo = meta.valor_alvo
        percentual = meta.percentual_concluido()

        # Calcular se está no prazo
        dias_totais = (meta.data_fim - meta.data_inicio).days
        dias_passados = (date.today() - meta.data_inicio).days
        percentual_tempo = (dias_passados / dias_totais * 100) if dias_totais > 0 else 0

        # Determinar status e urgência
        if percentual >= 100:
            status = 'concluida'
            urgencia = 'baixa'
        elif percentual < percentual_tempo * 0.8:
            status = 'atrasado'
            urgencia = 'alta'
        elif percentual < percentual_tempo * 0.9:
            status = 'atencao'
            urgencia = 'media'
        else:
            status = 'no_prazo'
            urgencia = 'baixa'

        # Calcular valor mensal sugerido
        dias_restantes = (meta.data_fim - date.today()).days
        if dias_restantes > 0:
            faltante = float(alvo - acumulado)
            meses_restantes = dias_restantes / 30
            aporte_sugerido = faltante / meses_restantes if meses_restantes > 0 else faltante
        else:
            aporte_sugerido = 0

        lembretes_metas.append({
            'id': meta.id,
            'titulo': meta.titulo,
            'percentual': round(percentual, 1),
            'acumulado': float(acumulado),
            'alvo': float(alvo),
            'faltante': float(alvo - acumulado),
            'data_fim': meta.data_fim,
            'status': status,
            'urgencia': urgencia,
            'aporte_sugerido': round(aporte_sugerido, 2),
            'meses_restantes': meta.meses_restantes()
        })

    # ALERTAS DE ORÇAMENTOS - Orçamentos do mês atual
    orcamentos_mes = Orcamento.query.filter_by(
        user_id=current_user.id,
        mes=datetime.now().month,
        ano=datetime.now().year
    ).all()

    alertas_orcamentos = []
    for orc in orcamentos_mes:
        gasto = float(orc.valor_gasto())
        limite = float(orc.valor_limite)
        percentual = orc.percentual_gasto()

        # Determinar status
        if percentual >= 100:
            status = 'excedido'
            urgencia = 'alta'
        elif percentual >= orc.alerta_em_percentual:
            status = 'alerta'
            urgencia = 'media'
        else:
            status = 'ok'
            urgencia = 'baixa'

        # Só adicionar se tiver alerta ou excedido
        if status != 'ok':
            alertas_orcamentos.append({
                'id': orc.id,
                'categoria': orc.categoria.nome,
                'cor': orc.categoria.cor,
                'gasto': gasto,
                'limite': limite,
                'disponivel': limite - gasto,
                'percentual': round(percentual, 1),
                'status': status,
                'urgencia': urgencia
            })

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
                         proximas_receitas=proximas_receitas,
                         lembretes_metas=lembretes_metas,
                         alertas_orcamentos=alertas_orcamentos)


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


@bp.route('/api/evolucao-patrimonial')
@login_required
def api_evolucao_patrimonial():
    """API: Evolução patrimonial ao longo do tempo"""
    periodo = request.args.get('periodo', 'ano')  # mes, ano, tudo

    # Buscar todas as contas do usuário
    contas = Conta.query.filter_by(user_id=current_user.id).all()
    saldo_atual = sum(conta.saldo_atual for conta in contas)

    # Calcular evolução baseada nas transações
    if periodo == 'mes':
        # Últimos 30 dias
        inicio = date.today() - relativedelta(days=30)
        agrupamento = extract('day', Transacao.data)
    elif periodo == 'ano':
        # Últimos 12 meses
        inicio = date.today() - relativedelta(months=12)
        agrupamento = extract('month', Transacao.data)
    else:
        # Todo o histórico
        inicio = date(2020, 1, 1)
        agrupamento = extract('month', Transacao.data)

    # Buscar transações agrupadas
    transacoes = db.session.query(
        Transacao.data,
        Transacao.tipo,
        func.sum(Transacao.valor).label('total')
    ).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.data >= inicio,
        Transacao.pago == True
    ).group_by(Transacao.data, Transacao.tipo).order_by(Transacao.data).all()

    # Calcular patrimônio regressivamente
    datas = []
    valores = []
    saldo_temp = float(saldo_atual)

    # Criar dicionário de variações diárias
    variacoes = defaultdict(float)
    for t in reversed(transacoes):
        data_str = t.data.strftime('%Y-%m-%d')
        if t.tipo == 'receita':
            variacoes[data_str] -= float(t.total)
        else:
            variacoes[data_str] += float(t.total)

    # Gerar pontos do gráfico (do passado para o presente)
    data_atual = inicio
    while data_atual <= date.today():
        data_str = data_atual.strftime('%Y-%m-%d')
        if data_str in variacoes:
            saldo_temp -= variacoes[data_str]
        datas.append(data_str)
        valores.append(round(saldo_temp, 2))
        data_atual += relativedelta(days=1)
        saldo_temp += variacoes.get(data_str, 0)

    # Reverter para ordem correta
    datas.reverse()
    valores.reverse()

    return jsonify({
        'datas': datas,
        'valores': valores,
        'saldo_atual': float(saldo_atual)
    })


@bp.route('/api/analise-cartoes')
@login_required
def api_analise_cartoes():
    """API: Análise de uso de cartões de crédito"""
    cartoes = CartaoCredito.query.filter_by(user_id=current_user.id, ativo=True).all()

    dados = []
    for cartao in cartoes:
        # Buscar faturas em aberto
        faturas_abertas = Fatura.query.filter_by(
            cartao_id=cartao.id,
            status='aberta'
        ).count()

        # Calcular gasto médio mensal (últimos 6 meses)
        seis_meses_atras = date.today() - relativedelta(months=6)
        gasto_total = db.session.query(func.sum(Transacao.valor)).filter(
            Transacao.cartao_credito_id == cartao.id,
            Transacao.data >= seis_meses_atras
        ).scalar() or 0

        gasto_medio = float(gasto_total) / 6

        dados.append({
            'nome': cartao.nome,
            'bandeira': cartao.bandeira,
            'limite': float(cartao.limite),
            'utilizado': float(cartao.limite_utilizado),
            'disponivel': float(cartao.limite_disponivel()),
            'percentual': round(cartao.percentual_utilizado(), 1),
            'faturas_abertas': faturas_abertas,
            'gasto_medio_mensal': round(gasto_medio, 2)
        })

    return jsonify({'cartoes': dados})


@bp.route('/api/orcamentos-vs-realizado')
@login_required
def api_orcamentos_vs_realizado():
    """API: Comparação entre orçamentos e gastos realizados"""
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)

    orcamentos = Orcamento.query.filter_by(
        user_id=current_user.id,
        mes=mes,
        ano=ano
    ).all()

    dados = []
    for orc in orcamentos:
        gasto = float(orc.valor_gasto())
        limite = float(orc.valor_limite)
        percentual = orc.percentual_gasto()

        dados.append({
            'categoria': orc.categoria.nome,
            'orcado': limite,
            'gasto': gasto,
            'saldo': limite - gasto,
            'percentual': round(percentual, 1),
            'status': 'excedido' if percentual > 100 else 'alerta' if percentual >= orc.alerta_em_percentual else 'ok'
        })

    return jsonify({
        'orcamentos': dados,
        'total_orcado': sum(d['orcado'] for d in dados),
        'total_gasto': sum(d['gasto'] for d in dados)
    })


@bp.route('/api/progresso-metas')
@login_required
def api_progresso_metas():
    """API: Progresso das metas de economia"""
    metas = Meta.query.filter_by(
        user_id=current_user.id,
        status='ativa'
    ).all()

    dados = []
    for meta in metas:
        acumulado = float(meta.valor_acumulado())
        alvo = float(meta.valor_alvo)
        percentual = meta.percentual_concluido()

        # Calcular se está no prazo
        dias_totais = (meta.data_fim - meta.data_inicio).days
        dias_passados = (date.today() - meta.data_inicio).days
        percentual_tempo = (dias_passados / dias_totais * 100) if dias_totais > 0 else 0

        status = 'adiantado' if percentual > percentual_tempo else 'no_prazo' if percentual >= percentual_tempo * 0.9 else 'atrasado'

        dados.append({
            'titulo': meta.titulo,
            'alvo': alvo,
            'acumulado': acumulado,
            'faltante': alvo - acumulado,
            'percentual': round(percentual, 1),
            'percentual_tempo': round(percentual_tempo, 1),
            'status': status,
            'meses_restantes': meta.meses_restantes()
        })

    return jsonify({
        'metas': dados,
        'total_alvo': sum(d['alvo'] for d in dados),
        'total_acumulado': sum(d['acumulado'] for d in dados)
    })


@bp.route('/api/comparacao-periodos')
@login_required
def api_comparacao_periodos():
    """API: Comparação entre diferentes períodos"""
    tipo = request.args.get('tipo', 'mensal')  # mensal, trimestral, anual
    quantidade = request.args.get('quantidade', 6, type=int)

    periodos = []
    receitas = []
    despesas = []
    saldos = []

    hoje = date.today()

    for i in range(quantidade - 1, -1, -1):
        if tipo == 'mensal':
            data_ref = hoje - relativedelta(months=i)
            inicio_periodo = date(data_ref.year, data_ref.month, 1)
            fim_periodo = date(data_ref.year, data_ref.month, monthrange(data_ref.year, data_ref.month)[1])
            label = f"{inicio_periodo.strftime('%b/%y')}"
        elif tipo == 'trimestral':
            data_ref = hoje - relativedelta(months=i*3)
            inicio_periodo = date(data_ref.year, ((data_ref.month-1)//3)*3 + 1, 1)
            fim_mes = ((data_ref.month-1)//3)*3 + 3
            fim_periodo = date(data_ref.year, fim_mes, monthrange(data_ref.year, fim_mes)[1])
            label = f"Q{((data_ref.month-1)//3)+1}/{data_ref.year}"
        else:  # anual
            data_ref = hoje - relativedelta(years=i)
            inicio_periodo = date(data_ref.year, 1, 1)
            fim_periodo = date(data_ref.year, 12, 31)
            label = str(data_ref.year)

        # Buscar receitas do período
        total_receitas = db.session.query(func.sum(Transacao.valor)).join(Conta).filter(
            Conta.user_id == current_user.id,
            Transacao.tipo == 'receita',
            Transacao.data >= inicio_periodo,
            Transacao.data <= fim_periodo
        ).scalar() or 0

        # Buscar despesas do período
        total_despesas = db.session.query(func.sum(Transacao.valor)).join(Conta).filter(
            Conta.user_id == current_user.id,
            Transacao.tipo == 'despesa',
            Transacao.data >= inicio_periodo,
            Transacao.data <= fim_periodo
        ).scalar() or 0

        periodos.append(label)
        receitas.append(float(total_receitas))
        despesas.append(float(total_despesas))
        saldos.append(float(total_receitas - total_despesas))

    return jsonify({
        'periodos': periodos,
        'receitas': receitas,
        'despesas': despesas,
        'saldos': saldos
    })


@bp.route('/api/top-categorias')
@login_required
def api_top_categorias():
    """API: Top categorias por gastos"""
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)
    limite = request.args.get('limite', 10, type=int)

    resultados = db.session.query(
        Categoria.nome,
        Categoria.cor,
        func.sum(Transacao.valor).label('total'),
        func.count(Transacao.id).label('quantidade')
    ).join(Transacao).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.tipo == 'despesa',
        extract('month', Transacao.data) == mes,
        extract('year', Transacao.data) == ano
    ).group_by(Categoria.nome, Categoria.cor).order_by(func.sum(Transacao.valor).desc()).limit(limite).all()

    categorias = []
    valores = []
    cores = []
    quantidades = []

    for r in resultados:
        categorias.append(r[0])
        valores.append(float(r[2]))
        cores.append(r[1] or '#3498db')
        quantidades.append(r[3])

    return jsonify({
        'categorias': categorias,
        'valores': valores,
        'cores': cores,
        'quantidades': quantidades,
        'total': sum(valores)
    })


@bp.route('/api/analise-recorrentes')
@login_required
def api_analise_recorrentes():
    """API: Análise de despesas recorrentes"""
    # Buscar transações recorrentes ativas (próximas ocorrências)
    hoje = date.today()
    proximo_mes = hoje + relativedelta(months=1)

    # Buscar transações recorrentes que têm ocorrências futuras
    recorrentes = db.session.query(
        Transacao.descricao,
        Transacao.valor,
        Transacao.frequencia_recorrencia,
        Categoria.nome.label('categoria'),
        func.min(Transacao.data).label('proxima_data')
    ).join(Categoria).join(Conta).filter(
        Conta.user_id == current_user.id,
        Transacao.recorrente == True,
        Transacao.data >= hoje,
        Transacao.data <= proximo_mes
    ).group_by(
        Transacao.descricao,
        Transacao.valor,
        Transacao.frequencia_recorrencia,
        Categoria.nome
    ).all()

    dados = []
    total_mensal = 0

    for rec in recorrentes:
        valor = float(rec[1])

        # Estimar impacto mensal baseado na frequência
        frequencias_mult = {
            'semanal': 4.33,
            'quinzenal': 2,
            'mensal': 1,
            'bimestral': 0.5,
            'trimestral': 0.33,
            'semestral': 0.167,
            'anual': 0.083
        }

        multiplicador = frequencias_mult.get(rec[2], 1)
        impacto_mensal = valor * multiplicador
        total_mensal += impacto_mensal

        dados.append({
            'descricao': rec[0],
            'valor': valor,
            'frequencia': rec[2],
            'categoria': rec[3],
            'proxima_data': rec[4].strftime('%Y-%m-%d'),
            'impacto_mensal': round(impacto_mensal, 2)
        })

    return jsonify({
        'recorrentes': dados,
        'total_mensal_estimado': round(total_mensal, 2),
        'quantidade': len(dados)
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


# ==================== ORÇAMENTOS ====================

@bp.route('/orcamentos')
@login_required
def listar_orcamentos():
    """Lista orçamentos do mês atual"""
    mes = request.args.get('mes', type=int) or datetime.now().month
    ano = request.args.get('ano', type=int) or datetime.now().year

    # Calcular mês anterior e próximo para navegação
    if mes == 1:
        mes_anterior = 12
        ano_anterior = ano - 1
    else:
        mes_anterior = mes - 1
        ano_anterior = ano

    if mes == 12:
        mes_proximo = 1
        ano_proximo = ano + 1
    else:
        mes_proximo = mes + 1
        ano_proximo = ano

    # Buscar orçamentos do mês
    orcamentos = Orcamento.query.filter_by(
        user_id=current_user.id,
        mes=mes,
        ano=ano
    ).all()

    # Buscar categorias de despesa sem orçamento neste mês
    categorias_com_orcamento = [o.categoria_id for o in orcamentos]
    categorias_sem_orcamento = Categoria.query.filter(
        Categoria.user_id == current_user.id,
        Categoria.tipo == 'despesa',
        ~Categoria.id.in_(categorias_com_orcamento)
    ).all()

    # Calcular total orçado e total gasto
    total_orcado = sum(o.valor_limite for o in orcamentos)
    total_gasto = sum(o.valor_gasto() for o in orcamentos)

    # Nome do mês em português
    meses_pt = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }

    return render_template('orcamentos/listar.html',
                         orcamentos=orcamentos,
                         categorias_sem_orcamento=categorias_sem_orcamento,
                         mes=mes,
                         ano=ano,
                         mes_anterior=mes_anterior,
                         ano_anterior=ano_anterior,
                         mes_proximo=mes_proximo,
                         ano_proximo=ano_proximo,
                         nome_mes=meses_pt[mes],
                         total_orcado=total_orcado,
                         total_gasto=total_gasto)


@bp.route('/orcamentos/novo', methods=['GET', 'POST'])
@login_required
def novo_orcamento():
    """Criar novo orçamento"""
    if request.method == 'POST':
        categoria_id = int(request.form['categoria_id'])
        mes = int(request.form['mes'])
        ano = int(request.form['ano'])
        valor_limite = Decimal(request.form['valor_limite'])
        alerta_em_percentual = int(request.form.get('alerta_em_percentual', 80))

        # Verificar se já existe orçamento para esta categoria neste mês
        orcamento_existente = Orcamento.query.filter_by(
            user_id=current_user.id,
            categoria_id=categoria_id,
            mes=mes,
            ano=ano
        ).first()

        if orcamento_existente:
            flash('Já existe um orçamento para esta categoria neste mês!', 'error')
            return redirect(url_for('main.novo_orcamento'))

        orcamento = Orcamento(
            user_id=current_user.id,
            categoria_id=categoria_id,
            mes=mes,
            ano=ano,
            valor_limite=valor_limite,
            alerta_em_percentual=alerta_em_percentual
        )
        db.session.add(orcamento)
        db.session.commit()
        flash('Orçamento criado com sucesso!', 'success')
        return redirect(url_for('main.listar_orcamentos', mes=mes, ano=ano))

    # Buscar categorias de despesa
    categorias = Categoria.query.filter_by(
        user_id=current_user.id,
        tipo='despesa'
    ).order_by(Categoria.nome).all()

    mes_atual = datetime.now().month
    ano_atual = datetime.now().year

    return render_template('orcamentos/form.html',
                         categorias=categorias,
                         mes_atual=mes_atual,
                         ano_atual=ano_atual)


@bp.route('/orcamentos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_orcamento(id):
    """Editar orçamento existente"""
    orcamento = Orcamento.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == 'POST':
        orcamento.valor_limite = Decimal(request.form['valor_limite'])
        orcamento.alerta_em_percentual = int(request.form.get('alerta_em_percentual', 80))
        db.session.commit()
        flash('Orçamento atualizado com sucesso!', 'success')
        return redirect(url_for('main.listar_orcamentos', mes=orcamento.mes, ano=orcamento.ano))

    categorias = Categoria.query.filter_by(
        user_id=current_user.id,
        tipo='despesa'
    ).order_by(Categoria.nome).all()

    return render_template('orcamentos/form.html',
                         orcamento=orcamento,
                         categorias=categorias)


@bp.route('/orcamentos/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_orcamento(id):
    """Deletar um orçamento"""
    orcamento = Orcamento.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    mes = orcamento.mes
    ano = orcamento.ano

    db.session.delete(orcamento)
    db.session.commit()
    flash('Orçamento deletado com sucesso!', 'success')
    return redirect(url_for('main.listar_orcamentos', mes=mes, ano=ano))


# ==================== METAS ====================

@bp.route('/metas')
@login_required
def listar_metas():
    """Lista todas as metas"""
    # Buscar metas ativas
    metas_ativas = Meta.query.filter_by(
        user_id=current_user.id,
        status='ativa'
    ).order_by(Meta.data_fim).all()

    # Buscar metas concluídas (últimas 5)
    metas_concluidas = Meta.query.filter_by(
        user_id=current_user.id,
        status='concluida'
    ).order_by(Meta.data_conclusao.desc()).limit(5).all()

    # Calcular totais
    total_economizado = sum(m.valor_acumulado() for m in metas_ativas)
    total_metas = sum(m.valor_alvo for m in metas_ativas)

    return render_template('metas/listar.html',
                         metas_ativas=metas_ativas,
                         metas_concluidas=metas_concluidas,
                         total_economizado=total_economizado,
                         total_metas=total_metas)


@bp.route('/metas/nova', methods=['GET', 'POST'])
@login_required
def nova_meta():
    """Criar nova meta"""
    if request.method == 'POST':
        titulo = request.form['titulo']
        descricao = request.form.get('descricao', '')
        valor_alvo = Decimal(request.form['valor_alvo'])
        valor_inicial = Decimal(request.form.get('valor_inicial', 0))
        valor_mensal = Decimal(request.form.get('valor_mensal', 0))
        data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        data_fim = datetime.strptime(request.form['data_fim'], '%Y-%m-%d').date()
        conta_id = request.form.get('conta_id')

        if data_fim <= data_inicio:
            flash('A data fim deve ser posterior à data de início!', 'error')
            return redirect(url_for('main.nova_meta'))

        meta = Meta(
            user_id=current_user.id,
            titulo=titulo,
            descricao=descricao,
            valor_alvo=valor_alvo,
            valor_inicial=valor_inicial,
            valor_mensal=valor_mensal,
            data_inicio=data_inicio,
            data_fim=data_fim,
            conta_id=conta_id if conta_id else None,
            status='ativa'
        )
        db.session.add(meta)
        db.session.commit()
        flash('Meta criada com sucesso!', 'success')
        return redirect(url_for('main.listar_metas'))

    contas = Conta.query.filter_by(
        user_id=current_user.id,
        ativa=True
    ).all()

    data_hoje = date.today().strftime('%Y-%m-%d')

    return render_template('metas/form.html',
                         contas=contas,
                         data_hoje=data_hoje)


@bp.route('/metas/<int:id>')
@login_required
def ver_meta(id):
    """Ver detalhes de uma meta"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    # Buscar depósitos ordenados por data
    depositos = DepositoMeta.query.filter_by(
        meta_id=meta.id
    ).order_by(DepositoMeta.data.desc()).all()

    return render_template('metas/detalhes.html',
                         meta=meta,
                         depositos=depositos)


@bp.route('/metas/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_meta(id):
    """Editar meta existente"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == 'POST':
        meta.titulo = request.form['titulo']
        meta.descricao = request.form.get('descricao', '')
        meta.valor_alvo = Decimal(request.form['valor_alvo'])
        meta.valor_inicial = Decimal(request.form.get('valor_inicial', 0))
        meta.valor_mensal = Decimal(request.form.get('valor_mensal', 0))
        meta.data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        meta.data_fim = datetime.strptime(request.form['data_fim'], '%Y-%m-%d').date()
        conta_id = request.form.get('conta_id')
        meta.conta_id = conta_id if conta_id else None

        db.session.commit()
        flash('Meta atualizada com sucesso!', 'success')
        return redirect(url_for('main.ver_meta', id=meta.id))

    contas = Conta.query.filter_by(
        user_id=current_user.id,
        ativa=True
    ).all()

    return render_template('metas/form.html',
                         meta=meta,
                         contas=contas)


@bp.route('/metas/<int:id>/deletar', methods=['POST'])
@login_required
def deletar_meta(id):
    """Deletar uma meta"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    db.session.delete(meta)
    db.session.commit()
    flash('Meta deletada com sucesso!', 'success')
    return redirect(url_for('main.listar_metas'))


@bp.route('/metas/<int:id>/deposito', methods=['POST'])
@login_required
def adicionar_deposito(id):
    """Adicionar depósito a uma meta"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    valor = Decimal(request.form['valor'])
    data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
    observacao = request.form.get('observacao', '')

    if valor <= 0:
        flash('O valor deve ser maior que zero!', 'error')
        return redirect(url_for('main.ver_meta', id=id))

    deposito = DepositoMeta(
        meta_id=meta.id,
        valor=valor,
        data=data,
        observacao=observacao
    )
    db.session.add(deposito)

    # Verificar se a meta foi concluída
    if meta.valor_acumulado() + valor >= meta.valor_alvo:
        meta.status = 'concluida'
        meta.data_conclusao = date.today()
        flash('Parabéns! Meta concluída!', 'success')
    else:
        flash('Depósito adicionado com sucesso!', 'success')

    db.session.commit()
    return redirect(url_for('main.ver_meta', id=id))


@bp.route('/metas/<int:meta_id>/deposito/<int:deposito_id>/deletar', methods=['POST'])
@login_required
def deletar_deposito(meta_id, deposito_id):
    """Deletar um depósito"""
    meta = Meta.query.filter_by(
        id=meta_id,
        user_id=current_user.id
    ).first_or_404()

    deposito = DepositoMeta.query.filter_by(
        id=deposito_id,
        meta_id=meta_id
    ).first_or_404()

    # Se a meta estava concluída, reverter status
    if meta.status == 'concluida':
        meta.status = 'ativa'
        meta.data_conclusao = None

    db.session.delete(deposito)
    db.session.commit()
    flash('Depósito removido com sucesso!', 'success')
    return redirect(url_for('main.ver_meta', id=meta_id))


@bp.route('/metas/<int:id>/concluir', methods=['POST'])
@login_required
def concluir_meta(id):
    """Marcar meta como concluída manualmente"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    meta.status = 'concluida'
    meta.data_conclusao = date.today()
    db.session.commit()
    flash('Meta marcada como concluída!', 'success')
    return redirect(url_for('main.listar_metas'))


@bp.route('/metas/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_meta(id):
    """Cancelar uma meta"""
    meta = Meta.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    meta.status = 'cancelada'
    db.session.commit()
    flash('Meta cancelada!', 'info')
    return redirect(url_for('main.listar_metas'))
