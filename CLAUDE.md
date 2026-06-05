# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projecto

**MAP** (Minimum Acceptable Product) — casca navegável Streamlit para acompanhamento de pacientes em planos de tratamento. Apenas dados fictícios em memória, modelados como se viessem do banco futuro. Não há parser real de PDF/Excel, Supabase, login, deploy, WhatsApp ou Google Drive.

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

# Validar o contrato de dados mockados sem subir o servidor
.venv\Scripts\python.exe -c "from src.mock_data import load_mock_data; d=load_mock_data(); print('OK', list(d.keys()))"
.venv\Scripts\python.exe -c "from src.mock_data import load_mock_data; d=load_mock_data(); print(d['patients']['patient_id'].head(3).tolist())"

# Benchmark de SLA (gera benchmark_sla_results.json e atualiza SLA_REPORT.md)
# Rodar de dentro de um worktree de benchmark:
PYTHONPATH=. ../../../.venv/Scripts/python.exe benchmark_sla.py
```

Não há suíte de testes automatizados, linter ou formatter configurado. A validação padrão é `streamlit run app.py` + abertura manual de cada página + fluxo para a Ficha do Paciente a partir de Pacientes, Visão Geral, Mapa de Decisão e Alertas.

## Arquitetura

Casca navegável fina em Streamlit com sessão-controlada. Stack: Streamlit, Pandas, Plotly, OpenPyXL, python-dotenv.

### Ponto de entrada e roteamento lazy (`app.py`)

`app.py` define `_PAGE_MODULES` (mapeamento nome de página → módulo `src.pages.*`) e um `_route_cache`. `_route(page)` resolve e memoiza o `render` da página via `importlib.import_module` na primeira visita — pages não visitadas não pagam custo de import (importante para o cold start; ver SLA_REPORT.md). `get_data()` é decorado com `@st.cache_data` e faz o import de `load_mock_data` dentro do corpo para manter o pandas fora do caminho frio do `app.py`.

### Estado de navegação (`src/navigation.py`)

- `st.session_state["page"]` — chave primária de página; valores válidos em `PAGES = SIDEBAR_PAGES + ["Ficha do Paciente"]`.
- `st.session_state["selected_patient_id"]` — id do paciente aberto na Ficha.
- `go_to(page)` para páginas top-level (faz `st.rerun()`); `open_patient(patient_id)` para a Ficha do Paciente (NÃO chama `st.rerun()` — setar session state dentro de callback já dispara rerun; chamar `st.rerun()` é no-op).
- `init_navigation_state()` deve ser chamado no `main()` antes do sidebar; também faz fallback se `page` for inválido.

A sidebar (`src/components/sidebar.py`) também aceita deep-link via query params `?nav=<page>&patient_id=<id>` e `?refresh=1` (limpa `st.cache_data`). SVG icons são servidos como data URIs; `data/images/icones_Croquis_SVG/` é o diretório lido em runtime.

### Camadas

- **`src/mock_data.py`** — `load_mock_data() -> dict[str, pd.DataFrame]` com 11 tabelas. `_assert_referential_integrity` falha rápido se IDs entre tabelas forem inconsistentes. **Não alterar nomes de campos/tabelas** sem alinhar com `src/schemas.py` e as páginas.
- **`src/schemas.py`** — `EXPECTED_SCHEMAS` declara as colunas esperadas de cada tabela mock; `validate_mock_schema(data)` é o que a página Qualidade dos Dados usa.
- **`src/metrics.py`** — derivam `patient_summary` (engajamento, último status, último peso, `days_to_renewal`, `without_recent_weight`, etc.), `overview_kpis`, `attention_patients`. Cálculos vetorizados (NumPy `errstate`, `pd.cut`, `np.select`); funções decoradas com `@st.cache_data`.
- **`src/quality.py`** — `quality_scores(data)` e `client_checklist()` para a página Qualidade dos Dados.
- **`src/charts/`** — wrappers Plotly. `weight_chart.py` tem dois caminhos: `_weight_with_expected_single` (Ficha do Paciente — pré-filtra por patient_id) e `_weight_with_expected` (Visão Geral — agregado mensal). `import plotly` está dentro das funções, não no topo do módulo, para preservar o cold start.
- **`src/components/`** — peças reutilizadas: `sidebar`, `patient_header`, `badges`, `filters`, `kpi_cards`, `patient_actions`, `tables`, `empty_states`. O CSS da sidebar está inline em `sidebar.py` (injetado via `st.markdown(..., unsafe_allow_html=True)`).
- **`src/pages/`** — uma página por arquivo, cada uma com `def render(data) -> None`. Páginas: `visao_geral`, `mapa_decisao`, `pacientes`, `ficha_paciente`, `alertas`, `atualizacao_dados`, `qualidade_dados`. Trocar `st.columns` por `st.markdown(HTML único)` é a otimização recomendada para tabelas/listas grandes (ver `pacientes.py`).

### Tabelas mockadas (contrato)

`patients`, `treatment_plans`, `treatment_plan_items`, `execution_summary`, `appointments`, `appointment_items`, `patient_goals`, `weight_entries`, `satisfaction_entries`, `alerts`, `data_quality_issues`. Ver `src/schemas.py` para colunas exatas.

## Restrições de escopo (reforçadas pelos prompts do repositório)

As restrições abaixo aparecem em todos os `.github/agents/*.agent.md` e `.github/prompts/*.prompt.md` e devem ser respeitadas em qualquer mudança:

- **Não** implementar parser real de PDF/Excel, Supabase, login, deploy, WhatsApp, Google Drive ou outras integrações externas.
- **Não** expandir escopo funcional sem alinhamento — o projeto é uma casca navegável, não o produto final.
- **Preservar** nomes de campos e o contrato de `load_mock_data()` (ver `src/schemas.py`).
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
- `.claude/settings.local.json` já autorizou uma série de comandos de validação (imports, `streamlit --version`, smoke do `load_mock_data`). Para rodar benchmark ou outros comandos, observe o permission mode atual.
- `data/images/` guarda capturas de referência de cada página e o `Croquis_SAD_DClinique.png` (design base); SVGs customizados ficam em `data/images/icones_Croquis_SVG/`.
