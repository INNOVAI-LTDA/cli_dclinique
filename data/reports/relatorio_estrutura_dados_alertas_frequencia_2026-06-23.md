# Relatório de Estado Atual — Estrutura de Dados e Regra de Alertas por Frequência

> **Projeto:** MAP (Minimum Acceptable Product) — casca navegável Streamlit
> **Versão do relatório:** 2026-06-23
> **Objetivo:** Apresentar ao cliente o panorama atual da estrutura de dados, a regra de negócio pretendida para a tela **Matriz de Decisão (Mapa de Decisão)**, os pontos críticos que impedem a aplicação dessa regra hoje, e os pontos onde a ajuda do cliente é indispensável.

---

## 1. Estado atual da estrutura de dados

O data layer do MAP é um **router** entre **Postgres no Neon** (fonte de verdade em PRD — `src/data_layer/postgres_backend.py`) e **CSV** (fallback dev offline — `data/csv/`). O contrato de dados é o mesmo nos dois backends e está declarado em `src/schemas.py:EXPECTED_SCHEMAS`. São **11 tabelas**, todas com `patient_id` como chave estrangeira para `patients.patient_id` (exceto `patients` e `data_quality_issues`, que é diagnóstico).

### 1.1. Inventário das 11 tabelas

| # | Tabela | Função | Chaves relevantes | Observação |
|---|---|---|---|---|
| 1 | `patients` | Cadastro do paciente | `patient_id` (PK) + `cpf`/`rg` (natural-keys após import PDF) | Sem `email`/`data_nascimento`; `age` é o campo de idade |
| 2 | `treatment_plans` | Plano contratado | `plan_id` (PK), `patient_id` (FK), `status`, `start_date`, `end_date`, `is_renewal` | Status atual: `Ativo`, `Pausado`, `Aguardando início` |
| 3 | `treatment_plan_items` | Itens do plano | `plan_item_id` (PK), `plan_id` (FK), `frequency_text`, `frequency_type` ∈ {Semanal, Quinzenal, Diário}, `sessions_expected` | `frequency_type` é categórico, sem periodicidade numérica |
| 4 | `execution_summary` | Visão satélite do que foi executado | `execution_id`, `patient_id`, `plan_id`, `sessions_expected/completed/remaining` | `frequency_type` foi adicionado em jun/2026 (`src/schemas.py:65`); o status é agregado, **não há granularidade por sessão** |
| 5 | `appointments` | Cada sessão/consulta agendada | `appointment_id`, `patient_id`, `appointment_start/end`, `status` | `status` ∈ {`Atendido`, `Agendado`, `Confirmado`, `Atrasado`, `Cancelado`, `Reagendado`} — **única tabela que registra não-comparecimento** |
| 6 | `appointment_items` | Itens dentro de uma sessão | `appointment_item_id`, `appointment_id`, `patient_id`, `budget_code`, `status` | `status` herda da sessão; sem ligação com `plan_item_id` |
| 7 | `patient_goals` | Metas de peso | `goal_id`, `plan_id`, `initial_weight`, `target_weight`, `target_date` | Sem ligação com a meta de comparecimento |
| 8 | `weight_entries` | Medições de peso | `weight_id`, `plan_id`, `measurement_date`, `weight`, `source` | `source` distingue manual vs. PDF |
| 9 | `satisfaction_entries` | NPS/satisfação | `satisfaction_id`, `plan_id`, `date`, `satisfaction_status`, `score` | Status ∈ {Satisfeito, Neutro, Insatisfeito, Não informado} |
| 10 | `alerts` | Alertas operacionais | `alert_id`, `patient_id`, `plan_id`, `category`, `alert_type`, `description`, `priority`, `status`, `created_at`, `comment` | **Atualmente 100% injetada manualmente no `mock_data.py:270-284`**. CSVs e Postgres começam vazios |
| 11 | `data_quality_issues` | Problemas de qualidade de dados | `issue_id`, `source`, `severity`, `issue_type`, `patient_id` | Diagnóstico de importações; um dos `source` é literalmente "Relatório de frequência" |

### 1.2. Diagrama de relacionamentos (resumo)

```
patients ──< treatment_plans ──< treatment_plan_items
    │                │                    │
    │                │                    └─ (frequency_type / frequency_text)
    │                │
    │                ├──< execution_summary  (sessions_expected / completed / remaining)
    │                │
    │                ├──< patient_goals
    │                ├──< weight_entries
    │                ├──< satisfaction_entries
    │                └──< alerts
    │
    ├──< appointments ──< appointment_items
    │
    └──< data_quality_issues   (não-restrito a um paciente)
```

### 1.3. Onde a "frequência" já existe (parcialmente) hoje

| Sinal de frequência | Onde mora | Granularidade | Usado para alerta? |
|---|---|---|---|
| Sessões previstas × realizadas | `execution_summary.sessions_expected/completed` | Agregado por item de plano | Sim — define engajamento (Mapa de Decisão) |
| Frequência declarada no plano | `treatment_plan_items.frequency_type` | Categórico (Semanal/Quinzenal/Diário) | **Não** — apenas rótulo exibido na Ficha |
| Comparecimento por sessão | `appointments.status` (`Atendido` / `Atrasado` / `Cancelado` / `Reagendado`) | Por sessão | **Não** — nenhuma página consome |
| Qualidade de dados de frequência | `data_quality_issues.source = "Relatório de frequência"` | Linha de issue | Sim — exibido em Qualidade dos Dados, mas não vira alerta |

---

## 2. Regra de negócio pretendida — Mapa de Decisão × Frequência

### 2.1. Como o Mapa de Decisão funciona **hoje** (regra atual)

Implementado em `src/pages/mapa_decisao.py` e `src/metrics.py:patient_summary`:

- **Eixo X (Engajamento):** `engagement_rate = sessions_completed / sessions_expected` → classificado em `Baixo` (<30%), `Médio` (30–70%), `Alto` (>70%).
- **Eixo Y (Satisfação):** último `satisfaction_status` da tabela `satisfaction_entries` (apenas `Satisfeito` cai no quadrante positivo).
- **Quadrantes resultantes (4):** Engajado+Satisfeito / Engajado+Insatisfeito / Não engajado+Satisfeito / Não engajado+Insatisfeito.
- **Alertas no painel lateral:** apenas a contagem `open_alerts` lida da tabela `alerts` (que está **vazia** em PRD — só o mock injeta).

**Conclusão:** a regra atual é puramente **engajamento agregado × satisfação declarada**. A frequência *de comparecimento* (no-shows, atrasos, cancelamentos) **não entra** em nenhum dos eixos nem na geração de alertas.

### 2.2. Como a regra **deveria** funcionar segundo o que o cliente deseja

Inferência a partir dos pedidos já formalizados:

> A tela **Mapa de Decisão** deve posicionar os pacientes em uma matriz 2×2 cuja posição é **derivada dos relatórios de frequência** (comparecimento efetivo × frequência planejada). Pacientes com padrão crítico de faltas devem ser sinalizados automaticamente com **alertas** na aba **Alertas** e marcados no painel lateral da **Ficha do Paciente**.

A regra conceitual que precisa ser implementada é, no mínimo:

1. **Comparar presenças com a frequência planejada.** Para cada `plan_item`, somar:
   - sessões previstas no período (`frequency_type` × janela de tempo do plano);
   - sessões com status `Atendido` no `appointments`/`appointment_items` vinculado.
2. **Detectar violações.** Exemplos de regras razoáveis (a confirmar com o cliente):
   - 2 ou mais ausências consecutivas (Cancelado/Reagendado/Atrasado) → **alerta de alta prioridade**.
   - Atraso superior a X dias em relação à próxima sessão prevista → **alerta de média prioridade**.
   - Comparecimento abaixo de Y% no mês corrente → **alerta de média prioridade**.
3. **Persistir como alerta.** Criar registros em `alerts` com `category`, `alert_type`, `description`, `priority` e `created_at`, ligando o alerta ao `plan_id` correspondente.
4. **Refletir no Mapa de Decisão.** Mover o paciente para o quadrante "Não engajado + Insatisfeito" automaticamente, ou introduzir uma variante do quadrante baseada em frequência.

---

## 3. Pontos críticos que dificultam a aplicação da regra

Levantados a partir de inspeção do código atual (`src/metrics.py`, `src/pages/mapa_decisao.py`, `src/mock_data.py`, `src/data_layer/`, `data/csv/`):

### 3.1. Pontos críticos na **estrutura de dados**

| # | Problema | Onde aparece | Impacto |
|---|---|---|---|
| **C1** | **Não há ligação entre `appointments`/`appointment_items` e `plan_items`.** Só há `budget_code` (orçamento), não `plan_item_id`. | `data/csv/appointment_items.csv` e `src/mock_data.py:254-266` | Impossível saber *qual item do plano* o paciente faltou |
| **C2** | **`execution_summary` é agregado, sem granularidade por sessão.** Não carrega `appointment_id`, `session_date` ou status por sessão. | `src/schemas.py:46-66` e `src/mock_data.py:141-155` | Não dá para reconstruir "faltou dia X" — só "faltou N sessões no total" |
| **C3** | **`treatment_plan_items.frequency_type` é categórico (Semanal/Quinzenal/Diário), sem periodicidade numérica.** | `src/schemas.py:42` e `src/components/ficha.py:151` | Não dá para calcular "quantas sessões eram esperadas até hoje" sem convenção fixa |
| **C4** | **`appointments.status` é o único sinal de comparecimento granular, mas é "categoria livre" — não há normalização para "compareceu/não compareceu".** | `src/mock_data.py:233` | `Atrasado`, `Reagendado`, `Cancelado` precisam de regra explícita do que conta como falta |
| **C5** | **A tabela `alerts` é vazia em PRD.** Em `data/csv/alerts.csv` só há o cabeçalho; no Postgres, semeada por `scripts/init_neon_schema.py` apenas com `CREATE TABLE IF NOT EXISTS`. | `data/csv/alerts.csv` e `src/data_layer/schema.py` | A regra não tem onde persistir resultado |
| **C6** | **`data_quality_issues` tem source `Relatório de frequência`, mas não há pipeline que gere essas issues automaticamente.** | `src/mock_data.py:290` (linha `dq_003`) e `src/quality.py` | Sem histórico de problemas detectados |
| **C7** | **Não há coluna `plan_item_id` em `appointments` ou `appointment_items`.** Sem ela, não há como marcar "a sessão 3 do item de plano X foi cancelada". | `src/schemas.py:67-89` | Regra tem que ser estimada por `budget_code` (frágil) |
| **C8** | **`patients` não tem `data_nascimento` (só `age` calculado).** Limita cruzar idade × comportamento de frequência. | `src/schemas.py:7-20` | Cosmético, mas relevante para relatórios |

### 3.2. Pontos críticos no **código / regras de negócio**

| # | Problema | Onde aparece | Impacto |
|---|---|---|---|
| **R1** | **Não existe nenhuma função de "geração automática de alertas".** `metrics.py:patient_summary` apenas **lê** `alerts`; `mock_data.py:270-284` é o único lugar que **escreve**. | `src/metrics.py:51-54` e `src/mock_data.py:270-284` | A regra não tem motor de execução |
| **R2** | **Nenhuma página consome `appointments.status`.** O Mapa de Decisão deriva engajamento só de `execution_summary`. | `src/pages/mapa_decisao.py:457-471` e `src/metrics.py:19-43` | Faltas não afetam o quadrante |
| **R3** | **Não há definição de "frequência esperada vs. realizada"** — não existe função tipo `expected_sessions_between(plan_item, start, end)` ou `actual_sessions_between(plan_item, start, end)`. | ausência em `src/metrics.py` | A regra precisa ser escrita do zero |
| **R4** | **Limiares de alerta não foram pactuados.** O que conta como "alta frequência de faltas"? 2? 3? Percentual? Janela em dias? | ausência em `src/schemas.py` e `src/metrics.py` | Sem o input do cliente, qualquer implementação é chute |
| **R5** | **Não há "agendador" nem hook pós-import.** A `atualizacao_dados` lê planilhas CSV avulsas mas não há módulo que rode a regra depois de cada import. | `src/pages/atualizacao_dados.py` | A regra precisa de um "quando rodar?" |
| **R6** | **`metrics.py:patient_summary` está cacheado com `@st.cache_data`**, mas não há invalidação vinculada a mutações em `alerts` (a Ficha do Paciente limpa o cache, o import PDF também — mas não há garantia para o caso da regra rodando em batch). | `src/metrics.py:10` | Possível lag entre "alerta gerado" e "Mapa de Decisão atualizado" |

### 3.3. Pontos críticos de **fonte de dados externa**

| # | Problema | Impacto |
|---|---|---|
| **E1** | **A fonte real ("SupportHealth") não está integrada.** O data layer só conhece o que está no Postgres/CSV. Nada lê o sistema de origem. | Sem dados reais, a regra não pode rodar em produção |
| **E2** | **Não há dicionário do "relatório de frequência" do SupportHealth.** Que colunas tem? Qual o identificador do paciente (CPF? ID interno? Nome?)? | Sem o schema da fonte, o parser não pode ser escrito |
| **E3** | **Não há cadastro mínimo de paciente que possa ser feito a partir do relatório.** O fluxo atual de cadastro (`cadastro_ficha_paciente.py`) exige dados que o relatório pode não trazer (ex.: telefone, idade). | Pacientes só-no-relatório ficam órfãos |

---

## 4. Pontos onde a ajuda do cliente é indispensável

As alternativas abaixo são as que precisam de decisão do cliente para destravar o trabalho. **Os dois exemplos que o time já levantou estão consolidados nos itens 4.1 e 4.2.** Os itens 4.3, 4.4 e 4.5 são adicionais e foram identificados durante a análise deste relatório.

### 4.1. Vincular a importação a um paciente existente (já levantado)

> **Problema:** O relatório de frequência é uma planilha com N linhas por sessão; cada linha precisa ser atribuída a um `patient_id` do MAP. Não há um `patient_id` no SupportHealth que bata com o `patient_id` do MAP.

**Alternativa proposta:** Usar **CPF** (e secundariamente RG e nome normalizado) como chave de cruzamento.

**Implicações para o cliente:**

- **Se o paciente já está na base:** o import resolve automaticamente (busca trivial por CPF).
- **Se o paciente não está na base:** o import **precisa parar e exigir um cadastro mínimo** (nome + CPF + telefone + idade) antes de continuar. Sem essa interrupção, as linhas viram órfãs e a regra de frequência nunca roda para esse paciente.

**O que precisamos do cliente:**
1. Confirmação de que **CPF** pode ser tratado como natural-key confiável (incluindo pacientes que não estão no relatório atual mas virão em relatórios futuros).
2. Lista dos campos **mínimos obrigatórios** do paciente que o sistema consegue aceitar (e quais podem ser inferidos a partir do relatório, ex.: `name`, `phone` se houver coluna).
3. Política para **conflitos** (mesmo CPF, nome diferente — provavelmente erro de digitação; precisamos decidir se bloqueia ou só marca `data_quality_issue`).

### 4.2. Fornecer a base completa do SupportHealth (já levantado)

> **Problema:** Para que a regra de frequência funcione, o MAP precisa carregar e cruzar 4 fontes do SupportHealth: **(a) lista de pacientes ativos, (b) planos contratados, (c) relatórios de frequência/comparecimento, (d) cadastro de módulos/profissionais/procedimentos**. Hoje só temos (a) e (b) parciais, via PDF de plano.

**Alternativa proposta:** Solicitar ao cliente um pacote de dados inicial com o **universo completo** de pacientes, planos e relatórios de frequência, com **dicionário de dados** anexo (descrição de cada coluna e o que significam os valores).

**O que precisamos do cliente:**
1. **Dump/export** dos módulos do SupportHealth (em formato CSV, XLSX ou conexão read-only) para pelo menos:
   - Pacientes
   - Planos de tratamento
   - Itens de plano (com periodicidade)
   - Sessões/consultas com status de comparecimento
   - Profissionais e procedimentos
2. **Dicionário de dados** de cada módulo (colunas + valores possíveis + regras de status).
3. **Janela de tempo** dos dados (qual período o histórico cobre — para definirmos a janela mínima de cálculo de frequência, ex.: últimos 30 / 60 / 90 dias).
4. **Cadência de atualização** (diária, semanal, sob demanda) — define se a regra roda em batch ou em tempo real.

> **Após esse trabalho de saneamento**, será possível modelar com confiança o vínculo completo **Paciente ↔ Ficha ↔ Plano ↔ Frequência ↔ Alertas**, que é a fundação de qualquer regra de negócio confiável sobre comparecimento.

### 4.3. Definir a regra de "falta vira alerta" (adicional)

> **Problema:** Mesmo com dados disponíveis, sem regra explícita não há como codificar.

**O que precisamos do cliente (reunião de 1h com a equipe clínica):**
1. **Threshold de faltas consecutivas** que dispara alerta (1, 2, 3?).
2. **Threshold de comparecimento** abaixo do qual o paciente vira alerta (50%? 70%? 80%?).
3. **Janela de observação** (últimos 7, 15, 30, 60 dias?).
4. **Mapeamento de status → falta**:
   - `Cancelado` conta como falta?
   - `Atrasado` conta? E se o atraso for > X minutos?
   - `Reagendado` conta como falta da sessão original, da nova, ou de nenhuma?
5. **Prioridade e categoria** do alerta (a taxonomia atual `Médica/Enfermagem/Comercial/Nutrição` cobre? Falta cai em qual?).
6. **Workflow de resolução** — quem resolve? A coluna `comment` é suficiente ou precisa de histórico?

### 4.4. Definir o efeito no Mapa de Decisão (adicional)

> **Problema:** Se a regra gerar alertas, o Mapa de Decisão precisa refletir isso. Hoje ele cruza engajamento × satisfação.

**O que precisamos do cliente:**
1. Um alerta de frequência deve **mover o paciente de quadrante** (provavelmente para "Não engajado + Insatisfeito") ou apenas **anotar** no painel lateral?
2. Alerta de frequência vs. satisfação: se o paciente está `Satisfeito` no NPS mas faltou muito, ele vai para qual quadrante?
3. O contador de "Alertas" no painel lateral do Mapa deve incluir os de frequência ou ter um chip separado (ex.: "Alertas clínicos: 2 / Alertas de frequência: 3")?

### 4.5. Definir o mecanismo de carga do relatório (adicional)

> **Problema:** O item 4.2 fala do pacote inicial. Para o dia-a-dia, de onde vem o relatório?

**O que precisamos do cliente:**
1. **Formato e canal:** upload manual pelo usuário (extensão `.xlsx`/`.csv`)? Email automático? Integração direta?
2. **Identificador do relatório:** cada arquivo é um snapshot? Um delta? Tem que acumular?
3. **Política de retrocesso:** se o cliente apagar uma sessão no SupportHealth, o MAP precisa remover?
4. **Janela de aceitação:** relatórios atrasados (D+5, D+10) entram com impacto na regra ou são rejeitados?

---

## 5. Resumo executivo para a conversa com o cliente

1. **Hoje o MAP é uma casca navegável**, com 11 tabelas em Postgres/CSV e 4 fluxos implementados (Pacientes, Visão Geral, Mapa de Decisão, Alertas, Ficha do Paciente, Cadastro, Qualidade, Importação PDF).
2. **A Matriz de Decisão atual** classifica pacientes por **engajamento agregado** (sessões completadas ÷ previstas) × **satisfação declarada** (NPS). **Comparecimento granular (faltas) não entra no cálculo nem gera alerta.**
3. **A tabela `alerts` está vazia em PRD.** O que o cliente vê como "alertas" hoje é o mock injetado em `src/mock_data.py:270-284`.
4. **Para implementar a regra de frequência → alerta**, três coisas precisam acontecer em conjunto:
   - **(a) Mudança estrutural mínima** no data layer (adicionar `plan_item_id` em `appointments`/`appointment_items`, normalizar `appointments.status` em algo consultável, decidir o tipo de `frequency_type`).
   - **(b) Implementação da regra** em `src/metrics.py` (ou novo módulo `src/alerting/`), com limiares definidos pelo cliente.
   - **(c) Decisões de produto do cliente** (itens 4.1 a 4.5 acima), sem as quais qualquer implementação é chute.
5. **O pedido central que precisa ser formalizado** com o cliente é o **item 4.2** (entrega da base completa do SupportHealth) e o **item 4.3** (definição dos limiares da regra). Sem eles, o time consegue desenhar a infraestrutura, mas não consegue ligar a chave que faz a regra funcionar.
