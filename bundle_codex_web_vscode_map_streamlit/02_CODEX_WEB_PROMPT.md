# Prompt Principal para Codex Web

Use este prompt no Codex Web apontando para o repositório GitHub vazio.

---

Você é um engenheiro de software sênior especialista em Python, Streamlit, Pandas, Plotly e arquitetura modular.

Crie a primeira versão de uma **casca navegável em Streamlit** para o projeto:

> MAP de Acompanhamento de Pacientes em Planos de Tratamento

## Objetivo

Gerar um app navegável para validar visual, fluxo e contrato de dados.

Os dados devem ser fictícios, mas precisam seguir o modelo de banco planejado. A troca futura para dados reais não deve exigir redesenhar as telas.

## Importante

Não implemente parser real de PDF.  
Não implemente parser real de Excel.  
Não implemente Supabase.  
Não implemente login.  
Não implemente deploy.  
Não implemente WhatsApp.  
Não implemente Google Drive.

Esta entrega é somente:

```text
casca navegável
+
dados mockados fiéis ao schema futuro
+
estrutura modular
```

## Stack obrigatória

- Python
- Streamlit
- Pandas
- Plotly
- OpenPyXL

## Arquivos principais esperados

Crie:

```text
app.py
requirements.txt
README.md
.gitignore

src/
  mock_data.py
  metrics.py
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

data/
  mock/
```

## DataFrames mockados obrigatórios

Implemente em `src/mock_data.py` uma função:

```python
load_mock_data() -> dict[str, pandas.DataFrame]
```

Ela deve retornar:

```text
patients
treatment_plans
treatment_plan_items
execution_summary
appointments
appointment_items
patient_goals
weight_entries
satisfaction_entries
alerts
data_quality_issues
```

## Pacientes fictícios mínimos

Crie ao menos 8 pacientes:

1. Kelly Cristina Amorim
2. Jaqueline Aparecida Vilela
3. Ana Maria Souza
4. Ricardo Silva Lima
5. Carla Pereira
6. João Martins
7. Beatriz Gomes
8. Mariana Dias

Cubra os cenários:

- engajado e satisfeito;
- engajado e não satisfeito;
- não engajado e satisfeito;
- não engajado e não satisfeito;
- renovação próxima;
- sem peso atualizado;
- procedimento não iniciado;
- manipulado pendente.

## Telas obrigatórias

### 1. Visão Geral

Mostrar:

- KPIs com `st.metric`;
- pacientes em plano;
- engajados;
- com alerta;
- renovação próxima;
- não engajados;
- sem peso atualizado;
- gráfico médio de peso esperado vs realizado;
- lista de pacientes em atenção.

### 2. Mapa de Decisão

Mostrar matriz 2x2:

```text
Engajado + Satisfeito
Engajado + Não satisfeito
Não engajado + Satisfeito
Não engajado + Não satisfeito
```

Cada quadrante deve mostrar chips/iniciais dos pacientes.

### 3. Pacientes

Mostrar:

- busca por nome;
- filtros por status, engajamento, renovação e alerta;
- tabela de pacientes;
- seleção de paciente;
- botão ou ação para abrir Ficha do Paciente.

### 4. Ficha do Paciente

Mostrar:

- cabeçalho do paciente;
- status;
- objetivo;
- peso inicial;
- peso atual;
- peso meta;
- gráfico peso esperado vs realizado;
- tabela plano/execução:
  - procedimento;
  - previsto;
  - realizado;
  - restante;
  - status;
- últimos agendamentos;
- alertas do paciente;
- observações/resumo.

### 5. Alertas

Mostrar:

- filtros por categoria:
  - Todos
  - Enfermagem
  - Médica
  - Comercial
  - Nutrição
- tabela/cards de alertas;
- prioridade;
- status;
- data.

### 6. Atualização de Dados

Mostrar tela demonstrativa com:

- upload simulado;
- tipos de fonte:
  - PDFs de plano;
  - Relatório de frequência;
  - Relatório de agendamentos;
  - Dados manuais;
- preview fictício;
- status dos arquivos;
- botão `Processar dados`, sem lógica real.

### 7. Qualidade dos Dados

Mostrar:

- score geral;
- completude;
- consistência;
- atualidade;
- validade;
- tabela de problemas;
- checklist do que falta pedir ao cliente.

## Navegação

Use `st.session_state` para controlar:

```python
st.session_state["page"]
st.session_state["selected_patient_id"]
```

A navegação deve permitir:

```text
Pacientes → Ficha do Paciente
Mapa de Decisão → Ficha do Paciente
Alertas → Ficha do Paciente
Visão Geral → Ficha do Paciente
```

## Regras mockadas

### Engajamento

```text
Alto = sessões realizadas / sessões previstas >= 70%
Médio = entre 30% e 69%
Baixo = abaixo de 30%
```

### Renovação próxima

```text
end_date - hoje <= 30 dias
```

### Status possíveis

Plano:

```text
Ativo
Pausado
Concluído
Aguardando início
```

Agendamento:

```text
Agendado
Confirmado
Atendido
Cancelado
Atrasado
Reagendado
```

Frequência/execução:

```text
Não iniciado
Aguardando
Em tratamento
Finalizado
```

Alertas:

```text
Aberto
Em análise
Resolvido
```

## Critérios de aceite

A entrega deve cumprir:

```text
[ ] streamlit run app.py funciona.
[ ] Todas as páginas abrem sem erro.
[ ] Os DataFrames mockados seguem o schema definido.
[ ] A sidebar navega entre telas.
[ ] É possível selecionar paciente e abrir ficha.
[ ] A Ficha do Paciente mostra plano, execução, peso, agendamentos e alertas.
[ ] O Mapa de Decisão mostra quatro quadrantes.
[ ] A tela Alertas filtra por categoria.
[ ] A tela Atualização de Dados deixa claro que é demonstrativa.
[ ] A tela Qualidade dos Dados mostra lacunas.
[ ] O código está modular.
[ ] O README explica como rodar.
```

## Primeira ação

Antes de escrever código, crie a estrutura de pastas e arquivos. Depois implemente `mock_data.py`. Depois implemente `app.py` e as páginas.

Ao final, garanta que:

```bash
pip install -r requirements.txt
streamlit run app.py
```

funcione localmente.
