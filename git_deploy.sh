#!/bin/bash
# Script de deploy via Git
# Execute na VPS (servidor de produção)

set -e

echo "=========================================="
echo "🚀 GIT DEPLOY - Atualizando de Produção"
echo "=========================================="
echo ""

# Verificar se estamos no diretório correto
if [ ! -f "app.py" ] && [ ! -f "run.py" ]; then
    echo "❌ ERRO: Execute este script do diretório do projeto"
    exit 1
fi

# ========================================
# 1. BACKUP AUTOMÁTICO
# ========================================
echo "💾 Fazendo backup automático..."
BACKUP_DIR=~/backups/$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup do banco de dados
POSTGRES_CONTAINER=$(docker ps --filter "ancestor=postgres:15-alpine" --format "{{.Names}}" | head -n 1)
if [ -n "$POSTGRES_CONTAINER" ]; then
    docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres gestao_financeira > "$BACKUP_DIR/backup_db.sql"
    echo "   ✅ Backup do banco: $(ls -lh $BACKUP_DIR/backup_db.sql | awk '{print $5}')"
else
    echo "   ⚠️  Container PostgreSQL não encontrado"
fi

# ========================================
# 2. ATUALIZAR CÓDIGO DO GITHUB
# ========================================
echo ""
echo "📥 Baixando código atualizado do GitHub..."

# Verificar branch atual
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "   Branch: $CURRENT_BRANCH"

# Fazer pull
git pull origin $CURRENT_BRANCH

if [ $? -eq 0 ]; then
    echo "   ✅ Código atualizado"
else
    echo "   ❌ ERRO no git pull!"
    exit 1
fi

# ========================================
# 3. PARAR APLICAÇÃO WEB
# ========================================
echo ""
echo "🛑 Parando aplicação web..."
docker-compose stop web
echo "   ✅ Aplicação parada"

# ========================================
# 4. MIGRATIONS (se necessário)
# ========================================
echo ""
echo "🔄 Verificando migrations..."

# Verificar se há migrations pendentes
HAS_MIGRATIONS=$(docker-compose run --rm web flask db current 2>&1 | grep -c "head" || echo "0")

if [ "$HAS_MIGRATIONS" -gt 0 ]; then
    read -p "   Executar migrations? (S/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo "   Executando migrations..."
        docker-compose run --rm web flask db upgrade
        echo "   ✅ Migrations executadas"
    fi
else
    echo "   ✅ Nenhuma migration pendente"
fi

# ========================================
# 5. REBUILD DOCKER
# ========================================
echo ""
echo "🔨 Rebuilding imagem Docker..."
docker-compose build web --no-cache

if [ $? -eq 0 ]; then
    echo "   ✅ Build concluído"
else
    echo "   ❌ ERRO no build!"
    echo "   Revertendo..."
    docker-compose up -d web
    exit 1
fi

# ========================================
# 6. REINICIAR APLICAÇÃO
# ========================================
echo ""
echo "🚀 Reiniciando aplicação..."
docker-compose up -d

# Aguardar inicialização
echo "   Aguardando inicialização (15s)..."
sleep 15

# ========================================
# 7. VERIFICAR STATUS
# ========================================
echo ""
echo "🔍 Verificando status..."

# Verificar se container está rodando
if docker ps | grep -q gestao_financeira_app; then
    echo "   ✅ Container rodando"

    # Testar resposta HTTP
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo "   ✅ Aplicação respondendo (HTTP $HTTP_CODE)"
    else
        echo "   ⚠️  Status HTTP: $HTTP_CODE"
    fi
else
    echo "   ❌ ERRO: Container não está rodando!"
    echo ""
    echo "📋 Últimos logs:"
    docker-compose logs --tail=30 web
    exit 1
fi

# ========================================
# 8. RESUMO
# ========================================
echo ""
echo "=========================================="
echo "✅ DEPLOY CONCLUÍDO COM SUCESSO!"
echo "=========================================="
echo ""
echo "📊 Informações:"
echo "   - Backup em: $BACKUP_DIR"
echo "   - Branch: $CURRENT_BRANCH"
echo "   - Último commit: $(git log -1 --oneline)"
echo ""
echo "🔍 Comandos úteis:"
echo "   - Ver logs: docker-compose logs -f web"
echo "   - Status: docker-compose ps"
echo "   - Restart: docker-compose restart web"
echo ""
echo "=========================================="
