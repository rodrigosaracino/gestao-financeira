#!/bin/bash
# Script 1: Criar pacote de deploy
# Executa na máquina LOCAL

set -e  # Para em caso de erro

echo "=========================================="
echo "📦 CRIANDO PACOTE DE DEPLOY"
echo "=========================================="

# Verificar se estamos no diretório correto
if [ ! -f "run.py" ]; then
    echo "❌ ERRO: Execute este script do diretório raiz do projeto"
    exit 1
fi

# Criar nome do arquivo com timestamp
DEPLOY_FILE="deploy_$(date +%Y%m%d_%H%M%S).tar.gz"

echo ""
echo "🔨 Criando arquivo: $DEPLOY_FILE"
echo ""

# Criar arquivo tar.gz excluindo arquivos desnecessários
tar -czf "$DEPLOY_FILE" \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.tar.gz' \
  --exclude='backups' \
  --exclude='scripts' \
  app/ \
  migrations/ \
  config.py \
  init_db.py \
  run.py \
  requirements.txt \
  Dockerfile \
  docker-compose.yml \
  .gitignore

# Verificar se arquivo foi criado
if [ -f "$DEPLOY_FILE" ]; then
    SIZE=$(ls -lh "$DEPLOY_FILE" | awk '{print $5}')
    echo "✅ Pacote criado com sucesso!"
    echo "   Arquivo: $DEPLOY_FILE"
    echo "   Tamanho: $SIZE"
    echo ""
    echo "📋 Próximo passo:"
    echo "   Transfira este arquivo para sua VPS usando:"
    echo "   scp $DEPLOY_FILE seu_usuario@seu_servidor.com:~/"
    echo ""
else
    echo "❌ ERRO: Falha ao criar pacote"
    exit 1
fi

echo "=========================================="
