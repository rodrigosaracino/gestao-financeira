#!/bin/bash
# Script 2: Fazer backup na VPS
# Executa na VPS (servidor de produção)

set -e  # Para em caso de erro

echo "=========================================="
echo "💾 FAZENDO BACKUP DO SISTEMA"
echo "=========================================="

# Criar diretório de backup com timestamp
BACKUP_DIR=~/backups/$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo ""
echo "📁 Diretório de backup: $BACKUP_DIR"
echo ""

# 1. Backup do Banco de Dados
echo "🗄️  Fazendo backup do banco de dados..."

# Descobrir nome do container do PostgreSQL
POSTGRES_CONTAINER=$(docker ps --filter "ancestor=postgres:15-alpine" --format "{{.Names}}" | head -n 1)

if [ -z "$POSTGRES_CONTAINER" ]; then
    echo "❌ ERRO: Container PostgreSQL não encontrado!"
    exit 1
fi

echo "   Container: $POSTGRES_CONTAINER"

# Fazer dump do banco
docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres gestao_financeira > "$BACKUP_DIR/backup_db.sql"

# Verificar se backup foi criado
DB_SIZE=$(ls -lh "$BACKUP_DIR/backup_db.sql" | awk '{print $5}')
echo "   ✅ Backup do banco criado: $DB_SIZE"

# 2. Backup da Aplicação
echo ""
echo "📦 Fazendo backup da aplicação..."

cd ~
tar -czf "$BACKUP_DIR/backup_app.tar.gz" gestao_financeira_app/ 2>/dev/null || true

# Verificar se backup foi criado
APP_SIZE=$(ls -lh "$BACKUP_DIR/backup_app.tar.gz" | awk '{print $5}')
echo "   ✅ Backup da aplicação criado: $APP_SIZE"

# 3. Resumo
echo ""
echo "=========================================="
echo "✅ BACKUP CONCLUÍDO COM SUCESSO!"
echo "=========================================="
echo ""
echo "📊 Arquivos criados:"
echo "   - $BACKUP_DIR/backup_db.sql ($DB_SIZE)"
echo "   - $BACKUP_DIR/backup_app.tar.gz ($APP_SIZE)"
echo ""
echo "💡 IMPORTANTE: Baixe estes arquivos para sua máquina local:"
echo "   scp -r seu_usuario@seu_servidor.com:$BACKUP_DIR ~/Desktop/backup_producao/"
echo ""
echo "=========================================="
