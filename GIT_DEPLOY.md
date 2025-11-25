# 🚀 Deploy Simples via Git

## ⚡ Configuração Inicial (Faça UMA VEZ apenas)

### 1. Criar repositório no GitHub

1. Acesse https://github.com/new
2. Crie um repositório (pode ser privado)
3. **NÃO** inicialize com README

### 2. No seu computador (LOCAL)

```bash
cd gestao_financeira_app

# Inicializar Git (se ainda não foi)
git init

# Adicionar remote do GitHub (SUBSTITUA com seu repo)
git remote add origin https://github.com/seu_usuario/seu_repositorio.git

# Primeiro commit
git add .
git commit -m "Initial commit"
git push -u origin main
```

### 3. Na VPS (PRIMEIRA VEZ)

```bash
# Conectar na VPS
ssh seu_usuario@seu_servidor.com

# Clonar repositório
cd ~
git clone https://github.com/seu_usuario/seu_repositorio.git gestao_financeira_app
cd gestao_financeira_app

# Configurar .env (IMPORTANTE!)
cp .env.example .env
nano .env  # Edite com suas credenciais de produção

# Subir sistema pela primeira vez
docker-compose up -d
```

---

## 🔄 Deploy Diário (Sempre que atualizar)

### 1️⃣ No seu computador (LOCAL):

```bash
# Entre no diretório
cd gestao_financeira_app

# Execute o script
bash git_push.sh
```

O script vai:
- ✅ Mostrar arquivos modificados
- ✅ Pedir mensagem de commit
- ✅ Fazer commit e push para GitHub

### 2️⃣ Na VPS:

```bash
# Conectar na VPS
ssh seu_usuario@seu_servidor.com

# Entrar no diretório
cd ~/gestao_financeira_app

# Executar deploy
bash git_deploy.sh
```

O script vai **AUTOMATICAMENTE**:
- ✅ Fazer backup do banco de dados
- ✅ Baixar código atualizado (git pull)
- ✅ Executar migrations (se houver)
- ✅ Rebuild do Docker
- ✅ Reiniciar aplicação
- ✅ Verificar se está funcionando

---

## ⏱️ Tempo Total: ~3 minutos

```
┌─────────────┐
│ Seu PC      │  bash git_push.sh  (30 segundos)
└─────────────┘
       ↓
┌─────────────┐
│  GitHub     │  (Repositório)
└─────────────┘
       ↓
┌─────────────┐
│  VPS        │  bash git_deploy.sh  (2 minutos)
└─────────────┘
```

---

## 🔐 Segurança

### ✅ O que VAI para o GitHub:
- ✅ Código da aplicação
- ✅ Templates HTML
- ✅ CSS/JavaScript
- ✅ Configurações Docker
- ✅ Migrations

### ❌ O que NÃO vai para o GitHub:
- ❌ `.env` (senhas e chaves)
- ❌ `venv/` (ambiente virtual)
- ❌ `__pycache__/` (cache Python)
- ❌ Backups
- ❌ Banco de dados

---

## 🆘 Resolver Problemas Comuns

### Erro: "Your local changes would be overwritten"

```bash
# Na VPS
git stash  # Guarda mudanças locais
bash git_deploy.sh
```

### Erro: "Permission denied (publickey)"

```bash
# Configure SSH do GitHub na VPS
ssh-keygen -t ed25519 -C "seu_email@example.com"
cat ~/.ssh/id_ed25519.pub
# Adicione a chave em: https://github.com/settings/keys
```

### Erro: "Container não está rodando"

```bash
# Ver logs
docker-compose logs -f web

# Restart manual
docker-compose restart
```

---

## 📋 Checklist Rápido

Antes de cada deploy:

- [ ] ✅ Testei localmente?
- [ ] ✅ `bash git_push.sh` executado?
- [ ] ✅ Conectei na VPS?
- [ ] ✅ `bash git_deploy.sh` executado?
- [ ] ✅ Sistema funcionando?

---

## 🎯 Comandos Úteis na VPS

```bash
# Ver logs em tempo real
docker-compose logs -f web

# Ver status
docker-compose ps

# Restart rápido
docker-compose restart web

# Ver últimos backups
ls -lt ~/backups/ | head -n 5
```

---

## 💡 Dicas

1. **Sempre teste localmente** antes de fazer push
2. **Backups são automáticos** - não precisa se preocupar
3. **Commits pequenos e frequentes** são melhores
4. **Use mensagens de commit descritivas**

---

## 🎓 Exemplo Completo

```bash
# ============================
# NO SEU COMPUTADOR (LOCAL)
# ============================

cd gestao_financeira_app

# Fazer mudanças no código...
nano app/routes.py

# Testar localmente
docker-compose up -d

# Subir para GitHub
bash git_push.sh
# Digite: "Corrige bug nas faturas"

# ============================
# NA VPS
# ============================

ssh seu_usuario@seu_servidor.com
cd ~/gestao_financeira_app

# Deploy automático
bash git_deploy.sh

# ✅ PRONTO! Sistema atualizado
```

---

**É ISSO!** Super simples, rápido e seguro! 🚀

Para mais detalhes técnicos, veja: `DEPLOY_GUIDE.md`
