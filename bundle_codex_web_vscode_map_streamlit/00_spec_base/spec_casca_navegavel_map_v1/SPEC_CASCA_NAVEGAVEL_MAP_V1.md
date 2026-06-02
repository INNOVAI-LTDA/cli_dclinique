# SPEC — Casca Navegável do MAP de Acompanhamento de Pacientes

**Versão:** 1.0  
**Objetivo:** orientar uma IA de codificação a construir uma casca navegável em Streamlit, usando dados fictícios, porém aderentes ao modelo de banco de dados planejado.  
**Prioridade:** validar visual, navegação, layout, fluxo de telas e contrato de dados antes da integração com dados reais.

---

## 1. Definição da entrega

Esta entrega **não** deve implementar a lógica real completa de parsing, cruzamento ou alertas clínicos definitivos.

Ela deve criar uma aplicação Streamlit navegável com:

- dados fictícios;
- estrutura de dados compatível com o banco futuro;
- telas funcionais;
- navegação entre páginas;
- seleção de paciente;
- visualização de plano, execução, alertas e qualidade dos dados;
- placeholders coerentes para dados ainda não recebidos;
- arquitetura modular para plugar dados reais depois.

A ideia é que, quando os dados reais entrarem, a estrutura visual e o formato dos dados **não precisem mudar**.

---

## 2. Princípio principal

> Primeiro validar a experiência e o contrato de dados. Depois conectar as fontes reais.

O app deve ser desenhado como se os dados viessem do banco, mas nesta versão eles virão de arquivos mock/funções Python.

---

## 3. Stack

- Python 3.11+
- Streamlit
- Pandas
- Plotly
- OpenPyXL, apenas preparado para futuro
- Pydantic opcional, se a IA quiser validar schemas

Arquivo `requirements.txt` mínimo:

```txt
streamlit
pandas
plotly
openpyxl
python-dotenv
```

---

## 4. Estrutura esperada do projeto

```txt
map-pacientes-streamlit/
  app.py
  requirements.txt
  README.md
  .gitignore

  data/
    mock/
      patients.csv
      treatment_plans.csv
      treatment_plan_items.csv
      execution_summary.csv
      appointments.csv
      appointment_items.csv
      patient_goals.csv
      weight_entries.csv
      satisfaction_entries.csv
      alerts.csv
      data_quality_issues.csv

  src/
    mock_data.py
    schemas.py
    metrics.py
    alerts.py
    quality.py
    navigation.py

    pages/
      visao_geral.py
      mapa_decisao.py
      pacientes.py
      ficha_paciente.py
      alertas.py
      atualizacao_dados.py
      qualidade_dados.py

    components/
      sidebar.py
      kpi_cards.py
      badges.py
      tables.py
      filters.py
      patient_header.py
      empty_states.py

    charts/
      weight_chart.py
      decision_map.py
      execution_chart.py
```

---

## 5. Escopo da casca navegável

### Deve implementar

- Sidebar navegável.
- Página Visão Geral.
- Página Mapa de Decisão.
- Página Pacientes.
- Página Ficha do Paciente.
- Página Alertas.
- Página Atualização de Dados.
- Página Qualidade dos Dados.
- Dados fictícios compatíveis com o modelo.
- Seleção de paciente.
- Filtros básicos.
- Tabelas e cards.
- Gráficos com Plotly.
- Estados vazios para informações faltantes.
- Mensagens indicando “dados fictícios / aguardando integração”.

### Não deve implementar agora

- Parser real de PDF.
- Parser real de Excel.
- Supabase.
- Login.
- Deploy.
- WhatsApp.
- Google Drive.
- Alertas reais complexos.
- Persistência real.
- Permissões de usuário.
- Edição real no banco.

---

## 6. Modelo de dados mockado

A aplicação deve funcionar com DataFrames que simulam o banco futuro.

### 6.1. patients

| Campo | Tipo | Exemplo |
|---|---|---|
| patient_id | string | `pat_001` |
| name | string | `Kelly Cristina Amorim` |
| normalized_name | string | `kelly cristina amorim` |
| medical_record | string | `7714697` |
| phone | string | `(62) 99999-9999` |
| age | int | `38` |
| created_at | datetime/string | `2026-05-25` |

Observação: telefone deve existir no mock, mas não precisa aparecer de forma destacada.

### 6.2. treatment_plans

| Campo | Tipo | Exemplo |
|---|---|---|
| plan_id | string | `plan_001` |
| patient_id | string | `pat_001` |
| budget_code | string | `orc_001` |
| issue_date | date/string | `2026-05-25` |
| start_date | date/string | `2026-05-25` |
| end_date | date/string | `2026-06-22` |
| status | string | `Ativo` |
| main_goal | string | `Emagrecimento` |
| is_renewal | bool | `false` |
| notes | string | `Plano inicial de acompanhamento.` |

### 6.3. treatment_plan_items

| Campo | Tipo | Exemplo |
|---|---|---|
| plan_item_id | string | `item_001` |
| plan_id | string | `plan_001` |
| patient_id | string | `pat_001` |
| budget_code | string | `orc_001` |
| raw_name | string | `Injetáveis EV - Plano` |
| category | string | `EV` |
| sessions_expected | int | `4` |
| frequency_text | string | `4 sessões 1 vez por semana` |
| frequency_type | string | `Semanal` |
| source | string | `PDF` |
| needs_manual_review | bool | `false` |

Categorias iniciais:

```txt
EV
IM
SC
Medicamento emagrecedor
Medicamento manipulado
Implante
Acompanhamento profissional
Deep Regenera
Outro
```

### 6.4. execution_summary

Fonte futura: relatório de frequência.

| Campo | Tipo | Exemplo |
|---|---|---|
| execution_id | string | `exec_001` |
| patient_id | string | `pat_001` |
| plan_id | string | `plan_001` |
| budget_code | string | `orc_001` |
| procedure_raw | string | `Injetáveis EV - Plano` |
| procedure_category | string | `EV` |
| status | string | `Em tratamento` |
| sessions_expected | int | `4` |
| sessions_completed | int | `2` |
| sessions_remaining | int | `2` |
| plan_created_at | date/string | `2026-05-25` |

Status possíveis:

```txt
Não iniciado
Aguardando
Em tratamento
Finalizado
```

### 6.5. appointments

Fonte futura: relatório de agendamentos.

| Campo | Tipo | Exemplo |
|---|---|---|
| appointment_id | string | `appt_001` |
| appointment_code | string | `12345` |
| patient_id | string | `pat_001` |
| budget_codes | string/list | `orc_001` |
| appointment_start | datetime/string | `2026-06-01 14:00` |
| appointment_end | datetime/string | `2026-06-01 15:00` |
| appointment_raw | string | `Injetáveis EV, Injetáveis IM` |
| professional | string | `Débora` |
| scheduled_by | string | `Recepção` |
| status | string | `Atendido` |

Status possíveis:

```txt
Agendado
Confirmado
Atendido
Cancelado
Atrasado
Reagendado
```

### 6.6. appointment_items

| Campo | Tipo | Exemplo |
|---|---|---|
| appointment_item_id | string | `appt_item_001` |
| appointment_id | string | `appt_001` |
| patient_id | string | `pat_001` |
| budget_code | string | `orc_001` |
| raw_item | string | `Injetáveis EV` |
| category | string | `EV` |
| status | string | `Atendido` |
| appointment_start | datetime/string | `2026-06-01 14:00` |
| professional | string | `Débora` |

### 6.7. patient_goals

| Campo | Tipo | Exemplo |
|---|---|---|
| goal_id | string | `goal_001` |
| patient_id | string | `pat_001` |
| plan_id | string | `plan_001` |
| goal_type | string | `Emagrecimento` |
| initial_weight | float | `98.0` |
| target_weight | float | `85.0` |
| target_date | date/string | `2026-06-22` |
| goal_notes | string | `Reduzir peso com acompanhamento semanal.` |

### 6.8. weight_entries

| Campo | Tipo | Exemplo |
|---|---|---|
| weight_id | string | `w_001` |
| patient_id | string | `pat_001` |
| plan_id | string | `plan_001` |
| measurement_date | date/string | `2026-05-25` |
| weight | float | `98.0` |
| source | string | `Manual` |
| notes | string | `Peso inicial` |

### 6.9. satisfaction_entries

| Campo | Tipo | Exemplo |
|---|---|---|
| satisfaction_id | string | `sat_001` |
| patient_id | string | `pat_001` |
| plan_id | string | `plan_001` |
| date | date/string | `2026-06-01` |
| satisfaction_status | string | `Satisfeito` |
| score | int | `4` |
| notes | string | `Paciente relata boa evolução.` |

Status possíveis:

```txt
Satisfeito
Neutro
Insatisfeito
Não informado
```

### 6.10. alerts

| Campo | Tipo | Exemplo |
|---|---|---|
| alert_id | string | `alert_001` |
| patient_id | string | `pat_001` |
| plan_id | string | `plan_001` |
| category | string | `Comercial` |
| alert_type | string | `Renovação próxima` |
| description | string | `Plano termina nos próximos 30 dias.` |
| priority | string | `Média` |
| status | string | `Aberto` |
| created_at | datetime/string | `2026-06-01` |
| comment | string | `Entrar em contato para renovação.` |

Categorias:

```txt
Enfermagem
Médica
Comercial
Nutrição
```

Prioridades:

```txt
Alta
Média
Baixa
```

Status:

```txt
Aberto
Em análise
Resolvido
```

### 6.11. data_quality_issues

| Campo | Tipo | Exemplo |
|---|---|---|
| issue_id | string | `dq_001` |
| source | string | `Dados manuais` |
| severity | string | `Média` |
| issue_type | string | `Campo ausente` |
| description | string | `Paciente sem satisfação informada.` |
| patient_id | string | `pat_003` |
| field_name | string | `satisfaction_status` |

---

## 7. Dados fictícios mínimos

Criar pelo menos 8 pacientes fictícios:

1. Kelly Cristina Amorim
2. Jaqueline Aparecida Vilela
3. Ana Maria Souza
4. Ricardo Silva Lima
5. Carla Pereira
6. João Martins
7. Beatriz Gomes
8. Mariana Dias

Os dados devem cobrir cenários diferentes:

| Cenário | Exemplo |
|---|---|
| Paciente engajado e satisfeito | Kelly |
| Paciente engajado mas insatisfeito | Carla |
| Paciente não engajado e satisfeito | João |
| Paciente não engajado e insatisfeito | Ricardo |
| Plano próximo do fim | Beatriz |
| Sem peso atualizado | Mariana |
| Procedimento não iniciado | Jaqueline |
| Medicamento manipulado pendente | Ana |

---

## 8. Telas obrigatórias

## 8.1. Visão Geral

### Objetivo

Mostrar leitura rápida da operação.

### Componentes

- Título: `Visão Geral`
- Cards:
  - Pacientes em plano
  - Engajados
  - Com alerta
  - Renovação próxima
  - Não engajados
  - Sem peso atualizado
- Gráfico: evolução média de peso esperado vs realizado
- Lista: pacientes que precisam de atenção
- Texto: última atualização fictícia
- Aviso discreto: `Dados fictícios para validação visual`

### DataFrames usados

- patients
- treatment_plans
- execution_summary
- alerts
- weight_entries
- patient_goals

---

## 8.2. Mapa de Decisão

### Objetivo

Mostrar pacientes nos quatro quadrantes.

### Quadrantes

```txt
Engajado + Satisfeito
Engajado + Não satisfeito
Não engajado + Satisfeito
Não engajado + Não satisfeito
```

### Componentes

- Matriz 2x2.
- Chips/iniciais dos pacientes.
- Contagem por quadrante.
- Legenda.
- Ao selecionar um paciente, abrir ou indicar a ficha dele.

### Regra mockada

- Engajamento vem de `execution_summary` e `appointments`.
- Satisfação vem de `satisfaction_entries`.

---

## 8.3. Pacientes

### Objetivo

Listar pacientes e permitir seleção.

### Componentes

- Busca por nome.
- Filtros:
  - Status do plano
  - Engajamento
  - Renovação
  - Alerta ativo
- Tabela com:
  - Nome
  - Status
  - Início
  - Fim
  - Orçamento
  - Sessões previstas
  - Sessões realizadas
  - Sessões restantes
  - Engajamento
  - Alertas
- Selectbox ou botão para abrir ficha do paciente.

---

## 8.4. Ficha do Paciente

### Objetivo

Mostrar visão completa individual.

### Componentes

- Cabeçalho:
  - Nome
  - Idade
  - Status do plano
  - Objetivo
  - Peso inicial
  - Peso atual
  - Peso meta
- Gráfico:
  - Peso esperado
  - Peso realizado
- Tabela:
  - Procedimento
  - Previsto
  - Realizado
  - Restante
  - Status
- Tabela:
  - Últimos agendamentos
  - Data
  - Procedimento
  - Profissional
  - Status
- Alertas do paciente.
- Observações/resumo.

---

## 8.5. Alertas

### Objetivo

Centralizar ações necessárias.

### Componentes

- Filtros:
  - Todos
  - Enfermagem
  - Médica
  - Comercial
  - Nutrição
- Tabela/cards:
  - Paciente
  - Categoria
  - Tipo
  - Descrição
  - Prioridade
  - Status
  - Data
- Destaque visual por prioridade.

---

## 8.6. Atualização de Dados

### Objetivo

Mostrar como será o fluxo futuro de alimentação.

### Componentes

- Upload simulado:
  - PDFs de plano
  - Relatório de frequência
  - Relatório de agendamentos
  - Dados manuais
- Preview dos dados fictícios.
- Cards de status:
  - Arquivos recebidos
  - Registros processados
  - Problemas encontrados
- Botão fictício: `Processar dados`
- Mensagem: `Nesta versão, o processamento é demonstrativo.`

---

## 8.7. Qualidade dos Dados

### Objetivo

Mostrar lacunas e confiabilidade dos dados.

### Componentes

- Score geral de qualidade.
- Barras:
  - Completude
  - Consistência
  - Atualidade
  - Validade
- Tabela de problemas:
  - Paciente
  - Fonte
  - Tipo
  - Severidade
  - Descrição
- Checklist do que falta pedir ao cliente:
  - peso inicial
  - peso objetivo
  - peso atual
  - satisfação
  - renovação
  - regra de data fim

---

## 9. Regras mockadas para a casca

### Engajamento

Para a casca, calcular:

```txt
Alto = sessões realizadas / sessões previstas >= 70%
Médio = entre 30% e 69%
Baixo = abaixo de 30%
```

Quando não houver execução, marcar:

```txt
Não informado
```

### Renovação próxima

```txt
end_date - hoje <= 30 dias
```

### Status do plano

Mockar valores:

```txt
Ativo
Pausado
Concluído
Aguardando início
```

### Alertas mockados

Gerar ou carregar alertas fictícios para:

```txt
Renovação próxima
Procedimento não iniciado
Sessões restantes
Peso sem atualização
Satisfação ausente
Agendamento cancelado
Agendamento atrasado
Manipulado pendente
```

---

## 10. Comportamento de navegação

### Requisito

O usuário deve conseguir navegar assim:

```txt
Visão Geral
  → clicar/ver paciente em atenção
  → ir para Ficha do Paciente

Pacientes
  → selecionar paciente
  → abrir Ficha do Paciente

Mapa de Decisão
  → selecionar paciente
  → abrir Ficha do Paciente

Alertas
  → selecionar paciente do alerta
  → abrir Ficha do Paciente
```

### Implementação simples

Como Streamlit não tem roteamento complexo nativo obrigatório, usar `st.session_state`.

Exemplo:

```python
st.session_state["selected_patient_id"] = patient_id
st.session_state["page"] = "Ficha do Paciente"
st.rerun()
```

---

## 11. Critérios de aceite da casca

A casca será considerada pronta quando:

```txt
[ ] O app abrir localmente com streamlit run app.py.
[ ] A sidebar permitir navegação entre todas as páginas.
[ ] Todas as páginas renderizarem sem erro.
[ ] Os dados fictícios seguirem os schemas definidos.
[ ] A tela Visão Geral mostrar KPIs e lista de atenção.
[ ] A tela Pacientes permitir busca/filtro e seleção.
[ ] A Ficha do Paciente mostrar plano, execução, peso, agendamentos e alertas.
[ ] O Mapa de Decisão mostrar quatro quadrantes.
[ ] A tela Alertas permitir filtro por categoria.
[ ] A tela Atualização de Dados mostrar fluxo futuro de upload/processamento.
[ ] A tela Qualidade dos Dados mostrar lacunas e score.
[ ] O código estiver modular.
[ ] Trocar dados fictícios por reais não deve exigir redesenhar telas.
```

---

## 12. Prompt final para IA de codificação

```txt
Você é um engenheiro sênior especialista em Python, Streamlit, Pandas e Plotly.

Construa uma casca navegável em Streamlit para o MAP de Acompanhamento de Pacientes.

Objetivo:
Validar visual, navegação e contrato de dados usando dados fictícios aderentes ao modelo de banco futuro.

Não implemente parser real, Supabase, login, deploy, WhatsApp ou Google Drive.

Implemente:
- app.py com navegação lateral
- páginas separadas em src/pages
- componentes em src/components
- gráficos em src/charts
- dados fictícios em src/mock_data.py ou data/mock/*.csv
- schemas coerentes com:
  - patients
  - treatment_plans
  - treatment_plan_items
  - execution_summary
  - appointments
  - appointment_items
  - patient_goals
  - weight_entries
  - satisfaction_entries
  - alerts
  - data_quality_issues

Crie pelo menos 8 pacientes fictícios cobrindo cenários:
- engajado/satisfeito
- engajado/não satisfeito
- não engajado/satisfeito
- não engajado/não satisfeito
- renovação próxima
- sem peso atualizado
- procedimento não iniciado
- manipulado pendente

Telas:
1. Visão Geral
2. Mapa de Decisão
3. Pacientes
4. Ficha do Paciente
5. Alertas
6. Atualização de Dados
7. Qualidade dos Dados

A navegação deve permitir selecionar um paciente e abrir sua ficha.

Priorize uma entrega funcional, limpa e modular.
Use Streamlit nativo sempre que possível:
- st.sidebar
- st.columns
- st.metric
- st.dataframe
- st.tabs
- st.file_uploader
- st.container
- st.session_state

Use Plotly para gráficos.

A aplicação deve deixar claro que os dados são fictícios e que a estrutura está pronta para receber dados reais depois.
```

---

## 13. Resultado esperado

Ao final, teremos uma aplicação navegável que funciona como protótipo técnico-visual.

Ela não será apenas imagem. Será uma casca executável.

Quando os dados reais forem integrados, a expectativa é trocar a origem dos DataFrames, não redesenhar o app.
