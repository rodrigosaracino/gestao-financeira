# 🚀 Deploy Rápido e Seguro - VPS

## ⚡ Guia de Deploy em 10 Passos

Este guia cobre o deploy seguro do Sistema de Gestão Financeira em um VPS (Hostinger, DigitalOcean, AWS, etc).

---

## 📋 Pré-requisitos

- VPS com Ubuntu 20.04+ ou Debian 11+
- Acesso root ou sudo
- Domínio apontando para o IP do servidor
- PostgreSQL instalado

---

## 🔟 Passos do Deploy

### 1️⃣ Atualizar Sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv postgresql nginx certbot python3-certbot-nginx git ufw
```

### 2️⃣ Configurar Firewall

```bash
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable
sudo ufw status
```

### 3️⃣ Criar Usuário da Aplicação

```bash
sudo adduser --system --group --home /opt/gestaofinanceira gestaofinanceira
sudo mkdir -p /opt/gestaofinanceira
```

### 4️⃣ Configurar PostgreSQL

```bash
sudo -u postgres psql
```

```sql
-- No prompt do PostgreSQL:
CREATE USER gestaofinanceira WITH PASSWORD 'SENHA_FORTE_AQUI_MIN_16_CHARS';
CREATE DATABASE gestao_financeira OWNER gestaofinanceira;
GRANT ALL PRIVILEGES ON DATABASE gestao_financeira TO gestaofinanceira;
\q
```

**Gere senha forte:**
```bash
openssl rand -base64 24
```

### 5️⃣ Deploy da Aplicação

```bash
# Clone o repositório
cd /opt/gestaofinanceira
sudo git clone <URL_DO_REPOSITORIO> app
sudo chown -R gestaofinanceira:gestaofinanceira app

# Entre no diretório
cd app

# Crie ambiente virtual
sudo -u gestaofinanceira python3 -m venv venv

# Ative e instale dependências
sudo -u gestaofinanceira venv/bin/pip install --upgrade pip
sudo -u gestaofinanceira venv/bin/pip install -r requirements.txt
```

### 6️⃣ Configurar .env

```bash
# Copie o template
sudo -u gestaofinanceira cp .env.example .env

# Gere SECRET_KEY
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "SECRET_KEY gerada: $SECRET_KEY"

# Edite .env
sudo -u gestaofinanceira nano .env
```

**Configure no .env:**
```bash
SECRET_KEY=<cole_a_chave_gerada_acima>
DATABASE_URL=postgresql://gestaofinanceira:SENHA_DO_BANCO@localhost:5432/gestao_financeira
FLASK_ENV=production
FLASK_APP=run.py
```

**Proteja o arquivo:**
```bash
sudo chmod 600 .env
```

### 7️⃣ Executar Migrations

```bash
sudo -u gestaofinanceira venv/bin/flask db upgrade
```

### 8️⃣ Configurar Systemd

```bash
sudo nano /etc/systemd/system/gestao-financeira.service
```

**Cole este conteúdo:**
```ini
[Unit]
Description=Sistema de Gestão Financeira
After=network.target postgresql.service

[Service]
Type=notify
User=gestaofinanceira
Group=gestaofinanceira
WorkingDirectory=/opt/gestaofinanceira/app
Environment="PATH=/opt/gestaofinanceira/app/venv/bin"
ExecStart=/opt/gestaofinanceira/app/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/gestao-financeira/access.log \
    --error-logfile /var/log/gestao-financeira/error.log \
    run:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Inicie o serviço:**
```bash
# Criar diretório de logs
sudo mkdir -p /var/log/gestao-financeira
sudo chown gestaofinanceira:gestaofinanceira /var/log/gestao-financeira

# Habilitar e iniciar
sudo systemctl daemon-reload
sudo systemctl enable gestao-financeira
sudo systemctl start gestao-financeira
sudo systemctl status gestao-financeira
```

### 9️⃣ Configurar Nginx

```bash
sudo nano /etc/nginx/sites-available/gestao-financeira
```

**Cole este conteúdo (AJUSTE seudominio.com):**
```nginx
server {
    listen 80;
    server_name seudominio.com www.seudominio.com;

    # Tamanho máximo de upload
    client_max_body_size 16M;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    location / {
        limit_req zone=login burst=10 nodelay;

        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Security headers básicos (Talisman adiciona mais)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

**Ative o site:**
```bash
sudo ln -s /etc/nginx/sites-available/gestao-financeira /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 🔟 Configurar SSL (HTTPS)

```bash
# Obter certificado Let's Encrypt
sudo certbot --nginx -d seudominio.com -d www.seudominio.com

# Testar renovação automática
sudo certbot renew --dry-run
```

---

## ✅ Verificação Pós-Deploy

### 1. Testar Aplicação

```bash
# Verificar se está rodando
curl http://localhost:5000

# Verificar logs
sudo journalctl -u gestao-financeira -n 50

# Verificar logs da aplicação
tail -f /opt/gestaofinanceira/app/logs/gestao_financeira.log
```

### 2. Testar HTTPS

```bash
# Deve retornar 200
curl -I https://seudominio.com

# Verificar headers de segurança
curl -I https://seudominio.com | grep -i "x-frame\|x-content\|strict-transport"
```

### 3. Testar Rate Limiting

```bash
# Executar 15 vezes - deve começar a bloquear
for i in {1..15}; do curl -I https://seudominio.com/login; done
```

---

## 🔧 Comandos Úteis

### Gerenciar Serviço

```bash
# Parar
sudo systemctl stop gestao-financeira

# Iniciar
sudo systemctl start gestao-financeira

# Reiniciar
sudo systemctl restart gestao-financeira

# Ver logs
sudo journalctl -u gestao-financeira -f

# Ver status
sudo systemctl status gestao-financeira
```

### Atualizar Aplicação

```bash
cd /opt/gestaofinanceira/app
sudo -u gestaofinanceira git pull
sudo -u gestaofinanceira venv/bin/pip install -r requirements.txt
sudo -u gestaofinanceira venv/bin/flask db upgrade
sudo systemctl restart gestao-financeira
```

### Backup

```bash
# Backup do banco
sudo -u postgres pg_dump gestao_financeira > backup_$(date +%Y%m%d).sql

# Backup dos arquivos
sudo tar -czf backup_app_$(date +%Y%m%d).tar.gz /opt/gestaofinanceira/app
```

---

## 🛡️ Segurança Adicional

### 1. Configurar fail2ban

```bash
sudo apt install fail2ban

# Criar filtro
sudo nano /etc/fail2ban/filter.d/gestao-financeira.conf
```

```ini
[Definition]
failregex = ^.* Tentativa de login falhada de <HOST>
            ^.* IP bloqueado: <HOST>
ignoreregex =
```

```bash
# Criar jail
sudo nano /etc/fail2ban/jail.d/gestao-financeira.conf
```

```ini
[gestao-financeira]
enabled = true
port = http,https
filter = gestao-financeira
logpath = /opt/gestaofinanceira/app/logs/security.log
maxretry = 5
bantime = 3600
findtime = 600
```

```bash
sudo systemctl restart fail2ban
```

### 2. Configurar Logrotate

```bash
sudo nano /etc/logrotate.d/gestao-financeira
```

```
/opt/gestaofinanceira/app/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 gestaofinanceira gestaofinanceira
    sharedscripts
    postrotate
        systemctl reload gestao-financeira
    endscript
}
```

### 3. Desabilitar Login Root via SSH

```bash
sudo nano /etc/ssh/sshd_config
```

Adicione/modifique:
```
PermitRootLogin no
PasswordAuthentication no  # Apenas se usar chaves SSH
```

```bash
sudo systemctl restart ssh
```

---

## 🆘 Troubleshooting

### Aplicação não inicia

```bash
# Ver logs detalhados
sudo journalctl -u gestao-financeira -n 100 --no-pager

# Verificar permissões
ls -la /opt/gestaofinanceira/app/

# Testar manualmente
cd /opt/gestaofinanceira/app
sudo -u gestaofinanceira venv/bin/gunicorn run:app
```

### Erro 502 Bad Gateway

```bash
# Verificar se aplicação está rodando
sudo systemctl status gestao-financeira

# Verificar porta
sudo netstat -tlnp | grep 5000

# Ver logs do Nginx
sudo tail -f /var/log/nginx/error.log
```

### Erro de Banco de Dados

```bash
# Testar conexão
sudo -u gestaofinanceira psql -h localhost -U gestaofinanceira -d gestao_financeira

# Verificar .env
cat /opt/gestaofinanceira/app/.env | grep DATABASE_URL

# Executar migrations
cd /opt/gestaofinanceira/app
sudo -u gestaofinanceira venv/bin/flask db upgrade
```

---

## 📊 Monitoramento

### Comandos de Monitoramento

```bash
# CPU e Memória
htop

# Espaço em disco
df -h

# Logs em tempo real
tail -f /opt/gestaofinanceira/app/logs/security.log

# Conexões ativas
sudo netstat -an | grep :5000

# IPs bloqueados (fail2ban)
sudo fail2ban-client status gestao-financeira
```

---

## 🎯 Checklist Final

- [ ] Aplicação rodando sem erros
- [ ] HTTPS funcionando (certificado válido)
- [ ] Headers de segurança presentes
- [ ] Rate limiting ativo
- [ ] Logs funcionando
- [ ] Backup configurado
- [ ] fail2ban configurado
- [ ] Firewall ativo
- [ ] PostgreSQL com senha forte
- [ ] .env com permissões 600
- [ ] SECRET_KEY forte configurada
- [ ] Domínio apontando corretamente

---

## 📚 Próximos Passos

1. Configure monitoramento (Uptime Robot, Pingdom)
2. Configure backup automático diário
3. Configure alertas por email
4. Revise logs semanalmente
5. Atualize sistema mensalmente

---

## 📞 Suporte

- **Documentação completa:** `SECURITY.md`
- **Melhorias implementadas:** `SECURITY_IMPROVEMENTS.md`
- **Script de verificação:** `./setup_security.sh`

---

**Tempo estimado:** 30-45 minutos
**Dificuldade:** Intermediário
**Última atualização:** 2025-01-27
