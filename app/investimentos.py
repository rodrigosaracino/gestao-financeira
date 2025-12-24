"""
Blueprint de rotas para módulo de Investimentos
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, Ativo, TipoAtivo, TransacaoAtivo, Dividendo
from app.services.brapi_service import brapi_service
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func

investimentos_bp = Blueprint('investimentos', __name__, url_prefix='/investimentos')


@investimentos_bp.route('/')
@login_required
def index():
    """Dashboard principal de investimentos"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    # Atualizar cotações se necessário
    if ativos:
        brapi_service.atualizar_carteira(ativos)

    # Calcular estatísticas
    stats = calcular_estatisticas_carteira(ativos)

    return render_template('investimentos/index.html',
                         ativos=ativos,
                         stats=stats)


@investimentos_bp.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar():
    """Adicionar novo ativo à carteira"""
    if request.method == 'POST':
        try:
            ticker = request.form.get('ticker', '').upper().strip()
            tipo_ativo_id = request.form.get('tipo_ativo_id')
            quantidade = Decimal(request.form.get('quantidade', 0))
            preco_medio = Decimal(request.form.get('preco_medio', 0))

            # Validações
            if not ticker:
                flash('Ticker é obrigatório', 'danger')
                return redirect(url_for('investimentos.adicionar'))

            if quantidade <= 0:
                flash('Quantidade deve ser maior que zero', 'danger')
                return redirect(url_for('investimentos.adicionar'))

            if preco_medio <= 0:
                flash('Preço médio deve ser maior que zero', 'danger')
                return redirect(url_for('investimentos.adicionar'))

            # Verificar se ticker já existe para este usuário
            ativo_existente = Ativo.query.filter_by(
                user_id=current_user.id,
                ticker=ticker
            ).first()

            if ativo_existente:
                flash(f'Você já possui {ticker} na carteira. Use "Editar" para modificar.', 'warning')
                return redirect(url_for('investimentos.index'))

            # Buscar informações do ativo na API
            cotacao = brapi_service.buscar_cotacao(ticker)

            if not cotacao:
                flash(f'Ticker {ticker} não encontrado na B3. Verifique se está correto.', 'warning')

            # Criar ativo
            instituicao = request.form.get('instituicao', '').strip() or None

            ativo = Ativo(
                user_id=current_user.id,
                tipo_ativo_id=tipo_ativo_id,
                ticker=ticker,
                nome=cotacao['nome'] if cotacao else None,
                instituicao=instituicao,
                quantidade=quantidade,
                preco_medio=preco_medio,
                ultimo_preco=cotacao['preco'] if cotacao else None,
                ultima_atualizacao=cotacao['data_atualizacao'] if cotacao else None,
                variacao_dia=cotacao['variacao_dia'] if cotacao else None
            )

            db.session.add(ativo)
            db.session.commit()

            flash(f'Ativo {ticker} adicionado com sucesso!', 'success')
            return redirect(url_for('investimentos.index'))

        except ValueError as e:
            flash(f'Erro nos valores informados: {str(e)}', 'danger')
            return redirect(url_for('investimentos.adicionar'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar ativo: {str(e)}', 'danger')
            return redirect(url_for('investimentos.adicionar'))

    # GET - mostrar formulário
    tipos_ativos = TipoAtivo.query.all()
    return render_template('investimentos/adicionar.html', tipos_ativos=tipos_ativos)


@investimentos_bp.route('/<int:ativo_id>/editar', methods=['GET', 'POST'])
@login_required
def editar(ativo_id):
    """Editar ativo existente"""
    ativo = Ativo.query.get_or_404(ativo_id)

    # Verificar permissão
    if ativo.user_id != current_user.id:
        flash('Acesso negado', 'danger')
        return redirect(url_for('investimentos.index'))

    if request.method == 'POST':
        try:
            ativo.quantidade = Decimal(request.form.get('quantidade', 0))
            ativo.preco_medio = Decimal(request.form.get('preco_medio', 0))
            ativo.tipo_ativo_id = request.form.get('tipo_ativo_id')
            ativo.instituicao = request.form.get('instituicao', '').strip() or None

            db.session.commit()
            flash(f'Ativo {ativo.ticker} atualizado com sucesso!', 'success')
            return redirect(url_for('investimentos.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar ativo: {str(e)}', 'danger')

    tipos_ativos = TipoAtivo.query.all()
    return render_template('investimentos/editar.html', ativo=ativo, tipos_ativos=tipos_ativos)


@investimentos_bp.route('/<int:ativo_id>/excluir', methods=['POST'])
@login_required
def excluir(ativo_id):
    """Excluir ativo da carteira"""
    ativo = Ativo.query.get_or_404(ativo_id)

    # Verificar permissão
    if ativo.user_id != current_user.id:
        flash('Acesso negado', 'danger')
        return redirect(url_for('investimentos.index'))

    try:
        ticker = ativo.ticker
        db.session.delete(ativo)
        db.session.commit()
        flash(f'Ativo {ticker} removido da carteira', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir ativo: {str(e)}', 'danger')

    return redirect(url_for('investimentos.index'))


@investimentos_bp.route('/<int:ativo_id>/transacoes')
@login_required
def transacoes(ativo_id):
    """Ver histórico de transações de um ativo"""
    ativo = Ativo.query.get_or_404(ativo_id)

    # Verificar permissão
    if ativo.user_id != current_user.id:
        flash('Acesso negado', 'danger')
        return redirect(url_for('investimentos.index'))

    transacoes = TransacaoAtivo.query.filter_by(ativo_id=ativo_id)\
        .order_by(TransacaoAtivo.data_operacao.desc()).all()

    return render_template('investimentos/transacoes.html',
                         ativo=ativo,
                         transacoes=transacoes)


@investimentos_bp.route('/<int:ativo_id>/adicionar-transacao', methods=['GET', 'POST'])
@login_required
def adicionar_transacao(ativo_id):
    """Adicionar transação de compra/venda"""
    ativo = Ativo.query.get_or_404(ativo_id)

    # Verificar permissão
    if ativo.user_id != current_user.id:
        flash('Acesso negado', 'danger')
        return redirect(url_for('investimentos.index'))

    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            quantidade = Decimal(request.form.get('quantidade', 0))
            preco_unitario = Decimal(request.form.get('preco_unitario', 0))
            taxa_corretagem = Decimal(request.form.get('taxa_corretagem', 0))
            outros_custos = Decimal(request.form.get('outros_custos', 0))
            data_operacao = datetime.strptime(request.form.get('data_operacao'), '%Y-%m-%d').date()
            observacao = request.form.get('observacao', '')

            # Criar transação
            transacao = TransacaoAtivo(
                ativo_id=ativo_id,
                tipo=tipo,
                quantidade=quantidade,
                preco_unitario=preco_unitario,
                taxa_corretagem=taxa_corretagem,
                outros_custos=outros_custos,
                data_operacao=data_operacao,
                observacao=observacao
            )

            db.session.add(transacao)

            # Atualizar quantidade e preço médio do ativo
            recalcular_preco_medio(ativo)

            db.session.commit()
            flash(f'Transação de {tipo} registrada com sucesso!', 'success')
            return redirect(url_for('investimentos.transacoes', ativo_id=ativo_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar transação: {str(e)}', 'danger')

    return render_template('investimentos/adicionar_transacao.html', ativo=ativo)


@investimentos_bp.route('/<int:ativo_id>/dividendos')
@login_required
def dividendos(ativo_id):
    """Ver histórico de dividendos de um ativo"""
    ativo = Ativo.query.get_or_404(ativo_id)

    # Verificar permissão
    if ativo.user_id != current_user.id:
        flash('Acesso negado', 'danger')
        return redirect(url_for('investimentos.index'))

    dividendos = Dividendo.query.filter_by(ativo_id=ativo_id)\
        .order_by(Dividendo.data_pagamento.desc()).all()

    # Calcular total recebido
    total_recebido = sum(d.valor_total for d in dividendos if d.recebido)

    return render_template('investimentos/dividendos.html',
                         ativo=ativo,
                         dividendos=dividendos,
                         total_recebido=total_recebido)


@investimentos_bp.route('/api/pesquisar-ticker')
@login_required
def pesquisar_ticker():
    """API para pesquisar tickers"""
    termo = request.args.get('q', '')

    if len(termo) < 2:
        return jsonify([])

    resultados = brapi_service.pesquisar_ativo(termo)
    return jsonify(resultados)


@investimentos_bp.route('/api/atualizar-cotacoes', methods=['POST'])
@login_required
def atualizar_cotacoes():
    """API para atualizar todas as cotações da carteira"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    if not ativos:
        return jsonify({'success': False, 'message': 'Nenhum ativo na carteira'})

    stats = brapi_service.atualizar_carteira(ativos)

    return jsonify({
        'success': True,
        'stats': stats,
        'message': f'{stats["atualizados"]} ativos atualizados'
    })


@investimentos_bp.route('/relatorios')
@login_required
def relatorios():
    """Página de relatórios e gráficos de investimentos"""
    return render_template('investimentos/relatorios.html')


@investimentos_bp.route('/api/grafico-distribuicao-tipos')
@login_required
def api_grafico_distribuicao_tipos():
    """API: Distribuição da carteira por tipo de ativo"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    # Atualizar cotações se necessário
    brapi_service.atualizar_carteira(ativos)

    # Agrupar por tipo
    distribuicao = {}
    for ativo in ativos:
        tipo_nome = ativo.tipo.nome
        valor = float(ativo.valor_atual())

        if tipo_nome in distribuicao:
            distribuicao[tipo_nome] += valor
        else:
            distribuicao[tipo_nome] = valor

    return jsonify({
        'labels': list(distribuicao.keys()),
        'values': list(distribuicao.values())
    })


@investimentos_bp.route('/api/grafico-rentabilidade-ativos')
@login_required
def api_grafico_rentabilidade_ativos():
    """API: Rentabilidade individual de cada ativo"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    # Atualizar cotações se necessário
    brapi_service.atualizar_carteira(ativos)

    dados = []
    for ativo in ativos:
        dados.append({
            'ticker': ativo.ticker,
            'rentabilidade_percentual': float(ativo.rentabilidade_percentual()),
            'rentabilidade_reais': float(ativo.rentabilidade_reais()),
            'valor_atual': float(ativo.valor_atual())
        })

    # Ordenar por rentabilidade percentual
    dados.sort(key=lambda x: x['rentabilidade_percentual'], reverse=True)

    return jsonify(dados)


@investimentos_bp.route('/api/grafico-composicao-carteira')
@login_required
def api_grafico_composicao_carteira():
    """API: Composição da carteira por ativo (top 10)"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    # Atualizar cotações se necessário
    brapi_service.atualizar_carteira(ativos)

    # Calcular valor atual de cada ativo
    dados = []
    for ativo in ativos:
        dados.append({
            'ticker': ativo.ticker,
            'valor': float(ativo.valor_atual()),
            'percentual': 0  # Será calculado depois
        })

    # Ordenar por valor e pegar top 10
    dados.sort(key=lambda x: x['valor'], reverse=True)
    top_10 = dados[:10]

    # Calcular total para percentuais
    total = sum(d['valor'] for d in dados)

    if total > 0:
        for d in top_10:
            d['percentual'] = (d['valor'] / total) * 100

    return jsonify(top_10)


@investimentos_bp.route('/api/evolucao-patrimonial')
@login_required
def api_evolucao_patrimonial():
    """API: Evolução do patrimônio em investimentos (últimos 12 meses)"""
    from datetime import datetime, timedelta
    from sqlalchemy import extract

    # Buscar todas as transações dos últimos 12 meses
    data_inicial = datetime.now() - timedelta(days=365)

    transacoes = db.session.query(
        TransacaoAtivo,
        Ativo
    ).join(Ativo).filter(
        Ativo.user_id == current_user.id,
        TransacaoAtivo.data_operacao >= data_inicial.date()
    ).order_by(TransacaoAtivo.data_operacao).all()

    # Calcular patrimônio acumulado mês a mês
    patrimonio_por_mes = {}
    patrimonio_acumulado = Decimal('0')

    for trans, ativo in transacoes:
        mes_ano = trans.data_operacao.strftime('%Y-%m')

        if trans.tipo == 'compra':
            patrimonio_acumulado += trans.valor_total()
        else:  # venda
            patrimonio_acumulado -= trans.valor_total()

        patrimonio_por_mes[mes_ano] = float(patrimonio_acumulado)

    # Preencher meses faltantes
    meses = []
    valores = []

    for i in range(12):
        data = datetime.now() - timedelta(days=30*i)
        mes_ano = data.strftime('%Y-%m')
        mes_label = data.strftime('%b/%Y')

        meses.insert(0, mes_label)
        valores.insert(0, patrimonio_por_mes.get(mes_ano, float(patrimonio_acumulado)))

    return jsonify({
        'meses': meses,
        'valores': valores
    })


@investimentos_bp.route('/api/resumo-estatisticas')
@login_required
def api_resumo_estatisticas():
    """API: Resumo de estatísticas gerais"""
    ativos = Ativo.query.filter_by(user_id=current_user.id, ativo=True).all()

    # Atualizar cotações
    brapi_service.atualizar_carteira(ativos)

    stats = calcular_estatisticas_carteira(ativos)

    # Converter Decimal para float
    return jsonify({
        'valor_investido': float(stats['valor_investido']),
        'valor_atual': float(stats['valor_atual']),
        'rentabilidade_reais': float(stats['rentabilidade_reais']),
        'rentabilidade_percentual': float(stats['rentabilidade_percentual']),
        'total_ativos': stats['total_ativos'],
        'total_tipos': len(set(a.tipo.nome for a in ativos))
    })


# Funções auxiliares

def calcular_estatisticas_carteira(ativos):
    """Calcula estatísticas gerais da carteira"""
    if not ativos:
        return {
            'valor_investido': Decimal('0'),
            'valor_atual': Decimal('0'),
            'rentabilidade_reais': Decimal('0'),
            'rentabilidade_percentual': 0,
            'total_ativos': 0,
            'distribuicao_por_tipo': []
        }

    valor_investido = sum(a.valor_investido() for a in ativos)
    valor_atual = sum(a.valor_atual() for a in ativos)
    rentabilidade_reais = valor_atual - valor_investido

    rentabilidade_percentual = 0
    if valor_investido > 0:
        rentabilidade_percentual = float((rentabilidade_reais / valor_investido) * 100)

    # Distribuição por tipo
    distribuicao = db.session.query(
        TipoAtivo.nome,
        func.sum(Ativo.quantidade * Ativo.ultimo_preco).label('valor')
    ).join(Ativo).filter(
        Ativo.user_id == current_user.id,
        Ativo.ativo == True
    ).group_by(TipoAtivo.nome).all()

    return {
        'valor_investido': valor_investido,
        'valor_atual': valor_atual,
        'rentabilidade_reais': rentabilidade_reais,
        'rentabilidade_percentual': rentabilidade_percentual,
        'total_ativos': len(ativos),
        'distribuicao_por_tipo': distribuicao
    }


def recalcular_preco_medio(ativo):
    """Recalcula o preço médio e quantidade total baseado nas transações"""
    transacoes = TransacaoAtivo.query.filter_by(ativo_id=ativo.id)\
        .order_by(TransacaoAtivo.data_operacao).all()

    quantidade_total = Decimal('0')
    valor_total_investido = Decimal('0')

    for t in transacoes:
        if t.tipo == 'compra':
            quantidade_total += t.quantidade
            valor_total_investido += t.valor_total()
        elif t.tipo == 'venda':
            # Calcular preço médio atual antes da venda
            pm_atual = valor_total_investido / quantidade_total if quantidade_total > 0 else Decimal('0')

            # Subtrair quantidade vendida
            quantidade_total -= t.quantidade

            # Subtrair valor proporcional
            valor_total_investido -= (t.quantidade * pm_atual)

    ativo.quantidade = quantidade_total
    if quantidade_total > 0:
        ativo.preco_medio = valor_total_investido / quantidade_total
    else:
        ativo.preco_medio = Decimal('0')
