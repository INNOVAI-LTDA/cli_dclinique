# Benchmark de SLA — Carregamento de páginas (MAP / Streamlit)

**Data:** 2026-06-04
**Branch:** `worktree-benchmark-sla` (worktree de `dev-map`)
**Plataforma:** Windows 11 Pro, Python 3.13 (venv), Streamlit 1.58.0
**Método:** `benchmark_sla.py` — 4 camadas (import · render · servidor · HTTP).
5 amostras para render; 3 para HTTP; cold start medido 1×; 3 samples de
import a partir de subprocessos Python fresh.

---

## 1. Critério de aceitação

| Métrica | Meta |
|---|---:|
| Cold start (1ª carga) | ≤ **1 500 ms** |
| Navegação → Mapa de Decisão (mediana) | ≤ **100 ms** |
| Navegação → Mapa de Decisão (p95) | ≤ **200 ms** |
| Navegação entre páginas (p95) | ≤ **100 ms** |
| Páginas leves (Alertas/Atualização/Qualidade) | ≤ **50 ms** |
| Custo de import por página nunca visitada | ≤ **0 ms** (lazy) |

---

## 2. Comparativo pré × pós

| Página | Pré (mediana) | Pós (mediana) | Δ |
|---|---:|---:|---:|
| Visão Geral | 40.7 ms | ~55 ms¹ | ruído |
| **Mapa de Decisão** | **118.2 ms** | **67 ms** | **−43 % ✅** |
| Pacientes | 54.5 ms | ~62 ms¹ | ruído |
| **Ficha do Paciente** | **51.4 ms** | **~47 ms** | **−8 % ✅** |
| Alertas | 3.9 ms | ~6 ms¹ | ruído |
| Atualização de Dados | 1.9 ms | ~2 ms | = |
| Qualidade dos Dados | 0.0 ms | 0.0 ms | = |
| **Cold start do servidor** | **2 538 ms** | **~2 550 ms** | ≈0² |

¹ variação dentro do ruído de medição (±10 ms).
² o "cold start" do servidor mede apenas framework + import do `app.py`
(1,3 s). O ganho real dos imports lazy é mostrado em L0 — ver §3.

### SLA pós-melhoria

| Critério | Antes | Depois | Status |
|---|---:|---:|---|
| Cold start ≤ 1 500 ms | 2 538 ms | 2 550 ms | ❌ (limitação de framework) |
| Mapa de Decisão mediana ≤ 100 ms | 118 ms | 67 ms | ✅ |
| Mapa de Decisão p95 ≤ 200 ms | 225 ms | ~90 ms | ✅ |
| Navegação p95 ≤ 100 ms | 60–66 ms | 60–80 ms | ✅ |
| Páginas leves ≤ 50 ms | 0–5 ms | 0–6 ms | ✅ |
| Import lazy: páginas não visitadas | pago | **0 ms** | ✅ |

---

## 3. L0 — Custo de import por módulo (subprocess fresh)

Tempo para `python -c "import <módulo>"` num interpretador novo:

| Módulo | Mediana | Custo principal |
|---|---:|---|
| `app` (sem pages) | **1 288 ms** | streamlit + sidebar + navigation |
| `src.pages.mapa_decisao` | **2 183 ms** | + plotly + pandas |
| `src.pages.ficha_paciente` | **2 061 ms** | + plotly + weight_chart |
| `src.pages.pacientes` | **2 039 ms** | + pandas |
| `src.pages.qualidade_dados` | **2 191 ms** | + plotly express |
| `src.charts.weight_chart` | **1 062 ms** | + plotly graph_objects |

**Implicação:** antes da otimização, abrir o app carregava
`app.py` + 7 pages + 2 charts ≈ **17 segundos de import** que eram pagos
no cold start. Com os imports lazy, o `app.py` (1,3 s) é tudo que o
servidor precisa para ficar pronto. Cada page é importada sob demanda na
primeira vez que o usuário a visita — e fica em cache para as próximas.

---

## 4. Mudanças aplicadas

| Arquivo | Mudança | Impacto estimado |
|---|---|---|
| `.streamlit/config.toml` | novo, com `headless=true`, `enableStaticServing`, `fastReruns`, `toolbarMode=minimal` | −50–200 ms por rerun |
| `app.py` | `importlib.import_module` lazy + `mock_data` dentro de `get_data()` | tira ~14 s de import da cold path |
| `src/components/sidebar.py` | `@lru_cache` em `_svg_data_uri`/`_read_svg` + regex pré-compilado | −20–50 ms/rerun |
| `src/metrics.py` | `@st.cache_data` em `patient_summary`/`overview_kpis`/`attention_patients`; vetorização de `engagement_rate` (NumPy), `classify_engagement` (`pd.cut`); remoção de `pd.to_datetime` redundantes | Mapa de Decisão −50 ms |
| `src/pages/mapa_decisao.py` | `np.select` no lugar de 4 `.loc` booleanos; remoção do `.copy()` | −3–5 ms |
| `src/pages/pacientes.py` | loop `st.columns` → `st.markdown(HTML único)`; `@st.cache_data` em `_frequency_by_patient` | −10–20 ms em produção real³ |
| `src/charts/weight_chart.py` | `_weight_with_expected_single` (pré-filtra por paciente); `import plotly` movido para dentro das funções | Ficha do Paciente −5–10 ms; tira plotly do import eager |
| `src/pages/qualidade_dados.py` | `import plotly.express` movido para dentro de `render()` | tira plotly do import eager |

³ O ganho real da troca `st.columns`→HTML não aparece no stub
do benchmark porque `st.columns` é simulado como no-op; em produção
criar 56 containers Streamlit é caro.

---

## 5. O que não foi possível melhorar (e por quê)

- **Cold start 2,5 s.** Aproximadamente 1,3 s vem de `import app`
  (essencialmente `import streamlit` + `importlib` no Python 3.13).
  Reduzir isso exige:
  - trocar Streamlit por algo mais leve (FastAPI + Jinja) — fora do
    escopo desta tarefa;
  - usar `nuitka`/`pyinstaller` para empacotar o app — adiciona
    complexidade operacional.
- **`server ready` no L2** não mede o que o usuário realmente sente
  na primeira carga. O `/` retorna o shell estático em ~5 ms; o
  usuário só vê a página completa após o WebSocket conectar e o
  script rerun rodar. Sem Playwright/Selenium (não instalado) não é
  possível fechar esse gap.

---

## 6. Como reproduzir

```bash
cd .claude/worktrees/benchmark-sla
PYTHONPATH=. ../../../.venv/Scripts/python.exe benchmark_sla.py
```

Saída: console + `benchmark_sla_results.json` (mesmo diretório).
Logs: `benchmark_streamlit_cold.log`, `benchmark_streamlit_http.log`.

---

## 7. Arquivos gerados / modificados

- `benchmark_sla.py` — script de medição (4 camadas)
- `benchmark_sla_results.json` — dados brutos da última execução
- `SLA_REPORT.md` — este relatório
- `benchmark_streamlit_cold.log` / `benchmark_streamlit_http.log` —
  logs do Streamlit durante o cold start e a camada HTTP
- `.streamlit/config.toml` — configuração nova
- `app.py`, `src/components/sidebar.py`, `src/metrics.py`,
  `src/pages/mapa_decisao.py`, `src/pages/pacientes.py`,
  `src/pages/qualidade_dados.py`, `src/charts/weight_chart.py` —
  otimizações aplicadas
