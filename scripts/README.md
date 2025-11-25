# 🚀 Scripts de Deploy

Scripts automatizados para fazer deploy seguro em produção.

## 📋 Ordem de Execução

### 1️⃣ No seu computador LOCAL:

```bash
# Criar pacote de deploy
bash scripts/1_criar_pacote_deploy.sh

# Transferir para VPS
scp deploy_*.tar.gz seu_usuario@seu_servidor.com:~/
```

### 2️⃣ Na VPS (Servidor de Produção):

```bash
# Primeiro: fazer BACKUP (OBRIGATÓRIO!)
bash 2_backup_vps.sh

# Depois: fazer deploy
bash 3_deploy_vps.sh
```

### 🆘 Se algo der errado:

```bash
# Reverter para versão anterior
bash 4_rollback_vps.sh
```

---

## 📝 Descrição dos Scripts

### `1_criar_pacote_deploy.sh` (LOCAL)
- Cria arquivo `.tar.gz` com código atualizado
- Exclui automaticamente arquivos desnecessários
- Gera nome com timestamp

### `2_backup_vps.sh` (VPS)
- Faz backup completo do banco de dados PostgreSQL
- Faz backup de todos os arquivos da aplicação
- **SEMPRE execute antes do deploy!**

### `3_deploy_vps.sh` (VPS)
- Para aplicação web (mantém banco rodando)
- Atualiza código fonte
- Executa migrations (se necessário)
- Rebuild da imagem Docker
- Reinicia aplicação
- Verifica se está funcionando

### `4_rollback_vps.sh` (VPS - EMERGÊNCIA)
- Reverte para versão anterior
- Pode restaurar banco de dados também
- Use apenas se deploy falhou

---

## ⚠️ IMPORTANTE

1. **SEMPRE** faça backup antes do deploy
2. **TESTE** o sistema após o deploy
3. **MANTENHA** os backups por pelo menos 7 dias
4. **NÃO DELETE** backups sem necessidade

---

## 🔐 Permissões

Para tornar os scripts executáveis:

```bash
chmod +x scripts/*.sh
```

---

## 📞 Suporte

Em caso de dúvidas ou problemas:
1. Verifique os logs: `docker-compose logs -f`
2. Consulte o DEPLOY_GUIDE.md
3. Use o rollback se necessário

---

**Última atualização**: 2025-11-25
