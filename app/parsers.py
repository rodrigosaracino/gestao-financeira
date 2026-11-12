"""
Leitura de extratos bancários: OFX (conta corrente e cartão), PDF e CSV.

Todos os leitores devolvem o mesmo formato:

    {
        'formato': 'OFX' | 'PDF' | 'CSV',
        'tipo_extrato': 'conta' | 'cartao',
        'account_info': {'account_id': str|None, 'bank_id': str|None},
        'saldo_final': Decimal|None,       # saldo informado pelo banco (LEDGERBAL)
        'data_saldo': date|None,
        'transactions': [ {data, descricao, valor (>0), tipo ('receita'|'despesa'),
                           numero_documento, saldo_apos, eh_pagamento_fatura} ],
        'date_range': (date|None, date|None),
        'total': int,
        'avisos': [str],
    }

Convenção de sinal: valor negativo no extrato = saída (despesa / compra no cartão);
positivo = entrada (receita / estorno ou pagamento no cartão).
"""
import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_LINHAS_PADRAO = 5000


class ExtratoInvalido(ValueError):
    """Arquivo não pôde ser lido como extrato."""


# ---------------------------------------------------------------- utilidades

def _decodificar(conteudo):
    if isinstance(conteudo, str):
        return conteudo
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode('latin-1', errors='replace')


def _sem_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto or '') if not unicodedata.combining(c))


def parse_valor_br(texto):
    """
    Converte valores como '1.234,56', '-1234.56', 'R$ 12,30 D', '45,00-' em Decimal (com sinal).
    """
    if texto is None:
        raise InvalidOperation('vazio')
    s = str(texto).strip().upper().replace('R$', '').replace(' ', '').replace('\xa0', '')
    negativo = False
    if s.endswith('D') or s.endswith('-'):
        negativo = True
        s = s[:-1]
    elif s.endswith('C') or s.endswith('+'):
        s = s[:-1]
    if s.startswith('-'):
        negativo = not negativo if s.count('-') == 1 else True
        s = s.lstrip('-')
    elif s.startswith('+'):
        s = s[1:]
    if s.startswith('(') and s.endswith(')'):
        negativo, s = True, s[1:-1]
    if ',' in s and '.' in s:
        # o último separador é o decimal
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    valor = Decimal(s)
    return -valor if negativo else valor


def detectar_parcela(descricao):
    """Retorna (numero, total) se a descrição indicar parcela, ex.: 'LOJA PARC 02/10'."""
    d = _sem_acentos(descricao or '').upper()
    m = re.search(r'PARC(?:ELA)?\.?\s*(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})', d)
    if not m:
        m = re.search(r'(?:^|\s)(\d{1,2})\s*/\s*(\d{1,2})\s*$', d)
    if m:
        n, total = int(m.group(1)), int(m.group(2))
        if 1 <= n <= total <= 72 and total >= 2:
            return n, total
    return None


_PAGAMENTO_FATURA = re.compile(
    r'PAGAMENTO\s+(EFETUADO|RECEBIDO|DE\s+FATURA|FATURA|ONLINE|CARTAO|OBRIGADO)|PGTO\s+(FATURA|DEBITO)|'
    r'PAGTO\s+(FATURA|DEBITO)|PAGAMENTO\s*-\s*OBRIGADO', re.I)


def eh_pagamento_fatura(descricao):
    return bool(_PAGAMENTO_FATURA.search(_sem_acentos(descricao or '')))


def _resultado(formato, tipo_extrato, transacoes, account_info=None, saldo=None, data_saldo=None, avisos=None):
    datas = [t['data'] for t in transacoes]
    return {
        'formato': formato,
        'tipo_extrato': tipo_extrato,
        'account_info': account_info or {'account_id': None, 'bank_id': None},
        'saldo_final': saldo,
        'data_saldo': data_saldo,
        'transactions': transacoes,
        'date_range': (min(datas), max(datas)) if datas else (None, None),
        'total': len(transacoes),
        'avisos': avisos or [],
    }


def _transacao(data_, descricao, valor_com_sinal, tipo_extrato, numero_documento=None, saldo_apos=None):
    descricao = re.sub(r'\s+', ' ', (descricao or '').strip())[:500] or 'Sem descrição'
    return {
        'data': data_,
        'descricao': descricao,
        'valor': abs(valor_com_sinal),
        'tipo': 'receita' if valor_com_sinal > 0 else 'despesa',
        'numero_documento': (numero_documento or None) and str(numero_documento)[:100],
        'saldo_apos': saldo_apos,
        'eh_pagamento_fatura': tipo_extrato == 'cartao' and valor_com_sinal > 0 and eh_pagamento_fatura(descricao),
    }


# ---------------------------------------------------------------- OFX

def _ofx_data(texto):
    m = re.match(r'\s*(\d{4})(\d{2})(\d{2})', texto or '')
    if not m:
        raise ValueError(f'data inválida: {texto!r}')
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _ofx_tag(bloco, tag):
    m = re.search(r'<' + tag + r'>\s*([^<\r\n]*)', bloco, re.I)
    return m.group(1).strip() if m else None


def parse_ofx(file_content, max_linhas=MAX_LINHAS_PADRAO):
    """
    Lê OFX 1.x (SGML, comum nos bancos brasileiros) e 2.x (XML).
    Reconhece extrato de conta (BANKMSGSRSV1) e de cartão (CREDITCARDMSGSRSV1).
    """
    texto = _decodificar(file_content)
    if '<OFX' not in texto.upper():
        raise ExtratoInvalido('Arquivo não parece ser OFX.')

    eh_cartao = bool(re.search(r'<CREDITCARDMSGSRSV1>|<CCSTMTRS>', texto, re.I))
    tipo_extrato = 'cartao' if eh_cartao else 'conta'

    blocos = re.findall(r'<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)', texto, re.I | re.S)
    if len(blocos) > max_linhas:
        raise ExtratoInvalido(f'Extrato com mais de {max_linhas} lançamentos.')

    avisos = []
    transacoes = []
    for bloco in blocos:
        try:
            valor = parse_valor_br(_ofx_tag(bloco, 'TRNAMT'))
            data_ = _ofx_data(_ofx_tag(bloco, 'DTPOSTED') or _ofx_tag(bloco, 'DTUSER'))
        except (InvalidOperation, ValueError, TypeError):
            avisos.append('Um lançamento com data ou valor inválido foi ignorado.')
            continue
        if valor == 0:
            continue
        memo = _ofx_tag(bloco, 'MEMO')
        nome = _ofx_tag(bloco, 'NAME') or _ofx_tag(bloco, 'PAYEE')
        descricao = memo if memo and (not nome or len(memo) >= len(nome)) else (nome or memo)
        transacoes.append(_transacao(
            data_, descricao, valor, tipo_extrato,
            numero_documento=_ofx_tag(bloco, 'FITID') or _ofx_tag(bloco, 'CHECKNUM'),
        ))

    saldo = data_saldo = None
    ledger = re.search(r'<LEDGERBAL>(.*?)(?=</LEDGERBAL>|<AVAILBAL>|</STMTRS>|</CCSTMTRS>|$)', texto, re.I | re.S)
    if ledger:
        try:
            saldo = parse_valor_br(_ofx_tag(ledger.group(1), 'BALAMT'))
            data_saldo = _ofx_data(_ofx_tag(ledger.group(1), 'DTASOF'))
        except (InvalidOperation, ValueError, TypeError):
            pass

    if len(re.findall(r'<ACCTID>', texto, re.I)) > 1:
        avisos.append('O arquivo tem mais de uma conta; todos os lançamentos foram lidos juntos.')

    info = {'account_id': _ofx_tag(texto, 'ACCTID'), 'bank_id': _ofx_tag(texto, 'BANKID')}
    return _resultado('OFX', tipo_extrato, transacoes, info, saldo, data_saldo, avisos)


# ---------------------------------------------------------------- PDF

_DATA_PDF = r'(\d{2})[/.-](\d{2})(?:[/.-](\d{2,4}))?'
_VALOR_PDF = r'(-?\s?(?:R\$\s?)?-?\s?\d{1,3}(?:\.\d{3})*,\d{2}\s?(?:-|D|C)?)'
_LINHA_PDF = re.compile(r'^\s*' + _DATA_PDF + r'\s+(.+?)\s+' + _VALOR_PDF + r'(?:\s+' + _VALOR_PDF + r')?\s*$')
_MESES = {'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6, 'JUL': 7, 'AGO': 8,
          'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12}
_LINHA_PDF_MES = re.compile(r'^\s*(\d{2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(.+?)\s+'
                            + _VALOR_PDF + r'\s*$', re.I)
_IGNORAR_PDF = re.compile(r'\bSALDO\b|\bTOTAL\b|SUBTOTAL|LIMITE|ENCARGOS\s+PARA|VALOR\s+MINIMO|'
                          r'PAGAMENTO\s+MINIMO|TAXA\s+DE\s+JUROS|\bCET\b|IOF\s+PARA', re.I)


def _texto_pdf(file_content, max_paginas=60):
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ExtratoInvalido('Leitura de PDF indisponível (pdfplumber não instalado).') from exc
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            if len(pdf.pages) > max_paginas:
                raise ExtratoInvalido(f'PDF com mais de {max_paginas} páginas.')
            return '\n'.join((p.extract_text() or '') for p in pdf.pages)
    except ExtratoInvalido:
        raise
    except Exception as exc:
        raise ExtratoInvalido('Não foi possível ler o PDF (protegido por senha ou corrompido?).') from exc


def parse_pdf_texto(texto, max_linhas=MAX_LINHAS_PADRAO, hoje=None):
    """
    Extrator genérico de PDF: procura linhas "DD/MM[/AAAA] descrição valor [saldo]".
    Funciona com a maioria dos extratos e faturas com texto (não escaneados).
    """
    hoje = hoje or date.today()
    normalizado = _sem_acentos(texto).upper()
    eh_cartao = 'FATURA' in normalizado and ('CARTAO' in normalizado or 'VENCIMENTO' in normalizado)
    tipo_extrato = 'cartao' if eh_cartao else 'conta'

    # ano de referência: data completa mais recente que aparecer no documento
    anos = [(int(a) if len(a) == 4 else 2000 + int(a), int(m)) for _, m, a in
            re.findall(r'\b(\d{2})/(\d{2})/(\d{4}|\d{2})\b', texto) if 1 <= int(m) <= 12]
    anos = [x for x in anos if 2000 <= x[0] <= hoje.year + 1]
    ano_ref, mes_ref = max(anos) if anos else (hoje.year, hoje.month)

    transacoes, avisos = [], []
    for linha in texto.splitlines():
        if len(transacoes) >= max_linhas:
            raise ExtratoInvalido(f'Extrato com mais de {max_linhas} lançamentos.')
        bruta = linha.strip()
        if not bruta or _IGNORAR_PDF.search(_sem_acentos(bruta)):
            continue
        m = _LINHA_PDF.match(bruta)
        saldo_apos = None
        if m:
            dia, mes, ano, descricao, valor_txt, saldo_txt = m.groups()
            dia, mes = int(dia), int(mes)
            if ano:
                ano = int(ano) if len(ano) == 4 else 2000 + int(ano)
            if saldo_txt:
                try:
                    saldo_apos = parse_valor_br(saldo_txt)
                except InvalidOperation:
                    saldo_apos = None
        else:
            m = _LINHA_PDF_MES.match(_sem_acentos(bruta))
            if not m:
                continue
            dia, mes_txt, descricao, valor_txt = m.groups()
            dia, mes, ano = int(dia), _MESES[mes_txt.upper()], None
        if not ano:
            ano = ano_ref if mes <= mes_ref else ano_ref - 1  # fatura que cruza a virada do ano
        try:
            data_ = date(ano, mes, dia)
            valor = parse_valor_br(valor_txt)
        except (ValueError, InvalidOperation):
            continue
        if valor == 0:
            continue
        if eh_cartao:
            # Na fatura, compras aparecem positivas e créditos negativos: inverter para a convenção.
            valor = -valor
        transacoes.append(_transacao(data_, descricao, valor, tipo_extrato, saldo_apos=saldo_apos))

    if not transacoes:
        avisos.append('Nenhum lançamento reconhecido no PDF. Se possível, use o arquivo OFX do banco.')
    return _resultado('PDF', tipo_extrato, transacoes, avisos=avisos)


def parse_pdf(file_content, max_linhas=MAX_LINHAS_PADRAO):
    return parse_pdf_texto(_texto_pdf(file_content), max_linhas=max_linhas)


# ---------------------------------------------------------------- CSV

def _achar_coluna(cabecalho, *opcoes):
    norm = [_sem_acentos(c).strip().lower() for c in cabecalho]
    for opcao in opcoes:
        for i, c in enumerate(norm):
            if opcao in c:
                return i
    return None


def _data_csv(texto):
    texto = (texto or '').strip()[:10]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise ValueError(texto)


def parse_csv(file_content, config=None, max_linhas=MAX_LINHAS_PADRAO):
    """CSV com cabeçalho: data; descrição/histórico; valor (ou crédito/débito)."""
    texto = _decodificar(file_content)
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=';,\t|')
    except csv.Error:
        dialeto = csv.excel
        dialeto.delimiter = ';' if texto.count(';') > texto.count(',') else ','
    linhas = list(csv.reader(io.StringIO(texto), dialeto))
    if len(linhas) > max_linhas + 1:
        raise ExtratoInvalido(f'Extrato com mais de {max_linhas} lançamentos.')
    # cabeçalho = primeira linha que tenha uma coluna de data
    inicio = next((i for i, l in enumerate(linhas[:20]) if _achar_coluna(l, 'data') is not None), None)
    if inicio is None:
        raise ExtratoInvalido('CSV sem coluna "data".')
    cab = linhas[inicio]
    i_data = _achar_coluna(cab, 'data')
    i_desc = _achar_coluna(cab, 'descri', 'historico', 'lancamento', 'estabelecimento', 'titulo', 'memo')
    i_valor = _achar_coluna(cab, 'valor', 'amount', 'quantia')
    i_cred = _achar_coluna(cab, 'credito', 'entrada')
    i_deb = _achar_coluna(cab, 'debito', 'saida')
    if i_valor is None and i_cred is None and i_deb is None:
        raise ExtratoInvalido('CSV sem coluna de valor.')

    transacoes = []
    for linha in linhas[inicio + 1:]:
        if not linha or len(linha) <= i_data:
            continue
        try:
            data_ = _data_csv(linha[i_data])
            if i_valor is not None and i_valor < len(linha) and linha[i_valor].strip():
                valor = parse_valor_br(linha[i_valor])
            else:
                cred = linha[i_cred].strip() if i_cred is not None and i_cred < len(linha) else ''
                deb = linha[i_deb].strip() if i_deb is not None and i_deb < len(linha) else ''
                valor = parse_valor_br(cred) if cred else -abs(parse_valor_br(deb))
        except (ValueError, InvalidOperation, IndexError):
            continue
        if valor == 0:
            continue
        descricao = linha[i_desc] if i_desc is not None and i_desc < len(linha) else ''
        if 'SALDO' in _sem_acentos(descricao).upper():
            continue
        transacoes.append(_transacao(data_, descricao, valor, 'conta'))
    return _resultado('CSV', 'conta', transacoes)


# ---------------------------------------------------------------- despacho

def detect_format(file_content, filename=None):
    """Detecta OFX, PDF ou CSV pelo conteúdo (e extensão como desempate)."""
    cabeca = file_content[:2048] if isinstance(file_content, (bytes, bytearray)) else file_content[:2048].encode()
    if cabeca.startswith(b'%PDF'):
        return 'PDF'
    texto = cabeca.decode('latin-1').upper()
    if 'OFXHEADER' in texto or '<OFX' in texto:
        return 'OFX'
    ext = (filename or '').rsplit('.', 1)[-1].lower() if filename and '.' in filename else ''
    if ext in ('csv', 'txt') or ';' in texto or ',' in texto:
        return 'CSV'
    return 'UNKNOWN'


def parse_file(file_content, file_format=None, csv_config=None, max_linhas=MAX_LINHAS_PADRAO, filename=None):
    formato = file_format or detect_format(file_content, filename)
    if formato == 'OFX':
        return parse_ofx(file_content, max_linhas=max_linhas)
    if formato == 'PDF':
        return parse_pdf(file_content, max_linhas=max_linhas)
    if formato == 'CSV':
        return parse_csv(file_content, csv_config, max_linhas=max_linhas)
    raise ExtratoInvalido('Formato não suportado. Use OFX, PDF ou CSV.')
