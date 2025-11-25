"""
Módulo para parsear arquivos de extratos bancários (OFX, CSV)
"""
from datetime import datetime
from decimal import Decimal
import pandas as pd
import ofxparse
from io import StringIO, BytesIO


def parse_ofx(file_content):
    """
    Parseia arquivo OFX e retorna lista de transações

    Args:
        file_content: conteúdo do arquivo (bytes ou string)

    Returns:
        dict com:
            - transactions: lista de dicts com as transações
            - account_info: informações da conta
            - date_range: tuple com (data_inicio, data_fim)
    """
    try:
        # Se for bytes, converter para BytesIO
        if isinstance(file_content, bytes):
            file_obj = BytesIO(file_content)
        else:
            file_obj = StringIO(file_content)

        # Parsear OFX
        ofx = ofxparse.OfxParser.parse(file_obj)

        transactions = []
        dates = []

        # Processar cada conta no arquivo OFX
        for account in ofx.accounts:
            for transaction in account.statement.transactions:
                # Determinar tipo (receita ou despesa)
                valor = float(transaction.amount)
                tipo = 'receita' if valor > 0 else 'despesa'

                # Extrair informações
                trans_dict = {
                    'data': transaction.date.date() if hasattr(transaction.date, 'date') else transaction.date,
                    'descricao': transaction.memo or transaction.payee or 'Sem descrição',
                    'valor': abs(Decimal(str(valor))),
                    'tipo': tipo,
                    'numero_documento': transaction.id or transaction.checknum,
                    'saldo_apos': None  # OFX geralmente não inclui saldo após cada transação
                }

                transactions.append(trans_dict)
                dates.append(trans_dict['data'])

        # Informações da conta
        account_info = {
            'account_id': account.account_id if account else None,
            'routing_number': account.routing_number if account else None,
        }

        # Range de datas
        date_range = (min(dates), max(dates)) if dates else (None, None)

        return {
            'transactions': transactions,
            'account_info': account_info,
            'date_range': date_range,
            'total': len(transactions)
        }

    except Exception as e:
        raise Exception(f"Erro ao processar arquivo OFX: {str(e)}")


def parse_csv(file_content, config=None):
    """
    Parseia arquivo CSV e retorna lista de transações

    Args:
        file_content: conteúdo do arquivo (string ou bytes)
        config: dict com configurações do CSV (opcional)
            - delimiter: separador (padrão: ',')
            - date_column: nome da coluna de data (padrão: 'data')
            - description_column: nome da coluna de descrição (padrão: 'descricao')
            - amount_column: nome da coluna de valor (padrão: 'valor')
            - date_format: formato da data (padrão: '%d/%m/%Y')
            - has_header: se tem cabeçalho (padrão: True)

    Returns:
        dict com:
            - transactions: lista de dicts com as transações
            - date_range: tuple com (data_inicio, data_fim)
    """
    try:
        # Configurações padrão
        default_config = {
            'delimiter': ',',
            'date_column': 'data',
            'description_column': 'descricao',
            'amount_column': 'valor',
            'date_format': '%d/%m/%Y',
            'has_header': True,
            'encoding': 'utf-8'
        }

        if config:
            default_config.update(config)

        config = default_config

        # Se for bytes, decodificar
        if isinstance(file_content, bytes):
            file_content = file_content.decode(config['encoding'])

        # Ler CSV com pandas
        df = pd.read_csv(
            StringIO(file_content),
            delimiter=config['delimiter'],
            header=0 if config['has_header'] else None
        )

        # Se não tem header, usar índices de coluna
        if not config['has_header']:
            # Assumir formato: data, descricao, valor
            df.columns = ['data', 'descricao', 'valor']
            config['date_column'] = 'data'
            config['description_column'] = 'descricao'
            config['amount_column'] = 'valor'

        transactions = []
        dates = []

        for _, row in df.iterrows():
            try:
                # Parsear data
                date_str = str(row[config['date_column']])
                data = pd.to_datetime(date_str, format=config['date_format']).date()

                # Parsear valor
                valor_str = str(row[config['amount_column']]).replace('.', '').replace(',', '.')
                valor = float(valor_str)

                # Determinar tipo
                tipo = 'receita' if valor > 0 else 'despesa'

                # Descrição
                descricao = str(row[config['description_column']])

                trans_dict = {
                    'data': data,
                    'descricao': descricao,
                    'valor': abs(Decimal(str(valor))),
                    'tipo': tipo,
                    'numero_documento': None,
                    'saldo_apos': None
                }

                transactions.append(trans_dict)
                dates.append(data)

            except Exception as e:
                # Pular linhas com erro
                continue

        # Range de datas
        date_range = (min(dates), max(dates)) if dates else (None, None)

        return {
            'transactions': transactions,
            'account_info': {},
            'date_range': date_range,
            'total': len(transactions)
        }

    except Exception as e:
        raise Exception(f"Erro ao processar arquivo CSV: {str(e)}")


def detect_format(file_content):
    """
    Detecta o formato do arquivo (OFX ou CSV)

    Args:
        file_content: conteúdo do arquivo

    Returns:
        str: 'OFX' ou 'CSV' ou 'UNKNOWN'
    """
    try:
        # Converter para string se for bytes
        if isinstance(file_content, bytes):
            content_str = file_content.decode('utf-8', errors='ignore')
        else:
            content_str = file_content

        # Verificar se é OFX
        if '<OFX>' in content_str.upper() or 'OFXHEADER' in content_str.upper():
            return 'OFX'

        # Verificar se é CSV (tem vírgulas ou ponto-e-vírgula)
        lines = content_str.split('\n')[:5]  # Primeiras 5 linhas
        if any(',' in line or ';' in line for line in lines):
            return 'CSV'

        return 'UNKNOWN'

    except:
        return 'UNKNOWN'


def parse_file(file_content, file_format=None, csv_config=None):
    """
    Parseia um arquivo bancário detectando automaticamente o formato

    Args:
        file_content: conteúdo do arquivo
        file_format: formato do arquivo ('OFX' ou 'CSV'), se None detecta automaticamente
        csv_config: configurações para CSV (se aplicável)

    Returns:
        dict com as transações parseadas
    """
    # Detectar formato se não fornecido
    if not file_format:
        file_format = detect_format(file_content)

    # Parsear de acordo com o formato
    if file_format == 'OFX':
        return parse_ofx(file_content)
    elif file_format == 'CSV':
        return parse_csv(file_content, csv_config)
    else:
        raise Exception("Formato de arquivo não suportado. Use OFX ou CSV.")
