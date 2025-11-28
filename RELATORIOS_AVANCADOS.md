# Relatórios Avançados - Sistema de Gestão Financeira

## Visão Geral

O sistema de relatórios avançados foi completamente reformulado para oferecer análises financeiras profundas e insights acionáveis sobre suas finanças pessoais.

## Estrutura

O sistema está organizado em **7 abas principais**, cada uma focada em um aspecto específico da análise financeira:

---

## 1. 📊 Visão Geral

Dashboard principal com os principais indicadores financeiros.

### Gráficos Disponíveis:
- **Gastos por Categoria** - Gráfico de pizza mostrando distribuição de despesas
- **Fluxo de Caixa Anual** - Comparação mensal de receitas vs despesas
- **Top 10 Categorias** - Ranking horizontal das categorias com maiores gastos

### Uso:
```
- Acesse: /relatorios
- Primeira tela carregada automaticamente
- Use os filtros superiores para mudar mês/ano
```

---

## 2. 📈 Evolução Patrimonial

Acompanhe o crescimento (ou redução) do seu patrimônio ao longo do tempo.

### Recursos:
- **Gráfico de linha** com evolução histórica
- **Saldo atual** destacado
- **3 períodos de visualização**:
  - Último Mês (30 dias)
  - Último Ano (12 meses)
  - Todo Histórico

### API:
```
GET /api/evolucao-patrimonial?periodo=ano
```

### Cálculo:
- Considera todas as transações **pagas** do usuário
- Calcula regressivamente a partir do saldo atual
- Gera pontos diários de evolução patrimonial

---

## 3. 🥧 Categorias

Análise detalhada de gastos por categoria com insights sobre padrões de consumo.

### Seção 1: Distribuição por Categoria
- Gráfico de pizza interativo
- Cores customizadas por categoria
- Tabela com ranking completo

### Seção 2: Análise de Despesas Recorrentes
- Lista de todas as despesas recorrentes ativas
- **Impacto mensal estimado** de cada recorrência
- Próxima data de ocorrência
- Total mensal consolidado

### APIs:
```
GET /api/top-categorias?mes=11&ano=2025&limite=15
GET /api/analise-recorrentes
```

### Detalhes da Tabela:
| Coluna | Descrição |
|--------|-----------|
| Categoria | Nome com indicador colorido |
| Quantidade | Número de transações |
| Total | Valor total gasto |
| % do Total | Percentual sobre total de despesas |

---

## 4. 💰 Orçamentos

Comparação entre valores orçados e gastos reais por categoria.

### Recursos:
- **Resumo consolidado**:
  - Total Orçado
  - Total Gasto
  - Saldo (verde/vermelho conforme situação)

- **Gráfico de barras agrupadas**:
  - Azul: Orçado
  - Vermelho: Gasto

- **Tabela detalhada com status**:
  - ✅ OK - Abaixo do limite de alerta
  - ⚠️ Alerta - Entre limite de alerta e 100%
  - 🚫 Excedido - Acima de 100%

### API:
```
GET /api/orcamentos-vs-realizado?mes=11&ano=2025
```

### Status Automático:
```javascript
status = percentual > 100 ? 'excedido'
       : percentual >= alerta ? 'alerta'
       : 'ok'
```

---

## 5. 🏆 Metas

Acompanhamento do progresso de metas de economia.

### Recursos:
- **Resumo geral**:
  - Total de metas ativas
  - Meta total (soma dos alvos)
  - Total acumulado

- **Gráfico comparativo**:
  - Verde: Valor acumulado
  - Cinza: Valor alvo

- **Análise de prazo**:
  - 🟢 Adiantado - Progresso acima do esperado
  - 🔵 No Prazo - Progresso adequado
  - 🟡 Atrasado - Progresso abaixo do esperado

### API:
```
GET /api/progresso-metas
```

### Cálculo de Status:
```javascript
percentual_tempo = (dias_passados / dias_totais) * 100
status = percentual > percentual_tempo ? 'adiantado'
       : percentual >= percentual_tempo * 0.9 ? 'no_prazo'
       : 'atrasado'
```

---

## 6. 💳 Cartões

Análise completa do uso de cartões de crédito.

### Seção 1: Gráfico de Limites
- Barras empilhadas mostrando:
  - Vermelho: Limite utilizado
  - Verde: Limite disponível

### Seção 2: Tabela Detalhada
| Coluna | Descrição |
|--------|-----------|
| Cartão | Nome do cartão |
| Bandeira | Visa, Mastercard, etc. |
| Limite Total | Limite do cartão |
| Utilizado | Valor utilizado |
| Disponível | Limite - Utilizado |
| % Uso | Barra de progresso colorida |
| Faturas Abertas | Quantidade |
| Gasto Médio/Mês | Média dos últimos 6 meses |

### API:
```
GET /api/analise-cartoes
```

### Indicadores de % Uso:
- 🟢 Verde: 0-50%
- 🟡 Amarelo: 50-80%
- 🔴 Vermelho: >80%

---

## 7. 🔄 Comparações

Análise comparativa entre diferentes períodos de tempo.

### Modos de Comparação:
1. **6 Meses** - Comparação mensal
2. **12 Meses** - Comparação mensal (ano completo)
3. **4 Trimestres** - Comparação trimestral
4. **3 Anos** - Comparação anual

### Gráficos:
1. **Receitas vs Despesas por Período**
   - Barras agrupadas
   - Verde: Receitas
   - Vermelho: Despesas

2. **Saldo por Período**
   - Linha com marcadores
   - Mostra saldo líquido (receitas - despesas)

### API:
```
GET /api/comparacao-periodos?tipo=mensal&quantidade=6
```

### Tipos de Período:
- `mensal` - Agrupa por mês
- `trimestral` - Agrupa por trimestre (Q1, Q2, Q3, Q4)
- `anual` - Agrupa por ano

---

## Filtros Globais

Todos os relatórios respeitam os filtros globais no topo da página:

```html
- Mês: Seletor de 1-12
- Ano: Campo numérico (2020-2099)
- Período Comparação: mensal/trimestral/anual
```

Botão **"Atualizar Relatórios"** recarrega todos os gráficos da aba ativa.

---

## Tecnologias Utilizadas

### Backend:
- **Flask** - Framework web
- **SQLAlchemy** - ORM para consultas ao banco
- **PostgreSQL** - Banco de dados

### Frontend:
- **Plotly.js** - Biblioteca de gráficos interativos
- **Bootstrap 5** - Framework CSS
- **Bootstrap Icons** - Ícones

### Arquitetura:
```
Frontend (HTML/JS)
    ↓ fetch()
API REST (Flask)
    ↓ SQLAlchemy
PostgreSQL Database
    ↓ JSON
Frontend (Plotly)
```

---

## Endpoints de API Criados

### 1. Evolução Patrimonial
```http
GET /api/evolucao-patrimonial?periodo=ano
```
**Retorna:**
```json
{
  "datas": ["2024-01-01", "2024-01-02", ...],
  "valores": [10000.00, 10050.00, ...],
  "saldo_atual": 15000.00
}
```

### 2. Análise de Cartões
```http
GET /api/analise-cartoes
```
**Retorna:**
```json
{
  "cartoes": [
    {
      "nome": "Nubank",
      "bandeira": "Mastercard",
      "limite": 5000.00,
      "utilizado": 1200.00,
      "disponivel": 3800.00,
      "percentual": 24.0,
      "faturas_abertas": 2,
      "gasto_medio_mensal": 1500.00
    }
  ]
}
```

### 3. Orçamentos vs Realizado
```http
GET /api/orcamentos-vs-realizado?mes=11&ano=2025
```
**Retorna:**
```json
{
  "orcamentos": [
    {
      "categoria": "Alimentação",
      "orcado": 1000.00,
      "gasto": 850.00,
      "saldo": 150.00,
      "percentual": 85.0,
      "status": "alerta"
    }
  ],
  "total_orcado": 5000.00,
  "total_gasto": 4200.00
}
```

### 4. Progresso de Metas
```http
GET /api/progresso-metas
```
**Retorna:**
```json
{
  "metas": [
    {
      "titulo": "Viagem Europa",
      "alvo": 20000.00,
      "acumulado": 8500.00,
      "faltante": 11500.00,
      "percentual": 42.5,
      "percentual_tempo": 40.0,
      "status": "adiantado",
      "meses_restantes": 8
    }
  ],
  "total_alvo": 50000.00,
  "total_acumulado": 22000.00
}
```

### 5. Comparação de Períodos
```http
GET /api/comparacao-periodos?tipo=mensal&quantidade=6
```
**Retorna:**
```json
{
  "periodos": ["Jun/25", "Jul/25", "Ago/25", "Set/25", "Out/25", "Nov/25"],
  "receitas": [5000, 5200, 5100, 5300, 5400, 5500],
  "despesas": [4200, 4500, 4100, 4300, 4600, 4400],
  "saldos": [800, 700, 1000, 1000, 800, 1100]
}
```

### 6. Top Categorias
```http
GET /api/top-categorias?mes=11&ano=2025&limite=10
```
**Retorna:**
```json
{
  "categorias": ["Alimentação", "Transporte", "Lazer"],
  "valores": [1200.00, 800.00, 500.00],
  "cores": ["#e74c3c", "#3498db", "#2ecc71"],
  "quantidades": [45, 28, 12],
  "total": 2500.00
}
```

### 7. Análise de Recorrentes
```http
GET /api/analise-recorrentes
```
**Retorna:**
```json
{
  "recorrentes": [
    {
      "descricao": "Netflix",
      "valor": 49.90,
      "frequencia": "mensal",
      "categoria": "Assinaturas",
      "proxima_data": "2025-12-01",
      "impacto_mensal": 49.90
    }
  ],
  "total_mensal_estimado": 850.00,
  "quantidade": 8
}
```

---

## Funcionalidades Técnicas

### Carregamento Sob Demanda
- Abas carregam dados apenas quando acessadas
- Reduz tempo de carregamento inicial
- Melhora performance

### Atualização Dinâmica
- Filtros globais afetam todas as abas
- Botão "Atualizar" recarrega dados
- Gráficos são redesenhados automaticamente

### Isolamento de Dados
- Todos os endpoints verificam `current_user.id`
- Usuários veem apenas seus próprios dados
- Segurança em nível de query SQL

### Tratamento de Erros
```javascript
.catch(error => {
    console.error('Erro ao carregar:', error);
    // Exibe mensagem amigável ao usuário
});
```

---

## Como Usar

### 1. Acesso
```
http://localhost:5000/relatorios
```

### 2. Navegação
- Use as **7 abas** no topo para alternar entre relatórios
- Ajuste **mês/ano** nos filtros globais
- Clique em **"Atualizar Relatórios"** para aplicar filtros

### 3. Interação com Gráficos
- **Hover** sobre elementos para ver valores
- **Zoom** em gráficos (canto superior direito)
- **Pan** para navegar em gráficos grandes
- **Download** de imagens (ícone câmera)

### 4. Análise de Dados
- Tabelas são **ordenáveis** (clique nos cabeçalhos)
- **Badges coloridos** indicam status
- **Barras de progresso** mostram percentuais
- **Cores** ajudam na identificação rápida

---

## Melhorias Futuras (Sugestões)

### Exportação de Dados
- [ ] Exportar relatórios para PDF
- [ ] Exportar dados para Excel/CSV
- [ ] Enviar relatórios por e-mail

### Análises Adicionais
- [ ] Previsão de gastos futuros (ML)
- [ ] Detecção de anomalias
- [ ] Recomendações personalizadas
- [ ] Análise de sazonalidade

### Visualizações
- [ ] Gráficos de Sankey (fluxo de dinheiro)
- [ ] Heatmaps de gastos
- [ ] Gráficos de radar para comparações
- [ ] Timeline de eventos financeiros

### Compartilhamento
- [ ] Compartilhar relatórios com família
- [ ] Metas conjuntas
- [ ] Comparação com médias nacionais
- [ ] Benchmarking com outros usuários

---

## Troubleshooting

### Gráficos não aparecem
```bash
# Verificar se Plotly está sendo carregado
# No console do navegador (F12):
console.log(typeof Plotly);  // Deve retornar "object"
```

### Dados não carregam
```bash
# Verificar endpoints no backend
curl http://localhost:5000/api/evolucao-patrimonial?periodo=ano
```

### Erros 403 (Forbidden)
```python
# Verificar autenticação
# Usuário deve estar logado
@login_required
```

### Performance lenta
```sql
-- Criar índices no banco
CREATE INDEX idx_transacoes_data ON transacoes(data);
CREATE INDEX idx_transacoes_user ON transacoes(conta_id);
CREATE INDEX idx_contas_user ON contas(user_id);
```

---

## Arquivos Modificados/Criados

### Arquivos Modificados:
1. `app/routes.py` - 7 novos endpoints de API (linhas 1187-1532)

### Arquivos Criados:
1. `app/templates/relatorios/index.html` - Template completo (845 linhas)
2. `RELATORIOS_AVANCADOS.md` - Esta documentação

---

## Estatísticas do Código

### Backend (routes.py):
- **7 novos endpoints** de API
- **~350 linhas** de código Python
- **7 funções** de relatórios

### Frontend (index.html):
- **~850 linhas** totais
- **7 abas** interativas
- **15+ gráficos** diferentes
- **7 funções JavaScript** principais

### APIs:
- **Total de endpoints**: 9 (2 existentes + 7 novos)
- **Média de complexidade**: Média-Alta
- **Queries otimizadas**: Sim (uso de joins e aggregations)

---

## Conclusão

O sistema de Relatórios Avançados oferece uma visão 360° das finanças pessoais, permitindo:

✅ **Acompanhar** patrimônio ao longo do tempo
✅ **Analisar** padrões de gastos por categoria
✅ **Monitorar** orçamentos e metas
✅ **Controlar** uso de cartões de crédito
✅ **Comparar** diferentes períodos
✅ **Identificar** despesas recorrentes
✅ **Tomar decisões** informadas

Com gráficos interativos, tabelas detalhadas e APIs robustas, o sistema está pronto para auxiliar na gestão financeira pessoal de forma profissional e eficiente.

---

**Desenvolvido por:** Claude Code
**Data:** Novembro 2025
**Versão:** 1.0.0
