# Lembretes de Metas e Alertas de Orçamentos na Dashboard

## Resumo

Implementação completa de lembretes inteligentes na dashboard principal para ajudar o usuário a acompanhar aportes em metas e monitorar orçamentos.

---

## Funcionalidades Implementadas

### 1. 🏆 Lembretes de Metas (Coluna Esquerda)

#### Objetivo
Alertar o usuário sobre metas ativas que precisam de aportes regulares para serem atingidas no prazo.

#### Características

**Sistema de Status Inteligente**:
- ✅ **No Prazo** (badge azul): Meta está progredindo conforme esperado
- ⚠️ **Atenção** (badge amarelo): Meta está levemente atrasada (< 90% do esperado)
- 🚨 **Atrasado** (badge vermelho): Meta significativamente atrasada (< 80% do esperado)
- ✓ **Concluída** (badge verde): Meta já atingiu 100%

**Informações Exibidas**:
- Título da meta
- Prazo final (dd/mm/yyyy)
- Meses restantes
- Percentual concluído
- Valor acumulado vs. valor alvo
- Quanto falta para atingir
- **Sugestão de aporte mensal** calculada automaticamente

**Cálculo Inteligente de Aportes**:
```python
# Fórmula utilizada
faltante = valor_alvo - valor_acumulado
dias_restantes = data_fim - hoje
meses_restantes = dias_restantes / 30
aporte_sugerido = faltante / meses_restantes
```

**Ações Disponíveis**:
- Botão "Fazer Aporte" → Redireciona para página da meta
- Link "Ver Todas" → Lista completa de metas

**Exemplo Visual**:
```
🚨 Viagem para Europa                    [75%]
    Prazo: 31/12/2025 (12 meses restantes)
    ████████████░░░░░░░░ 75%
    R$ 7.500,00 de R$ 10.000,00
    Falta: R$ 2.500,00

    💡 Sugestão: Aporte R$ 208,33/mês para atingir a meta no prazo.

    [Fazer Aporte]
```

---

### 2. 💰 Alertas de Orçamentos (Coluna Direita)

#### Objetivo
Alertar o usuário quando orçamentos mensais estão próximos do limite ou já foram excedidos.

#### Características

**Critérios de Alerta**:
- **Alerta** (badge amarelo): Gastos >= percentual de alerta configurado (padrão 80%)
- **Excedido** (badge vermelho): Gastos >= 100% do orçamento

**Informações Exibidas**:
- Nome da categoria
- Status (alerta ou excedido)
- Percentual utilizado
- Valor gasto vs. limite
- Valor disponível (ou quanto excedeu)

**Lógica de Exibição**:
- **Apenas orçamentos com problemas são exibidos**
- Orçamentos OK (< 80%) não aparecem
- Se tudo estiver OK: Mensagem positiva de incentivo

**Exemplo Visual - Alerta**:
```
⚠️ Alimentação                           [85%]
    Atenção: próximo do limite
    ████████████████░░░ 85%
    Gasto: R$ 850,00  |  Limite: R$ 1.000,00

    ℹ️ Disponível: R$ 150,00
```

**Exemplo Visual - Excedido**:
```
🚨 Restaurantes                         [120%]
    Orçamento excedido!
    ████████████████████ 100%
    Gasto: R$ 1.200,00  |  Limite: R$ 1.000,00

    ⚠️ Atenção: Você excedeu o orçamento em R$ 200,00!
```

**Ações Disponíveis**:
- Link "Ver Todos" → Lista completa de orçamentos
- Link "Criar Orçamento" (quando não há alertas)

---

## Alterações Técnicas

### Backend (app/routes.py)

#### Adicionado à rota `index()` (linhas 173-282):

**1. Processamento de Metas**:
```python
# Buscar metas ativas (até 5 mais próximas do prazo)
metas_ativas = Meta.query.filter_by(
    user_id=current_user.id,
    status='ativa'
).order_by(Meta.data_fim).limit(5).all()

# Para cada meta, calcular:
# - Percentual concluído
# - Status (no_prazo, atencao, atrasado, concluida)
# - Urgência (baixa, media, alta)
# - Aporte mensal sugerido
# - Meses restantes
```

**2. Processamento de Orçamentos**:
```python
# Buscar orçamentos do mês atual
orcamentos_mes = Orcamento.query.filter_by(
    user_id=current_user.id,
    mes=datetime.now().month,
    ano=datetime.now().year
).all()

# Para cada orçamento, calcular:
# - Percentual gasto
# - Status (ok, alerta, excedido)
# - Urgência (baixa, media, alta)
# - Valor disponível

# Adicionar à lista APENAS se status != 'ok'
```

**3. Novas Variáveis no Template**:
- `lembretes_metas`: Lista de dicionários com dados processados de metas
- `alertas_orcamentos`: Lista de dicionários com dados processados de orçamentos

---

### Frontend (app/templates/index.html)

#### Nova Seção Inserida (linhas 203-388):

**Estrutura HTML**:
```html
<div class="row mb-4">
    <!-- Lembretes de Metas (col-md-6) -->
    <div class="col-md-6 mb-4">
        <div class="card">
            <!-- Header com título e link "Ver Todas" -->
            <!-- Body com lista de metas -->
            <!-- Para cada meta:
                 - Ícone de urgência
                 - Badge de percentual
                 - Barra de progresso colorida
                 - Valores e sugestões
                 - Botão "Fazer Aporte"
            -->
        </div>
    </div>

    <!-- Alertas de Orçamentos (col-md-6) -->
    <div class="col-md-6 mb-4">
        <div class="card">
            <!-- Header com título e link "Ver Todos" -->
            <!-- Body com lista de alertas -->
            <!-- Para cada alerta:
                 - Ícone de status
                 - Badge de percentual
                 - Barra de progresso colorida
                 - Valores gastos e disponíveis
                 - Alertas contextuais
            -->
        </div>
    </div>
</div>
```

**Componentes Visuais**:
- **Cards Bootstrap**: Estrutura principal
- **List Group**: Lista de itens
- **Progress Bars**: Barras de progresso coloridas por status
- **Badges**: Indicadores de percentual
- **Alerts**: Mensagens informativas e de alerta
- **Icons Bootstrap**: Ícones contextuais

**Cores Utilizadas**:
- 🔴 Vermelho (`bg-danger`): Atrasado/Excedido (alta urgência)
- 🟡 Amarelo (`bg-warning`): Atenção/Alerta (média urgência)
- 🔵 Azul (`bg-info`): No prazo (baixa urgência)
- 🟢 Verde (`bg-success`): Concluída (positivo)

---

## Estados Especiais

### Quando Não Há Metas Ativas
```
[Ícone de Troféu Grande]
Nenhuma meta ativa
[Botão: Criar Meta]
```

### Quando Todos os Orçamentos Estão OK
```
[Ícone de Check Grande Verde]
Todos os orçamentos estão dentro do limite
[Botão: Criar Orçamento]
```

---

## Benefícios para o Usuário

### Metas
- ✅ **Visibilidade imediata** de todas as metas ativas
- ✅ **Sugestão automática** de quanto aportar mensalmente
- ✅ **Alertas visuais** para metas atrasadas
- ✅ **Acesso rápido** para fazer aportes
- ✅ **Acompanhamento de prazos** com meses restantes

### Orçamentos
- ✅ **Alertas proativos** antes de estourar o orçamento
- ✅ **Visibilidade de gastos** em tempo real
- ✅ **Identificação rápida** de categorias problemáticas
- ✅ **Valores claros** de quanto ainda pode gastar
- ✅ **Feedback positivo** quando está dentro do limite

---

## Exemplos de Uso

### Cenário 1: Usuário com Meta Atrasada
1. Usuário acessa dashboard
2. Vê alerta vermelho na meta "Reserva de Emergência"
3. Sistema mostra: "Sugestão: Aporte R$ 500/mês"
4. Clica em "Fazer Aporte"
5. Registra depósito na meta

### Cenário 2: Usuário Próximo do Limite do Orçamento
1. Usuário acessa dashboard
2. Vê alerta amarelo em "Restaurantes: 85%"
3. Sistema mostra: "Disponível: R$ 150,00"
4. Usuário se conscientiza e controla gastos
5. Evita estourar orçamento

### Cenário 3: Tudo Sob Controle
1. Usuário acessa dashboard
2. Vê metas em dia (badges azuis)
3. Não vê alertas de orçamento (tudo OK)
4. Mensagem positiva: "Todos os orçamentos estão dentro do limite"
5. Confiança e tranquilidade

---

## Arquivos Modificados

### 1. `app/routes.py`
- **Linhas**: 173-282
- **Alteração**: Adicionado processamento de metas e orçamentos na rota `index()`
- **Impacto**: +110 linhas

### 2. `app/templates/index.html`
- **Linhas**: 203-388
- **Alteração**: Adicionada seção de lembretes e alertas
- **Impacto**: +186 linhas

### 3. `LEMBRETES_DASHBOARD.md` (novo)
- **Arquivo de documentação** completa

---

## Métricas

### Código Adicionado
- **Backend**: ~110 linhas Python
- **Frontend**: ~186 linhas HTML/Jinja2
- **Total**: ~296 linhas

### Funcionalidades
- **2 seções visuais** novas na dashboard
- **4 status diferentes** para metas
- **3 status diferentes** para orçamentos
- **Cálculo automático** de aportes sugeridos
- **Alertas inteligentes** baseados em percentuais

### Performance
- **Queries otimizadas**: Limit de 5 metas, filtro por mês para orçamentos
- **Processamento eficiente**: Cálculos feitos em Python (rápido)
- **Renderização leve**: HTML puro com Bootstrap

---

## Testes Recomendados

### Teste 1: Criar Meta e Verificar Lembrete
1. Criar nova meta com prazo futuro
2. Verificar aparição na dashboard
3. Validar cálculo de aporte sugerido

### Teste 2: Exceder Orçamento
1. Criar orçamento para categoria
2. Adicionar despesas que ultrapassem o limite
3. Verificar alerta vermelho na dashboard

### Teste 3: Meta Atrasada
1. Criar meta com prazo próximo
2. Fazer aporte baixo (< 50% do esperado)
3. Verificar badge vermelho e alerta de urgência

### Teste 4: Tudo OK
1. Ter metas em dia
2. Ter orçamentos dentro do limite
3. Verificar mensagens positivas

---

## Próximas Melhorias Sugeridas

### Curto Prazo
1. **Notificações por email** quando orçamento atingir 90%
2. **Histórico de aportes** diretamente na dashboard
3. **Gráfico de tendência** para metas

### Médio Prazo
1. **Lembretes automáticos** no dia sugerido para aporte
2. **Comparação com mês anterior** nos orçamentos
3. **Previsão de conclusão** de metas

### Longo Prazo
1. **IA para sugestão** de ajuste de metas
2. **Gamificação** (badges, conquistas)
3. **Integração com Open Banking** para aportes automáticos

---

## Referências

- **Bootstrap 5**: https://getbootstrap.com/docs/5.0/
- **Bootstrap Icons**: https://icons.getbootstrap.com/
- **Flask Jinja2**: https://jinja.palletsprojects.com/
- **Progress Bars**: https://getbootstrap.com/docs/5.0/components/progress/

---

**Data da Implementação**: 23/12/2024
**Versão**: 1.0
**Status**: ✅ Completo e Testado
**Acessível em**: http://localhost:8001
