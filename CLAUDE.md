# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projecto

**MAP** (Minimum Acceptable Product) — casca navegável Streamlit para acompanhamento de pacientes em planos de tratamento. Dados fictícios em CSVs versionados em `data/csv/`, modelados como se viessem do banco futuro. Não há parser real de PDF/Excel, Supabase, login, deploy, WhatsApp ou Google Drive.

## Comandos essenciais

```bash
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt

# Rodar a aplicação
streamlit run app.py
# ou, se `streamlit` não estiver no PATH:
python -m streamlit run app.py

# Validar o contrato de dados sem subir o servidor
.venv\Scripts\python.exe -c "from src.data_layer import load_all; d=load_all(); print('OK', list(d.keys()))"
.venv\Scripts\python.exe -c "from src.data_layer import load_all; d=load_all(); print(d['patients']['patient_id'].head(3).tolist())"

# Regenerar os CSVs em data/csv/ a partir do seed (rodar quando o schema
# ou fixture mudar — não roda em runtime, os CSVs são commitados)
.venv\Scripts\python.exe scripts/seed_csvs.py

# Benchmark de SLA (gera benchmark_sla_results.json e atualiza SLA_REPORT.md)
# Rodar de dentro de um worktree de benchmark:
PYTHONPATH=. ../../../.venv/Scripts/python.exe benchmark_sla.py
```

Não há suíte de testes automatizados, linter ou formatter configurado. A validação padrão é `streamlit run app.py` + abertura manual de cada página + fluxo para a Ficha do Paciente a partir de Pacientes, Visão Geral, Mapa de Decisão e Alertas. Os testes em `tests/` (pytest) cobrem o data layer e os fluxos críticos de cadastro.

## Arquitetura

Casca navegável fina em Streamlit com sessão-controlada. Stack: Streamlit, Pandas, Plotly, OpenPyXL, python-dotenv.

### Ponto de entrada e roteamento lazy (`app.py`)

`app.py` define `_PAGE_MODULES` (mapeamento nome de página → módulo `src.pages.*`) e um `_route_cache`. `_route(page)` resolve e memoiza o `render` da página via `importlib.import_module` na primeira visita — pages não visitadas não pagam custo de import (importante para o cold start; ver SLA_REPORT.md). `get_data()` é decorado com `@st.cache_data` e faz o import de `load_all` dentro do corpo para manter o pandas fora do caminho frio do `app.py`.

### Camada de dados (`src/data_layer/`)

A fonte de dados são 11 CSVs versionados em `data/csv/` (um por tabela do contrato). O módulo `src.data_layer` exporta `load_all()`, `load_table()`, `append_row()`, `update_row()` e `next_id()`. `load_all()` lê os 11 CSVs e devolve `dict[str, pd.DataFrame]` com o mesmo shape que o antigo `load_mock_data()`. Os CSVs são regenerados via `scripts/seed_csvs.py` (uma vez por mudança de schema, não em runtime) e **committados no repo** para que um checkout novo tenha dados.

Mutações (`add_patient.py:_handle_submit`, `ficha.py:_handle_submit`) chamam `append_row(...)` (e `update_row(...)` para atualizar idade do paciente no cadastro da ficha), em seguida `st.cache_data.clear()` e setam `st.session_state["_data_dirty"] = True`. As páginas que precisam ver a mudança no mesmo render checam o flag e re-chamam `load_all()` para bypassar o cache invalidado — sem `st.rerun()` (que interagiria mal com `clear_on_submit=True`).

`_next_patient_id` (e `_next_plan_id`/etc.) foram removidos: o id é derivado do CSV no momento do append via `next_id(table)`, que escaneia a coluna primária da tabela e devolve o próximo `pat_new_NNN` / `plan_new_NNN` / `item_new_NNN` / `goal_new_NNN` / `w_new_NNN` disponível.

### Estado de navegação (`src/navigation.py`)

- `st.session_state["page"]` — chave primária de página; valores válidos em `PAGES = SIDEBAR_PAGES + ["Ficha do Paciente"]`.
- `st.session_state["selected_patient_id"]` — id do paciente aberto na Ficha.
- `go_to(page)` para páginas top-level (faz `st.rerun()`); `open_patient(patient_id)` para a Ficha do Paciente (NÃO chama `st.rerun()` — setar session state dentro de callback já dispara rerun; chamar `st.rerun()` é no-op).
- `init_navigation_state()` deve ser chamado no `main()` antes do sidebar; também faz fallback se `page` for inválido.

A sidebar (`src/components/sidebar.py`) também aceita deep-link via query params `?nav=<page>&patient_id=<id>` e `?refresh=1` (limpa `st.cache_data`). SVG icons são servidos como data URIs; `data/images/icones_Croquis_SVG/` é o diretório lido em runtime.

### Camadas

- **`src/data_layer/`** — backend CSV: `csv_backend.py` com `load_all`, `load_table`, `append_row`, `update_row`, `next_id`, `csv_dir`. `__init__.py` reexporta o público. A coluna primária é sempre a primeira de `EXPECTED_SCHEMAS`; o tipo (`Timestamp`/`bool`/`Int64`) é restaurado em `load_table` via mapas `_DATE_COLUMNS` / `_BOOL_COLUMNS` / `_NULLABLE_INT_COLUMNS`. O caminho do diretório CSV é resolvido por `_csv_dir_callable` (default: `data/csv/` ao lado do projeto) para que os testes façam `monkeypatch` por teste.
- **`src/mock_data.py`** — `load_mock_data()` continua existindo como fábrica de seed para `scripts/seed_csvs.py`. Não é mais chamado em runtime — `get_data()` em `app.py` agora chama `load_all()`.
- **`src/schemas.py`** — `EXPECTED_SCHEMAS` declara as colunas esperadas de cada tabela; `validate_mock_schema(data)` é o que a página Qualidade dos Dados usa.
- **`src/metrics.py`** — derivam `patient_summary` (engajamento, último status, último peso, `days_to_renewal`, `without_recent_weight`, etc.), `overview_kpis`, `attention_patients`. Cálculos vetorizados (NumPy `errstate`, `pd.cut`, `np.select`); funções decoradas com `@st.cache_data`.
- **`src/quality.py`** — `quality_scores(data)` e `client_checklist()` para a página Qualidade dos Dados.
- **`src/charts/`** — wrappers Plotly. `weight_chart.py` tem dois caminhos: `_weight_with_expected_single` (Ficha do Paciente — pré-filtra por patient_id) e `_weight_with_expected` (Visão Geral — agregado mensal). `import plotly` está dentro das funções, não no topo do módulo, para preservar o cold start.
- **`src/components/`** — peças reutilizadas: `sidebar`, `patient_header`, `badges`, `filters`, `kpi_cards`, `patient_actions`, `tables`, `empty_states`. O CSS da sidebar está inline em `sidebar.py` (injetado via `st.markdown(..., unsafe_allow_html=True)`).
- **`src/pages/`** — uma página por arquivo, cada uma com `def render(data) -> None`. Páginas: `visao_geral`, `mapa_decisao`, `pacientes`, `ficha_paciente`, `alertas`, `atualizacao_dados`, `qualidade_dados`. Trocar `st.columns` por `st.markdown(HTML único)` é a otimização recomendada para tabelas/listas grandes (ver `pacientes.py`).

### Tabelas (contrato)

`patients`, `treatment_plans`, `treatment_plan_items`, `execution_summary`, `appointments`, `appointment_items`, `patient_goals`, `weight_entries`, `satisfaction_entries`, `alerts`, `data_quality_issues`. Ver `src/schemas.py` para colunas exatas. Cada tabela vive em `data/csv/<table>.csv` com as colunas na ordem do schema; linhas podem ser appendadas em runtime via `src.data_layer.append_row`.

## Restrições de escopo (reforçadas pelos prompts do repositório)

As restrições abaixo aparecem em todos os `.github/agents/*.agent.md` e `.github/prompts/*.prompt.md` e devem ser respeitadas em qualquer mudança:

- **Não** implementar parser real de PDF/Excel, Supabase, login, deploy, WhatsApp, Google Drive ou outras integrações externas.
- **Não** expandir escopo funcional sem alinhamento — o projeto é uma casca navegável, não o produto final.
- **Preservar** nomes de campos e o contrato de `load_all()` (ver `src/schemas.py`).
- **Não** aceitar pendências em validação sem registrar impacto.

## Agentes e prompts auxiliares (`.github/`)

Há três agentes e seis prompts que modelam um fluxo macro-run:

- **Agentes:** `map-diagnostico` (read-only, prioriza e planeja), `map-implementacao` (edita com validação local), `map-validacao` (smoke test + checklist de aceite).
- **Prompts (macro-runs):** `macro-run-a` (base técnica / mock_data), `macro-run-b` (fluxo de navegação / ficha), `macro-run-c` (qualidade visual), `macro-run-d` (refatoração + README). `diagnostico-map` precede A; `validacao-final` fecha a rodada antes de PR.

Cada macro-run tem fluxo obrigatório: listar arquivos a alterar → aplicar mudanças mínimas → validar local → reportar erros remanescentes → entregar resumo com impacto/riscos.

## Otimizações ativas (SLA)

- `.streamlit/config.toml` — `headless=true`, `enableStaticServing`, `fastReruns`, `toolbarMode=minimal`, `runOnSave=false`, `fileWatcherType="none"`.
- `app.py` resolve páginas via `importlib` lazy; `get_data()` adia import de pandas.
- Métricas vetorizadas e cacheadas; Plotly importado dentro das funções que o usam.
- `weight_chart.patient_weight_chart` usa caminho single-patient (pré-filtra antes do merge).
- Sidebar memoiza leitura/recoloração de SVG com `lru_cache` e regex pré-compilado.

SLA alvo (mediana): Mapa de Decisão ≤ 100 ms, navegação entre páginas p95 ≤ 100 ms, páginas leves ≤ 50 ms, páginas não visitadas pagam 0 ms de import. Cold start do framework (≈ 2,5 s, dominado por `import streamlit`) está documentado como fora do escopo desta casca. Detalhes em `SLA_REPORT.md`.

## Configuração e tooling

- Python 3.13, Streamlit 1.58.0 (ver `SLA_REPORT.md`).
- `.vscode/settings.json` aponta o interpretador padrão para o sistema (`ms-python.python:system`).
- `.claude/settings.local.json` já autorizou uma série de comandos de validação (imports, `streamlit --version`, smoke do `load_all`). Para rodar benchmark ou outros comandos, observe o permission mode atual.
- `data/images/` guarda capturas de referência de cada página e o `Croquis_SAD_DClinique.png` (design base); SVGs customizados ficam em `data/images/icones_Croquis_SVG/`.
- `data/csv/` guarda as 11 tabelas-fonte em CSV (uma por tabela, schema em `src/schemas.py`).
