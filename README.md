# 💰 Sistema de Gestão Financeira

Sistema completo de gestão financeira pessoal desenvolvido com Flask, PostgreSQL e Bootstrap 5.

## 🚀 Deploy Rápido em Produção

### Deploy via Git (RECOMENDADO) ⚡

```bash
# 1. No seu computador
bash git_push.sh

# 2. Na VPS
bash git_deploy.sh
```

📖 **Guia completo**: [GIT_DEPLOY.md](GIT_DEPLOY.md) | [QUICK_START_DEPLOY.md](QUICK_START_DEPLOY.md)

## Funcionalidades

- **Autenticação de Usuários**: Sistema completo de registro e login com isolamento de dados por usuário
- **Gestão de Contas Bancárias**: Controle de contas correntes, poupança e outras
- **Transações Financeiras**: Registro de receitas e despesas com categorização
- **Transações Recorrentes**: Criação automática de transações recorrentes (semanal, mensal, etc.)
- **Cartões de Crédito**: Gestão completa de cartões com controle de limite
- **Compras Parceladas**: Parcelamento automático com geração de faturas mensais
- **Faturas de Cartão**: Controle detalhado de faturas com data de vencimento
- **Categorias Personalizadas**: Criação de categorias por usuário com cores customizadas
- **Dashboard Interativo**: Visão geral com gráficos e projeção de fluxo de caixa
- **Relatórios**: Gráficos de gastos por categoria e fluxo de caixa anual

## Tecnologias Utilizadas

- **Backend**: Python 3.11, Flask
- **Banco de Dados**: PostgreSQL 15
- **ORM**: SQLAlchemy com Flask-Migrate
- **Autenticação**: Flask-Login
- **Frontend**: Bootstrap 5, Plotly.js para gráficos
- **Containerização**: Docker e Docker Compose

## Requisitos

- Docker e Docker Compose (recomendado)
- OU Python 3.11+ e PostgreSQL 15+

## Instalação e Execução

### Opção 1: Usando Docker (Recomendado)

1. Clone o repositório:
```bash
git clone <repository-url>
cd gestao_financeira_app
```

2. Inicie os containers:
```bash
docker-compose up -d
```

3. Acesse a aplicação em: http://localhost:5000

### Opção 2: Instalação Local

1. Clone o repositório:
```bash
git clone <repository-url>
cd gestao_financeira_app
```

2. Crie e ative um ambiente virtual:
```bash
python3 -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Configure as variáveis de ambiente:
```bash
export DATABASE_URL="postgresql://usuario:senha@localhost:5432/gestao_financeira"
export SECRET_KEY="sua-chave-secreta-aqui"
```

5. Execute as migrações:
```bash
flask db upgrade
```

6. Inicie a aplicação:
```bash
python run.py
```

7. Acesse a aplicação em: http://localhost:8000

## Configuração

### Variáveis de Ambiente

- `DATABASE_URL`: URL de conexão com o PostgreSQL
- `SECRET_KEY`: Chave secreta para sessões Flask
- `FLASK_ENV`: Ambiente de execução (development/production)

### Primeiro Acesso

Ao executar pela primeira vez, você pode criar um novo usuário através da tela de registro em `/registro`.

Alternativamente, existe um usuário padrão criado pela migração:
- Email: admin@admin.com
- Senha: 123456

**IMPORTANTE**: Altere a senha padrão em produção!

## Estrutura do Projeto

```
gestao_financeira_app/
├── app/
│   ├── __init__.py          # Inicialização da aplicação Flask
│   ├── models.py            # Modelos do banco de dados
│   ├── routes.py            # Rotas da aplicação
│   ├── auth.py              # Autenticação de usuários
│   ├── static/              # Arquivos estáticos (CSS, JS, imagens)
│   └── templates/           # Templates HTML
├── migrations/              # Migrações do banco de dados
├── config.py               # Configurações da aplicação
├── run.py                  # Arquivo principal de execução
├── requirements.txt        # Dependências Python
├── Dockerfile             # Configuração Docker
├── docker-compose.yml     # Orquestração de containers
└── README.md              # Este arquivo
```

## Comandos Úteis do Docker

```bash
# Iniciar os containers
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar os containers
docker-compose down

# Reconstruir as imagens
docker-compose build

# Executar migrações
docker-compose exec web flask db upgrade

# Acessar o shell do Python na aplicação
docker-compose exec web python
```

## Desenvolvimento

Para desenvolvimento local, é recomendado usar o modo debug do Flask:

```bash
export FLASK_ENV=development
python run.py
```

A aplicação irá recarregar automaticamente ao detectar mudanças no código.

## Segurança

- Senhas são hasheadas usando Werkzeug Security
- Sessões protegidas com chave secreta
- Isolamento completo de dados entre usuários
- Validação de propriedade de recursos em todas as rotas
- Proteção contra SQL injection através do SQLAlchemy ORM

## Licença

Este projeto é de código aberto e está disponível sob a licença MIT.

## Contribuindo

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## Autor

Desenvolvido com Claude Code
