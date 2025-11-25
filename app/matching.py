"""
Módulo para matching inteligente de transações
"""
from datetime import timedelta
from decimal import Decimal
from fuzzywuzzy import fuzz
from app.models import Transacao, Categoria


def calcular_score_matching(item_extrato, transacao):
    """
    Calcula um score de matching entre um item do extrato e uma transação

    Args:
        item_extrato: dict com dados do item do extrato
        transacao: objeto Transacao do banco de dados

    Returns:
        int: score de 0 a 100
    """
    score = 0
    max_score = 100

    # 1. Comparação de valor (40 pontos)
    if abs(float(item_extrato['valor']) - float(transacao.valor)) < 0.01:
        score += 40
    else:
        # Penalizar proporcionalmente à diferença
        diferenca_percentual = abs(float(item_extrato['valor']) - float(transacao.valor)) / float(transacao.valor)
        score += max(0, 40 - (diferenca_percentual * 40))

    # 2. Comparação de data (30 pontos)
    diferenca_dias = abs((item_extrato['data'] - transacao.data).days)
    if diferenca_dias == 0:
        score += 30
    elif diferenca_dias <= 1:
        score += 25
    elif diferenca_dias <= 3:
        score += 20
    elif diferenca_dias <= 7:
        score += 10
    else:
        score += 0

    # 3. Comparação de descrição usando fuzzy matching (30 pontos)
    descricao_score = fuzz.token_sort_ratio(
        item_extrato['descricao'].lower(),
        transacao.descricao.lower()
    )
    score += (descricao_score / 100) * 30

    return int(min(score, max_score))


def encontrar_matches(item_extrato, conta_id, user_id, threshold=60):
    """
    Encontra possíveis matches para um item do extrato

    Args:
        item_extrato: dict com dados do item do extrato
        conta_id: ID da conta
        user_id: ID do usuário
        threshold: score mínimo para considerar match (padrão: 60)

    Returns:
        list: lista de tuplas (transacao, score) ordenada por score descendente
    """
    # Buscar transações em uma janela de ±7 dias
    data_inicio = item_extrato['data'] - timedelta(days=7)
    data_fim = item_extrato['data'] + timedelta(days=7)

    # Buscar transações não conciliadas na conta
    transacoes = Transacao.query.join(
        Transacao.conta
    ).filter(
        Transacao.conta_id == conta_id,
        Transacao.data >= data_inicio,
        Transacao.data <= data_fim,
        Transacao.tipo == item_extrato['tipo'],
        # Apenas transações que ainda não foram conciliadas
        ~Transacao.itens_conciliacao.any()
    ).all()

    # Calcular score para cada transação
    matches = []
    for transacao in transacoes:
        score = calcular_score_matching(item_extrato, transacao)
        if score >= threshold:
            matches.append((transacao, score))

    # Ordenar por score descendente
    matches.sort(key=lambda x: x[1], reverse=True)

    return matches


def sugerir_categoria(item_extrato, user_id):
    """
    Sugere uma categoria para um item do extrato baseado em transações anteriores

    Args:
        item_extrato: dict com dados do item do extrato
        user_id: ID do usuário

    Returns:
        Categoria ou None
    """
    # Buscar transações com descrição similar
    todas_transacoes = Transacao.query.join(
        Transacao.conta
    ).filter(
        Transacao.conta.has(user_id=user_id),
        Transacao.tipo == item_extrato['tipo']
    ).limit(1000).all()  # Limitar para performance

    # Calcular similaridade de descrição
    scores_categoria = {}

    for transacao in todas_transacoes:
        if not transacao.categoria_id:
            continue

        # Calcular similaridade
        similarity = fuzz.token_sort_ratio(
            item_extrato['descricao'].lower(),
            transacao.descricao.lower()
        )

        # Acumular score por categoria
        if transacao.categoria_id not in scores_categoria:
            scores_categoria[transacao.categoria_id] = {
                'score_total': 0,
                'count': 0,
                'categoria': transacao.categoria
            }

        scores_categoria[transacao.categoria_id]['score_total'] += similarity
        scores_categoria[transacao.categoria_id]['count'] += 1

    # Encontrar categoria com melhor score médio
    melhor_categoria = None
    melhor_score = 0

    for cat_id, data in scores_categoria.items():
        score_medio = data['score_total'] / data['count']
        if score_medio > melhor_score and score_medio >= 70:  # Threshold de 70%
            melhor_score = score_medio
            melhor_categoria = data['categoria']

    return melhor_categoria


def processar_matching(itens_extrato, conta_id, user_id):
    """
    Processa matching para todos os itens de um extrato

    Args:
        itens_extrato: lista de dicts com itens do extrato
        conta_id: ID da conta
        user_id: ID do usuário

    Returns:
        list: lista de dicts com itens processados incluindo matches e sugestões
    """
    resultados = []

    for item in itens_extrato:
        # Encontrar possíveis matches
        matches = encontrar_matches(item, conta_id, user_id)

        # Sugerir categoria
        categoria_sugerida = sugerir_categoria(item, user_id)

        # Adicionar informações ao item
        item_processado = item.copy()
        item_processado['matches'] = [
            {
                'transacao_id': transacao.id,
                'transacao': transacao,
                'score': score,
                'descricao': transacao.descricao,
                'data': transacao.data,
                'valor': float(transacao.valor)
            }
            for transacao, score in matches[:5]  # Top 5 matches
        ]

        item_processado['melhor_match'] = matches[0] if matches else None
        item_processado['categoria_sugerida'] = categoria_sugerida
        item_processado['score_matching'] = matches[0][1] if matches else 0

        # Definir status inicial
        if matches and matches[0][1] >= 90:
            item_processado['status_sugerido'] = 'conciliar'  # Match muito forte
        elif matches and matches[0][1] >= 70:
            item_processado['status_sugerido'] = 'revisar'  # Match razoável
        else:
            item_processado['status_sugerido'] = 'importar'  # Sem match, importar como novo

        resultados.append(item_processado)

    return resultados


def estatisticas_matching(itens_processados):
    """
    Gera estatísticas sobre o matching

    Args:
        itens_processados: lista de itens processados

    Returns:
        dict: estatísticas
    """
    total = len(itens_processados)
    com_match_forte = sum(1 for item in itens_processados if item['score_matching'] >= 90)
    com_match_medio = sum(1 for item in itens_processados if 70 <= item['score_matching'] < 90)
    sem_match = sum(1 for item in itens_processados if item['score_matching'] < 70)

    return {
        'total': total,
        'com_match_forte': com_match_forte,
        'com_match_medio': com_match_medio,
        'sem_match': sem_match,
        'percentual_match_forte': (com_match_forte / total * 100) if total > 0 else 0,
        'percentual_match_medio': (com_match_medio / total * 100) if total > 0 else 0,
        'percentual_sem_match': (sem_match / total * 100) if total > 0 else 0
    }
