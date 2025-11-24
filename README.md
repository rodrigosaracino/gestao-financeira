# Sistema de Gestão Financeira Pessoal

Sistema completo de gestão financeira pessoal desenvolvido em Python/Flask com funcionalidades de:
- Fluxo de caixa
- Gestão de contas bancárias
- Controle de cartões de crédito
- Gestão de faturas
- Categorização de gastos
- Relatórios e gráficos interativos

## Funcionalidades

### Contas Bancárias
- Cadastro de múltiplas contas (corrente, poupança, investimento)
- Controle de saldo inicial e atual
- Ativação/desativação de contas

### Transações
- Registro de receitas e despesas
- Categorização de transações
- Histórico completo com paginação
- Atualização automática de saldos

### Cartões de Crédito
- Cadastro de cartões com limite
- Configuração de dias de fechamento e vencimento
- Suporte para múltiplas bandeiras

### Faturas
- Criação e gerenciamento de faturas
- Status automático (aberta, fechada, paga, vencida)
- Vinculação de transações a faturas
- Pagamento de faturas com débito em conta

### Relatórios
- Gráfico de gastos por categoria (pizza)
- Gráfico de fluxo de caixa mensal (barras)
- Filtros por mês e ano
- Visualizações interativas com Plotly

## Requisitos

- Python 3.8+
- PostgreSQL 12+
- pip (gerenciador de pacotes Python)

## Instalação

### 1. Clone ou baixe o projeto

```bash
cd gestao_financeira_app
```

### 2. Crie um ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o PostgreSQL

Crie um banco de dados PostgreSQL:

```bash
# Entre no PostgreSQL
psql -U postgres

# Crie o banco de dados
CREATE DATABASE gestao_financeira;

# Crie um usuário (opcional)
CREATE USER seu_usuario WITH PASSWORD 'sua_senha';
GRANT ALL PRIVILEGES ON DATABASE gestao_financeira TO seu_usuario;
```

### 5. Configure as variáveis de ambiente

Copie o arquivo de exemplo e edite com suas configurações:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:

```
DATABASE_URL=postgresql://seu_usuario:sua_senha@localhost:5432/gestao_financeira
SECRET_KEY=sua-chave-secreta-muito-segura-aqui
FLASK_APP=run.py
FLASK_ENV=development
```

### 6. Inicialize o banco de dados

```bash
# Inicializar migrações
flask db init

# Criar migração
flask db migrate -m "Initial migration"

# Aplicar migração
flask db upgrade
```

### 7. (Opcional) Adicione dados iniciais

Você pode criar categorias padrão executando Python:

```bash
python3
```

```python
from app import create_app
from app.models import db, Categoria

app = create_app()
with app.app_context():
    categorias = [
        Categoria(nome='Alimentação', tipo='despesa', cor='#e74c3c'),
        Categoria(nome='Transporte', tipo='despesa', cor='#3498db'),
        Categoria(nome='Moradia', tipo='despesa', cor='#2ecc71'),
        Categoria(nome='Lazer', tipo='despesa', cor='#f39c12'),
        Categoria(nome='Saúde', tipo='despesa', cor='#9b59b6'),
        Categoria(nome='Educação', tipo='despesa', cor='#1abc9c'),
        Categoria(nome='Salário', tipo='receita', cor='#27ae60'),
        Categoria(nome='Investimentos', tipo='receita', cor='#16a085'),
    ]
    db.session.add_all(categorias)
    db.session.commit()
    print("Categorias criadas com sucesso!")
```

## Como Executar

### Desenvolvimento

```bash
python3 run.py
```

O aplicativo estará disponível em: `http://localhost:5000`

### Produção

Para produção, use um servidor WSGI como Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

## Estrutura do Projeto

```
gestao_financeira_app/
├── app/
│   ├── __init__.py          # Inicialização do Flask
│   ├── models.py            # Modelos do banco de dados
│   ├── routes.py            # Rotas e lógica de negócio
│   ├── static/
│   │   └── css/
│   │       └── style.css    # Estilos personalizados
│   └── templates/           # Templates HTML
│       ├── base.html
│       ├── index.html
│       ├── contas/
│       ├── transacoes/
│       ├── cartoes/
│       ├── faturas/
│       ├── categorias/
│       └── relatorios/
├── migrations/              # Migrações do banco de dados
├── config.py               # Configurações do Flask
├── requirements.txt        # Dependências Python
├── .env.example           # Exemplo de variáveis de ambiente
├── run.py                 # Arquivo principal
└── README.md              # Este arquivo
```

## Uso do Sistema

### Dashboard
Acesse a página inicial para ver:
- Saldo total de todas as contas
- Receitas e despesas do mês
- Faturas abertas
- Ações rápidas

### Gerenciar Contas
1. Vá em "Contas" no menu
2. Clique em "Nova Conta"
3. Preencha: nome, tipo e saldo inicial
4. Salve

### Adicionar Transações
1. Vá em "Transações" > "Nova Transação"
2. Preencha: descrição, valor, data, tipo (receita/despesa)
3. Selecione a conta e categoria
4. Salve (o saldo da conta será atualizado automaticamente)

### Gerenciar Cartões
1. Vá em "Cartões" > "Novo Cartão"
2. Preencha: nome, bandeira, limite
3. Configure dias de fechamento e vencimento
4. Salve

### Criar Faturas
1. Vá em "Faturas" > "Nova Fatura"
2. Selecione o cartão
3. Defina mês/ano de referência
4. Configure datas de fechamento e vencimento
5. Salve

### Pagar Faturas
1. Vá em "Faturas" e clique em "Ver" na fatura desejada
2. Clique em "Pagar Fatura"
3. Informe o valor e a conta para débito
4. Confirme (será criada uma transação de despesa automaticamente)

### Ver Relatórios
1. Vá em "Relatórios"
2. Selecione mês e ano
3. Clique em "Atualizar"
4. Visualize os gráficos interativos

## Tecnologias Utilizadas

- **Backend**: Flask 3.0
- **Banco de Dados**: PostgreSQL + SQLAlchemy
- **Frontend**: Bootstrap 5 + Bootstrap Icons
- **Gráficos**: Plotly.js
- **Migrações**: Flask-Migrate

## Melhorias Futuras

- [ ] Autenticação de usuários
- [ ] Exportação de dados (PDF, Excel)
- [ ] Importação de extratos bancários (OFX)
- [ ] Metas financeiras
- [ ] Alertas por email de vencimento
- [ ] Modo escuro
- [ ] Aplicativo mobile

## Suporte

Para problemas ou dúvidas, entre em contato ou abra uma issue no repositório.

## Licença

Este projeto é de uso pessoal. Sinta-se livre para modificar e adaptar às suas necessidades.
