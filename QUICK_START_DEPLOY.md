# ⚡ Guia Rápido de Deploy

## 🎯 Para fazer deploy AGORA (5 minutos):

### Passo 1: No seu computador (LOCAL)

```bash
# 1. Entre no diretório do projeto
cd "/Users/rodrigosaracino/Library/CloudStorage/GoogleDrive-rodrigosaracino@gmail.com/Meu Drive/Profissional/Gestão financeira/Arquivos/gestao_financeira_app"

# 2. Crie o pacote de deploy
bash scripts/1_criar_pacote_deploy.sh

# 3. Transfira para VPS (SUBSTITUA com seus dados)
scp deploy_*.tar.gz seu_usuario@seu_servidor.com:~/
```

### Passo 2: Na VPS (conecte via SSH)

```bash
# 1. Conecte na VPS
ssh seu_usuario@seu_servidor.com

# 2. Transfira os scripts (primeira vez apenas)
# No seu computador LOCAL, execute:
scp -r scripts/ seu_usuario@seu_servidor.com:~/

# 3. Na VPS, faça BACKUP
cd ~
bash scripts/2_backup_vps.sh

# 4. Baixe o backup para sua máquina (IMPORTANTE!)
# No seu computador LOCAL, execute:
mkdir -p ~/Desktop/backup_producao
scp -r seu_usuario@seu_servidor.com:~/backups/* ~/Desktop/backup_producao/

# 5. Na VPS, faça o deploy
bash scripts/3_deploy_vps.sh
```

### Passo 3: Verificar

```bash
# Teste se está funcionando
curl -I http://localhost:8080

# Veja os logs
docker-compose logs -f web

# Teste no navegador
# Acesse: http://seu_dominio.com
```

---

## 🆘 Se algo der errado

```bash
# Na VPS, execute:
bash scripts/4_rollback_vps.sh
```

---

## 📋 Checklist Rápido

- [ ] ✅ Backup feito e baixado para máquina local
- [ ] ✅ Deploy executado sem erros
- [ ] ✅ Aplicação respondendo (HTTP 200 ou 302)
- [ ] ✅ Login funciona
- [ ] ✅ Dados de usuários preservados
- [ ] ✅ Transações aparecem
- [ ] ✅ Novas funcionalidades testadas

---

## 🔍 Comandos Úteis

```bash
# Ver status
docker-compose ps

# Ver logs em tempo real
docker-compose logs -f web

# Reiniciar apenas web
docker-compose restart web

# Ver último backup
ls -lt ~/backups/ | head -n 2
```

---

## ⚠️ LEMBRE-SE

1. **SEMPRE** faça backup antes
2. **SEMPRE** baixe o backup para sua máquina
3. **SEMPRE** teste após o deploy
4. **NÃO ENTRE EM PÂNICO** - você tem rollback!

---

Para instruções detalhadas, consulte: **DEPLOY_GUIDE.md**
