"""Importação de extrato: leitura, deduplicação, saldo, cartão, idempotência e CLI."""
import os
from datetime import date
from decimal import Decimal

import pytest

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


def _ler(nome):
    with open(os.path.join(FIX, nome), 'rb') as fh:
        return fh.read()


# ---------------------------------------------------------------- parsers

def test_parse_ofx_conta():
    from app.parsers import parse_file
    r = parse_file(_ler('extrato_conta.ofx'))
    assert r['formato'] == 'OFX' and r['tipo_extrato'] == 'conta'
    assert r['total'] == 4
    assert r['account_info']['account_id'] == '12345-6'
    assert r['saldo_final'] == Decimal('5560.85')
    pix = [t for t in r['transactions'] if 'Padaria' in t['descricao']][0]
    assert pix['valor'] == Decimal('89.90') and pix['tipo'] == 'despesa'
    assert r['transactions'][0]['tipo'] == 'receita' and r['transactions'][0]['data'] == date(2026, 11, 5)


def test_parse_ofx_cartao():
    from app.parsers import parse_file
    r = parse_file(_ler('fatura_cartao.ofx'))
    assert r['tipo_extrato'] == 'cartao' and r['total'] == 4
    pagamento = [t for t in r['transactions'] if 'PAGAMENTO' in t['descricao']][0]
    assert pagamento['eh_pagamento_fatura'] is True


@pytest.mark.parametrize('texto,esperado', [
    ('1.234,56', Decimal('1234.56')), ('-1234.56', Decimal('-1234.56')), ('R$ 12,30 D', Decimal('-12.30')),
    ('45,00-', Decimal('-45.00')), ('1,234.50', Decimal('1234.50')), ('-89,90', Decimal('-89.90')),
])
def test_parse_valor_br(texto, esperado):
    from app.parsers import parse_valor_br
    assert parse_valor_br(texto) == esperado


def test_detectar_parcela():
    from app.parsers import detectar_parcela
    assert detectar_parcela('MAGAZINE LOJA PARC 02/10') == (2, 10)
    assert detectar_parcela('LOJA X 03/12') == (3, 12)
    assert detectar_parcela('PADARIA') is None
    assert detectar_parcela('LOJA 12/03') is None  # 12 > 3: parece data, não parcela


def test_parse_pdf_extrato_conta():
    from app.parsers import parse_pdf_texto
    texto = """BANCO EXEMPLO - EXTRATO DE CONTA CORRENTE
Período: 01/11/2026 a 10/11/2026
05/11 SALARIO EMPRESA XYZ 5.000,00 6.000,00
06/11 SUPERMERCADO BOM PRECO -150,25 5.849,75
07/11 PIX ENVIADO PADARIA 89,90 D 5.759,85
SALDO DO DIA 5.759,85
"""
    r = parse_pdf_texto(texto, hoje=date(2026, 11, 12))
    assert r['tipo_extrato'] == 'conta' and r['total'] == 3
    assert r['transactions'][0]['data'] == date(2026, 11, 5) and r['transactions'][0]['tipo'] == 'receita'
    assert r['transactions'][2]['tipo'] == 'despesa' and r['transactions'][2]['valor'] == Decimal('89.90')


def test_parse_pdf_fatura_cruzando_ano():
    from app.parsers import parse_pdf_texto
    texto = """FATURA DO CARTÃO DE CRÉDITO
Vencimento: 10/01/2027
28/12 RESTAURANTE SABOR 120,00
03/01 UBER TRIP 25,50
05/01 ESTORNO LOJA -30,00
06/01 PAGAMENTO EFETUADO -500,00
TOTAL DA FATURA 115,50
"""
    r = parse_pdf_texto(texto, hoje=date(2027, 1, 8))
    assert r['tipo_extrato'] == 'cartao' and r['total'] == 4
    assert r['transactions'][0]['data'] == date(2026, 12, 28)
    assert r['transactions'][0]['tipo'] == 'despesa'
    assert r['transactions'][2]['tipo'] == 'receita'  # estorno
    assert r['transactions'][3]['eh_pagamento_fatura']


def test_parse_csv_brasileiro():
    from app.parsers import parse_file
    csv = 'Data;Histórico;Valor\n05/11/2026;SALARIO;5.000,00\n06/11/2026;MERCADO;-150,25\n'.encode('cp1252')
    r = parse_file(csv, filename='extrato.csv')
    assert r['total'] == 2 and r['transactions'][1]['valor'] == Decimal('150.25')


# ---------------------------------------------------------------- serviço

def _conta(app, conta_id):
    from app.models import db, Conta
    return db.session.get(Conta, conta_id)


def test_importar_ofx_conta_atualiza_saldo_e_nao_duplica(app, usuarios):
    from app.models import db, Transacao, Conta
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'extrato.ofx', conta_id=a['conta'])
        assert importacao.resumo(conc)['sugestoes'].get('importar') == 4
        r = importacao.aplicar_conciliacao(conc)
        assert r['por_status']['importado'] == 4
        # 1000 + 5000 - 150.25 - 89.90 - 200 = 5559.85
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('5559.85')
        assert r['diferenca_saldo'] == Decimal('-1.00')  # saldo inicial de teste difere do banco
        assert db.session.get(Conta, a['conta']).id_banco == '12345-6'  # conta aprendida

        # Reenviar o mesmo arquivo: nada novo
        conc2, avisos = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'extrato.ofx')
        assert conc2.conta_id == a['conta']  # reconhecida pelo ACCTID
        assert any('já foi importado' in x for x in avisos)
        r2 = importacao.aplicar_conciliacao(conc2)
        assert r2['por_status'] == {'duplicado': 4} or r2['por_status'].get('importado', 0) == 0
        assert Transacao.query.filter_by(conta_id=a['conta']).count() == 4
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('5559.85')


def test_processar_duas_vezes_nao_duplica(app, usuarios):
    from app.models import Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=a['conta'])
        importacao.aplicar_conciliacao(conc)
        with pytest.raises(importacao.ErroImportacao):
            importacao.aplicar_conciliacao(conc)
        assert Transacao.query.filter_by(conta_id=a['conta']).count() == 4


def test_conciliar_com_transacao_pendente_marca_paga(app, usuarios):
    from app.models import db, Transacao, Conta
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        luz = Transacao(descricao='Conta de luz Enel', valor=Decimal('200'), tipo='despesa', data=date(2026, 11, 8),
                        conta_id=a['conta'], categoria_id=a['despesa'], pago=False)
        db.session.add(luz)
        db.session.commit()
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=a['conta'])
        item_luz = [i for i in conc.itens if 'ENEL' in i.descricao][0]
        assert item_luz.acao_sugerida == 'conciliar' and item_luz.transacao_id == luz.id
        importacao.aplicar_conciliacao(conc)
        assert db.session.get(Transacao, luz.id).pago is True
        assert Transacao.query.filter_by(conta_id=a['conta']).count() == 4  # 3 novas + a luz
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('5559.85')


def test_categoria_sugerida_por_palavra_chave_e_padrao(app, usuarios):
    from app.models import db, Categoria, Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        db.session.add(Categoria(nome='Mercado', tipo='despesa', cor='#c0392b', user_id=a['user']))
        db.session.add(Categoria(nome='Salário', tipo='receita', cor='#27ae60', user_id=a['user']))
        db.session.commit()
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=a['conta'])
        importacao.aplicar_conciliacao(conc)
        cat = {t.descricao: t.categoria.nome for t in Transacao.query.filter_by(conta_id=a['conta'])}
        assert cat['SALARIO EMPRESA XYZ'] == 'Salário'
        assert cat['COMPRA CARTAO DEBITO SUPERMERCADO BOM PRECO'] == 'Mercado'
        assert cat['PIX ENVIADO Padaria São João'] == 'Outros'  # sem 'Restaurantes' -> padrão


def test_fatura_cartao_lanca_na_fatura_e_limite(app, usuarios):
    from app.models import db, CartaoCredito, Conta, Fatura, Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], _ler('fatura_cartao.ofx'), 'fatura.ofx', cartao_id=a['cartao'])
        assert conc.cartao_credito_id == a['cartao']
        sugest = {i.descricao: i.acao_sugerida for i in conc.itens}
        assert sugest['PAGAMENTO EFETUADO'] == 'ignorar'
        importacao.aplicar_conciliacao(conc)
        cartao = db.session.get(CartaoCredito, a['cartao'])
        assert cartao.limite_utilizado == Decimal('319.90')  # 59.90 + 300 - 40
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('1000')  # conta não muda
        parc = Transacao.query.filter(Transacao.descricao.like('%PARC%')).one()
        assert (parc.numero_parcela, parc.total_parcelas, parc.forma_pagamento) == (2, 10, 'cartao_credito')
        assert sum(f.valor_total for f in Fatura.query.filter_by(cartao_id=a['cartao'])) == Decimal('319.90')


def test_fatura_sem_cartao_pede_cartao(app, usuarios):
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        with pytest.raises(importacao.ErroImportacao, match='cartão'):
            importacao.analisar_extrato(a['user'], _ler('fatura_cartao.ofx'), 'fatura.ofx')


def test_desfazer_restaura_saldo(app, usuarios):
    from app.models import db, Conta, Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=a['conta'])
        importacao.aplicar_conciliacao(conc)
        assert importacao.desfazer_conciliacao(conc) == 4
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('1000')
        assert Transacao.query.filter_by(conta_id=a['conta']).count() == 0


def test_nao_importa_em_conta_de_outro_usuario(app, usuarios):
    from app.services import importacao
    a, b = usuarios
    with app.app_context():
        with pytest.raises(importacao.ErroImportacao):
            importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=b['conta'])


def test_extensao_invalida(app, usuarios):
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        with pytest.raises(importacao.ErroImportacao):
            importacao.analisar_extrato(a['user'], b'MZ\x90\x00', 'virus.exe', conta_id=a['conta'])


# ---------------------------------------------------------------- tela

def test_fluxo_pela_tela(app, usuarios, client_a):
    import io
    from app.models import db, Conta, ConciliacaoBancaria
    a, _ = usuarios
    resp = client_a.post('/conciliacao/nova', data={
        'conta_id': a['conta'], 'arquivo': (io.BytesIO(_ler('extrato_conta.ofx')), 'extrato.ofx'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 302 and '/revisar' in resp.headers['Location']
    with app.app_context():
        conc = ConciliacaoBancaria.query.one()
        itens = {i.descricao: i.id for i in conc.itens}
        cid = conc.id
    pagina = client_a.get(f'/conciliacao/{cid}/revisar')
    assert pagina.status_code == 200 and 'Padaria' in pagina.get_data(as_text=True)
    form = {f'acao_{i}': 'importar' for i in itens.values()}
    form[f'acao_{itens["CONTA DE LUZ ENEL"]}'] = 'ignorar'
    assert client_a.post(f'/conciliacao/{cid}/processar', data=form).status_code == 302
    assert client_a.post(f'/conciliacao/{cid}/processar', data=form).status_code == 302  # 2º clique
    with app.app_context():
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('5759.85')
    assert client_a.get(f'/conciliacao/{cid}/revisar').status_code == 200
    assert client_a.post(f'/conciliacao/{cid}/excluir').status_code == 302
    with app.app_context():
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('1000')


def test_usuario_b_nao_ve_conciliacao_de_a(app, usuarios):
    from app.services import importacao
    from app.models import db
    from tests.conftest import login
    a, b = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], _ler('extrato_conta.ofx'), 'x.ofx', conta_id=a['conta'])
        db.session.commit()
        cid = conc.id
    c = app.test_client()
    login(c, b)
    assert c.get(f'/conciliacao/{cid}/revisar').status_code == 404
    assert c.post(f'/conciliacao/{cid}/processar').status_code == 404


# ---------------------------------------------------------------- CLI

def test_cli_simulacao_e_aplicar(app, usuarios):
    from app.models import db, Conta, Transacao
    a, _ = usuarios
    runner = app.test_cli_runner()
    arq = os.path.join(FIX, 'extrato_conta.ofx')
    r = runner.invoke(args=['importar-extrato', arq, '--usuario', a['email'], '--conta', str(a['conta']), '--detalhado'])
    assert r.exit_code == 0, r.output
    assert 'SIMULAÇÃO' in r.output and 'novos a importar:        4' in r.output
    with app.app_context():
        assert Transacao.query.count() == 0
    r = runner.invoke(args=['importar-extrato', arq, '--usuario', a['email'], '--conta', 'Atacante', '--aplicar'])
    assert r.exit_code == 0, r.output
    with app.app_context():
        assert Transacao.query.count() == 4
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('5559.85')
    r = runner.invoke(args=['importar-extrato', arq, '--usuario', 'naoexiste@x.com'])
    assert r.exit_code != 0
