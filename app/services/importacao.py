"""
Importação de extratos bancários e faturas de cartão.

Usado pela tela de Conciliação e pelo comando `flask importar-extrato`, para
que os dois caminhos tenham exatamente a mesma regra:

1. analisar_extrato()   -> lê o arquivo, descarta o que já foi importado,
                           casa com transações existentes e sugere categoria.
2. aplicar_conciliacao() -> grava: concilia, importa (atualizando saldo da conta
                           ou a fatura do cartão) ou ignora cada linha.
3. desfazer_conciliacao() -> remove o que a importação criou e devolve o saldo.
"""
import hashlib
from collections import Counter
from datetime import date, datetime
from decimal import Decimal

from app.matching import SugestorCategoria, normalizar_descricao, processar_matching
from app.models import (db, CartaoCredito, Categoria, ConciliacaoBancaria, Conta, Fatura,
                        ItemConciliacao, Transacao)
from app.parsers import ExtratoInvalido, detect_format, detectar_parcela, eh_pagamento_fatura, parse_file

EXTENSOES_PERMITIDAS = {'ofx', 'pdf', 'csv', 'txt'}
TAMANHO_MAXIMO = 16 * 1024 * 1024
MAX_LINHAS = 5000
ACOES = ('conciliar', 'importar', 'ignorar')


class ErroImportacao(ValueError):
    """Erro de negócio com mensagem pronta para o usuário."""


# ---------------------------------------------------------------- auxiliares

def hash_conteudo(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _assinatura(data_, valor, tipo, descricao):
    return f"{data_.isoformat()}|{Decimal(valor):.2f}|{tipo}|{normalizar_descricao(descricao)}"


def _id_externo(item, assinatura, ocorrencia):
    if item.get('numero_documento'):
        base = f"F|{item['numero_documento']}|{item['data'].isoformat()}|{item['valor']:.2f}"
    else:
        base = f"H|{assinatura}|{ocorrencia}"
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:40]


def _categoria_padrao(user_id, tipo):
    nome = 'Outros' if tipo == 'despesa' else 'Outras Receitas'
    cat = Categoria.query.filter_by(user_id=user_id, tipo=tipo, nome=nome).first()
    if not cat:
        cat = Categoria(nome=nome, tipo=tipo, cor='#95a5a6', user_id=user_id)
        db.session.add(cat)
        db.session.flush()
    return cat


def _obter_ou_criar_fatura(cartao, data_referencia):
    from app.routes import obter_ou_criar_fatura  # import tardio: evita ciclo
    return obter_ou_criar_fatura(cartao, data_referencia)


def _conta_do_usuario(user_id, conta_id):
    if not conta_id:
        return None
    try:
        conta_id = int(conta_id)
    except (TypeError, ValueError):
        return None
    return Conta.query.filter_by(id=conta_id, user_id=user_id).first()


def _cartao_do_usuario(user_id, cartao_id):
    if not cartao_id:
        return None
    try:
        cartao_id = int(cartao_id)
    except (TypeError, ValueError):
        return None
    return CartaoCredito.query.filter_by(id=cartao_id, user_id=user_id).first()


def _definir_destino(user_id, resultado, conta_id, cartao_id):
    """Decide em qual conta/cartão o extrato será lançado."""
    cartao = _cartao_do_usuario(user_id, cartao_id)
    if cartao_id and not cartao:
        raise ErroImportacao('Cartão não encontrado.')
    conta = _conta_do_usuario(user_id, conta_id)
    if conta_id and not conta:
        raise ErroImportacao('Conta não encontrada.')

    acct = (resultado.get('account_info') or {}).get('account_id') or ''
    if resultado['tipo_extrato'] == 'cartao' and not cartao:
        finais = acct[-4:] if len(acct) >= 4 else None
        if finais:
            cartao = CartaoCredito.query.filter_by(user_id=user_id, numero_cartao=finais, ativo=True).first()
        if not cartao:
            raise ErroImportacao('Este arquivo é uma fatura de cartão. Selecione o cartão de crédito.')
    if not conta and acct and not cartao:
        conta = Conta.query.filter_by(user_id=user_id, id_banco=acct[:50]).first()
    if not conta and cartao:
        conta = Conta.query.filter_by(user_id=user_id, ativa=True).order_by(Conta.id).first()
    if not conta:
        raise ErroImportacao('Selecione a conta do extrato.')
    if acct and not cartao and not conta.id_banco:
        conta.id_banco = acct[:50]  # da próxima vez a conta é reconhecida sozinha
    return conta, cartao


def _ja_importadas(conta, cartao):
    """ids externos e assinaturas de transações que vieram de extratos anteriores."""
    q = db.session.query(Transacao.id_externo, Transacao.data, Transacao.valor, Transacao.tipo,
                         Transacao.descricao).filter(Transacao.id_externo.isnot(None))
    if cartao:
        q = q.filter(Transacao.cartao_credito_id == cartao.id)
    else:
        q = q.filter(Transacao.conta_id == conta.id,
                     db.or_(Transacao.forma_pagamento.is_(None), Transacao.forma_pagamento != 'cartao_credito'))
    ids, assinaturas = set(), Counter()
    for id_ext, data_, valor, tipo, descricao in q.all():
        ids.add(id_ext)
        assinaturas[_assinatura(data_, valor, tipo, descricao)] += 1
    if cartao:
        # pagamentos de fatura já baixados não viram transação: lembrar pelos itens
        pagos = (db.session.query(ItemConciliacao.id_externo)
                 .join(ConciliacaoBancaria, ItemConciliacao.conciliacao_id == ConciliacaoBancaria.id)
                 .filter(ConciliacaoBancaria.cartao_credito_id == cartao.id,
                         ItemConciliacao.status == 'pagamento', ItemConciliacao.id_externo.isnot(None)))
        ids.update(i for (i,) in pagos.all())
    return ids, assinaturas


# ---------------------------------------------------------------- 1. analisar

def analisar_extrato(user_id, conteudo, nome_arquivo, conta_id=None, cartao_id=None, titular=None):
    """
    Lê o extrato e cria uma ConciliacaoBancaria 'pendente_revisao' (flush, sem commit).
    Retorna (conciliacao, avisos).
    """
    nome_arquivo = (nome_arquivo or 'extrato')[:200]
    ext = nome_arquivo.rsplit('.', 1)[-1].lower() if '.' in nome_arquivo else ''
    if ext not in EXTENSOES_PERMITIDAS:
        raise ErroImportacao('Formato não aceito. Envie OFX, PDF ou CSV.')
    if not conteudo:
        raise ErroImportacao('Arquivo vazio.')
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ErroImportacao('Arquivo maior que 16 MB.')

    formato = detect_format(conteudo, nome_arquivo)
    try:
        resultado = parse_file(conteudo, formato, max_linhas=MAX_LINHAS, filename=nome_arquivo)
    except ExtratoInvalido as exc:
        raise ErroImportacao(str(exc)) from exc
    if resultado['total'] == 0:
        raise ErroImportacao(' '.join(resultado['avisos']) or 'Nenhum lançamento encontrado no arquivo.')

    conta, cartao = _definir_destino(user_id, resultado, conta_id, cartao_id)
    avisos = list(resultado['avisos'])
    hash_arq = hash_conteudo(conteudo)
    anterior = ConciliacaoBancaria.query.filter_by(user_id=user_id, hash_arquivo=hash_arq,
                                                   status='concluida').first()
    if anterior:
        avisos.append(f'Este arquivo já foi importado em {anterior.data_upload:%d/%m/%Y}; '
                      'os lançamentos repetidos foram marcados como "já importado".')

    # --- deduplicação contra importações anteriores
    ids_existentes, assinaturas_existentes = _ja_importadas(conta, cartao)
    ocorrencias = Counter()
    novos, todos = [], []
    for item in resultado['transactions']:
        assin = _assinatura(item['data'], item['valor'], item['tipo'], item['descricao'])
        ocorrencias[assin] += 1
        item = dict(item)
        item['id_externo'] = _id_externo(item, assin, ocorrencias[assin])
        duplicado = item['id_externo'] in ids_existentes
        if not duplicado and assinaturas_existentes[assin] > 0:
            assinaturas_existentes[assin] -= 1
            duplicado = True
        item['duplicado'] = duplicado
        todos.append(item)
        if not duplicado:
            novos.append(item)

    # processar_matching devolve cópias na mesma ordem da entrada
    if titular is None:
        from app.models import User
        titular = getattr(db.session.get(User, user_id), 'nome', None)
    processados_lista = processar_matching(novos, conta.id, user_id, cartao_id=cartao.id if cartao else None,
                                           titular=titular)
    mapa = {id(orig): proc for orig, proc in zip(novos, processados_lista)}

    conciliacao = ConciliacaoBancaria(
        user_id=user_id, conta_id=conta.id, cartao_credito_id=cartao.id if cartao else None,
        arquivo_nome=nome_arquivo, formato=resultado['formato'], hash_arquivo=hash_arq,
        saldo_extrato=resultado.get('saldo_final') if not cartao else None,
        status='processando', total_linhas=len(todos),
        data_inicio=resultado['date_range'][0], data_fim=resultado['date_range'][1],
    )
    db.session.add(conciliacao)
    db.session.flush()

    for item in todos:
        proc = mapa.get(id(item))
        parcela = detectar_parcela(item['descricao']) if cartao else None
        if item['duplicado']:
            acao, status, match, score, categoria = 'ignorar', 'duplicado', None, None, None
        else:
            match = proc['melhor_match']
            score = proc['score_matching']
            categoria = proc['categoria_sugerida']
            acao = proc['status_sugerido']
            status = 'pendente'
            if item.get('eh_pagamento_fatura') or item.get('eh_saldo_anterior'):
                # pagamento já sai no extrato da conta; "saldo em atraso" é a fatura anterior repetida
                acao = 'ignorar'
        db.session.add(ItemConciliacao(
            conciliacao_id=conciliacao.id, data=item['data'], descricao=item['descricao'],
            valor=item['valor'], tipo=item['tipo'], numero_documento=item.get('numero_documento'),
            saldo_apos=item.get('saldo_apos'), id_externo=item['id_externo'],
            numero_parcela=parcela[0] if parcela else None,
            total_parcelas=parcela[1] if parcela else None,
            status=status, acao_sugerida=acao,
            transacao_id=match[0].id if match else None,
            categoria_sugerida_id=categoria.id if categoria else None,
            score_matching=score,
        ))
    conciliacao.status = 'pendente_revisao'
    db.session.flush()
    return conciliacao, avisos


# ---------------------------------------------------------------- 2. aplicar

def _aplicar_saldo(conta, tipo, valor, sinal=1):
    delta = Decimal(valor) * sinal
    if tipo == 'receita':
        conta.saldo_atual = (conta.saldo_atual or 0) + delta
    else:
        conta.saldo_atual = (conta.saldo_atual or 0) - delta


def aplicar_conciliacao(conciliacao, decisoes=None):
    """
    decisoes: {item_id: {'acao': 'conciliar'|'importar'|'ignorar',
                         'transacao_id': int|None, 'categoria_id': int|None}}
    Itens sem decisão usam a ação sugerida. Faz commit. Retorna o resumo().
    """
    if conciliacao.status == 'concluida':
        raise ErroImportacao('Esta conciliação já foi processada.')
    decisoes = decisoes or {}
    user_id = conciliacao.user_id
    conta = conciliacao.conta
    cartao = conciliacao.cartao
    sugestor = SugestorCategoria(user_id, historico=0)
    hoje = date.today()

    def _eh_pagamento(item):
        return bool(cartao) and item.tipo == 'receita' and eh_pagamento_fatura(item.descricao)

    # compras/estornos primeiro, pagamentos de fatura por último (as faturas já existem)
    itens = sorted(conciliacao.itens, key=lambda i: (_eh_pagamento(i), i.data, i.id))
    try:
        conciliadas = importadas = 0
        for item in itens:
            if item.status not in ('pendente', 'duplicado'):
                continue
            decisao = decisoes.get(item.id, {})
            acao = decisao.get('acao') or item.acao_sugerida or 'ignorar'
            if acao not in ACOES:
                acao = 'ignorar'
            if item.status == 'duplicado' and not decisao.get('acao'):
                acao = 'ignorar'  # duplicado só entra se o usuário pedir explicitamente

            if acao == 'ignorar' and item.status == 'pendente' and _eh_pagamento(item):
                # Pagamento da fatura: a saída já vem no extrato da conta; aqui só
                # libera o limite e dá baixa nas faturas em aberto (mais antigas primeiro).
                _baixar_faturas(cartao, item.valor, item.data)
                item.status = 'pagamento'
                continue

            if acao == 'conciliar':
                alvo_id = decisao.get('transacao_id') or item.transacao_id
                alvo = None
                if alvo_id:
                    alvo = (Transacao.query.join(Conta, Transacao.conta_id == Conta.id)
                            .filter(Transacao.id == int(alvo_id), Conta.user_id == user_id).first())
                if not alvo:
                    acao = 'importar'  # sem transação válida para conciliar
                else:
                    item.transacao_id = alvo.id
                    item.status = 'conciliado'
                    if not alvo.id_externo:
                        alvo.id_externo = item.id_externo
                    if not alvo.pago and alvo.pode_marcar_pago():
                        alvo.pago = True  # o banco confirmou o lançamento
                        if alvo.data <= hoje:
                            _aplicar_saldo(alvo.conta, alvo.tipo, alvo.valor)
                    conciliadas += 1
                    continue

            if acao == 'importar':
                categoria = None
                if decisao.get('categoria_id'):
                    categoria = Categoria.query.filter_by(id=int(decisao['categoria_id']), user_id=user_id).first()
                if not categoria and item.categoria_sugerida_id:
                    categoria = db.session.get(Categoria, item.categoria_sugerida_id)
                if not categoria or categoria.user_id != user_id or categoria.tipo != item.tipo:
                    categoria = sugestor.sugerir(item.descricao, item.tipo) or _categoria_padrao(user_id, item.tipo)

                nova = Transacao(
                    descricao=item.descricao[:200], valor=item.valor, tipo=item.tipo, data=item.data,
                    conta_id=conta.id, categoria_id=categoria.id, id_externo=item.id_externo,
                    conciliacao_origem_id=conciliacao.id,
                )
                if cartao:
                    fatura = _obter_ou_criar_fatura(cartao, item.data)
                    nova.forma_pagamento = 'cartao_credito'
                    nova.cartao_credito_id = cartao.id
                    nova.fatura_id = fatura.id
                    nova.pago = False
                    if item.total_parcelas:
                        nova.parcelado = True
                        nova.numero_parcela = item.numero_parcela
                        nova.total_parcelas = item.total_parcelas
                    sinal = 1 if item.tipo == 'despesa' else -1  # estorno reduz a fatura
                    fatura.valor_total = (fatura.valor_total or 0) + sinal * item.valor
                    cartao.limite_utilizado = max(Decimal('0'), (cartao.limite_utilizado or 0) + sinal * item.valor)
                else:
                    nova.forma_pagamento = 'dinheiro'
                    nova.pago = True  # se está no extrato, já aconteceu
                    if item.data <= hoje:
                        _aplicar_saldo(conta, item.tipo, item.valor)
                db.session.add(nova)
                db.session.flush()
                sugestor.aprender(item.descricao, item.tipo, categoria.id)
                item.transacao_id = nova.id
                item.categoria_sugerida_id = categoria.id
                item.status = 'importado'
                importadas += 1
                continue

            if item.status != 'duplicado':
                item.status = 'ignorado'

        conciliacao.linhas_conciliadas = conciliadas
        conciliacao.linhas_importadas = importadas
        conciliacao.status = 'concluida'
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return resumo(conciliacao)


def _baixar_faturas(cartao, valor, data_pagamento):
    from datetime import timedelta
    cartao.limite_utilizado = max(Decimal('0'), (cartao.limite_utilizado or 0) - valor)
    restante = Decimal(valor)
    abertas = (Fatura.query.filter(Fatura.cartao_id == cartao.id, Fatura.status != 'paga',
                                   Fatura.data_vencimento <= data_pagamento + timedelta(days=10))
               .order_by(Fatura.ano_referencia, Fatura.mes_referencia).all())
    for fatura in abertas:
        if restante <= 0:
            break
        devido = Decimal(fatura.valor_total or 0) - Decimal(fatura.valor_pago or 0)
        if devido <= 0:
            fatura.status = 'paga'
            continue
        pago = min(devido, restante)
        fatura.valor_pago = Decimal(fatura.valor_pago or 0) + pago
        restante -= pago
        if fatura.valor_pago >= Decimal(fatura.valor_total or 0) - Decimal('0.01'):
            fatura.status = 'paga'


def _estornar_baixa(cartao, valor):
    cartao.limite_utilizado = Decimal(cartao.limite_utilizado or 0) + valor
    restante = Decimal(valor)
    pagas = (Fatura.query.filter(Fatura.cartao_id == cartao.id, Fatura.valor_pago > 0)
             .order_by(Fatura.ano_referencia.desc(), Fatura.mes_referencia.desc()).all())
    for fatura in pagas:
        if restante <= 0:
            break
        tirar = min(Decimal(fatura.valor_pago), restante)
        fatura.valor_pago = Decimal(fatura.valor_pago) - tirar
        restante -= tirar
        if fatura.valor_pago < Decimal(fatura.valor_total or 0):
            fatura.status = 'aberta'


# ---------------------------------------------------------------- 3. desfazer

def desfazer_conciliacao(conciliacao):
    """Remove as transações criadas por esta importação e devolve saldo/fatura. Faz commit."""
    removidas = 0
    try:
        if conciliacao.cartao:
            for item in conciliacao.itens:
                if item.status == 'pagamento':
                    _estornar_baixa(conciliacao.cartao, item.valor)
        criadas = Transacao.query.filter_by(conciliacao_origem_id=conciliacao.id).all()
        for t in criadas:
            if t.forma_pagamento == 'cartao_credito':
                sinal = 1 if t.tipo == 'despesa' else -1
                if t.fatura_id:
                    fatura = db.session.get(Fatura, t.fatura_id)
                    if fatura:
                        fatura.valor_total = (fatura.valor_total or 0) - sinal * t.valor
                if t.cartao_credito_id:
                    c = db.session.get(CartaoCredito, t.cartao_credito_id)
                    if c:
                        c.limite_utilizado = max(Decimal('0'), (c.limite_utilizado or 0) - sinal * t.valor)
            elif t.pago and t.data <= date.today():
                _aplicar_saldo(t.conta, t.tipo, t.valor, sinal=-1)
            for item in t.itens_conciliacao:
                item.transacao_id = None
            db.session.delete(t)
            removidas += 1
        db.session.delete(conciliacao)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return removidas


# ---------------------------------------------------------------- resumo

def resumo(conciliacao):
    itens = conciliacao.itens
    contagem = Counter(i.status for i in itens)
    sugeridas = Counter(i.acao_sugerida for i in itens if i.status == 'pendente')
    total_novo = sum((i.valor if i.tipo == 'receita' else -i.valor)
                     for i in itens if i.status == 'pendente' and i.acao_sugerida == 'importar')
    diferenca = None
    if conciliacao.saldo_extrato is not None and not conciliacao.cartao_credito_id:
        diferenca = Decimal(conciliacao.conta.saldo_atual or 0) - Decimal(conciliacao.saldo_extrato)
    return {
        'id': conciliacao.id,
        'arquivo': conciliacao.arquivo_nome,
        'formato': conciliacao.formato,
        'destino': (f'Cartão {conciliacao.cartao.nome}' if conciliacao.cartao_credito_id
                    else f'Conta {conciliacao.conta.nome}'),
        'periodo': (conciliacao.data_inicio, conciliacao.data_fim),
        'status': conciliacao.status,
        'total': len(itens),
        'por_status': dict(contagem),
        'sugestoes': dict(sugeridas),
        'impacto_sugerido': total_novo,
        'saldo_sistema': conciliacao.conta.saldo_atual,
        'saldo_banco': conciliacao.saldo_extrato,
        'diferenca_saldo': diferenca,
    }
