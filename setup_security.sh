#!/bin/bash
# ==================================================
# Script de Configuração de Segurança
# Sistema de Gestão Financeira
# ==================================================

set -e  # Parar em caso de erro

echo "=================================================="
echo "🔒 Configuração de Segurança - Gestão Financeira"
echo "=================================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para mensagens
error() {
    echo -e "${RED}❌ ERRO: $1${NC}"
    exit 1
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

info() {
    echo -e "ℹ️  $1"
}

# Verificar se está executando como root
if [ "$EUID" -eq 0 ]; then
    error "NÃO execute este script como root! Use um usuário normal."
fi

# 1. Verificar se .env existe
echo ""
info "Verificando arquivo .env..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        success ".env criado a partir de .env.example"
    else
        error "Arquivo .env.example não encontrado!"
    fi
else
    warning ".env já existe - mantendo arquivo atual"
fi

# 2. Gerar SECRET_KEY se necessário
echo ""
info "Verificando SECRET_KEY..."
if grep -q "SUBSTITUA_POR_UMA_CHAVE_FORTE" .env 2>/dev/null; then
    warning "SECRET_KEY padrão detectada - gerando nova chave..."
    NEW_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    # Usar sed de forma compatível com macOS e Linux
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=${NEW_SECRET_KEY}/" .env
    else
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=${NEW_SECRET_KEY}/" .env
    fi

    success "Nova SECRET_KEY gerada!"
else
    success "SECRET_KEY já configurada"
fi

# 3. Configurar permissões do .env
echo ""
info "Configurando permissões do .env..."
chmod 600 .env
success "Permissões do .env: 600 (somente leitura/escrita do proprietário)"

# 4. Criar diretório de logs
echo ""
info "Criando diretório de logs..."
if [ ! -d logs ]; then
    mkdir -p logs
    success "Diretório logs/ criado"
else
    success "Diretório logs/ já existe"
fi

# 5. Verificar dependências Python
echo ""
info "Verificando dependências Python..."
if [ -d venv ]; then
    if [ -f venv/bin/pip ]; then
        venv/bin/pip install --upgrade pip > /dev/null 2>&1
        venv/bin/pip install -r requirements.txt > /dev/null 2>&1
        success "Dependências instaladas/atualizadas"
    else
        error "Ambiente virtual corrompido. Delete 'venv' e execute novamente."
    fi
else
    info "Criando ambiente virtual..."
    python3 -m venv venv
    venv/bin/pip install --upgrade pip > /dev/null 2>&1
    venv/bin/pip install -r requirements.txt > /dev/null 2>&1
    success "Ambiente virtual criado e dependências instaladas"
fi

# 6. Verificar .gitignore
echo ""
info "Verificando .gitignore..."
if ! grep -q "^\.env$" .gitignore 2>/dev/null; then
    warning ".env não está no .gitignore - ADICIONANDO!"
    echo -e "\n# Environment files\n.env" >> .gitignore
    success ".env adicionado ao .gitignore"
else
    success ".env está protegido no .gitignore"
fi

# 7. Verificar configuração do banco de dados
echo ""
info "Verificando configuração do banco de dados..."
if grep -q "DATABASE_URL=postgresql" .env; then
    success "DATABASE_URL configurada"

    # Extrair informações do banco
    DB_URL=$(grep "^DATABASE_URL=" .env | cut -d'=' -f2-)
    if [[ $DB_URL == *"localhost"* ]] || [[ $DB_URL == *"127.0.0.1"* ]]; then
        info "Banco de dados: Local (desenvolvimento)"
    else
        warning "Banco de dados: Remoto (verifique conexão segura!)"
    fi
else
    warning "DATABASE_URL não configurada - configure manualmente!"
fi

# 8. Verificar FLASK_ENV
echo ""
info "Verificando FLASK_ENV..."
FLASK_ENV=$(grep "^FLASK_ENV=" .env | cut -d'=' -f2-)
if [ "$FLASK_ENV" = "production" ]; then
    warning "FLASK_ENV=production - modo de produção ativado"
    warning "Certifique-se de que SSL/HTTPS está configurado!"
else
    info "FLASK_ENV=$FLASK_ENV - modo de desenvolvimento"
fi

# 9. Checklist de segurança
echo ""
echo "=================================================="
echo "📋 CHECKLIST DE SEGURANÇA"
echo "=================================================="
echo ""

# Array para rastrear pendências
PENDING_ITEMS=0

# Verificar SECRET_KEY
if grep -q "SUBSTITUA_POR_UMA_CHAVE_FORTE\|dev-secret-key" .env; then
    echo -e "${RED}❌${NC} SECRET_KEY forte configurada"
    ((PENDING_ITEMS++))
else
    echo -e "${GREEN}✅${NC} SECRET_KEY forte configurada"
fi

# Verificar DATABASE_URL
if grep -q "SENHA_FORTE_AQUI\|sua_senha" .env; then
    echo -e "${RED}❌${NC} Senha do banco de dados configurada"
    ((PENDING_ITEMS++))
else
    echo -e "${GREEN}✅${NC} Senha do banco de dados configurada"
fi

# Verificar permissões .env
if [ "$(stat -f '%A' .env 2>/dev/null || stat -c '%a' .env 2>/dev/null)" = "600" ]; then
    echo -e "${GREEN}✅${NC} Permissões do .env seguras (600)"
else
    echo -e "${RED}❌${NC} Permissões do .env seguras (600)"
    ((PENDING_ITEMS++))
fi

# Verificar .gitignore
if grep -q "^\.env$" .gitignore 2>/dev/null; then
    echo -e "${GREEN}✅${NC} .env no .gitignore"
else
    echo -e "${RED}❌${NC} .env no .gitignore"
    ((PENDING_ITEMS++))
fi

# Verificar dependências
if [ -d venv ] && [ -f venv/bin/activate ]; then
    echo -e "${GREEN}✅${NC} Ambiente virtual configurado"
else
    echo -e "${RED}❌${NC} Ambiente virtual configurado"
    ((PENDING_ITEMS++))
fi

# Verificar logs
if [ -d logs ]; then
    echo -e "${GREEN}✅${NC} Diretório de logs criado"
else
    echo -e "${RED}❌${NC} Diretório de logs criado"
    ((PENDING_ITEMS++))
fi

echo ""
echo "=================================================="

if [ $PENDING_ITEMS -eq 0 ]; then
    echo -e "${GREEN}🎉 TUDO CONFIGURADO CORRETAMENTE!${NC}"
    echo ""
    echo "Próximos passos:"
    echo "1. Revise o arquivo .env e ajuste conforme necessário"
    echo "2. Execute as migrations: venv/bin/flask db upgrade"
    echo "3. Inicie o servidor: venv/bin/flask run"
    echo ""
    echo "📖 Para mais informações, leia SECURITY.md"
else
    echo -e "${YELLOW}⚠️  $PENDING_ITEMS ITEM(S) PRECISAM DE ATENÇÃO${NC}"
    echo ""
    echo "Revise os itens marcados com ❌ e configure manualmente."
    echo "Consulte SECURITY.md para instruções detalhadas."
fi

echo "=================================================="
