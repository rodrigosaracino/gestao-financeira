# 🚀 Guia de Deploy Seguro para Produção

## ⚠️ IMPORTANTE: LEIA ANTES DE COMEÇAR

Este guia garante que você possa atualizar o sistema em produção **SEM PERDER DADOS**.

---

## 📋 Pré-requisitos

- [ ] Acesso SSH à VPS
- [ ] Credenciais do banco de dados
- [ ] Backup local do código atualizado
- [ ] Pelo menos 30 minutos disponíveis

---

## 🔐 Etapa 1: Backup Completo (CRÍTICO)

### 1.1 Conectar na VPS

```bash
ssh seu_usuario@seu_servidor.com
```

### 1.2 Criar diretório de backup

```bash
mkdir -p ~/backups/$(date +%Y%m%d_%H%M%S)
cd ~/backups/$(date +%Y%m%d_%H%M%S)
```

### 1.3 Backup do Banco de Dados PostgreSQL

```bash
# Descobrir o nome do container do PostgreSQL
docker ps | grep postgres

# Fazer backup do banco (substitua CONTAINER_NAME)
docker exec CONTAINER_NAME pg_dump -U postgres gestao_financeira > backup_db.sql

# Verificar se backup foi criado
ls -lh backup_db.sql
```

**✅ CHECKPOINT**: O arquivo `backup_db.sql` deve ter sido criado e ter tamanho > 0

### 1.4 Backup dos Arquivos da Aplicação

```bash
# Voltar para o diretório home
cd ~

# Fazer backup de toda a aplicação
tar -czf backups/$(date +%Y%m%d_%H%M%S)/backup_app.tar.gz gestao_financeira_app/

# Verificar backup
ls -lh backups/*/backup_app.tar.gz
```

**✅ CHECKPOINT**: O arquivo `backup_app.tar.gz` deve ter sido criado

### 1.5 Baixar backups para sua máquina local (RECOMENDADO)

```bash
# No seu computador local (NÃO na VPS)
scp seu_usuario@seu_servidor.com:~/backups/*/backup_db.sql ~/Desktop/
scp seu_usuario@seu_servidor.com:~/backups/*/backup_app.tar.gz ~/Desktop/
```

---

## 📦 Etapa 2: Preparar Código Atualizado

### 2.1 Criar pacote de deploy

```bash
# No seu computador LOCAL, no diretório do projeto
cd "/Users/rodrigosaracino/Library/CloudStorage/GoogleDrive-rodrigosaracino@gmail.com/Meu Drive/Profissional/Gestão financeira/Arquivos/gestao_financeira_app"

# Criar arquivo com código atualizado
tar -czf deploy_$(date +%Y%m%d_%H%M%S).tar.gz \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  app/ \
  migrations/ \
  app.py \
  config.py \
  init_db.py \
  run.py \
  requirements.txt \
  Dockerfile \
  docker-compose.yml \
  .gitignore
```

### 2.2 Transferir para VPS

```bash
# Transferir arquivo
scp deploy_*.tar.gz seu_usuario@seu_servidor.com:~/
```

---

## 🔄 Etapa 3: Deploy na VPS

### 3.1 Conectar na VPS novamente

```bash
ssh seu_usuario@seu_servidor.com
```

### 3.2 Parar aplicação (mantém banco de dados rodando)

```bash
cd ~/gestao_financeira_app

# Parar APENAS o container da aplicação web
docker-compose stop web

# Verificar que o banco de dados ainda está rodando
docker ps | grep postgres
```

**✅ CHECKPOINT**: Apenas o container do PostgreSQL deve estar rodando

### 3.3 Extrair código atualizado

```bash
# Voltar para home
cd ~

# Criar diretório temporário
mkdir -p temp_deploy
cd temp_deploy

# Extrair arquivos
tar -xzf ../deploy_*.tar.gz

# Copiar arquivos atualizados (SOBRESCREVE código antigo, MAS MANTÉM DADOS)
cp -r app ../gestao_financeira_app/
cp -r migrations ../gestao_financeira_app/
cp requirements.txt ../gestao_financeira_app/
cp docker-compose.yml ../gestao_financeira_app/
cp Dockerfile ../gestao_financeira_app/

# Voltar para diretório da aplicação
cd ../gestao_financeira_app
```

### 3.4 Executar Migrations (se houver)

```bash
# Verificar se há migrations pendentes
docker-compose run --rm web flask db current

# Se houver migrations pendentes, executar:
docker-compose run --rm web flask db upgrade

# Verificar se migrations foram aplicadas
docker-compose run --rm web flask db current
```

### 3.5 Rebuild da imagem Docker

```bash
# Rebuild da imagem com código atualizado
docker-compose build web

# Verificar se build foi bem-sucedido
echo $?  # Deve retornar 0
```

### 3.6 Reiniciar aplicação

```bash
# Iniciar aplicação atualizada
docker-compose up -d web

# Verificar logs
docker-compose logs -f --tail=50 web
```

**✅ CHECKPOINT**: Procure por mensagens de erro nos logs. Deve aparecer:
- "Starting gunicorn"
- "Listening at: http://0.0.0.0:5000"

---

## ✅ Etapa 4: Verificação Pós-Deploy

### 4.1 Testar conectividade

```bash
# Testar se a aplicação responde
curl -I http://localhost:8080

# Deve retornar: HTTP/1.1 200 OK ou 302 Found
```

### 4.2 Verificar banco de dados

```bash
# Entrar no container da aplicação
docker exec -it gestao_financeira_app bash

# Dentro do container, executar Python
python3 << EOF
from app import create_app
from app.models import db, User, Transacao

app = create_app()
with app.app_context():
    print(f"Total de usuários: {User.query.count()}")
    print(f"Total de transações: {Transacao.query.count()}")
EOF

# Sair do container
exit
```

**✅ CHECKPOINT**: Os números devem estar corretos (não zerados)

### 4.3 Teste funcional via browser

1. Acesse seu domínio: `http://seu_dominio.com`
2. Faça login com usuário existente
3. Navegue pelas páginas principais
4. Verifique se transações e faturas aparecem corretamente

---

## 🆘 Plano de Rollback (Se Algo Der Errado)

### Se precisar voltar para versão anterior:

```bash
# 1. Parar containers
cd ~/gestao_financeira_app
docker-compose down

# 2. Restaurar código anterior
cd ~
rm -rf gestao_financeira_app
tar -xzf backups/*/backup_app.tar.gz

# 3. Restaurar banco de dados (SE NECESSÁRIO)
docker exec -i gestao_financeira_db psql -U postgres -c "DROP DATABASE gestao_financeira;"
docker exec -i gestao_financeira_db psql -U postgres -c "CREATE DATABASE gestao_financeira;"
docker exec -i gestao_financeira_db psql -U postgres gestao_financeira < backups/*/backup_db.sql

# 4. Reiniciar sistema
cd gestao_financeira_app
docker-compose up -d
```

---

## 📊 Checklist Final

Antes de considerar o deploy completo, verifique:

- [ ] ✅ Backups criados e baixados
- [ ] ✅ Código transferido para VPS
- [ ] ✅ Migrations executadas sem erros
- [ ] ✅ Aplicação iniciou sem erros nos logs
- [ ] ✅ Login funcionando
- [ ] ✅ Dados de usuários preservados
- [ ] ✅ Transações aparecem corretamente
- [ ] ✅ Faturas com valores corretos
- [ ] ✅ Novas funcionalidades testadas

---

## 🔍 Comandos Úteis de Diagnóstico

```bash
# Ver status de todos os containers
docker-compose ps

# Ver logs em tempo real
docker-compose logs -f

# Ver logs específicos da aplicação
docker-compose logs -f web

# Ver logs do banco de dados
docker-compose logs -f db

# Verificar uso de recursos
docker stats

# Listar volumes (onde estão os dados do banco)
docker volume ls
```

---

## 📞 Suporte

Se encontrar problemas:

1. **NÃO DELETE NADA** antes de pedir ajuda
2. Capture os logs: `docker-compose logs > error_logs.txt`
3. Verifique se os backups estão intactos
4. Use o plano de rollback se necessário

---

## 🎯 Dicas de Segurança

1. **Sempre** faça backup antes de qualquer mudança
2. **Nunca** delete backups antigos (mantenha pelo menos 3)
3. **Teste** em ambiente local antes de produção
4. **Monitore** os logs após o deploy por 24h
5. **Configure** backups automáticos diários

---

**Última atualização**: 2025-11-25
