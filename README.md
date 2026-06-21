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
- psycopg 3 (apenas no backend Postgres — `psycopg[binary]>=3.2,<4`)

## Como rodar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Observação: em alguns ambientes Windows, o comando `streamlit` pode não estar no PATH. Nesse caso, prefira `python -m streamlit`.

## Deploy

A publicação no Streamlit Community Cloud ainda não foi feita. Quando for a hora, o guia completo está em [`DEPLOY.md`](DEPLOY.md) — inclui gate de LGPD, setup, configuração de secrets, modelo de acesso privado por lista de emails e plano de rollback. Para o passo-a-passo operacional de provisionar e configurar o Neon Postgres, ver [`NEON_SETUP.md`](NEON_SETUP.md).

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
  init_neon_schema.py # bootstrap one-shot do schema no Neon
  make_synthetic_pdf.py # gera PDF PII-clean para primeiro teste de import
src/
  data_layer/        # router + 2 backends (csv_backend + postgres_backend)
  mock_data.py       # fábrica de seed usada por scripts/seed_csvs.py
  metrics.py
  quality.py
  navigation.py
  schemas.py
  pages/
  components/
  charts/
data/
  csv/               # 11 tabelas do contrato (header only em runtime; schema reference)
  images/            # capturas de referência e Croquis_SAD_DClinique.png
NEON_SETUP.md        # runbook de provisionamento e config do Neon
SLA_REPORT.md        # benchmarks de cold start e impacto da migração Postgres
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

`src.data_layer.load_all() -> dict[str, pandas.DataFrame]` devolve o
mesmo shape do antigo `load_mock_data()`. Tabelas:

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

**Backend em runtime:** o `src/data_layer/__init__.py` decide o
backend via env var ``DCLINIQUE_BACKEND``:

- ``postgres`` (default) — `postgres_backend.py` conecta no Neon
  Serverless Postgres (DSN em `st.secrets["postgres"]["dsn"]` ou
  env var ``NEON_DSN``). Ativo em PRD.
- ``csv`` (fallback) — `csv_backend.py` lê os 11 CSVs em
  `data/csv/`. Útil para dev local sem internet e para reproduzir
  bugs sem subir Postgres.

Em ambos os casos a API pública (`load_all`, `load_table`,
`append_row`, `update_row`, `next_id`) é **idêntica** — o resto do
código (`app.py`, `src/components/`, `src/pages/`) não sabe qual
backend está ativo.

Os CSVs em `data/csv/` hoje têm **header only** (zero linhas); são
schema reference compartilhada entre dev local e PRD. ``seed_csvs.py``
ainda existe no repo caso seja necessário repopular (não roda em
runtime).

## Revisão automática de aceite

Além de abrir a aplicação, a entrega foi revisada contra o checklist de execução, estrutura, dados, navegação e visual. A página **Qualidade dos Dados** também valida se os DataFrames lidos do CSV contêm as colunas esperadas do contrato futuro.

## Navegação

A navegação usa `st.session_state["page"]` e `st.session_state["selected_patient_id"]`, permitindo abrir a ficha a partir de Visão Geral, Mapa de Decisão, Pacientes e Alertas.

## Escopo desta casca

- Foco em fluxo navegavel, legibilidade visual e contrato de dados mockado.
- Persistência em runtime: Neon Postgres (PRD) ou CSVs locais (dev fallback). Sem autenticação e sem integrações externas.
- Mudanças devem preservar nomes de campos e tabelas retornados por `load_all()`.
