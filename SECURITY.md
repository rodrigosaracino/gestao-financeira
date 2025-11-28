# Guia de Segurança - Sistema de Gestão Financeira

## 📋 Índice
1. [Medidas de Segurança Implementadas](#medidas-de-segurança-implementadas)
2. [Configuração Segura](#configuração-segura)
3. [Deploy Seguro](#deploy-seguro)
4. [Monitoramento e Logs](#monitoramento-e-logs)
5. [Manutenção de Segurança](#manutenção-de-segurança)
6. [Checklist de Segurança](#checklist-de-segurança)

---

## 🛡️ Medidas de Segurança Implementadas

### 1. Proteção CSRF (Cross-Site Request Forgery)
- **Flask-WTF CSRF Protection** ativado em todos os formulários
- Tokens CSRF validados automaticamente
- Proteção para requisições AJAX

### 2. Proteção XSS (Cross-Site Scripting)
- Sanitização de todos os inputs do usuário com `bleach`
- Headers de segurança configurados (X-XSS-Protection)
- Content Security Policy (CSP) implementado
- Escape automático de templates Jinja2

### 3. Proteção SQL Injection
- SQLAlchemy ORM com prepared statements
- Validação adicional de inputs
- Detecção de padrões de SQL injection

### 4. Proteção Contra Força Bruta
- Rate limiting em rotas de login (10 tentativas/minuto)
- Rate limiting em registro (5 tentativas/hora)
- Bloqueio automático de IP após 5 tentativas falhadas
- Timeout de 15 minutos para desbloqueio

### 5. Headers de Segurança HTTP
```
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: (configurado)
```

### 6. Segurança de Sessão
- Cookies seguros (HttpOnly, Secure em produção, SameSite)
- Timeout de sessão: 1 hora
- Regeneração de sessão após login

### 7. Autenticação Segura
- Senhas hasheadas com Werkzeug (PBKDF2 + salt)
- Requisitos de senha forte:
  - Mínimo 8 caracteres
  - Letras maiúsculas e minúsculas
  - Números
- Validação de email
- Proteção contra Open Redirect

### 8. Sistema de Logs
- Logs de segurança separados (`logs/security.log`)
- Registro de tentativas de login
- Detecção de atividades suspeitas
- Rotação automática de logs

### 9. Upload de Arquivos
- Extensões permitidas: `.ofx`, `.csv`, `.txt`
- Tamanho máximo: 16MB
- Validação de tipo MIME
- Sanitização de nomes de arquivo

### 10. Isolamento de Usuários
- Queries com filtro `user_id`
- Verificação de ownership em todas as operações
- Proteção contra acesso não autorizado

---

## ⚙️ Configuração Segura

### 1. Variáveis de Ambiente

**CRÍTICO**: Configure o arquivo `.env` corretamente

```bash
# Copie o exemplo
cp .env.example .env

# Edite o arquivo
nano .env

# Configure permissões seguras
chmod 600 .env
```

**Gere uma SECRET_KEY forte:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Banco de Dados

**PostgreSQL - Configuração Segura:**

```sql
-- Crie usuário específico para a aplicação
CREATE USER gestao_financeira WITH PASSWORD 'SENHA_FORTE_AQUI';

-- Crie o banco
CREATE DATABASE gestao_financeira OWNER gestao_financeira;

-- Garanta permissões mínimas
GRANT CONNECT ON DATABASE gestao_financeira TO gestao_financeira;
GRANT USAGE ON SCHEMA public TO gestao_financeira;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gestao_financeira;
```

**Senha do PostgreSQL:**
- Mínimo 16 caracteres
- Letras maiúsculas, minúsculas, números e símbolos
- Gerador: `openssl rand -base64 24`

### 3. Firewall (UFW)

```bash
# Habilitar UFW
sudo ufw enable

# Permitir apenas portas necessárias
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 5432/tcp from 127.0.0.1  # PostgreSQL (apenas local)

# Verificar status
sudo ufw status verbose
```

### 4. SSL/TLS (HTTPS)

**Usando Certbot (Let's Encrypt):**

```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx

# Obter certificado
sudo certbot --nginx -d seudominio.com

# Auto-renovação
sudo certbot renew --dry-run
```

### 5. Nginx - Configuração Segura

```nginx
server {
    listen 443 ssl http2;
    server_name seudominio.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seudominio.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    limit_req zone=login burst=10 nodelay;

    # Tamanho máximo de upload
    client_max_body_size 16M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirecionar HTTP para HTTPS
server {
    listen 80;
    server_name seudominio.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 🚀 Deploy Seguro

### 1. Preparação do Servidor

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependências
sudo apt install -y python3 python3-pip python3-venv postgresql nginx

# Criar usuário para aplicação (não use root!)
sudo adduser --system --group gestaofinanceira
```

### 2. Deploy da Aplicação

```bash
# Clone o repositório
cd /opt
sudo git clone <repo-url> gestao_financeira
sudo chown -R gestaofinanceira:gestaofinanceira gestao_financeira

# Entre no diretório
cd gestao_financeira

# Crie ambiente virtual
sudo -u gestaofinanceira python3 -m venv venv

# Ative e instale dependências
sudo -u gestaofinanceira venv/bin/pip install -r requirements.txt

# Configure .env
sudo -u gestaofinanceira cp .env.example .env
sudo -u gestaofinanceira nano .env
sudo chmod 600 .env

# Execute migrations
sudo -u gestaofinanceira venv/bin/flask db upgrade
```

### 3. Systemd Service

Crie `/etc/systemd/system/gestao-financeira.service`:

```ini
[Unit]
Description=Sistema de Gestão Financeira
After=network.target postgresql.service

[Service]
Type=notify
User=gestaofinanceira
Group=gestaofinanceira
WorkingDirectory=/opt/gestao_financeira
Environment="PATH=/opt/gestao_financeira/venv/bin"
ExecStart=/opt/gestao_financeira/venv/bin/gunicorn \
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

Ative o serviço:

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

---

## 📊 Monitoramento e Logs

### 1. Logs de Segurança

Os logs ficam em:
- `/opt/gestao_financeira/logs/security.log` - Eventos de segurança
- `/opt/gestao_financeira/logs/gestao_financeira.log` - Logs da aplicação
- `/var/log/gestao-financeira/` - Logs do Gunicorn

**Monitorar eventos suspeitos:**

```bash
# Tentativas de login falhadas
grep "Tentativa de login falhada" logs/security.log

# IPs bloqueados
grep "IP bloqueado" logs/security.log

# Possíveis ataques SQL injection
grep "SQL injection" logs/security.log
```

### 2. Configurar Logrotate

Crie `/etc/logrotate.d/gestao-financeira`:

```
/opt/gestao_financeira/logs/*.log {
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

### 3. Alertas Automáticos

Configure `fail2ban` para bloquear IPs suspeitos:

```bash
sudo apt install fail2ban

# Crie /etc/fail2ban/filter.d/gestao-financeira.conf
[Definition]
failregex = ^.* Tentativa de login falhada de <HOST>
            ^.* IP bloqueado: <HOST>
ignoreregex =
```

```bash
# Crie /etc/fail2ban/jail.d/gestao-financeira.conf
[gestao-financeira]
enabled = true
port = http,https
filter = gestao-financeira
logpath = /opt/gestao_financeira/logs/security.log
maxretry = 5
bantime = 3600
findtime = 600
```

---

## 🔧 Manutenção de Segurança

### 1. Atualizações Regulares

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Atualizar dependências Python
cd /opt/gestao_financeira
sudo -u gestaofinanceira venv/bin/pip install --upgrade -r requirements.txt

# Reiniciar serviço
sudo systemctl restart gestao-financeira
```

### 2. Backup Regular

```bash
# Backup do banco de dados
pg_dump -U gestao_financeira gestao_financeira > backup_$(date +%Y%m%d).sql

# Backup dos arquivos .env
cp .env .env.backup

# Armazenar backups em local seguro e criptografado
```

### 3. Auditoria de Segurança

**Mensalmente:**
- Revisar logs de segurança
- Verificar tentativas de acesso não autorizado
- Atualizar dependências
- Verificar certificados SSL

**Trimestralmente:**
- Testar restore de backups
- Revisar permissões de usuários
- Atualizar políticas de senha
- Realizar scan de vulnerabilidades

---

## ✅ Checklist de Segurança

### Antes do Deploy

- [ ] `.env` configurado com valores fortes
- [ ] SECRET_KEY gerada com 64 caracteres hex
- [ ] FLASK_ENV=production
- [ ] Senha do PostgreSQL forte (16+ caracteres)
- [ ] `.env` com permissões 600
- [ ] `.env` no `.gitignore`
- [ ] Dependências atualizadas
- [ ] Migrations aplicadas

### Servidor

- [ ] UFW configurado e ativo
- [ ] SSH com chave pública (desabilitar senha)
- [ ] Usuário não-root criado
- [ ] PostgreSQL acessível apenas localmente
- [ ] Nginx configurado com SSL/TLS
- [ ] Certificado SSL válido
- [ ] Headers de segurança configurados
- [ ] Rate limiting configurado

### Aplicação

- [ ] Logs de segurança funcionando
- [ ] Rate limiting ativo
- [ ] CSRF protection ativa
- [ ] Sessões seguras configuradas
- [ ] Upload de arquivos validado
- [ ] Backup automático configurado

### Monitoramento

- [ ] Logrotate configurado
- [ ] fail2ban configurado
- [ ] Alertas de segurança ativos
- [ ] Monitoramento de disco/CPU

---

## 🆘 Em Caso de Incidente

### Se Suspeitar de Comprometimento:

1. **Isole imediatamente:**
   ```bash
   sudo systemctl stop gestao-financeira
   sudo ufw deny from <IP_SUSPEITO>
   ```

2. **Analise logs:**
   ```bash
   tail -n 1000 logs/security.log | grep <IP_SUSPEITO>
   ```

3. **Troque credenciais:**
   - Gere nova SECRET_KEY
   - Troque senha do banco de dados
   - Force logout de todos os usuários

4. **Restaure de backup** se necessário

5. **Investigue** a causa raiz

6. **Aplique patches** e atualize sistema

---

## 📞 Suporte

Para reportar vulnerabilidades de segurança:
- **NÃO** abra issue pública
- Entre em contato diretamente com o administrador

---

## 📚 Referências

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security](https://flask.palletsprojects.com/en/2.3.x/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/security.html)
- [Nginx Security](https://nginx.org/en/docs/http/configuring_https_servers.html)

---

**Última atualização:** 2025-01-27
**Versão:** 1.0
