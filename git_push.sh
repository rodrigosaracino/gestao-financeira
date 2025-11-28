#!/bin/bash
# Script para fazer commit e push para GitHub
# Execute no seu COMPUTADOR LOCAL

set -e

echo "=========================================="
echo "📤 GIT PUSH - Subindo código para GitHub"
echo "=========================================="
echo ""

# Verificar se tem mudanças
if [[ -z $(git status -s) ]]; then
    echo "✅ Nenhuma mudança para commitar"
    exit 0
fi

# Mostrar mudanças
echo "📝 Arquivos modificados:"
git status -s
echo ""

# Pedir mensagem de commit
read -p "💬 Digite a mensagem do commit: " COMMIT_MSG

if [ -z "$COMMIT_MSG" ]; then
    echo "❌ Mensagem de commit vazia!"
    exit 1
fi

# Git add, commit e push
echo ""
echo "📦 Fazendo commit..."
git add .
git commit -m "$COMMIT_MSG"

echo ""
echo "🚀 Fazendo push para GitHub..."
git push

echo ""
echo "=========================================="
echo "✅ CÓDIGO ENVIADO PARA GITHUB!"
echo "=========================================="
echo ""
echo "🎯 Próximo passo:"
echo "   Na VPS, execute: bash git_deploy.sh"
echo ""
echo "=========================================="
