"""
Serviço de integração com a API brapi.dev
API gratuita de cotações da B3
"""
import requests
from datetime import datetime, timedelta
from flask import current_app


class BrapiService:
    """Serviço para integração com brapi.dev"""

    BASE_URL = "https://brapi.dev/api"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Gestao-Financeira-App/1.0'
        })

    def buscar_cotacao(self, ticker):
        """
        Busca cotação de um ativo específico

        Args:
            ticker (str): Código do ativo (ex: PETR4, MXRF11)

        Returns:
            dict: Dados da cotação ou None em caso de erro
        """
        try:
            url = f"{self.BASE_URL}/quote/{ticker}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('results') and len(data['results']) > 0:
                    result = data['results'][0]

                    return {
                        'ticker': result.get('symbol'),
                        'nome': result.get('longName') or result.get('shortName'),
                        'preco': result.get('regularMarketPrice'),
                        'variacao_dia': result.get('regularMarketChangePercent'),
                        'volume': result.get('regularMarketVolume'),
                        'data_atualizacao': datetime.now(),
                        'moeda': result.get('currency', 'BRL'),
                        'tipo_mercado': result.get('market'),
                    }

            current_app.logger.warning(f"Erro ao buscar cotação de {ticker}: {response.status_code}")
            return None

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Erro de rede ao buscar {ticker}: {str(e)}")
            return None
        except Exception as e:
            current_app.logger.error(f"Erro inesperado ao buscar {ticker}: {str(e)}")
            return None

    def buscar_multiplas_cotacoes(self, tickers_list):
        """
        Busca cotações de múltiplos ativos

        IMPORTANTE: No plano gratuito, só podemos buscar 1 ticker por request
        Esta função faz múltiplas requisições sequencialmente

        Args:
            tickers_list (list): Lista de tickers

        Returns:
            dict: Dicionário com ticker como chave e dados como valor
        """
        resultados = {}

        for ticker in tickers_list:
            cotacao = self.buscar_cotacao(ticker)
            if cotacao:
                resultados[ticker] = cotacao

        return resultados

    def buscar_informacoes_ativo(self, ticker):
        """
        Busca informações detalhadas de um ativo
        Inclui dados como tipo, setor, descrição

        Args:
            ticker (str): Código do ativo

        Returns:
            dict: Informações do ativo ou None
        """
        try:
            url = f"{self.BASE_URL}/quote/{ticker}"
            params = {
                'fundamental': 'true',  # Apenas disponível em planos pagos
                'dividends': 'true'     # Apenas disponível em planos pagos
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('results') and len(data['results']) > 0:
                    result = data['results'][0]

                    info = {
                        'ticker': result.get('symbol'),
                        'nome_completo': result.get('longName'),
                        'nome_curto': result.get('shortName'),
                        'logo_url': result.get('logourl'),
                        'setor': result.get('sector'),
                        'industria': result.get('industry'),
                    }

                    # Dividendos (se disponível)
                    if result.get('dividendsData'):
                        info['dividendos'] = result['dividendsData']

                    return info

            return None

        except Exception as e:
            current_app.logger.error(f"Erro ao buscar informações de {ticker}: {str(e)}")
            return None

    def pesquisar_ativo(self, termo):
        """
        Pesquisa ativos por nome ou ticker

        Args:
            termo (str): Termo de pesquisa

        Returns:
            list: Lista de ativos encontrados
        """
        try:
            url = f"{self.BASE_URL}/quote/list"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Filtrar resultados pelo termo
                if data.get('stocks'):
                    termo_lower = termo.lower()
                    resultados = [
                        stock for stock in data['stocks']
                        if termo_lower in stock.get('stock', '').lower() or
                           termo_lower in stock.get('name', '').lower()
                    ]

                    return resultados[:10]  # Limitar a 10 resultados

            return []

        except Exception as e:
            current_app.logger.error(f"Erro ao pesquisar '{termo}': {str(e)}")
            return []

    def verificar_ticker_valido(self, ticker):
        """
        Verifica se um ticker é válido (existe na B3)

        Args:
            ticker (str): Código do ativo

        Returns:
            bool: True se válido, False caso contrário
        """
        cotacao = self.buscar_cotacao(ticker)
        return cotacao is not None

    def atualizar_ativo_se_necessario(self, ativo):
        """
        Atualiza cotação de um ativo apenas se necessário (cache > 15 min)

        Args:
            ativo (Ativo): Instância do modelo Ativo

        Returns:
            bool: True se atualizou, False se usou cache
        """
        from app.models import db

        # Verifica se precisa atualizar
        if not ativo.precisa_atualizar():
            current_app.logger.info(f"Usando cache para {ativo.ticker}")
            return False

        # Busca nova cotação
        cotacao = self.buscar_cotacao(ativo.ticker)

        if cotacao:
            ativo.ultimo_preco = cotacao['preco']
            ativo.variacao_dia = cotacao['variacao_dia']
            ativo.ultima_atualizacao = cotacao['data_atualizacao']

            if not ativo.nome and cotacao['nome']:
                ativo.nome = cotacao['nome']

            db.session.commit()
            current_app.logger.info(f"Cotação de {ativo.ticker} atualizada: R$ {cotacao['preco']}")
            return True

        current_app.logger.warning(f"Não foi possível atualizar {ativo.ticker}")
        return False

    def atualizar_carteira(self, ativos_list):
        """
        Atualiza cotações de uma carteira de ativos
        Otimizado para minimizar requisições no plano gratuito

        Args:
            ativos_list (list): Lista de objetos Ativo

        Returns:
            dict: Estatísticas da atualização
        """
        from app.models import db

        stats = {
            'total': len(ativos_list),
            'atualizados': 0,
            'cache': 0,
            'erros': 0
        }

        for ativo in ativos_list:
            try:
                if ativo.precisa_atualizar():
                    if self.atualizar_ativo_se_necessario(ativo):
                        stats['atualizados'] += 1
                    else:
                        stats['erros'] += 1
                else:
                    stats['cache'] += 1

            except Exception as e:
                current_app.logger.error(f"Erro ao atualizar {ativo.ticker}: {str(e)}")
                stats['erros'] += 1

        current_app.logger.info(
            f"Carteira atualizada: {stats['atualizados']} ativos, "
            f"{stats['cache']} do cache, {stats['erros']} erros"
        )

        return stats


# Instância global do serviço
brapi_service = BrapiService()
