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
        assert r2['por_status'] == {'duplicado': 4}
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
        # compras 59.90 + 300 - 40 = 319.90, + 8 parcelas futuras de 300 (PARC 02/10) = 2719.90;
        # o "PAGAMENTO EFETUADO" de 1200 é de uma fatura anterior que não está no sistema: não libera limite
        assert cartao.limite_utilizado == Decimal('2719.90')
        assert db.session.get(Conta, a['conta']).saldo_atual == Decimal('1000')  # conta não muda
        parc = Transacao.query.filter(Transacao.descricao.like('%PARC 02%')).one()
        assert (parc.numero_parcela, parc.total_parcelas, parc.forma_pagamento) == (2, 10, 'cartao_credito')
        assert sum(f.valor_total for f in Fatura.query.filter_by(cartao_id=a['cartao'])) == Decimal('2719.90')
        assert Transacao.query.filter(Transacao.id_externo.like('PROJ%')).count() == 8


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


# ---------------------------------------------------------------- histórico real (Inter, Nubank)

INTER_CSV = (
    'Extrato Conta Corrente \nConta ;123456\nPeríodo ;01/01/2026 a 12/11/2026\nSaldo ;1.150,00\n\n'
    'Data Lançamento;Histórico;Descrição;Valor;Saldo\n'
    '03/11/2026;Pix recebido;Fulano de Tal;200,00;1.150,00\n'
    '02/11/2026;Pix enviado ;Maria Exemplo Silva;-50,00;950,00\n'
    '01/11/2026;Pagamento efetuado;Conta de luz;-0,00;1.000,00\n'
)


def test_csv_inter_combina_historico_e_saldo():
    from app.parsers import parse_file
    r = parse_file(INTER_CSV.encode('utf-8'), filename='Extrato.csv')
    assert r['total'] == 2  # linha de valor zero é ignorada
    assert r['transactions'][0]['descricao'] == 'Pix recebido - Fulano de Tal'
    assert r['saldo_final'] == Decimal('1150.00')


def test_transferencia_entre_contas_proprias_tem_categoria_propria(app, usuarios):
    from app.models import Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], INTER_CSV.encode('utf-8'), 'Extrato.csv',
                                              conta_id=a['conta'], titular='Maria Exemplo Silva')
        r = importacao.aplicar_conciliacao(conc)
        cats = {t.descricao: t.categoria.nome for t in Transacao.query.filter_by(conta_id=a['conta'])}
        assert cats['Pix enviado - Maria Exemplo Silva'] == 'Transferência enviada (minhas contas)'
        assert cats['Pix recebido - Fulano de Tal'] == 'Outras Receitas'
        assert r['saldo_banco'] == Decimal('1150.00')


def test_pagamento_de_fatura_na_conta_tem_categoria():
    from app.matching import SugestorCategoria
    from app.models import db
    # usa app/usuarios via fixture abaixo
    assert SugestorCategoria._RE_PAGTO_FATURA.search('PAGAMENTO DE FATURA')


def test_pagamento_fatura_libera_limite_e_baixa_fatura(app, usuarios):
    from app.models import db, CartaoCredito, Fatura
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        c1, _ = importacao.analisar_extrato(a['user'], _ler('fatura_cartao.ofx'), 'f1.ofx', cartao_id=a['cartao'])
        importacao.aplicar_conciliacao(c1)
        cartao = db.session.get(CartaoCredito, a['cartao'])
        # mês 1: 319.90 + 2400 em parcelas futuras; o pagamento de 1200 é de fatura fora do sistema
        assert cartao.limite_utilizado == Decimal('2719.90')
        c2, _ = importacao.analisar_extrato(a['user'], _ler('fatura_cartao_mes2.ofx'), 'f2.ofx', cartao_id=a['cartao'])
        r2 = importacao.aplicar_conciliacao(c2)
        assert r2['por_status'].get('pagamento') == 1
        outubro = Fatura.query.filter_by(cartao_id=a['cartao'], mes_referencia=10, ano_referencia=2026).one()
        assert outubro.status == 'paga' and outubro.valor_pago == Decimal('319.90')
        # reimportar o mês 2 não baixa o pagamento de novo
        c3, _ = importacao.analisar_extrato(a['user'], _ler('fatura_cartao_mes2.ofx'), 'f2.ofx', cartao_id=a['cartao'])
        r3 = importacao.aplicar_conciliacao(c3)
        assert r3['por_status'] == {'duplicado': 2}
        # desfazer o mês 2 reabre outubro
        importacao.desfazer_conciliacao(c2)
        assert db.session.get(Fatura, outubro.id).status == 'aberta'


def test_transferencia_recebida_e_enviada_no_mesmo_extrato(app, usuarios):
    from app.models import Transacao
    from app.services import importacao
    a, _ = usuarios
    csv = INTER_CSV.replace('Pix recebido;Fulano de Tal', 'Pix recebido;Maria Exemplo Silva')
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], csv.encode('utf-8'), 'Extrato.csv',
                                              conta_id=a['conta'], titular='Maria Exemplo Silva')
        importacao.aplicar_conciliacao(conc)
        nomes = {t.tipo: t.categoria.nome for t in Transacao.query.filter_by(conta_id=a['conta'])}
        assert nomes == {'receita': 'Transferência recebida (minhas contas)',
                         'despesa': 'Transferência enviada (minhas contas)'}


def test_ofx_nubank_rendimento_no_ballist():
    from app.parsers import parse_file
    ofx = (b'OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>1</BANKACCTFROM>'
           b'<BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260305<TRNAMT>-10.00<FITID>X1<MEMO>Compra</STMTTRN>'
           b'</BANKTRANLIST><LEDGERBAL><BALAMT>90.82</BALAMT><DTASOF>20260331000000[-3:BRT]</DTASOF></LEDGERBAL>'
           b'<BALLIST><BAL><NAME>RENDIMENTO LIQUIDO</NAME><DESC>RENDIMENTO LIQUIDO NO PERIODO</DESC>'
           b'<BALTYPE>NUMBER</BALTYPE><VALUE>0.82</VALUE></BAL></BALLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>')
    r = parse_file(ofx)
    rend = [t for t in r['transactions'] if t['descricao'].startswith('Rendimento')]
    assert len(rend) == 1 and rend[0]['valor'] == Decimal('0.82') and rend[0]['tipo'] == 'receita'
    assert rend[0]['data'] == date(2026, 3, 31)


def test_saldo_em_atraso_da_fatura_e_ignorado(app, usuarios):
    from app.models import db, CartaoCredito, Transacao
    from app.services import importacao
    a, _ = usuarios
    ofx = (b'OFXHEADER:100\n<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CCACCTFROM><ACCTID>abc</CCACCTFROM>'
           b'<BANKTRANLIST>'
           b'<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260108<TRNAMT>-100.00<FITID>S1<MEMO>Saldo em atraso</STMTTRN>'
           b'<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260113<TRNAMT>100.00<FITID>S2<MEMO>Pagamento recebido</STMTTRN>'
           b'<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260115<TRNAMT>-50.00<FITID>S3<MEMO>Padaria</STMTTRN>'
           b'</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>')
    with app.app_context():
        conc, _ = importacao.analisar_extrato(a['user'], ofx, 'f.ofx', cartao_id=a['cartao'])
        assert {i.descricao: i.acao_sugerida for i in conc.itens}['Saldo em atraso'] == 'ignorar'
        importacao.aplicar_conciliacao(conc)
        assert [t.descricao for t in Transacao.query.filter_by(cartao_credito_id=a['cartao'])] == ['Padaria']
        # o pagamento quita a fatura anterior (fora do sistema): só a compra de 50 usa limite
        assert db.session.get(CartaoCredito, a['cartao']).limite_utilizado == Decimal('50')


# ---------------------------------------------------------------- projeção de parcelas

def _ofx_cartao(itens):
    corpo = ''.join(f'<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{d}<TRNAMT>-{v}<FITID>{fid}<MEMO>{m}</STMTTRN>'
                    for d, v, fid, m in itens)
    return ('OFXHEADER:100\n<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CCACCTFROM><ACCTID>abc</CCACCTFROM>'
            f'<BANKTRANLIST>{corpo}</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>').encode()


def test_parcelas_futuras_sao_projetadas_e_confirmadas_sem_duplicar(app, usuarios):
    from app.models import db, CartaoCredito, Fatura, Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        mes1 = _ofx_cartao([('20261001', '100.00', 'P1', 'Loja X - Parcela 2/4')])
        c1, _ = importacao.analisar_extrato(a['user'], mes1, 'out.ofx', cartao_id=a['cartao'])
        importacao.aplicar_conciliacao(c1)
        parcelas = Transacao.query.filter_by(cartao_credito_id=a['cartao']).order_by(Transacao.data).all()
        assert [(t.numero_parcela, t.data.month) for t in parcelas] == [(2, 10), (3, 11), (4, 12)]
        assert db.session.get(CartaoCredito, a['cartao']).limite_utilizado == Decimal('300')
        assert Fatura.query.filter_by(cartao_id=a['cartao'], mes_referencia=12).one().valor_total == Decimal('100')

        # chega a fatura real de novembro, com centavos diferentes
        mes2 = _ofx_cartao([('20261102', '100.01', 'P2', 'Loja X - Parcela 3/4')])
        c2, _ = importacao.analisar_extrato(a['user'], mes2, 'nov.ofx', cartao_id=a['cartao'])
        item = c2.itens[0]
        prevista_nov = [t for t in parcelas if t.numero_parcela == 3][0]
        assert item.acao_sugerida == 'conciliar' and item.transacao_id == prevista_nov.id
        importacao.aplicar_conciliacao(c2)
        parcelas = Transacao.query.filter_by(cartao_credito_id=a['cartao']).order_by(Transacao.data).all()
        assert len(parcelas) == 3
        nov = [t for t in parcelas if t.numero_parcela == 3][0]
        assert nov.valor == Decimal('100.01') and not nov.id_externo.startswith('PROJ')
        assert db.session.get(CartaoCredito, a['cartao']).limite_utilizado == Decimal('300.01')

        # reimportar novembro não duplica
        c3, _ = importacao.analisar_extrato(a['user'], mes2, 'nov.ofx', cartao_id=a['cartao'])
        assert importacao.aplicar_conciliacao(c3)['por_status'] == {'duplicado': 1}
        # desfazer outubro remove a parcela 2 e a prevista 4 (a 3 agora é de novembro)
        importacao.desfazer_conciliacao(c1)
        assert sorted(t.numero_parcela for t in Transacao.query.filter_by(cartao_credito_id=a['cartao'])) == [3]


def test_projetar_historico_cli(app, usuarios):
    from app.models import db, Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        mes1 = _ofx_cartao([('20261001', '50.00', 'Q1', 'Curso Y - Parcela 1/3')])
        c1, _ = importacao.analisar_extrato(a['user'], mes1, 'out.ofx', cartao_id=a['cartao'])
        importacao.aplicar_conciliacao(c1)
        # simula histórico antigo sem projeção: apaga as previstas
        for t in Transacao.query.filter(Transacao.id_externo.like('PROJ%')).all():
            db.session.delete(t)
        db.session.commit()
    runner = app.test_cli_runner()
    r = runner.invoke(args=['projetar-parcelas', '--usuario', a['email'], '--cartao', str(a['cartao'])])
    assert 'SIMULAÇÃO' in r.output and '2 parcela' in r.output, r.output
    with app.app_context():
        assert Transacao.query.filter(Transacao.id_externo.like('PROJ%')).count() == 0
    r = runner.invoke(args=['projetar-parcelas', '--usuario', a['email'], '--cartao', str(a['cartao']), '--aplicar'])
    assert r.exit_code == 0 and '2 parcela' in r.output
    r = runner.invoke(args=['projetar-parcelas', '--usuario', a['email'], '--cartao', str(a['cartao']), '--aplicar'])
    assert '0 parcela' in r.output  # idempotente


def test_projecao_com_centavos_diferentes_nao_duplica_nem_preve_passado(app, usuarios):
    from app.models import Transacao
    from app.services import importacao
    a, _ = usuarios
    with app.app_context():
        # 1ª parcela 33.34, demais 33.33 (arredondamento do banco); out tem a 1/3, nov tem a 2/3
        for nome, d, v, fid, m in [('out.ofx', '20261001', '33.34', 'R1', 'Tenis Z - Parcela 1/3'),
                                   ('nov.ofx', '20261101', '33.33', 'R2', 'Tenis Z - Parcela 2/3')]:
            c, _ = importacao.analisar_extrato(a['user'], _ofx_cartao([(d, v, fid, m)]), nome, cartao_id=a['cartao'])
            importacao.aplicar_conciliacao(c)
        assert importacao.projetar_historico(db_cartao(a)) == 0  # 3/3 já foi prevista ao importar
        parcelas = sorted((t.numero_parcela, t.data.month) for t in Transacao.query.filter_by(cartao_credito_id=a['cartao']))
        assert parcelas == [(1, 10), (2, 11), (3, 12)]


def db_cartao(a):
    from app.models import db, CartaoCredito
    return db.session.get(CartaoCredito, a['cartao'])


def test_fatura_pdf_estilo_mercado_pago(app, usuarios):
    """Fecha dia 8, vence dia 13; parcelas antigas vêm com a data da compra; pagamento sem sinal."""
    from app.models import db, CartaoCredito, Fatura, Transacao
    from app.parsers import parse_pdf_texto
    from app.services import importacao
    a, _ = usuarios
    texto = """Essa é sua fatura de novembro
Cartão de crédito - Vencimento: 13/11/2026
Fechamento da fatura 08/11/2026
19/10 Pagamento da fatura de outubro/2026 R$ 513,19
09/11 Juros do rotativo R$ 18,38
10/09 LOJA A Parcela 2 de 4 R$ 8,74
16/09 LOJA B Parcela 2 de 15 R$ 432,00
12/10 LOJA C R$ 80,00
25/08 LOJA D Parcela 8 de 8 R$ 27,47
"""
    r = parse_pdf_texto(texto, hoje=date(2026, 11, 12))
    pag = [t for t in r['transactions'] if t['eh_pagamento_fatura']]
    assert len(pag) == 1 and pag[0]['tipo'] == 'receita'
    with app.app_context():
        cartao = db.session.get(CartaoCredito, a['cartao'])
        cartao.dia_fechamento, cartao.dia_vencimento, cartao.limite = 8, 13, Decimal('6700')
        db.session.commit()
        # monta a conciliação a partir do texto (sem PDF binário)
        from unittest import mock
        with mock.patch('app.services.importacao.parse_file', return_value=r):
            conc, _ = importacao.analisar_extrato(a['user'], b'%PDF-fake', 'fatura.pdf', cartao_id=a['cartao'])
        importacao.aplicar_conciliacao(conc)
        nov = Fatura.query.filter_by(cartao_id=a['cartao'], mes_referencia=11, ano_referencia=2026).one()
        assert nov.data_vencimento == date(2026, 11, 13)
        assert nov.valor_total == Decimal('566.59')  # 18.38 + 8.74 + 432 + 80 + 27.47
        reais = Transacao.query.filter(Transacao.cartao_credito_id == a['cartao'],
                                       ~Transacao.id_externo.like('PROJ%')).all()
        assert all(t.data.month == 11 for t in reais)  # parcelas antigas trazidas para a fatura de novembro
        # limite: 566.59 + 2 x 8.74 + 13 x 432 = 6200.07; o pagamento de outubro (fatura fora do sistema) não libera
        assert db.session.get(CartaoCredito, a['cartao']).limite_utilizado == Decimal('6200.07')
        dez = Fatura.query.filter_by(cartao_id=a['cartao'], mes_referencia=12, ano_referencia=2026).one()
        assert dez.valor_total == Decimal('440.74')  # parcelas 3/4 e 3/15
