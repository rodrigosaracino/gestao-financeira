#!/bin/bash
# Script 4: Rollback (Reverter deploy)
# Executa na VPS (servidor de produção)
# ⚠️  Use apenas se o deploy falhou!

set -e  # Para em caso de erro

echo "=========================================="
echo "⚠️  INICIANDO ROLLBACK"
echo "=========================================="
echo ""
echo "🚨 ATENÇÃO: Este script vai reverter para a versão anterior!"
echo ""

# Confirmar antes de continuar
read -p "Tem certeza que deseja fazer ROLLBACK? (s/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "❌ ROLLBACK CANCELADO"
    exit 1
fi

# Encontrar backup mais recente
LATEST_BACKUP=$(ls -td ~/backups/*/ 2>/dev/null | head -n 1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ ERRO: Nenhum backup encontrado!"
    exit 1
fi

echo ""
echo "📦 Backup encontrado: $LATEST_BACKUP"
echo ""

# 1. Parar todos os containers
echo "🛑 Parando containers..."
cd ~/gestao_financeira_app
docker-compose down
echo "   ✅ Containers parados"

# 2. Confirmar restauração do banco
echo ""
read -p "⚠️  Restaurar BANCO DE DADOS também? (s/N): " -n 1 -r
echo

RESTORE_DB=false
if [[ $REPLY =~ ^[Ss]$ ]]; then
    RESTORE_DB=true
fi

# 3. Restaurar código
echo ""
echo "📂 Restaurando código anterior..."
cd ~
rm -rf gestao_financeira_app
tar -xzf "${LATEST_BACKUP}backup_app.tar.gz"
echo "   ✅ Código restaurado"

# 4. Restaurar banco de dados (se confirmado)
if [ "$RESTORE_DB" = true ]; then
    echo ""
    echo "🗄️  Restaurando banco de dados..."
    echo "   ⚠️  ATENÇÃO: Isso vai APAGAR todos os dados novos!"
    read -p "   Confirmar restauração do banco? (s/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Ss]$ ]]; then
        # Descobrir nome do container do PostgreSQL
        docker-compose -f ~/gestao_financeira_app/docker-compose.yml up -d db
        sleep 5

        POSTGRES_CONTAINER=$(docker ps --filter "ancestor=postgres:15-alpine" --format "{{.Names}}" | head -n 1)

        # Dropar e recriar banco
        docker exec "$POSTGRES_CONTAINER" psql -U postgres -c "DROP DATABASE IF EXISTS gestao_financeira;"
        docker exec "$POSTGRES_CONTAINER" psql -U postgres -c "CREATE DATABASE gestao_financeira;"

        # Restaurar backup
        docker exec -i "$POSTGRES_CONTAINER" psql -U postgres gestao_financeira < "${LATEST_BACKUP}backup_db.sql"

        echo "   ✅ Banco de dados restaurado"
    fi
fi

# 5. Reiniciar sistema
echo ""
echo "🚀 Reiniciando sistema..."
cd ~/gestao_financeira_app
docker-compose up -d

# Aguardar inicialização
echo ""
echo "⏳ Aguardando inicialização (20 segundos)..."
sleep 20

# 6. Verificar status
echo ""
echo "🔍 Verificando status..."
if docker ps | grep -q gestao_financeira; then
    echo "   ✅ Sistema restaurado e rodando"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo "   ✅ Aplicação respondendo (HTTP $HTTP_CODE)"
    fi
else
    echo "   ❌ ERRO: Sistema não está rodando!"
    docker-compose logs --tail=30
    exit 1
fi

# 7. Resumo
echo ""
echo "=========================================="
echo "✅ ROLLBACK CONCLUÍDO"
echo "=========================================="
echo ""
echo "📊 Sistema revertido para backup de:"
echo "   $LATEST_BACKUP"
echo ""
echo "💡 Próximos passos:"
echo "   1. Verifique os logs: docker-compose logs -f"
echo "   2. Teste o sistema"
echo "   3. Investigue o que causou o problema"
echo ""
echo "=========================================="
