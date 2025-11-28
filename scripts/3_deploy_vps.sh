#!/bin/bash
# Script 3: Deploy na VPS
# Executa na VPS (servidor de produção)

set -e  # Para em caso de erro

echo "=========================================="
echo "🚀 INICIANDO DEPLOY"
echo "=========================================="

# Verificar se arquivo de deploy existe
DEPLOY_FILE=$(ls ~/deploy_*.tar.gz 2>/dev/null | tail -n 1)

if [ -z "$DEPLOY_FILE" ]; then
    echo "❌ ERRO: Arquivo de deploy não encontrado em ~/"
    echo "   Execute primeiro: scp deploy_*.tar.gz seu_usuario@seu_servidor.com:~/"
    exit 1
fi

echo ""
echo "📦 Arquivo de deploy: $DEPLOY_FILE"
echo ""

# Confirmar antes de continuar
read -p "⚠️  Você fez o BACKUP? (s/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo "❌ DEPLOY CANCELADO"
    echo "   Execute primeiro: bash 2_backup_vps.sh"
    exit 1
fi

# 1. Parar aplicação web (mantém banco de dados rodando)
echo ""
echo "🛑 Parando aplicação web..."
cd ~/gestao_financeira_app
docker-compose stop web
echo "   ✅ Aplicação web parada"

# 2. Extrair código atualizado
echo ""
echo "📂 Extraindo código atualizado..."
cd ~
mkdir -p temp_deploy
cd temp_deploy
tar -xzf "$DEPLOY_FILE"

# 3. Copiar arquivos atualizados
echo ""
echo "📋 Copiando arquivos..."
cp -r app ../gestao_financeira_app/
cp -r migrations ../gestao_financeira_app/
cp requirements.txt ../gestao_financeira_app/
cp docker-compose.yml ../gestao_financeira_app/
cp Dockerfile ../gestao_financeira_app/
cp config.py ../gestao_financeira_app/ 2>/dev/null || true
cp run.py ../gestao_financeira_app/ 2>/dev/null || true
cp init_db.py ../gestao_financeira_app/ 2>/dev/null || true
echo "   ✅ Arquivos copiados"

# 4. Voltar para diretório da aplicação
cd ~/gestao_financeira_app

# 5. Verificar migrations pendentes
echo ""
echo "🔄 Verificando migrations..."
CURRENT_MIGRATION=$(docker-compose run --rm web flask db current 2>&1 | tail -n 1)
echo "   Versão atual: $CURRENT_MIGRATION"

# Executar migrations se necessário
echo ""
read -p "🔄 Executar migrations? (s/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "   Executando migrations..."
    docker-compose run --rm web flask db upgrade
    echo "   ✅ Migrations executadas"
fi

# 6. Rebuild da imagem Docker
echo ""
echo "🔨 Rebuilding imagem Docker..."
docker-compose build web

if [ $? -eq 0 ]; then
    echo "   ✅ Build concluído com sucesso"
else
    echo "   ❌ ERRO no build!"
    echo "   Revertendo..."
    docker-compose up -d web
    exit 1
fi

# 7. Reiniciar aplicação
echo ""
echo "🚀 Reiniciando aplicação..."
docker-compose up -d web

# Aguardar inicialização
echo ""
echo "⏳ Aguardando inicialização (15 segundos)..."
sleep 15

# 8. Verificar se está rodando
echo ""
echo "🔍 Verificando status..."
if docker ps | grep -q gestao_financeira_app; then
    echo "   ✅ Container está rodando"

    # Testar resposta HTTP
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        echo "   ✅ Aplicação respondendo (HTTP $HTTP_CODE)"
    else
        echo "   ⚠️  Aplicação pode estar com problemas (HTTP $HTTP_CODE)"
    fi
else
    echo "   ❌ ERRO: Container não está rodando!"
    echo ""
    echo "📋 Últimos logs:"
    docker-compose logs --tail=30 web
    exit 1
fi

# 9. Limpar arquivos temporários
echo ""
echo "🧹 Limpando arquivos temporários..."
cd ~
rm -rf temp_deploy
echo "   ✅ Limpeza concluída"

# 10. Resumo final
echo ""
echo "=========================================="
echo "✅ DEPLOY CONCLUÍDO COM SUCESSO!"
echo "=========================================="
echo ""
echo "📊 Próximos passos:"
echo "   1. Verifique os logs: docker-compose logs -f web"
echo "   2. Teste o sistema acessando: http://seu_dominio.com"
echo "   3. Faça login e verifique se dados estão preservados"
echo "   4. Teste as novas funcionalidades"
echo ""
echo "💡 Em caso de problemas:"
echo "   - Logs: docker-compose logs web"
echo "   - Rollback: bash scripts/4_rollback_vps.sh"
echo ""
echo "=========================================="
