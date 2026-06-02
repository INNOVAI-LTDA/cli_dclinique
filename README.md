# MAP — Casca Navegável de Acompanhamento de Pacientes

Primeira versão do **MAP (Minimum Acceptable Product)** para validar visual, fluxo de navegação e contrato de dados de acompanhamento de pacientes em planos de tratamento.

Esta entrega usa somente dados fictícios em memória, modelados como se viessem do banco futuro. Não há parser real de PDF, parser real de Excel, Supabase, login, deploy, WhatsApp ou Google Drive.

## Stack

- Python
- Streamlit
- Pandas
- Plotly
- OpenPyXL

## Como rodar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app.py
```

Observacao: em alguns ambientes Windows, o comando `streamlit` pode nao estar no PATH. Nesse caso, prefira `python -m streamlit`.

## Estrutura

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
  components/
  charts/
data/mock/
```

## Páginas disponíveis

- **Visão Geral**: KPIs, peso médio esperado vs realizado e pacientes em atenção.
- **Mapa de Decisão**: matriz 2x2 de engajamento e satisfação.
- **Pacientes**: busca, filtros, tabela e abertura da ficha.
- **Ficha do Paciente**: cabeçalho, objetivo, peso, plano, execução, agendamentos, alertas e resumo.
- **Alertas**: filtros por categoria e abertura da ficha do paciente.
- **Atualização de Dados**: fluxo demonstrativo de upload/processamento, sem lógica real.
- **Qualidade dos Dados**: score, dimensões de qualidade, problemas e checklist para o cliente.

## Contrato de dados mockado

`src/mock_data.py` expõe `load_mock_data() -> dict[str, pandas.DataFrame]` com as tabelas:

- `patients`
- `treatment_plans`
- `treatment_plan_items`
- `execution_summary`
- `appointments`
- `appointment_items`
- `patient_goals`
- `weight_entries`
- `satisfaction_entries`
- `alerts`
- `data_quality_issues`

## Revisão automática de aceite

Além de abrir a aplicação, a entrega foi revisada contra o checklist de execução, estrutura, dados, navegação e visual. A página **Qualidade dos Dados** também valida se os DataFrames mockados contêm as colunas esperadas do contrato futuro.

## Navegação

A navegação usa `st.session_state["page"]` e `st.session_state["selected_patient_id"]`, permitindo abrir a ficha a partir de Visão Geral, Mapa de Decisão, Pacientes e Alertas.

## Escopo desta casca

- Foco em fluxo navegavel, legibilidade visual e contrato de dados mockado.
- Sem persistencia em banco, sem autenticacao e sem integracoes externas.
- Mudancas devem preservar nomes de campos e tabelas retornados por `load_mock_data()`.
