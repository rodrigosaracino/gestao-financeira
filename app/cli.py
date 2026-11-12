"""
Comandos de linha de comando.

    flask importar-extrato ARQUIVO --usuario EMAIL [--conta ID|NOME] [--cartao ID|NOME] [--aplicar]
    flask listar-contas --usuario EMAIL

Sem --aplicar é apenas uma SIMULAÇÃO: mostra o que seria feito e não grava nada.
"""
import json
import os
from decimal import Decimal

import click
from flask.cli import with_appcontext

from app.models import db, CartaoCredito, Conta, User
from app.services import importacao


def _usuario(email):
    user = User.query.filter(db.func.lower(User.email) == (email or '').strip().lower()).first()
    if not user:
        raise click.ClickException('Usuário não encontrado.')
    return user


def _resolver(model, user_id, valor):
    if valor in (None, ''):
        return None
    q = model.query.filter_by(user_id=user_id)
    obj = q.filter_by(id=int(valor)).first() if str(valor).isdigit() else None
    if not obj:
        candidatos = [o for o in q.all() if str(valor).lower() in (o.nome or '').lower()]
        if len(candidatos) > 1:
            raise click.ClickException(f'"{valor}" corresponde a mais de um registro: '
                                       + ', '.join(f'{c.id}={c.nome}' for c in candidatos))
        obj = candidatos[0] if candidatos else None
    if not obj:
        raise click.ClickException(f'{model.__name__} "{valor}" não encontrado.')
    return obj.id


def _fmt(v):
    if v is None:
        return '-'
    return f'R$ {Decimal(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _imprimir(conciliacao, r, simulacao, detalhado):
    click.echo('')
    click.echo(('SIMULAÇÃO (nada foi gravado)' if simulacao else 'IMPORTAÇÃO GRAVADA') + f' — {r["arquivo"]} [{r["formato"]}]')
    click.echo(f'Destino: {r["destino"]}')
    if r['periodo'][0]:
        click.echo(f'Período: {r["periodo"][0]:%d/%m/%Y} a {r["periodo"][1]:%d/%m/%Y}')
    click.echo(f'Lançamentos no arquivo: {r["total"]}')
    if simulacao:
        s, ps = r['sugestoes'], r['por_status']
        click.echo(f'  novos a importar:        {s.get("importar", 0)}')
        click.echo(f'  já cadastrados (conciliar): {s.get("conciliar", 0)}')
        click.echo(f'  já importados antes:     {ps.get("duplicado", 0)}')
        click.echo(f'  ignorar (ex.: pagamento de fatura): {s.get("ignorar", 0)}')
        click.echo(f'  impacto dos novos:       {_fmt(r["impacto_sugerido"])}')
    else:
        for k in ('importado', 'conciliado', 'duplicado', 'ignorado'):
            click.echo(f'  {k}: {r["por_status"].get(k, 0)}')
    if r['saldo_banco'] is not None:
        click.echo(f'Saldo no banco: {_fmt(r["saldo_banco"])} | saldo no sistema: {_fmt(r["saldo_sistema"])}'
                   + ('' if simulacao else f' | diferença: {_fmt(r["diferenca_saldo"])}'))
    if detalhado:
        click.echo('')
        for item in sorted(conciliacao.itens, key=lambda i: (i.data, i.id)):
            acao = item.status if item.status != 'pendente' else item.acao_sugerida
            sinal = '+' if item.tipo == 'receita' else '-'
            cat = item.categoria_sugerida.nome if item.categoria_sugerida else ''
            extra = f' ~ "{item.transacao.descricao}"' if item.transacao and acao == 'conciliar' else ''
            click.echo(f'  {item.data:%d/%m} {sinal}{_fmt(item.valor):>14}  {acao:<10} {cat[:22]:<22} {item.descricao[:60]}{extra}')


@click.command('importar-extrato')
@click.argument('arquivo', type=click.Path(exists=True, dir_okay=False))
@click.option('--usuario', required=True, help='E-mail do usuário dono das contas.')
@click.option('--conta', help='ID ou parte do nome da conta (opcional se o OFX já foi reconhecido).')
@click.option('--cartao', help='ID ou parte do nome do cartão (para faturas).')
@click.option('--aplicar', is_flag=True, help='Grava de fato. Sem isso é só simulação.')
@click.option('--detalhado', is_flag=True, help='Lista cada lançamento.')
@click.option('--json', 'saida_json', is_flag=True, help='Saída em JSON.')
@with_appcontext
def importar_extrato(arquivo, usuario, conta, cartao, aplicar, detalhado, saida_json):
    """Importa um extrato (OFX/PDF/CSV) usando as mesmas regras da tela de Conciliação."""
    user = _usuario(usuario)
    conta_id = _resolver(Conta, user.id, conta)
    cartao_id = _resolver(CartaoCredito, user.id, cartao)
    with open(arquivo, 'rb') as fh:
        conteudo = fh.read(importacao.TAMANHO_MAXIMO + 1)
    try:
        conciliacao, avisos = importacao.analisar_extrato(
            user.id, conteudo, os.path.basename(arquivo), conta_id=conta_id, cartao_id=cartao_id)
        if aplicar:
            r = importacao.aplicar_conciliacao(conciliacao)
        else:
            r = importacao.resumo(conciliacao)
    except importacao.ErroImportacao as exc:
        db.session.rollback()
        raise click.ClickException(str(exc))

    if saida_json:
        click.echo(json.dumps({'avisos': avisos, 'resumo': r}, default=str, ensure_ascii=False, indent=2))
    else:
        for aviso in avisos:
            click.echo(f'Aviso: {aviso}')
        _imprimir(conciliacao, r, simulacao=not aplicar, detalhado=detalhado)
    if not aplicar:
        db.session.rollback()  # simulação: descarta tudo


@click.command('listar-contas')
@click.option('--usuario', required=True)
@with_appcontext
def listar_contas(usuario):
    """Lista contas e cartões do usuário (para usar em --conta/--cartao)."""
    user = _usuario(usuario)
    for c in Conta.query.filter_by(user_id=user.id).order_by(Conta.id):
        click.echo(f'conta  {c.id:>4}  {c.nome}  saldo {_fmt(c.saldo_atual)}{"" if c.ativa else "  (inativa)"}')
    for c in CartaoCredito.query.filter_by(user_id=user.id).order_by(CartaoCredito.id):
        click.echo(f'cartao {c.id:>4}  {c.nome}  final {c.numero_cartao or "-"}{"" if c.ativo else "  (inativo)"}')


def registrar(app):
    app.cli.add_command(importar_extrato)
    app.cli.add_command(listar_contas)
