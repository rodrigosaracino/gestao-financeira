"""
Casamento (matching) de lançamentos do extrato com transações já cadastradas
e sugestão automática de categoria.

Tudo é calculado com as transações carregadas UMA vez por extrato (sem uma
consulta por linha), para que arquivos grandes não travem o servidor.
"""
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from rapidfuzz import fuzz, process

from app.models import db, Transacao, Conta, Categoria, ItemConciliacao

JANELA_DIAS = 7
SCORE_MINIMO = 60
SCORE_CONCILIAR = 85


def normalizar_descricao(texto):
    """'PIX ENVIADO 12/03 Padaria São João' -> 'PADARIA SAO JOAO' (para comparar)."""
    t = ''.join(c for c in unicodedata.normalize('NFKD', texto or '') if not unicodedata.combining(c)).upper()
    t = re.sub(r'\d{1,2}/\d{1,2}(/\d{2,4})?', ' ', t)  # datas
    t = re.sub(r'\bPARC(ELA)?\.?\s*\d+\s*(/|DE)\s*\d+', ' ', t)
    t = re.sub(r'\b(PIX|TED|DOC|TEF|ENVIADO|RECEBIDO|TRANSF(ERENCIA)?|COMPRA|CARTAO|DEBITO|CREDITO|'
               r'PAGAMENTO|PAG|PGTO|BOLETO|ELO|VISA|MASTERCARD|MAESTRO|APLICACAO|NO|EM|DE|DA|DO)\b', ' ', t)
    t = re.sub(r'[^A-Z ]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def calcular_score_matching(item_extrato, transacao):
    """Score 0-100: valor (50), data (30), descrição (20)."""
    valor_item = Decimal(str(item_extrato['valor']))
    valor_trans = Decimal(str(transacao.valor or 0))
    if valor_trans <= 0:
        return 0
    diferenca = abs(valor_item - valor_trans)
    if diferenca < Decimal('0.01'):
        score = 50
    else:
        score = max(0.0, 50 - float(diferenca / valor_trans) * 200)  # 25% de diferença zera

    dias = abs((item_extrato['data'] - transacao.data).days)
    score += {0: 30, 1: 25, 2: 20, 3: 20}.get(dias, 10 if dias <= JANELA_DIAS else 0)

    score += fuzz.token_set_ratio(normalizar_descricao(item_extrato['descricao']),
                                  normalizar_descricao(transacao.descricao)) / 100 * 20
    return int(min(score, 100))


def _candidatas(user_id, conta_id, cartao_id, data_min, data_max):
    """Transações do período ainda não vinculadas a um item já processado."""
    ja_vinculadas = db.session.query(ItemConciliacao.transacao_id).filter(
        ItemConciliacao.transacao_id.isnot(None),
        ItemConciliacao.status.in_(('conciliado', 'importado')),
    )
    q = Transacao.query.join(Conta, Transacao.conta_id == Conta.id).filter(
        Conta.user_id == user_id,
        Transacao.data >= data_min - timedelta(days=JANELA_DIAS),
        Transacao.data <= data_max + timedelta(days=JANELA_DIAS),
        ~Transacao.id.in_(ja_vinculadas),
    )
    if cartao_id:
        q = q.filter(Transacao.cartao_credito_id == cartao_id)
    else:
        q = q.filter(Transacao.conta_id == conta_id, Transacao.forma_pagamento != 'cartao_credito')
    return q.all()


class SugestorCategoria:
    """
    Sugere categoria a partir do histórico do usuário (aprende com cada importação)
    e, se não houver histórico parecido, por palavras-chave comuns no Brasil.
    """

    PALAVRAS_CHAVE = [
        (r'UBER|99 ?(APP|POP|TAXI)|CABIFY|METRO|ONIBUS|BILHETE UNICO|ESTACIONAMENTO|SEM PARAR|CONECTCAR|PEDAGIO', 'Transporte'),
        (r'POSTO|SHELL|IPIRANGA|PETROBRAS|\bBR\b|COMBUSTIVEL|GASOLINA', 'Combustível'),
        (r'IFOOD|RAPPI|RESTAURANTE|LANCHONETE|PIZZA|BURGER|MC ?DONALDS|BK |OUTBACK|BAR |CAFE|PADARIA|PANIFICADORA', 'Restaurantes'),
        (r'MERCADO|SUPERMERC|CARREFOUR|ASSAI|ATACADAO|PAO DE ACUCAR|EXTRA |SAMS CLUB|HORTIFRUTI|ATACAD', 'Mercado'),
        (r'FARMACIA|DROGA|RAIA|PACHECO|PAGUE MENOS|DROGASIL|PANVEL', 'Farmácia'),
        (r'NETFLIX|SPOTIFY|DISNEY|HBO|MAX\b|PRIME VIDEO|AMAZON PRIME|DEEZER|YOUTUBE|GLOBOPLAY|APPLE\.COM|GOOGLE ', 'Streaming e Assinaturas'),
        (r'VIVO|CLARO|TIM\b|OI |NET |INTERNET|TELEFON', 'Internet e Telefone'),
        (r'ENEL|LIGHT|CEMIG|COPEL|SABESP|CEDAE|COMGAS|ENERGIA|AGUA|CONDOMINIO', 'Contas e Serviços'),
        (r'ALUGUEL|IMOBILIARIA', 'Moradia'),
        (r'SMART ?FIT|ACADEMIA|BLUEFIT|GYMPASS|WELLHUB', 'Academia e Esportes'),
        (r'ESCOLA|FACULDADE|CURSO|UDEMY|ALURA|LIVRARIA', 'Educação'),
        (r'HOSPITAL|CLINICA|LABORATORIO|UNIMED|AMIL|SULAMERICA|BRADESCO SAUDE|ODONTO', 'Saúde'),
        (r'IOF|TARIFA|ANUIDADE|JUROS|MULTA|IPVA|IPTU|DARF|IMPOSTO', 'Impostos e Taxas'),
        (r'SEGURO|PORTO SEGURO', 'Seguros'),
        (r'PET ?SHOP|PETZ|COBASI|VETERIN', 'Pets'),
        (r'HOTEL|AIRBNB|BOOKING|LATAM|GOL |AZUL |DECOLAR|CVC', 'Viagens'),
        (r'RENNER|C ?& ?A|RIACHUELO|ZARA|NIKE|CENTAURO|NETSHOES|SHEIN', 'Vestuário'),
    ]
    PALAVRAS_RECEITA = [
        (r'SALARIO|FOLHA|PROVENTOS|PAGTO SALARIO|REMUNERACAO', 'Salário'),
        (r'RENDIMENTO|DIVIDENDO|JCP|RESGATE', 'Investimentos'),
        (r'RESTITUICAO', 'Restituição de Impostos'),
    ]

    def __init__(self, user_id, historico=3000):
        self.user_id = user_id
        self.categorias = Categoria.query.filter_by(user_id=user_id).all()
        self._por_nome = {(c.tipo, self._chave_nome(c.nome)): c for c in self.categorias}
        self._por_id = {c.id: c for c in self.categorias}
        self.memoria = {'receita': {}, 'despesa': {}}
        recentes = (db.session.query(Transacao.descricao, Transacao.tipo, Transacao.categoria_id)
                    .join(Conta, Transacao.conta_id == Conta.id)
                    .filter(Conta.user_id == user_id)
                    .order_by(Transacao.data.desc(), Transacao.id.desc())
                    .limit(historico).all())
        for descricao, tipo, categoria_id in recentes:
            chave = normalizar_descricao(descricao)
            if chave and tipo in self.memoria and categoria_id in self._por_id:
                self.memoria[tipo].setdefault(chave, categoria_id)  # o mais recente vence

    @staticmethod
    def _chave_nome(nome):
        return ''.join(c for c in unicodedata.normalize('NFKD', nome or '') if not unicodedata.combining(c)).lower()

    def categoria_por_nome(self, nome, tipo):
        return self._por_nome.get((tipo, self._chave_nome(nome)))

    def sugerir(self, descricao, tipo):
        chave = normalizar_descricao(descricao)
        memoria = self.memoria.get(tipo, {})
        if chave and chave in memoria:
            return self._por_id[memoria[chave]]
        if chave and memoria:
            melhor = process.extractOne(chave, memoria.keys(), scorer=fuzz.token_set_ratio, score_cutoff=85)
            if melhor:
                return self._por_id[memoria[melhor[0]]]
        texto = ' ' + chave + ' ' + (descricao or '').upper() + ' '
        regras = self.PALAVRAS_RECEITA if tipo == 'receita' else self.PALAVRAS_CHAVE
        for padrao, nome in regras:
            if re.search(padrao, texto):
                cat = self.categoria_por_nome(nome, tipo)
                if cat:
                    return cat
        return None

    def aprender(self, descricao, tipo, categoria_id):
        chave = normalizar_descricao(descricao)
        if chave and tipo in self.memoria:
            self.memoria[tipo][chave] = categoria_id


def processar_matching(itens_extrato, conta_id, user_id, cartao_id=None):
    """
    Para cada item do extrato devolve uma cópia com:
      melhor_match (transacao, score) | None, matches (top 5), score_matching,
      categoria_sugerida, status_sugerido ('conciliar' | 'importar').
    Uma mesma transação nunca é sugerida para duas linhas do mesmo extrato.
    """
    if not itens_extrato:
        return []
    datas = [i['data'] for i in itens_extrato]
    candidatas = _candidatas(user_id, conta_id, cartao_id, min(datas), max(datas))
    sugestor = SugestorCategoria(user_id)

    # pontua todos os pares e atribui do melhor para o pior (guloso), sem repetir transação
    pares = []
    por_item = {i: [] for i in range(len(itens_extrato))}
    for idx, item in enumerate(itens_extrato):
        for t in candidatas:
            if t.tipo != item['tipo']:
                continue
            if abs((t.data - item['data']).days) > JANELA_DIAS:
                continue
            score = calcular_score_matching(item, t)
            if score >= SCORE_MINIMO:
                pares.append((score, idx, t))
                por_item[idx].append((t, score))
    pares.sort(key=lambda p: (-p[0], p[1]))
    usadas, atribuido = set(), {}
    for score, idx, t in pares:
        if idx in atribuido or t.id in usadas:
            continue
        atribuido[idx] = (t, score)
        usadas.add(t.id)

    resultados = []
    for idx, item in enumerate(itens_extrato):
        proc = dict(item)
        melhor = atribuido.get(idx)
        proc['melhor_match'] = melhor
        proc['matches'] = [
            {'transacao_id': t.id, 'transacao': t, 'score': s, 'descricao': t.descricao,
             'data': t.data, 'valor': float(t.valor)}
            for t, s in sorted(por_item[idx], key=lambda x: -x[1])[:5]
        ]
        proc['score_matching'] = melhor[1] if melhor else 0
        proc['categoria_sugerida'] = sugestor.sugerir(item['descricao'], item['tipo'])
        proc['status_sugerido'] = 'conciliar' if melhor and melhor[1] >= SCORE_CONCILIAR else 'importar'
        resultados.append(proc)
    return resultados


def estatisticas_matching(itens_processados):
    total = len(itens_processados)
    forte = sum(1 for i in itens_processados if i['score_matching'] >= 90)
    medio = sum(1 for i in itens_processados if 70 <= i['score_matching'] < 90)
    sem = total - forte - medio
    pct = (lambda n: n / total * 100 if total else 0)
    return {
        'total': total, 'com_match_forte': forte, 'com_match_medio': medio, 'sem_match': sem,
        'percentual_match_forte': pct(forte), 'percentual_match_medio': pct(medio),
        'percentual_sem_match': pct(sem),
    }
