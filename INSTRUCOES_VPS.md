# 🎯 INSTRUÇÕES PARA ATUALIZAR NA VPS

## ✅ PRONTO! Código já está no GitHub!

Repositório: https://github.com/rodrigosaracino/gestao-financeira

---

## 🚀 Agora execute na VPS:

### 1️⃣ Conecte na VPS via SSH

```bash
ssh seu_usuario@seu_servidor_vps.com
```

### 2️⃣ Entre no diretório do projeto

```bash
cd gestao_financeira_app
# OU
cd ~/gestao_financeira_app
```

**Se o diretório não existir**, clone pela primeira vez:
```bash
cd ~
git clone https://github.com/rodrigosaracino/gestao-financeira.git gestao_financeira_app
cd gestao_financeira_app
```

### 3️⃣ Execute o script de deploy

```bash
bash git_deploy.sh
```

**O script vai automaticamente:**
- ✅ Fazer backup do banco de dados
- ✅ Baixar código atualizado do GitHub
- ✅ Executar migrations (se houver)
- ✅ Rebuild do Docker
- ✅ Reiniciar aplicação
- ✅ Verificar se está funcionando

### 4️⃣ Aguarde ~2 minutos

Você verá:
```
========================================
✅ DEPLOY CONCLUÍDO COM SUCESSO!
========================================
```

### 5️⃣ Verifique se está funcionando

**No navegador:**
```
http://seu_dominio.com
```

**OU veja os logs:**
```bash
docker-compose logs -f web
```

---

## 🆘 Se der algum erro:

### Erro: "git_deploy.sh not found"

O arquivo ainda não está na VPS. Baixe manualmente:

```bash
cd ~/gestao_financeira_app
git pull origin main
chmod +x git_deploy.sh
bash git_deploy.sh
```

### Erro: "Permission denied"

```bash
chmod +x git_deploy.sh
bash git_deploy.sh
```

### Erro: "Container não está rodando"

Veja os logs:
```bash
docker-compose logs --tail=50 web
```

E reinicie:
```bash
docker-compose restart
```

---

## 📞 Precisa de Ajuda?

1. **Copie os logs**: `docker-compose logs web > error.txt`
2. **Verifique o status**: `docker-compose ps`
3. **Último backup está em**: `~/backups/` (ordenado por data)

---

## ✨ O que foi atualizado nesta versão:

- ✅ **Bug corrigido**: Duplicação de transações parceladas
- ✅ **Bug corrigido**: Valores das faturas agora sempre corretos
- ✅ **Novo**: Campos banco emissor e número do cartão
- ✅ **Melhoria**: Código otimizado e mais limpo
- ✅ **Melhoria**: Deploy automático via Git
- ✅ **Melhoria**: Responsividade mobile aprimorada

---

**Tempo estimado**: 2-3 minutos
**Risco de perda de dados**: ❌ ZERO (backup automático)

🎉 **Bom deploy!**
