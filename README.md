# MAP — Casca Navegável de Acompanhamento de Pacientes

Primeira versão do **MAP (Minimum Acceptable Product)** para validar visual, fluxo de navegação e contrato de dados de acompanhamento de pacientes em planos de tratamento.

Esta entrega usa somente dados fictícios em memória, modelados como se viessem do banco futuro. Não há parser real de PDF, parser real de Excel, Supabase, login, deploy, WhatsApp ou Google Drive.

> **Sobre deploy**: os artefatos para publicação no Streamlit Community Cloud estão **preparados** (ver [`DEPLOY.md`](DEPLOY.md)), mas **nenhum deploy efetivo foi feito nesta versão**. O deploy real exige a anonimização dos CSVs em `data/csv/` e uma revisão de LGPD — gate documentado em `DEPLOY.md`.

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
streamlit run app.py
```

Observação: em alguns ambientes Windows, o comando `streamlit` pode não estar no PATH. Nesse caso, prefira `python -m streamlit`.

## Deploy

A publicação no Streamlit Community Cloud ainda não foi feita. Quando for a hora, o guia completo está em [`DEPLOY.md`](DEPLOY.md) — inclui gate de LGPD, setup, configuração de secrets, modelo de acesso privado por lista de emails e plano de rollback.

## Estrutura

```text
app.py
requirements.txt
README.md
DEPLOY.md
.gitignore
.streamlit/
  config.toml
  secrets.toml.example
scripts/
  scan_pii.py
src/
  data_layer/        # backend CSV: load_all, append_row, update_row, next_id
  mock_data.py       # fábrica de seed usada por scripts/seed_csvs.py
  metrics.py
  quality.py
  navigation.py
  schemas.py
  pages/
  components/
  charts/
data/
  csv/               # 11 tabelas do contrato (fonte de verdade em runtime)
  images/            # capturas de referência e Croquis_SAD_DClinique.png
```

## Páginas disponíveis

- **Visão Geral**: KPIs, peso médio esperado vs realizado e pacientes em atenção.
- **Mapa de Decisão**: matriz 2x2 de engajamento e satisfação.
- **Pacientes**: busca, filtros, tabela e abertura da ficha.
- **Ficha do Paciente**: cabeçalho, objetivo, peso, plano, execução, agendamentos, alertas e resumo.
- **Alertas**: filtros por categoria e abertura da ficha do paciente.
- **Atualização de Dados**: fluxo demonstrativo de upload/processamento, sem lógica real.
- **Qualidade dos Dados**: score, dimensões de qualidade, problemas e checklist para o cliente.

## Contrato de dados

`src.data_layer.load_all() -> dict[str, pandas.DataFrame]` lê os 11 CSVs em `data/csv/` e devolve o mesmo shape do antigo `load_mock_data()`. Tabelas:

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

Os CSVs são regenerados via `scripts/seed_csvs.py` (uma vez por mudança de schema, não em runtime) e **committados no repo** para que um checkout novo tenha dados.

## Revisão automática de aceite

Além de abrir a aplicação, a entrega foi revisada contra o checklist de execução, estrutura, dados, navegação e visual. A página **Qualidade dos Dados** também valida se os DataFrames lidos do CSV contêm as colunas esperadas do contrato futuro.

## Navegação

A navegação usa `st.session_state["page"]` e `st.session_state["selected_patient_id"]`, permitindo abrir a ficha a partir de Visão Geral, Mapa de Decisão, Pacientes e Alertas.

## Escopo desta casca

- Foco em fluxo navegavel, legibilidade visual e contrato de dados mockado.
- Sem persistência em banco, sem autenticação e sem integrações externas.
- Mudanças devem preservar nomes de campos e tabelas retornados por `load_all()`.
