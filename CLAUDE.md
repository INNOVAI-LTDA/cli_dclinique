# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projecto

**MAP** (Minimum Acceptable Product) — casca navegável Streamlit para acompanhamento de pacientes em planos de tratamento. A fonte de verdade em PRD é **Postgres no Neon** (feature aprovada pelo Cliente — `src/data_layer/postgres_backend.py`, `scripts/init_neon_schema.py`, `scripts/validate_neon.py`). CSVs em `data/csv/` viraram schema de referência + fallback `csv` para dev offline (ativo quando `DCLINIQUE_BACKEND=csv`; default é `postgres`). A feature de **importação de pacientes via PDF** (`src/pdf_importer/`, `data/import_zones/default.json`, componente `importar_pdf_wizard`) é parte oficial do app — parser real de PDF é **exigência do Cliente** (não exceção). O **deploy no Streamlit Community Cloud** foi liberado (ver `DEPLOY.md` para o gate de LGPD, setup e modelo de acesso); o gate continua obrigatório antes de qualquer publicação. Continua fora do escopo: Supabase, login próprio, WhatsApp, Google Drive, parser de Excel e outras integrações externas não listadas.

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

# Bootstrap do schema Postgres no Neon (idempotente: CREATE TABLE IF NOT EXISTS
# para as 11 tabelas em EXPECTED_SCHEMAS). Roda uma vez apos provisionar o
# projeto Neon; re-rodar e' no-op.
DCLINIQUE_BACKEND=postgres .venv\Scripts\python.exe scripts/init_neon_schema.py

# Smoke test end-to-end do data layer Neon: conectividade, schema (init_schema),
# INSERT/UPDATE/DELETE em cada uma das 11 tabelas, e cleanup defensivo por
# `patient_id LIKE 'pat_test%'`. NAO-destrutivo (try/finally garante cleanup).
# Requer NEON_DSN (ou DCLINIQUE_DSN / st.secrets["postgres"]["dsn"]) configurado.
DCLINIQUE_BACKEND=postgres .venv\Scripts\python.exe scripts/validate_neon.py

# Wrapper PowerShell do smoke test: cria .venv se faltar, instala requirements
# se pandas/psycopg nao estiverem presentes, carrega .env, seta o backend
# postgres, e roda o validate_neon.py. Idempotente. Parametros: -DsnPath,
# -VenvDir, -SkipInstall.
pwsh scripts/run_validate_neon.ps1

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

A fonte de verdade em PRD é **Postgres no Neon** (default: `DCLINIQUE_BACKEND=postgres`). O módulo `src.data_layer` é um router: `__init__.py` lê `DCLINIQUE_BACKEND` e delega para `postgres_backend` (Neon) ou `csv_backend` (fallback dev offline). A API pública é idêntica nos dois backends: `load_all()`, `load_table()`, `append_row()`, `update_row()`, `next_id()`, `csv_dir()` / `data_dir()`. `reset_backend_cache()` está exposto para testes que alternam entre backends.

`postgres_backend.py` espelha `csv_backend.py` 1:1: lê as 11 tabelas via `SELECT *` e devolve `dict[str, pd.DataFrame]` com o mesmo shape. `connection.py` resolve o DSN na ordem `st.secrets["postgres"]["dsn"]` → `NEON_DSN` → `DCLINIQUE_DSN`, com `psycopg` lazy dentro de `get_engine()`. `schema.py` aplica `CREATE TABLE IF NOT EXISTS` em todas as 11 tabelas (idempotente; chamado por `scripts/init_neon_schema.py` no bootstrap e por `scripts/validate_neon.py` no smoke test). `psycopg`, `streamlit` e `pandas` são lazy — `import src.data_layer` não dispara conexão nem importa pacotes pesados.

Em modo `csv` (fallback dev), os 11 CSVs em `data/csv/` (header only após T9) servem como schema de referência e fonte de dados local. `seed_csvs.py` ainda funciona para repopular via `src.mock_data.load_mock_data()`. `psycopg` não precisa estar instalado no venv de quem usa só o modo `csv`.

Mutações (`add_patient.py:_handle_submit`, `ficha.py:_handle_submit`) chamam `append_row(...)` (e `update_row(...)` para atualizar idade do paciente no cadastro da ficha), em seguida `st.cache_data.clear()` e setam `st.session_state["_data_dirty"] = True`. As páginas que precisam ver a mudança no mesmo render checam o flag e re-chamam `load_all()` para bypassar o cache invalidado — sem `st.rerun()` (que interagiria mal com `clear_on_submit=True`).

`_next_patient_id` (e `_next_plan_id`/etc.) foram removidos: o id é derivado no momento do append via `next_id(table)`, que escaneia a coluna primária da tabela e devolve o próximo `pat_new_NNN` / `plan_new_NNN` / `item_new_NNN` / `goal_new_NNN` / `w_new_NNN` disponível.

### Estado de navegação (`src/navigation.py`)

- `st.session_state["page"]` — chave primária de página; valores válidos em `PAGES = SIDEBAR_PAGES + ["Ficha do Paciente"]`.
- `st.session_state["selected_patient_id"]` — id do paciente aberto na Ficha.
- `go_to(page)` para páginas top-level (faz `st.rerun()`); `open_patient(patient_id)` para a Ficha do Paciente (NÃO chama `st.rerun()` — setar session state dentro de callback já dispara rerun; chamar `st.rerun()` é no-op).
- `init_navigation_state()` deve ser chamado no `main()` antes do sidebar; também faz fallback se `page` for inválido.

A sidebar (`src/components/sidebar.py`) também aceita deep-link via query params `?nav=<page>&patient_id=<id>` e `?refresh=1` (limpa `st.cache_data`). SVG icons são servidos como data URIs; `data/images/icones_Croquis_SVG/` é o diretório lido em runtime.

### Camadas

- **`src/data_layer/`** — router Postgres/CSV: `__init__.py` delega para o backend ativo conforme `DCLINIQUE_BACKEND` (default `postgres`). `postgres_backend.py` (Neon) e `csv_backend.py` (fallback dev) expõem a mesma API (`load_all`, `load_table`, `append_row`, `update_row`, `next_id`, `csv_dir`/`data_dir`). `connection.py` resolve o DSN e cacheia o `psycopg.Connection` por processo. `schema.py` mapeia colunas para tipos Postgres (`TIMESTAMP`/`BOOLEAN`/`INTEGER`/`DOUBLE PRECISION`/`TEXT`) e aplica `CREATE TABLE IF NOT EXISTS` em todas as 11 tabelas. A coluna primária é sempre a primeira de `EXPECTED_SCHEMAS`; o tipo é restaurado em `load_table` via mapas `_DATE_COLUMNS` / `_BOOL_COLUMNS` / `_NULLABLE_INT_COLUMNS` (csv) ou `_postgres_type` (postgres). O caminho do diretório CSV é resolvido por `_csv_dir_callable` (default: `data/csv/`) para que os testes façam `monkeypatch` por teste.
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

- **Não** implementar Supabase, login próprio, WhatsApp, Google Drive, parser de Excel, ou outras integrações externas. As exceções aprovadas pelo Cliente são: **parser de PDF** (`src/pdf_importer/`, exigência do Cliente), **Postgres no Neon** como data layer em PRD (`src/data_layer/postgres_backend.py`, `scripts/init_neon_schema.py`) e **deploy no Streamlit Community Cloud** (ver `DEPLOY.md` para o gate de LGPD, obrigatório antes de qualquer publicação). Qualquer outra integração nova exige alinhamento antes.
- **Não** expandir escopo funcional sem alinhamento — o projeto é uma casca navegável, não o produto final.
- **Preservar** nomes de campos e o contrato de `load_all()` (ver `src/schemas.py`).
- **Não** aceitar pendências em validação sem registrar impacto.

## Caminho B — referência obrigatória (N7, N8, N9)

Quando o trabalho envolver o refactor incremental para o **modelo de dados v2** (4 classes: Organization / Users / Deliverables / Clients — ver `docs/data_model.md`), as políticas abaixo são **não-negociáveis** e devem ser lidas/consultadas **antes de qualquer código ser escrito**.

### Documentos mandatórios

| Doc | Propósito | Quando ler |
|---|---|---|
| `docs/data_model.md` | Design do modelo v2 (entidades, associações, DDL) | Antes de qualquer PR do refactor |
| `docs/caminho_b_plano.md` | 8 fases do refactor + plano de testes + modelo de execução | Antes de iniciar cada fase |
| `docs/exception_catalog.md` | Exceções por lib + mensagens PT-BR | Antes de chamar qualquer lib em `src/core/` |
| `docs/experience_log.md` | Histórico de testes (passou/falhou) e lições | **No início de cada fase**, antes de escrever código |
| `docs/phase_reports/phase_N_report.md` | Métricas de tempo/tokens por fase | Gerado a cada fim de fase |

### Princípios não-negociáveis (resumo; detalhes em `docs/caminho_b_plano.md` §2)

- **N7 — Tratamento de exceção obrigatório.** Toda chamada a função (lib externa ou código do projeto) é envolvida em `try/except` específico. Mensagem em **português**, log via `logging` (nunca `print`/`traceback`), **nunca** expor stacktrace bruto ao usuário. Catálogo de exceções da lib deve estar em `docs/exception_catalog.md` **antes** de o código ser escrito.
- **N8 — Acumulação de experiência.** Todo teste (passou **ou** falhou) gera entrada no `docs/experience_log.md` antes da fase ser declarada pronta. Log é **append-only** — entradas nunca são editadas/deletadas. A IA lê o log inteiro **no início de cada fase**.
- **N9 — Auditoria de custo de tokens.** A cada fim de fase, é produzido `docs/phase_reports/phase_N_report.md` com 9 métricas: tempo total, tempo código, tempo testes, tempo outros, caracteres totais, caracteres por feedback humano, método de conversão de tokens, tokens totais, tokens por feedback humano. Razão output/input > 20 = trigger para simplificar a próxima fase.

### Critério de "fase pronta"

Toda fase é considerada pronta apenas quando as 4 condições abaixo são **simultaneamente verdadeiras**:
1. `ruff check src/core tests/` retorna 0 erros
2. `pytest tests/` retorna 100% passed (incluindo `test_exception_handling.py`)
3. `streamlit run app.py` sobe sem traceback e as 7 páginas renderizam
4. N7 satisfeito: `test_exception_handling.py` passa, `docs/exception_catalog.md` atualizado, nenhum `print(` / `traceback.print_exc()` / `except:` em `src/core/`

Adicionalmente: N8 satisfeito (entradas no `experience_log.md`) e N9 satisfeito (`phase_N_report.md` produzido).

### Test execution

- **Quem roda os testes:** o usuário (`pwsh scripts/run_core_tests.ps1`). A IA **não** roda os testes pelo usuário.
- **Em caso de falha:** o usuário cola o conteúdo de `logs/test_core_<ts>.log` (humano) ou `logs/test_core_<ts>.json` (máquina) na conversa. A IA diagnostica a partir disso.
- **Detalhes do script:** ver `docs/caminho_b_plano.md` §5.

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
