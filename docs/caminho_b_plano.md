# Caminho B — Plano de Refactor Incremental + Testes

> **Documento de planejamento.** Nenhum código deste plano foi escrito ainda. Aguarda aprovação.
> **Referência:** `docs/data_model.md` (modelo v2), `data/reports/relatorio_estrutura_dados_alertas_frequencia_2026-06-23.md` (motivação).
> **Premissa:** o schema **v1 (atual, 11 tabelas) continua sendo a fonte de verdade** durante todo o caminho B. A camada `src/core/` é uma **fachada** que traduz v1 → tipos v2; só na Fase 8 (cutover) o schema v2 é introduzido fisicamente.

---

## 1. Por que caminho B, em uma frase

Construir `src/core/` como uma **camada de tradução** entre o schema v1 (que já funciona) e o modelo v2 (que queremos), e ir substituindo a fundação **de baixo para cima** (modelos → métricas → regra de frequência → páginas), com **testes que protegem cada camada** e **garantia de que o app continua rodando** entre fases.

---

## 2. Princípios não-negociáveis

| # | Princípio | Consequência |
|---|---|---|
| N1 | **O app não pode quebrar entre fases** | Cada fase termina com `streamlit run app.py` funcionando e todas as 7 páginas renderizando |
| N2 | **Toda fase tem linter + teste + smoke antes de ser declarada pronta** | A definição de "pronta" é: `ruff check` 0 erros **E** `pytest` 100% **E** `streamlit run app.py` renderiza 7 páginas. Falha em qualquer um dos três ⇒ fase NÃO está pronta. |
| N3 | **Nenhuma fase toca o schema do banco** até Fase 8 | `src/data_layer/postgres_backend.py` e `data/csv/*.csv` ficam intactos |
| N4 | **Erros triviais não chegam no runtime nem no handoff** | Type hints, `from __future__ import annotations`, validação em fronteira, **`ruff check` é obrigatório** (não opcional) e roda como **primeira etapa** do script de teste — antes de pytest e antes do smoke. Se o linter reclamar, o script aborta com exit ≠ 0 e o usuário não precisa gastar tokens para descobrir. |
| N5 | **Logs de teste são machine-parseable** | JSON estruturado, além do `.log` humano, para o usuário colar de volta como insumo |
| N6 | **Testes rodam com backend CSV (default dev)** | Não dependem do Neon, não exigem credenciais |
| N7 | **Tratamento de exceção obrigatório em toda chamada de função (libs externas e código do projeto)** | Toda chamada a função de lib externa ou função interna do `src/core/` é envolvida em `try/except` com **(a)** captura da exceção **específica** (não bare `except:` nem `except Exception:` cego), **(b)** mensagem **traduzida para português** descrevendo o que o usuário pode fazer, **(c)** log via `logging` (não `print`, não `traceback.print_exc()`), **(d)** **nunca** exposição do stacktrace bruto ao usuário. Antes de escrever código contra uma lib, o catálogo de exceções da lib é consultado e documentado em `docs/exception_catalog.md` — ver §11. |
| N8 | **Acumulação de experiência: todo teste (passou ou falhou) vira entrada no `docs/experience_log.md`** | Cada teste (passou ou falhou) gera **1 entrada estruturada** no `docs/experience_log.md` com: fase, data, categoria (lint/runtime/test/design), descrição, causa raiz (se falha), resolução, lição. A entrada é registrada **antes de fechar a fase**. O log é **append-only** (nunca edita entrada existente). A IA consulta o log **no início de cada fase** para evitar repetir erros já conhecidos. A persistência cross-session é garantida por (a) `docs/experience_log.md` no repo + (b) `CLAUDE.md` referenciando o log + (c) memórias do projeto. |
| N9 | **Auditoria de custo de tokens a cada fase** | A cada fim de fase, a IA produz `docs/phase_reports/phase_N_report.md` com **9 métricas** (ver §2.3): tempo total, tempo código, tempo testes, tempo outros, caracteres totais, caracteres por feedback humano, método de conversão, tokens totais, tokens por feedback humano. O objetivo é tornar visível **onde o orçamento de tokens está sendo gasto** para que a IA (e o usuário) possam otimizar nas próximas fases. |

### 2.1. Política de exceções (N7 detalhado)

**Forma canônica de uma chamada segura:**

```python
import logging

_log = logging.getLogger(__name__)

def safe_load_clients(data: DataDict, organization_id: int = 1) -> list[Client]:
    """Carrega clients; nunca levanta exceção ao chamador."""
    try:
        df = data["clients"]  # KeyError tratado abaixo
    except KeyError as e:
        _log.error("Tabela 'clients' ausente no data layer: %s", e)
        return []
    try:
        return [_row_to_client(row) for _, row in df.iterrows()]
    except (ValueError, TypeError, KeyError) as e:
        _log.error(
            "Falha ao carregar clients (org_id=%s): %s — linha pulada. "
            "Verifique se as colunas esperadas estão presentes em data['clients'].",
            organization_id, type(e).__name__,
        )
        return []
```

**Regras obrigatórias (N7):**

| # | Regra | Exemplo de violação |
|---|---|---|
| E1 | Captura **específica**: `except KeyError`, `except pd.errors.EmptyDataError`, etc. — nunca `except:` ou `except Exception:` cego (a menos que seja **barreira defensiva** na camada de UI, e nesse caso com log e mensagem traduzida) | `except: pass` |
| E2 | Mensagem **em português**, descrevendo o que o usuário pode fazer | `raise ValueError("invalid input")` direto |
| E3 | `logging` (não `print`, não `traceback.print_exc()`) | `print(e)`, `traceback.print_exc()` |
| E4 | **Nunca** expor stacktrace bruto ao usuário via `st.error(traceback.format_exc())` | `st.exception(e)` em código de produção |
| E5 | **Funções puras** (`frequency.py`) só levantam exceções de domínio próprio (`ValueError("data_inicio é obrigatório")`) — sem captura interna, o chamador é que decide | `try: ... except: return None` em função pura |
| E6 | **Funções de fronteira** (`repos.py`, `persistence.py`, `csv_importer/*`) **capturam e traduzem** — não deixam exceção vazar | `return load_clients(data)` sem try/except |
| E7 | **Camada de UI** (`pages/*`) tem barreira defensiva: `try/except Exception` final com `st.error()` traduzido e `_log.exception()` para auditoria (já é o padrão atual em `mapa_decisao.py`) | `raise` solto em página |
| E8 | Toda exceção capturada gera **entrada estruturada no log** com: `timestamp`, `module:function`, `exception_type`, `mensagem_traduzida` — **sem** o traceback completo (a menos que `_log.exception()` em barreira defensiva, com `exc_info=False` em produção) | log sem contexto |

**Testes obrigatórios para N7 (em `tests/test_exception_handling.py`):**

- `test_no_bare_except` — `ruff check --select E722` deve passar; AST scan detecta `except:` em `src/core/`
- `test_no_traceback_in_user_logs` — captura `st.error` output, verifica que não contém `"Traceback (most recent call last)"`
- `test_exception_message_is_portuguese` — cada exceção levantada por `src/core/` tem assertion no teste: `assert "Coluna" in str(exc.value)` ou similar
- `test_pure_functions_raise_domain_exceptions` — `frequency.py:expected_sessions(...)` com inputs inválidos levanta `ValueError` com mensagem PT-BR
- `test_boundary_functions_silently_translate` — `repos.py:load_clients({})` retorna `[]` e loga erro traduzido
- `test_logging_not_print` — `ruff` custom check (ou AST): nenhum `print(` em `src/core/*.py`

**Catálogo de exceções por lib (a ser preenchido em `docs/exception_catalog.md`):**

| Lib | Operações usadas | Exceções esperadas | Mensagem PT-BR |
|---|---|---|---|
| `pandas` | `pd.read_csv`, `df.iterrows`, `df.to_dict`, `pd.to_datetime`, `pd.to_numeric` | `pd.errors.EmptyDataError`, `pd.errors.ParserError`, `KeyError`, `ValueError` | "Arquivo CSV vazio ou malformado: {path}" |
| `psycopg` (Fase 8) | `conn.execute`, `cursor.fetchall` | `psycopg.OperationalError`, `psycopg.errors.UndefinedTable`, `psycopg.IntegrityError` | "Não foi possível conectar ao banco de dados. Verifique NEON_DSN." |
| `streamlit` | `st.error`, `st.exception`, `st.cache_data` | `StreamlitAPIException` (uso incorreto da API) | "Erro de configuração da interface. Contate o suporte." |
| `pathlib` | `Path.read_text`, `Path.open` | `FileNotFoundError`, `PermissionError`, `OSError` | "Arquivo não encontrado: {path}" |
| `python-dateutil` | `dateutil.parser.parse` | `dateutil.parser.ParserError`, `OverflowError` | "Data inválida: {value}" |

> **Regra de ouro:** ao adicionar uma chamada a uma lib nova, **antes** de escrever o código, o dev (ou eu) consulta a doc da lib, identifica as exceções possíveis, adiciona a linha no catálogo, e só então escreve o `try/except`. O catálogo vira parte do PR — se a chamada não está no catálogo, o PR é bloqueado.

---

### 2.2. Acumulação de experiência (N8 detalhado)

**Propósito:** transformar o ciclo planejamento → implementação → teste → aprovação numa **base de conhecimento cumulativa**. Cada teste (passou ou falhou) vira insumo para as próximas decisões da IA.

**Mecanismo:** `docs/experience_log.md` é um arquivo append-only com 1 entrada por teste relevante.

**Formato de cada entrada:**

```markdown
### [YYYY-MM-DD] Fase N — <categoria> — <uma linha de resumo>

- **Categoria:** `lint` | `runtime` | `test` | `design` | `tooling` | `process`
- **Status:** `passed` | `failed`
- **Componente:** `src/core/mapping.py::patient_row_to_client`
- **Teste:** `tests/test_core_types.py::test_client_roundtrip`
- **Causa raiz (se falha):** <descrição técnica, 1-3 linhas>
- **Resolução:** <como foi resolvido, 1-3 linhas>
- **Lição:** <o que lembrar daqui em diante, 1-2 linhas, acionável>
- **Cross-ref:** [[docs/data_model.md §3.4]] [[docs/exception_catalog.md §1]]
```

**Workflow obrigatório:**

1. **Início de cada fase:** a IA (eu) **lê** o `docs/experience_log.md` inteiro antes de começar a escrever código. Entradas recentes da mesma categoria são destacadas mentalmente.
2. **Durante a fase:** cada teste que passa ou falha **deve** virar entrada no log, antes da fase ser declarada pronta. Sem entrada = sem critério de aceite (N2).
3. **Final da fase:** o sumário do log da fase (entradas da fase N) é incluído no `phase_reports/phase_N_report.md` (N9).
4. **Cross-session:** o log é commitado no repo e referenciado em `CLAUDE.md` (ver §13). Sessões futuras da IA carregam o log via `CLAUDE.md` → leem antes de cada fase.

**Categorias e exemplos:**

| Categoria | O que cabe | Exemplo |
|---|---|---|
| `lint` | Falha/acerto de regra ruff específica | "ruff E501 (line-too-long) bloqueou PR; ajustar `line-length` em pyproject.toml" |
| `runtime` | Exceção em runtime que escapou da fronteira | "psycopg.OperationalError em `load_clients`; adicionar retry com backoff" |
| `test` | Falha/acerto de caso de teste | "test_max_consecutive_missed_with_gap falhou: assertion `expected 3, got 2`" |
| `design` | Decisão arquitetural que se mostrou boa/ruim | "Mapa de Decisão com 5 quadrantes confunde; voltar a 4 + chip lateral" |
| `tooling` | Problema com o script PowerShell, ruff, pytest | "pytest-json-report não instala em Python 3.13; usar pytest-json" |
| `process` | Workflow, planejamento, comunicação | "Auditoria de tokens da Fase 3 revelou 60% do tempo em 'outros'; revisar" |

**Política de retenção:** entradas **nunca são editadas ou deletadas**. Erros já corrigidos permanecem no log como histórico — é justamente isso que permite à IA evitar repeti-los. Se uma lição for superada, a entrada antiga recebe um addendum `**Superseded by:** [link]` em vez de ser apagada.

---

### 2.3. Auditoria de custo de tokens (N9 detalhado)

**Propósito:** medir, a cada fase, **onde o orçamento de tokens/tempo está sendo gasto**, para que tanto a IA quanto o usuário possam otimizar nas fases seguintes.

**Mecanismo:** a cada fim de fase, a IA produz `docs/phase_reports/phase_N_report.md` com 9 métricas obrigatórias.

**As 9 métricas (do brief do usuário):**

| # | Métrica | Como medir | Granularidade |
|---|---|---|---|
| 1 | **Tempo total de execução da fase (ms)** | Timestamp do 1º tool call → timestamp do último tool call da fase | ms |
| 2 | **Tempo total da IA implementando código (ms)** | Soma das durações de tool calls `Write`/`Edit` em `src/core/` | ms |
| 3 | **Tempo total da IA implementando testes (ms)** | Soma das durações de tool calls `Write`/`Edit` em `tests/` | ms |
| 4 | **Tempo total da IA em outras tarefas (ms)** | Total − (código + testes). Categorizar: Read, Grep, Glob, Bash (sem build) | ms |
| 5 | **Total de caracteres produzidos** | `len(text)` somado sobre **todos** os arquivos `Write`/`Edit` + conteúdo de tool calls que produziram output textual significativo (relatórios, mensagens, etc.) | chars |
| 6 | **Caracteres produzidos por feedback humano** | Soma de `len()` das mensagens do usuário (inputs) que geraram trabalho da IA | chars |
| 7 | **Método de conversão de tokens** | `tiktoken.get_encoding("cl100k_base")` quando disponível; fallback: `chars / 3.5` para PT-BR + código | string |
| 8 | **Total de tokens produzidos** | Aplicar método #7 sobre o #5 | tokens |
| 9 | **Tokens produzidos por feedback humano** | Aplicar método #7 sobre o #6 | tokens |

**Script de medição:** `scripts/measure_phase_metrics.py` é executado **no início** da fase (seta baseline) e **no fim** (computa diff). Salva em `logs/metrics_phase_N_<ts>.json`. A IA então converte o JSON no markdown do relatório.

**Formato do relatório (`docs/phase_reports/phase_N_report.md`):**

```markdown
# Relatório de Auditoria — Fase N

> **Período:** YYYY-MM-DD HH:MM:SS — YYYY-MM-DD HH:MM:SS
> **Fase:** N — <título>
> **Branch:** worktree-<nome>

## 1. Métricas de tempo

| Métrica | Valor (ms) | % do total |
|---|---|---|
| Tempo total | 123.456 | 100% |
| Implementando código | 45.678 | 37% |
| Implementando testes | 23.456 | 19% |
| Outras tarefas (leitura, busca, etc.) | 54.322 | 44% |

## 2. Métricas de caracteres

| Métrica | Valor |
|---|---|
| Caracteres produzidos | 12.345 |
| Caracteres por feedback humano | 678 |

## 3. Métricas de tokens

| Métrica | Valor |
|---|---|
| Método de conversão | `tiktoken cl100k_base` (ou fallback `chars / 3.5`) |
| Tokens totais | 3.527 |
| Tokens por feedback humano | 194 |
| **Razão output/input** | **18.2** (cada 1 char de feedback gerou 18.2 chars de output) |

## 4. Distribuição de tempo por tarefa "outra"

| Subtarefa | Tempo (ms) | % de "outras" |
|---|---|---|
| Leitura de arquivos (Read) | 12.345 | 23% |
| Busca em código (Grep) | 8.901 | 16% |
| Listagem de diretórios (Glob) | 4.567 | 8% |
| Bash (sem build) | 28.509 | 53% |

## 5. Acumulado até o momento (todas as fases)

| Fase | Tempo (ms) | Tokens | Output/Input |
|---|---|---|---|
| Fase 0 | 12.345 | 1.234 | 5.2 |
| Fase 1 | 45.678 | 4.567 | 12.3 |
| Fase 2 | ... | ... | ... |
| **Total** | **123.456** | **12.345** | **média: 10.5** |

## 6. Lições e oportunidades de otimização

- "<lição específica desta fase>"
- "<oportunidade de reduzir tokens na próxima fase>"

## 7. Entradas no `experience_log.md` (N8)

- Total de entradas nesta fase: N
- Categorias: lint=X, test=Y, design=Z, ...
- Lições mais importantes: <bullets>
```

**Por que medir output/input ratio:** é a métrica que melhor revela **explosão de trabalho**. Razão > 20 indica que pouco feedback humano está gerando muito output da IA — pode ser:
- (bom) trabalho genuíno de implementação a partir de um brief bem escrito
- (ruim) a IA está "viajando" — verbose demais, falta foco, gerou código que vai ser reescrito

A IA é incentivada a **manter a razão < 15** (média do caminho B proposta). Razão > 20 = trigger para a IA se auto-criticar e propor simplificação na próxima fase.

**Privacidade:** o relatório fica **dentro do repo** (`docs/phase_reports/`) — não vaza nada do conteúdo do código, só métricas. O usuário pode compartilhar o relatório com o cliente sem expor detalhes técnicos.

---

## 3. Fases

> **Critério de aceite global (N2 + N7):** toda fase é considerada pronta apenas quando as **4 condições** abaixo são **simultaneamente verdadeiras**:
> 1. `ruff check src/core tests/test_core_*.py` retorna **0 erros** (linter passa primeiro, aborta cedo — ver §5.1)
> 2. `pytest tests/ -v` retorna **100% passed** (todos os testes daquela fase + fases anteriores, **incluindo** `test_exception_handling.py` que valida N7)
> 3. `streamlit run app.py` sobe sem traceback e as 7 páginas renderizam
> 4. **N7 satisfeito** — `tests/test_exception_handling.py` passa, `docs/exception_catalog.md` está atualizado com as libs tocadas na fase, e nenhum `print(` / `traceback.print_exc()` / `except:` em `src/core/`
>
> Os "Critério de aceite" listados em cada fase são **adicionais** ao critério global.

### Fase 0 — Setup (½ sprint, ~2 dias)

**Objetivo:** criar a infra de teste e o esqueleto de `src/core/`.

**Arquivos a criar:**
- `src/core/__init__.py` (vazio + exports)
- `src/core/_typing.py` (types compartilhados: `DataDict = dict[str, pd.DataFrame]`)
- `tests/__init__.py` (vazio)
- `tests/conftest.py` (fixtures: `data_dict`, `backend`, `tmp_csv_dir`)
- `tests/test_core_smoke.py` (importa tudo de `src.core`, falha se der `ImportError`)
- `scripts/run_core_tests.ps1` (wrapper PowerShell; **linter roda antes de pytest**)
- `requirements-dev.txt` (pytest, pytest-json-report, **ruff**)
- `pyproject.toml` (configuração do ruff: `target-version = "py313"`, `select = ["E", "F", "W", "I", "ANN", "B", "UP"]`)
- `docs/caminho_b_plano.md` (este doc)
- `logs/.gitkeep`

**Critério de aceite:**
- `pwsh scripts/run_core_tests.ps1` roda, exit 0, gera `logs/test_core_<ts>.log` e `.json`
- `python -c "from src.core import __version__; print('OK')` exit 0

**Teste:**
- `test_core_smoke.py::test_imports` — importa todos os submódulos de `src.core`
- `test_core_smoke.py::test_conftest_fixtures` — `data_dict` retorna 11 DataFrames com colunas de `EXPECTED_SCHEMAS`

---

### Fase 1 — Tipos v2 + Repositórios read-only (1 sprint, ~5 dias)

**Objetivo:** `src/core/types.py` define os dataclasses v2; `src/core/repos.py` lê do `load_all()` v1 e devolve instâncias v2.

**Arquivos a criar:**
- `src/core/types.py` — `@dataclass(frozen=True)` para cada entidade:
  ```python
  @dataclass(frozen=True)
  class Organization: id: int; nome: str; cnpj: str; ...
  @dataclass(frozen=True)
  class User: id: int; tipo: Literal["Provider","Admin"]; ...
  @dataclass(frozen=True)
  class Deliverable: id: int; titulo: str; tipo: str; parent_deliverable_id: int | None; ...
  @dataclass(frozen=True)
  class Client: id: int; nome: str; cpf: str | None; data_nascimento: date | None; ...
  @dataclass(frozen=True)
  class ClientDeliverable: id: int; client_id: int; deliverable_id: int; ...
  @dataclass(frozen=True)
  class ClientSession: id: int; client_id: int; provider_id: int; status: str; ...
  ```
- `src/core/repos.py`:
  ```python
  def load_clients(data: DataDict, organization_id: int = 1) -> list[Client]: ...
  def load_users(data: DataDict, organization_id: int = 1) -> list[User]: ...
  def load_deliverables(data: DataDict, organization_id: int = 1) -> list[Deliverable]: ...
  def load_client_deliverables(data: DataDict, organization_id: int = 1) -> list[ClientDeliverable]: ...
  def load_client_sessions(data: DataDict, organization_id: int = 1) -> list[ClientSession]: ...
  ```
  Cada função: (1) lê o DataFrame de `load_all()`, (2) normaliza tipos via `pd.to_numeric(..., errors="coerce")`, (3) instancia dataclass, (4) filtra `deleted_at IS NULL` quando houver.

- `src/core/mapping.py` — helpers de tradução:
  ```python
  PATIENT_TO_CLIENT = {"patient_id": "id", "name": "nome", "medical_record": "prontuario", ...}
  def patient_row_to_client(row: pd.Series) -> Client: ...
  ```

**Critério de aceite:**
- `load_clients(load_all())` retorna 8 instâncias no mock
- `load_clients(load_all())[0].cpf` é `None` (mock não tem CPF)
- Re-rodar `streamlit run app.py` mostra as 7 páginas idênticas ao estado atual

**Testes (`tests/test_core_types.py`):**
- `test_organization_roundtrip` — DataFrame → dataclass → DataFrame, hash igual
- `test_user_roundtrip` (Provider e Admin)
- `test_deliverable_roundtrip` (com e sem parent_deliverable_id)
- `test_client_roundtrip` (com e sem cpf, com e sem data_nascimento)
- `test_client_deliverable_roundtrip` (Plano e Item)
- `test_client_session_roundtrip` (cada status)
- `test_load_clients_empty` — DataFrame vazio → lista vazia, sem exceção
- `test_load_clients_ignores_deleted` — `deleted_at` populado → não retorna
- `test_na_safety` — coluna com `pd.NA` → dataclass com `None` ou default, **nunca** levanta

**Cuidados para evitar erros triviais:**
- `from __future__ import annotations` em todos os arquivos novos
- `from typing import Optional` → usar `int | None` (Python 3.13)
- Type hints **completos** em todos os parâmetros
- Linter: `ruff check src/core tests/test_core_*.py` (adicione `ruff` em `requirements-dev.txt`; escopo narrow — v1 tests não estão no escopo)

---

### Fase 2 — Cálculo de frequência (1 sprint, ~5 dias)

**Objetivo:** `src/core/frequency.py` implementa as funções que o relatório pediu (item 4.3 do `relatorio_estrutura_dados_alertas_frequencia_2026-06-23.md`).

**Arquivos a criar:**
- `src/core/frequency.py`:
  ```python
  PERIOD_DAYS = {"Diário": 1, "Semanal": 7, "Quinzenal": 14, "Mensal": 30, "Única": None}

  def expected_sessions(cd: ClientDeliverable, d: Deliverable, as_of: date) -> int:
      """Sessões que DEVERIAM ter ocorrido entre data_inicio e as_of."""
      if d.frequencia_tipo is None or d.frequencia_tipo == "Única":
          return cd.sessions_expected
      period = PERIOD_DAYS.get(d.frequencia_tipo)
      if period is None or cd.data_inicio is None:
          return cd.sessions_expected
      elapsed_days = (as_of - cd.data_inicio).days
      if elapsed_days <= 0:
          return 0
      return min(cd.sessions_expected, elapsed_days // period)

  def actual_sessions(cd_id: int, sessions: list[ClientSession], as_of: date) -> int:
      """Sessões com status='Atendido' para este client_deliverable até as_of."""
      return sum(
          1 for s in sessions
          if s.status == "Atendido"
          and s.session_start.date() <= as_of
      )

  def attendance_rate(cd: ClientDeliverable, sessions: list[ClientSession], as_of: date) -> float:
      expected = expected_sessions(cd, ...)
      actual = actual_sessions(cd.id, sessions, as_of)
      return actual / expected if expected > 0 else 0.0

  def max_consecutive_missed(cd_id: int, sessions: list[ClientSession]) -> int:
      """Maior sequência de sessões consecutivas com status != 'Atendido'."""
      # Ordena por data, conta o maior run de não-Atendido
      ...
  ```

- `tests/test_core_frequency.py`:
  - `test_expected_sessions_daily` — Injetável Diário, 10 dias, esperado = 10
  - `test_expected_sessions_weekly` — Injetável Semanal, 21 dias, esperado = 3
  - `test_expected_sessions_caps_at_expected` — se elapsed > expected*period, retorna expected
  - `test_expected_sessions_before_start` — as_of < data_inicio → 0
  - `test_expected_sessions_unique` — frequencia_tipo='Única' → retorna cd.sessions_expected
  - `test_expected_sessions_no_frequency` — frequencia None → retorna cd.sessions_expected
  - `test_actual_sessions_filters_by_date`
  - `test_actual_sessions_filters_by_status` (Atendido conta; outros não)
  - `test_attendance_rate_zero_expected` — sem expected → 0.0 (sem divisão por zero)
  - `test_max_consecutive_missed_empty` — sem sessions → 0
  - `test_max_consecutive_missed_all_attended` → 0
  - `test_max_consecutive_missed_three_in_a_row` → 3
  - `test_max_consecutive_missed_with_gap` — sequência quebrada por Atendido

**Dados de teste fixos** (`tests/fixtures/frequency_cases.json`) — 6 casos canônicos para evitar recalcular manualmente.

**Critério de aceite:**
- Todos os 12 testes passam em <1s
- Função `expected_sessions` lida com `data_inicio=None` e `frequencia_tipo=None` sem levantar

---

### Fase 3 — Geração de alertas de frequência (½ sprint, ~3 dias)

**Objetivo:** `src/core/alerts.py` materializa os alertas em `client_alerts` (ou na `alerts` v1, durante a transição).

**Arquivos a criar:**
- `src/core/alerts.py`:
  ```python
  THRESHOLDS = {
      "consecutive_missed_alta": 2,    # 2+ faltas seguidas → alta
      "attendance_rate_media": 0.70,   # <70% comparecimento → média
      "no_sessions_alta_days": 30,     # 30+ dias sem sessão → alta
  }

  def detect_frequency_alerts(
      clients: list[Client],
      client_deliverables: list[ClientDeliverable],
      deliverables: list[Deliverable],
      sessions: list[ClientSession],
      as_of: date,
  ) -> list[dict]:
      """Retorna lista de alertas (ainda em dict, sem persistir)."""
      alerts = []
      for cd in client_deliverables:
          if cd.parent_client_deliverable_id is None:
              continue  # Apenas itens, não o plano-pai
          if cd.status not in ("Ativo", "Aguardando"):
              continue
          d = next((d for d in deliverables if d.id == cd.deliverable_id), None)
          if d is None:
              continue

          consecutive = max_consecutive_missed(cd.id, sessions)
          if consecutive >= THRESHOLDS["consecutive_missed_alta"]:
              alerts.append(_make_alert(cd, "Alta", f"{consecutive} sessões consecutivas não atendidas"))

          rate = attendance_rate(cd, sessions, as_of)
          if rate < THRESHOLDS["attendance_rate_media"] and expected_sessions(cd, d, as_of) >= 3:
              alerts.append(_make_alert(cd, "Média", f"Comparecimento de {rate:.0%} no ciclo"))

      return alerts
  ```

- `src/core/persistence.py`:
  ```python
  def save_frequency_alerts(alerts: list[dict], data: DataDict) -> int:
      """Persiste via data_layer.append_row; retorna quantos gravou."""
      from src.data_layer import append_row
      n = 0
      for a in alerts:
          append_row("alerts", a)
          n += 1
      return n
  ```

- `tests/test_core_alerts.py`:
  - `test_no_alert_when_fully_attended`
  - `test_alta_alert_for_2_consecutive_misses`
  - `test_media_alert_for_low_attendance`
  - `test_no_alert_for_paused_plans`
  - `test_no_alert_for_plan_root` (só itens disparam, não o plano-pai)
  - `test_save_frequency_alerts_idempotent` — rodar 2x não duplica (precisa de `alert_id` determinístico)
  - `test_alert_dedup` — alerta já existente com mesmo tipo+cliente+item não duplica

**Critério de aceite:**
- Rodando no `load_mock_data()`, gera ≥ 2 alertas (cobre Kelly, Jaqueline, Ricardo, etc. do mock)
- `alerts.csv` pós-execução tem as linhas extras (verificável via fixture)

---

### Fase 4 — Refactor de `mapa_decisao.py` (½ sprint, ~3 dias)

**Objetivo:** Mapa de Decisão usa `core.frequency` em vez de `execution_summary` direto. Quadrante "Não compareceu" entra como dimensão.

**Arquivos a alterar:**
- `src/pages/mapa_decisao.py`:
  - `summary = patient_summary(data)` continua sendo a base (engajamento + satisfação)
  - **Adicionar**: `attendance_rate = core.frequency.attendance_rate(cd, sessions, today)` por `client_id`
  - **Adicionar**: 3ª dimensão visual no painel lateral: "Frequência" (X% comparecimento)
  - Quadrante ganha uma 5ª classe: "Sem comparecimento" se `attendance_rate == 0`

- `tests/test_mapa_decisao.py` (novo):
  - Smoke: `AppTest.from_file("app.py").run()` não levanta
  - Lógica: com mock, Kelly (alto comparecimento) NÃO vai para "Sem comparecimento"; Jaqueline (0 sessões) VAI
  - Visual: snapshot do HTML gerado (via `AppTest` ou capturando `st.markdown` output)

**Critério de aceite:**
- Página renderiza sem traceback
- Quadrante "Sem comparecimento" aparece quando há paciente com `attendance_rate == 0`

**Atenção:** o Mapa de Decisão atual tem `try/except` defensivo (commit 76d47ab). Manter o padrão: qualquer erro novo vira `st.error(...)` em vez de freeze.

---

### Fase 5 — Refactor de `alertas.py` (½ sprint, ~2 dias)

**Objetivo:** Página Alertas ganha a categoria `Frequência` (alertas automáticos).

**Arquivos a alterar:**
- `src/pages/alertas.py`:
  - `CATEGORIES = ["Todos", "Enfermagem", "Médica", "Comercial", "Nutrição", "Frequência"]` (adiciona 1)
  - `_category_counts` conta o novo valor
  - Badge visual diferencia alertas `Frequência` (cor distinta dos demais)

- `tests/test_alertas.py` (novo):
  - `test_category_counts_includes_frequency`
  - `test_frequency_alerts_visible`
  - `test_filter_by_frequency_works`

**Critério de aceite:**
- Filtro "Frequência" mostra apenas alertas automáticos
- App continua funcionando com 7 páginas

---

### Fase 6 — Importadores (1 sprint, ~5 dias)

**Objetivo:** `src/pdf_importer/persist.py` e um novo `src/csv_importer/` escrevem usando o `core` (mas ainda na tabela `alerts` v1, durante a transição).

**Arquivos a criar/alterar:**
- `src/csv_importer/__init__.py`
- `src/csv_importer/frequencia.py` — lê `Relatorio de frequencia.csv` e popula `client_deliverables` v1 (`treatment_plans` + `treatment_plan_items` + `execution_summary`)
- `src/csv_importer/agendamentos.py` — lê `Agendamentos.csv` e popula `appointments` + `appointment_items`
- `src/csv_importer/dedup.py` — resolve (Paciente + Orçamento) → `patient_id`:
  ```python
  def resolve_patient(name: str, cpf: str | None, orcamento: str) -> int:
      """Busca existente por cpf; se não, exige cadastro mínimo."""
      if cpf and (existing := find_by_cpf(cpf)):
          return existing
      raise PatientNotFoundError(name, cpf, orcamento)
  ```
- `src/csv_importer/wizard.py` — UI Streamlit (similar ao `importar_pdf_wizard`)

**Testes:**
- `test_csv_frequencia_dedup` — 26 pacientes, todos resolvem por (nome + orçamento)
- `test_csv_frequencia_missing_patient` — 1 paciente novo → exige cadastro, gera data_quality_issue
- `test_csv_agendamentos_multi_budget` — 40 linhas com `Orçamento` multi-valor → 1 sessão com múltiplos `appointment_items`
- `test_csv_agendamentos_typo` — "Kelly Cristina a Silva Amorim" resolve (typo é consistente entre os 2 arquivos)
- `test_csv_agendamentos_simone` — 1 paciente em Relatorio sem agendamentos → tem `0 sessões` (vira alerta na Fase 3)

**Critério de aceite:**
- Rodar o import sobre `data/new/Relatorio de frequencia.csv` produz 456 linhas em `treatment_plan_items` (igual ao mock)
- Rodar sobre `data/new/Agendamentos.csv` produz 238 linhas em `appointments`
- Typos de nome **não** duplicam pacientes (dedup por CPF quando presente, por nome+orçamento quando não)

---

### Fase 7 — Validação end-to-end (½ sprint, ~2 dias)

**Objetivo:** Rodar a cadeia completa **mock → import → frequency → alerts → Mapa de Decisão** e validar.

**Script:** `scripts/validate_end_to_end.py`
1. `from src.data_layer import load_all; data = load_all()` (mock)
2. `from src.core.repos import load_clients, ...`
3. `from src.core.frequency import expected_sessions, actual_sessions, attendance_rate`
4. `from src.core.alerts import detect_frequency_alerts`
5. `print` sumário: quantos alertas, distribuição por prioridade, sample de 3 alertas
6. `assert` que o total de alertas está dentro de `[1, 10]` (sentinela — se gerar 0 ou 100+, há bug)

**Teste:**
- `tests/test_end_to_end.py::test_full_chain` — roda o script, valida saída

**Critério de aceite:**
- O sumário mostra: 8 pacientes, 26 client_deliverables, 238 client_sessions, 3-6 alertas de frequência
- A página Mapa de Decisão renderiza com o novo quadrante "Sem comparecimento"
- A página Alertas mostra a aba "Frequência"

---

### Fase 8 — Cutover (1 sprint, ~5 dias) [OPCIONAL até o SupportHealth chegar]

**Objetivo:** schema v2 entra no Postgres, `src/core/` lê de v2 diretamente, v1 fica como compat shim.

> **Esta fase é opcional.** Se o cliente ainda não precisa de multi-clínica nem do SupportHealth sync, **o caminho B termina na Fase 7** com o modelo v2 documentado e `src/core/` como tradução, mas sem migração física. O cutover fica para quando o SupportHealth entrar.

**Decisão:** parar na Fase 7 e adiar a Fase 8 até a integração com SupportHealth.

---

## 4. Plano de testes (resumo por fase)

| Fase | Testes novos | Tipo | Estimativa |
|---|---|---|---|
| 0 | 1 arquivo (`test_core_smoke.py`), 2 casos | smoke | 2h |
| 1 | 1 arquivo (`test_core_types.py`), 9 casos **+ `test_exception_handling.py` (5 casos)** | roundtrip + edge + **N7** | 1.5 dia |
| 2 | 1 arquivo (`test_core_frequency.py`), 12 casos | unit | 1 dia |
| 3 | 1 arquivo (`test_core_alerts.py`), 7 casos | unit + integration | 0.5 dia |
| 4 | 1 arquivo (`test_mapa_decisao.py`), 3 casos | smoke + visual | 0.5 dia |
| 5 | 1 arquivo (`test_alertas.py`), 3 casos | smoke | 0.5 dia |
| 6 | 1 arquivo (`test_csv_importer.py`), 5 casos | integration | 1 dia |
| 7 | 1 arquivo (`test_end_to_end.py`), 1 caso | e2e | 0.5 dia |
| **Total** | **8 arquivos + `test_exception_handling.py` (permanente), ~47 casos** | — | **~7 dias** |

> O `test_exception_handling.py` é **cumulativo entre fases** — a cada fase que toca uma lib nova, o catálogo de exceções cresce e os testes daquele arquivo também. Não é por fase; é um arquivo vivo.

**Cobertura de erros triviais (N4):**

| Tipo de erro | Como é prevenido | Onde |
|---|---|---|
| **Lint (estilo, import não usado, naming)** | **`ruff check src/core tests/test_core_*.py` — primeira etapa do script, aborta com exit ≠ 0 antes de pytest** | `scripts/run_core_tests.ps1` (etapa 6) |
| Sintaxe | `python -m compileall src/core tests/` no script | `scripts/run_core_tests.ps1` (etapa 7) |
| Type hint errado | `ruff check` (modo `--select ANN` para annotation) | `scripts/run_core_tests.ps1` (etapa 6) |
| Import faltando | `test_core_smoke.py` falha se der `ImportError` | `tests/test_core_smoke.py` |
| Divisão por zero | Teste explícito em `test_attendance_rate_zero_expected` | `tests/test_core_frequency.py` |
| `pd.NA` em campo `Int64` | `test_na_safety` percorre todas as colunas | `tests/test_core_types.py` |
| `None` em campo obrigatório | Helper `_coerce(row, "campo", default)` em `mapping.py` | `src/core/mapping.py` |
| Variável de ambiente faltando | Script `run_core_tests.ps1` checa `DCLINIQUE_BACKEND` antes | `scripts/run_core_tests.ps1` (etapa 4) |
| Sessão/porta ocupada | Script checa se `8501/8502` está livre antes de smoke test | `scripts/run_core_tests.ps1` (etapa 5) |
| CSV malformado | `pd.read_csv(..., on_bad_lines="skip")` + log de linhas puladas | `src/csv_importer/*.py` |
| Encoding errado | `encoding="utf-8"` explícito, fallback `latin1` | `src/csv_importer/*.py` |
| **N7 — `except:` cego** | `ruff check --select E722` (regra nativa do ruff) + AST scan em `tests/test_exception_handling.py::test_no_bare_except` | `scripts/run_core_tests.ps1` (etapa 8) |
| **N7 — `except Exception:` cego em código de produção** | Mesmo ruff + barreira defensiva só permitida em `pages/*` (whitelist por path) | `src/core/*.py` não pode ter |
| **N7 — stacktrace exposto ao usuário** | `tests/test_exception_handling.py::test_no_traceback_in_user_logs` + grep no log do script (etapa 10) | `tests/test_exception_handling.py` |
| **N7 — mensagem em inglês** | `tests/test_exception_handling.py::test_exception_message_is_portuguese` percorre todas as exceções de `src/core/` | `tests/test_exception_handling.py` |
| **N7 — chamada a lib sem try/except** | Whitelist manual de chamadas externas em `src/core/` vs `docs/exception_catalog.md` | revisão por fase |

---

## 5. Modelo de execução de testes

### 5.1. Script: `scripts/run_core_tests.ps1`

Wrapper PowerShell único, idempotente, exit code claro. **Inspirado em `scripts/run_validate_neon.ps1`** (mesmo padrão do projeto).

**Funcionalidades (em ordem; aborta na primeira falha):**
1. Cria `.venv` se faltar (`python -m venv .venv`)
2. Instala `requirements.txt` + `requirements-dev.txt` se faltar
3. Carrega `.env` se existir
4. Define `DCLINIQUE_BACKEND=csv` (força dev offline; ignora Neon)
5. Verifica que nenhuma instância Streamlit está rodando na 8501/8502
6. **`ruff check src/core tests/test_core_*.py` — exit ≠ 0 aborta o script inteiro (não roda pytest, não roda smoke). Escopo narrow (NÃO escaneia o `tests/` inteiro) porque os v1 tests pré-existentes têm erros de lint legítimos acumulados antes do N2/N4 entrarem em vigor — fora do escopo do path B.**
7. **`python -m compileall src/core/` — exit ≠ 0 aborta (syntax check). Escopo narrow — syntax dos tests é coberto pelo import no step 10 (pytest).**
8. **`ruff check --select E722,F401,F811 src/core/` — exit ≠ 0 aborta (AST scan: nenhum `except:`, `except Exception:` cego, import duplicado)**
9. Roda `pytest tests/ -v --json-report --json-report-file=logs/test_core_<ts>.json 2>&1 | Tee-Object logs/test_core_<ts>.log`. Roda o diretório `tests/` inteiro (inclui v1 tests — garantia de que o refactor não quebrou o suite existente).
10. **Grep anti-stacktrace no log:** se `logs/test_core_<ts>.log` contiver `"Traceback (most recent call last)"` em **mais de 3 lugares** (limiar configurável em `N7_MAX_TRACEBACKS=3`), o script marca **N7 VIOLATION** e exit ≠ 0. Exceções em testes são esperadas, mas stacktraces inundando o log indicam que código de produção está deixando exceção vazar.
11. Roda smoke test do app: `streamlit run app.py --server.headless true --server.port 8501 &` ; sleep 5 ; curl http://localhost:8501 ; kill
12. Exit 0 só se **todas** as etapas (6+7+8+9+10+11) passaram; exit 1 caso contrário
13. Imprime no final: `LOG: logs/test_core_<ts>.log | JSON: logs/test_core_<ts>.json`

**Helper `Invoke-ExternalStep`:** todas as 6 chamadas externas a `python.exe`/`ruff`/`pytest` (steps 2, 6, 7, 8, 9) passam pelo helper que faz `$ErrorActionPreference = "SilentlyContinue"` em escopo léxico via try/finally. **Motivação (N2 + experiência Fase 0):** sob `$ErrorActionPreference = "Stop"` global, exit codes ≠ 0 de comandos externos são promovidos a terminating errors, o catch block dispara antes de ler `$LASTEXITCODE`, e o usuário recebe um FATAL com traceback Python truncado em vez de uma mensagem clara de "pacote X não instalado". Padrão espelhado de `scripts/run_validate_neon.ps1` (linhas 119-138).

**A ordem importa:** o linter (etapa 6) vem antes do pytest (etapa 9) por design — se houver erro de lint, o usuário recebe o diagnóstico do linter **antes** de gastar tempo rodando os 42 testes. Falhas precoces = menos tokens gastos.

**Exemplo de invocação:**
```powershell
pwsh scripts/run_core_tests.ps1
```

**Exemplo de invocação em modo verbose (mostra cada teste):**
```powershell
pwsh scripts/run_core_tests.ps1 -Verbose
```

**Exemplo de invocação rodando só Fase 2:**
```powershell
pwsh scripts/run_core_tests.ps1 -TestPattern "test_core_frequency"
```

### 5.2. Formato do log humano (`.log`)

```
[2026-06-23 14:32:01] run_core_tests.ps1 — start
[2026-06-23 14:32:01] venv: .venv (Python 3.13.2)
[2026-06-23 14:32:02] backend: csv
[2026-06-23 14:32:02] test pattern: tests/
[2026-06-23 14:32:05] test_core_smoke.py::test_imports PASSED 0.12s
[2026-06-23 14:32:05] test_core_smoke.py::test_conftest_fixtures PASSED 0.34s
[2026-06-23 14:32:06] test_core_types.py::test_organization_roundtrip PASSED 0.05s
...
[2026-06-23 14:32:18] test_core_frequency.py::test_max_consecutive_missed_with_gap FAILED 0.08s
  AssertionError: expected 3, got 2
  File "tests/test_core_frequency.py", line 87
    assert max_consecutive_missed(cd_id, sessions) == 3
[2026-06-23 14:32:20] smoke: streamlit on :8501 — OK (200)
[2026-06-23 14:32:21] run_core_tests.ps1 — FAILED (1 of 42 tests failed)
[2026-06-23 14:32:21] log:   logs/test_core_20260623-143201.log
[2026-06-23 14:32:21] json:  logs/test_core_20260623-143201.json
```

### 5.3. Formato do log JSON (`.json`)

```json
{
  "exit_code": 1,
  "started_at": "2026-06-23T14:32:01",
  "duration_seconds": 19.4,
  "backend": "csv",
  "summary": {
    "total": 42,
    "passed": 41,
    "failed": 1,
    "skipped": 0
  },
  "tests": [
    {
      "nodeid": "tests/test_core_smoke.py::test_imports",
      "outcome": "passed",
      "duration": 0.12
    },
    {
      "nodeid": "tests/test_core_frequency.py::test_max_consecutive_missed_with_gap",
      "outcome": "failed",
      "duration": 0.08,
      "message": "AssertionError: expected 3, got 2",
      "traceback": "..."
    }
  ],
  "smoke": {
    "streamlit_started": true,
    "port_8501_status": 200
  }
}
```

### 5.4. Como o usuário usa o log em caso de falha

1. Roda o script: `pwsh scripts/run_core_tests.ps1`
2. Se exit ≠ 0, abre `logs/test_core_<ts>.log` (humano) e/ou `logs/test_core_<ts>.json` (máquina)
3. Cola o conteúdo **integral** (ou só a seção do teste que falhou) na conversa comigo
4. Eu analiso o traceback + a fixture, corrijo o código, e peço para re-rodar

**Por que dois formatos?**
- `.log` é para você ler
- `.json` é para colar como insumo (machine-parseable, sem ruído de ANSI codes)

---

## 6. Comandos úteis durante o caminho B

```bash
# Rodar todos os testes
pwsh scripts/run_core_tests.ps1

# Rodar só testes de uma fase
pwsh scripts/run_core_tests.ps1 -TestPattern "test_core_frequency"

# Smoke manual: subir o app e abrir
streamlit run app.py

# Validar tipo estático (linter) — **primeira etapa** do script
ruff check src/core tests/test_core_*.py
ruff check src/core tests/test_core_*.py --fix   # auto-fix quando possível

# Verificar que todos os .py compilam (syntax check) — **segunda etapa** do script
python -m compileall src/core tests/

# Inspecionar dados em runtime
python -c "from src.data_layer import load_all; d=load_all(); print(d['patients'].head())"

# Rodar só a regra de frequência manualmente
python -c "
from src.data_layer import load_all
from src.core.repos import load_clients, load_client_deliverables, load_deliverables, load_client_sessions
from src.core.alerts import detect_frequency_alerts
from datetime import date
data = load_all()
alerts = detect_frequency_alerts(
    load_clients(data),
    load_client_deliverables(data),
    load_deliverables(data),
    load_client_sessions(data),
    date.today(),
)
print(f'{len(alerts)} alertas gerados')
for a in alerts[:3]: print(a)
"
```

---

## 7. Critérios globais de "caminho B completo"

| # | Critério | Verificação |
|---|---|---|
| 1 | `ruff check src/core tests/test_core_*.py` retorna 0 erros | `scripts/run_core_tests.ps1` etapa 6 |
| 2 | `pytest tests/` passa 100% (47 testes, incluindo `test_exception_handling.py`) | `scripts/run_core_tests.ps1` etapa 9 |
| 3 | `streamlit run app.py` sobe sem warning novo | smoke no script (etapa 11) |
| 4 | Mapa de Decisão mostra quadrante "Sem comparecimento" | visual + teste automatizado |
| 5 | Página Alertas tem filtro "Frequência" funcional | visual + teste automatizado |
| 6 | `core.alerts.detect_frequency_alerts(load_mock_data(), today)` retorna ≥ 1 alerta | teste e2e |
| 7 | CSVs de `data/new/` importam sem duplicar Kelly (typo consistente) | teste `test_csv_frequencia_missing_patient` |
| 8 | Cada página Streamlit renderiza 100% dos dados do mock | smoke por página (7 testes) |
| 9 | **N7 — nenhum stacktrace bruto no log de teste** | grep anti-traceback no script (etapa 10) |
| 10 | **N7 — `docs/exception_catalog.md` completo** para todas as libs usadas em `src/core/` | revisão manual por fase |
| 11 | **N8 — `docs/experience_log.md` atualizado** com entradas de todos os testes (passou/falhou) da fase | revisão manual por fase |
| 12 | **N9 — `docs/phase_reports/phase_N_report.md` produzido** com as 9 métricas | revisão manual por fase |

Quando todos os 7 estão ✅, **caminho B está pronto para apresentar ao cliente**.

---

## 8. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Mock data não tem colunas suficientes para popular tipos v2 (ex: `data_nascimento`, `cpf`) | Alta | Médio | Fase 1 testa com `None` em todos os campos opcionais; tipos v2 aceitam `None` |
| Refactor de `mapa_decisao.py` quebra o `try/except` defensivo | Média | Alto | Manter o try/except; cada mudança em `mapa_decisao.py` é coberta por teste de smoke |
| Streamlit `AppTest` API muda entre versões | Baixa | Médio | Pin em `streamlit==1.58.0` (versão documentada no `SLA_REPORT.md`) |
| Performance do `core.frequency` com N pacientes | Baixa | Baixo | Vetorizar (NumPy) na Fase 2; benchmark no `SLA_REPORT.md` |
| `pytest-json-report` não instala no venv Windows | Média | Baixo | Ter fallback `pytest-json` (mais antigo, mais compatível) |
| Typos no CSV (`Kelly Cristina a Silva Amorim`) quebram dedup | Alta | Médio | Teste explícito; tolerar via (nome + orçamento) como chave secundária |
| **`ruff` reclame de regras do projeto antigo (`src/metrics.py`, `src/pages/*`)** que não estão em `src/core/` ou `tests/` | Alta | Baixo | O script roda `ruff check src/core tests/test_core_*.py` — escopo restrito, **não** toca o código antigo. O código v1 não precisa passar no linter no caminho B. |
| **Linter pega erros legítimos em código que era pra passar** (false positive) | Baixa | Médio | `pyproject.toml` configura `select` conservador; `# noqa: <rule>` em ponto isolado, documentado inline |
| **N7 — `except Exception:` cego em função pura** (deveria ser exceção específica) | Média | Médio | `tests/test_exception_handling.py::test_no_bare_except` + revisão em cada PR; whitelist explícita para barreiras defensivas em `pages/*` |
| **N7 — esquecer de atualizar `docs/exception_catalog.md`** ao adicionar lib nova | Alta | Médio | Checklist no PR template (a ser criado); grep "from <lib> import" em `src/core/` é cruzado com catálogo |
| **N7 — mensagem traduzida mas pouco acionável** ("Erro desconhecido") | Média | Baixo | `test_exception_message_is_portuguese` valida presença de palavras-chave esperadas por tipo de erro |
| **N7 — barreira defensiva demais em `pages/*`** mascara bugs reais | Baixa | Médio | `pages/*` mantém o padrão atual (`try/except Exception` final com `_log.exception()`); barreira só na última fronteira, não no meio das funções |

---

## 9. Cronograma de alto nível

| Semana | Fase | Entregável |
|---|---|---|
| S1 | Fase 0 + Fase 1 (parcial) | Setup + tipos v2 + 1 repo funcionando |
| S2 | Fase 1 (resto) + Fase 2 (parcial) | 5 repos + 6 testes de frequency |
| S3 | Fase 2 (resto) + Fase 3 + Fase 4 | 12 testes de frequency + alertas + mapa_decisao refactor |
| S4 | Fase 5 + Fase 6 + Fase 7 | Alertas + importadores + e2e |

**Total: ~4 sprints (5-6 semanas)** para o caminho B completo até a Fase 7.

---

## 10. Próximos passos (quando você aprovar este plano)

1. **Aprovação do plano** — você confirma que as fases fazem sentido, **incluindo N7, N8, N9**.
2. **Setup do venv + requirements-dev.txt** — `pip install pytest pytest-json-report ruff tiktoken`.
3. **Criar `docs/exception_catalog.md`** — esqueleto com tabela vazia para preencher na Fase 1 (já criado).
4. **Criar `docs/experience_log.md`** — vazio, pronto para 1ª entrada.
5. **Criar `docs/phase_reports/`** — diretório vazio, pronto para o 1º relatório.
6. **Fase 0 (1-2 dias)** — criar a infra, rodar `run_core_tests.ps1` pela primeira vez, validar que exit 0. **Esta é a 1ª fase auditada** (N9) — o relatório `phase_0_report.md` será gerado a partir do baseline coletado pelo `scripts/measure_phase_metrics.py`.
7. **A partir daí: 1 fase por semana**, com você rodando o script e colando o log de volta.
8. **Em cada fase nova**:
   - **N8:** antes de implementar, eu **leio** o `experience_log.md` inteiro (N8) e destaco entradas recentes da mesma categoria.
   - **N7:** antes de escrever código contra uma lib, eu preencho/atualizo a linha correspondente em `docs/exception_catalog.md` (consultando a doc oficial).
   - Durante a fase, cada teste (passou/falhou) gera entrada no `experience_log.md` antes da fase ser declarada pronta.
   - Antes de declarar a fase pronta, os 5 testes de `test_exception_handling.py` precisam estar passando para as libs/funções tocadas.
9. **Em caso de falha**: você cola o `.log` ou `.json`; eu corrijo; você re-roda. Se a falha gerou entrada no `experience_log.md`, eu já a registrei.
10. **A cada fim de fase**: revisar juntos o `phase_N_report.md` (N9), decidir se segue ou ajusta. Razão output/input > 20 = trigger para simplificar a próxima fase.

Aguardo sua aprovação para começar a Fase 0.
