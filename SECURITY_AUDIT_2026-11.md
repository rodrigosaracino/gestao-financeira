# Auditoria de Segurança — Novembro/2026

Escopo: todo o código Python (`app/`, `config.py`, `run.py`), templates, Docker/compose, scripts de deploy e dependências.
Resultado: **4 críticos, 3 altos, 7 médios, 9 baixos** — todos os críticos e altos corrigidos nesta branch.
Testes automatizados: `tests/` (41 testes, `pytest`).

## Críticos (corrigidos)
| # | Problema | Correção |
|---|----------|----------|
| C1 | **IDOR de escrita**: `conta_id`, `categoria_id`, `cartao_credito_id` e `transacao_id` vindos do formulário não eram checados. Um usuário logado conseguia alterar o saldo e criar transações nas contas de outro (`nova_transacao`, `editar_transacao`, `pagar_fatura`, `criar-inline`, conciliação, orçamentos, metas). | Helpers `get_owned` / `get_owned_or_404` em `app/security.py`, aplicados em todo id recebido do cliente. Testes em `tests/test_seguranca.py`. |
| C2 | `SECRET_KEY` com valor padrão público no `docker-compose.yml` → sessão forjável se a VPS não tivesse `.env`. | Compose agora **exige** `SECRET_KEY`, `POSTGRES_PASSWORD` e `DATABASE_URL` (sem valores padrão). |
| C3 | **XSS** em `relatorios/index.html` (descrição/categoria/meta/cartão em `innerHTML`) — explorável via descrições de PIX/TED importadas de extrato. Cor de categoria sem validação. | `escapeHtml()`/`safeColor()` globais em `base.html`; cor validada (`#rrggbb`); `tojson` em `transacoes/form.html`. |
| C4 | gunicorn 21.2.0 (CVE-2024-1135, CVE-2024-6827 — request smuggling atrás de proxy). | gunicorn 23.0.0. |

## Altos (corrigidos)
- **A1** Vazamento de dados de outro usuário via ids de formulário (conciliação, metas, orçamentos) — coberto pelo C1.
- **A2** Talisman (HTTPS/HSTS/CSP) nunca era ativado (`FLASK_ENV` não estava na config). Agora ativo em produção; CSP sem `img-src https:`, com `object-src 'none'`, `base-uri`, `form-action`, `frame-ancestors`.
- **A3** Bloqueio de força bruta e rate-limit baseados em `X-Forwarded-For` (forjável; permitia escapar do bloqueio ou bloquear outra pessoa). Agora `ProxyFix` confia só no Traefik e o IP vem de `request.remote_addr`. Como o site fica atrás do Cloudflare, o IP real vem de `CF-Connecting-IP`, aceito **somente** quando a conexão chega de uma faixa oficial do Cloudflare (inclusive no rate limit).

## Médios (corrigidos)
- Open redirect no `?next=` (`/\evil.com`) → `is_safe_redirect()`.
- Porta 8001 exposta publicamente (pulando o Traefik) → bind em `127.0.0.1`. Postgres local também.
- Cookie "lembrar-me" sem `Secure` e com 365 dias → `Secure`, `HttpOnly`, `SameSite=Lax`, 14 dias.
- Mensagens de exceção (`str(e)`) mostradas ao usuário → mensagem genérica + log no servidor.
- Container rodando como root e com gcc → build multi-stage, usuário `app`; `.dockerignore` exclui scripts de teste, tarballs, extratos.
- **15 formulários sem token CSRF** (estavam quebrados: retornavam 400) e `fetch()` sem header → token em todos os forms + header automático `X-CSRFToken`; logout passou a ser POST; token expira em 8h.
- Falta de validação numérica (`total_parcelas` sem limite podia criar milhões de linhas; `tipo` livre) → limites e whitelist.

## Baixos
- `run.py` com `debug=True` em `0.0.0.0` → debug só com `FLASK_DEBUG=1`, host local. ✅
- E-mails completos nos logs → mascarados (`ro***@gmail.com`). ✅
- Diferença de tempo no login revelava se o e-mail existe → hash fictício. ✅
- Template `investimentos/dividendos.html` ausente (erro 500) → criado. ✅
- Ticker ia cru na URL da brapi → validado. ✅
- `toggle-pago` respondia 403 (revelava ids) → 404. ✅
- `fuzzywuzzy` (sem manutenção, GPL) → `rapidfuzz`. `requests` ≥ 2.32.4, Flask 3.1.2. ✅
- Mensagem de registro revela e-mail já cadastrado — mantido (UX); mitigado pelo rate-limit.
- **Pendente (ação manual):** a pasta do projeto está no Google Drive e sincroniza `.env`, `instance/*.db` e `logs/`. Recomendado mover segredos e bancos para fora da pasta sincronizada.

## Bugs de saldo corrigidos de passagem
- Editar uma transação **não paga** alterava o saldo da conta.
- Criar transação inline alterava o saldo mesmo sem estar paga.

## Itens verificados sem problema
- Sem SQL cru: todo acesso via ORM (sem SQL injection).
- Senhas com hash scrypt (Werkzeug).
- Todas as rotas (exceto login/registro) com `@login_required`; objetos da URL já eram filtrados pelo usuário.

## Antes do deploy na VPS
1. O `.env` da VPS precisa ter `SECRET_KEY` (forte), `POSTGRES_PASSWORD` e `DATABASE_URL`, senão o `docker compose` recusa subir.
2. Se o banco foi criado com a senha padrão `postgres`, defina `POSTGRES_PASSWORD=postgres` primeiro e depois troque a senha com `ALTER USER postgres PASSWORD '...'` (a variável só vale na criação do volume).
3. Se a `SECRET_KEY` atual for a padrão, gere uma nova (`python -c "import secrets;print(secrets.token_hex(32))"`) — todos serão deslogados.
