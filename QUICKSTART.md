# Guia Rápido de Instalação

## Passo a Passo para Começar

### 1. Instale o PostgreSQL

**macOS** (usando Homebrew):
```bash
brew install postgresql
brew services start postgresql
```

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows**:
Baixe e instale de: https://www.postgresql.org/download/windows/

### 2. Crie o Banco de Dados

```bash
# Entre no PostgreSQL
psql -U postgres

# No prompt do PostgreSQL, execute:
CREATE DATABASE gestao_financeira;
\q
```

### 3. Configure o Projeto

```bash
# Navegue até o diretório do projeto
cd gestao_financeira_app

# Crie um ambiente virtual
python3 -m venv venv

# Ative o ambiente virtual
source venv/bin/activate  # macOS/Linux
# OU
venv\Scripts\activate  # Windows

# Instale as dependências
pip install -r requirements.txt
```

### 4. Configure as Variáveis de Ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o arquivo .env e ajuste a URL do banco:
# DATABASE_URL=postgresql://postgres:sua_senha@localhost:5432/gestao_financeira
```

Se você não definiu senha no PostgreSQL durante a instalação, use:
```
DATABASE_URL=postgresql://postgres@localhost:5432/gestao_financeira
```

### 5. Inicialize o Banco de Dados

```bash
# Crie as tabelas e adicione categorias padrão
python3 init_db.py
```

### 6. Execute o Sistema

```bash
# Inicie o servidor
python3 run.py
```

### 7. Acesse o Sistema

Abra seu navegador e acesse: **http://localhost:5000**

## Primeiros Passos no Sistema

1. **Crie uma conta bancária**
   - Vá em "Contas" > "Nova Conta"
   - Ex: Conta Corrente, Saldo inicial: R$ 1000,00

2. **Adicione uma transação**
   - Vá em "Transações" > "Nova Transação"
   - Ex: Salário de R$ 3000,00

3. **Cadastre um cartão de crédito**
   - Vá em "Cartões" > "Novo Cartão"
   - Ex: Visa, Limite R$ 5000,00

4. **Veja seus relatórios**
   - Vá em "Relatórios" para visualizar gráficos

## Problemas Comuns

### Erro de conexão com PostgreSQL
- Verifique se o PostgreSQL está rodando: `brew services list` (macOS) ou `sudo systemctl status postgresql` (Linux)
- Verifique a URL no arquivo `.env`

### Erro "No module named 'psycopg2'"
```bash
pip install psycopg2-binary
```

### Porta 5000 já em uso
Edite o arquivo `run.py` e mude a porta:
```python
app.run(debug=True, host='0.0.0.0', port=8000)
```

## Dúvidas?

Consulte o arquivo README.md para documentação completa.
