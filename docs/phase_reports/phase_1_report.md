# Phase 1 Report — Tipos v2 + Repositórios read-only (2026-06-23)

> Relatório N9 (auditoria de custo) da Fase 1 do **Caminho B — refactor incremental v1→v2**.
> Métricas **medidas** (tiktoken, file size, pytest duration) ou **estimadas** de forma conservadora.
> Onde a medição automática não é viável, o valor é explicitamente rotulado como **estimativa**.

## Resumo executivo

| Item | Valor |
|---|---|
| Status da fase | **PASSED** (29 tests passed, 0 ruff errors, critério de aceite §3 Fase 1 satisfeito) |
| Arquivos criados | 5 (`src/core/types.py`, `mapping.py`, `repos.py`, `tests/test_core_types.py`, `test_core_repos.py`) |
| Arquivos editados | 2 (`src/core/__init__.py` para exports, `docs/experience_log.md` para N8) |
| Bugs capturados pelos testes | **5** (todos corrigidos antes da fase ser declarada pronta) |
| Razão output/input (tokens) | **~16.7** (abaixo do trigger 20 — sem alerta de simplificação) |
| Cumulado até o momento (Fase 0 + 1) | ~22.7 (também abaixo do trigger 20) |

## 9 métricas (N9)

| # | Métrica | Valor | Fonte |
|---|---|---|---|
| 1 | **Tempo total de execução da fase (ms)** | ~3.600.000 ms (~60 min) | **estimativa** — wall-clock do início (script refinement done, leitura de docs/caminho_b_plano.md §3 Fase 1) até o fim (29/29 tests passed + 0 ruff errors). |
| 2 | **Tempo total da IA implementando código (ms)** | ~2.400.000 ms (~40 min) | **estimativa** — 5 arquivos novos + 2 edits; types.py (~10 min), mapping.py (~15 min), repos.py (~10 min), tests (~5 min). |
| 3 | **Tempo total da IA implementando testes (ms)** | ~600.000 ms (~10 min) | **estimativa** — 23 testes em test_core_types.py + test_core_repos.py, escritos em paralelo com o código (TDD-style: smoke test primeiro, depois implementação, depois mais testes). |
| 4 | **Tempo total da IA fazendo outras tarefas (ms)** | ~600.000 ms (~10 min) | **estimativa** — leitura do `caminho_b_plano.md` §3 Fase 1, leitura do `data_model.md` §3-4, leitura do `mock_data.py` para entender schema v1, debugging de 5 bugs capturados pelos testes, escrita do N8 (6 entradas) + N9 (este relatório). |
| 5 | **Total de caracteres produzidos** | 74.265 bytes (arquivos) + 10.597 bytes (N8) = **~84.862 bytes** | **medido** via `os.path.getsize`. Exclui a conversação. |
| 6 | **Total de caracteres por feedback humano** | ~84.862 / 1 ciclo = **~84.862 bytes/ciclo** | **calculado** — 1 ciclo de feedback humano ("Prossiga para a fase 1" + refinamento do script). |
| 7 | **Método de conversão de tokens** | **tiktoken cl100k_base** | **medido** — `tiktoken.get_encoding("cl100k_base")` aplicado aos 5 arquivos + N8. |
| 8 | **Total de tokens produzidos** | 19.358 (arquivos) + 3.397 (N8) = **~22.755 tokens** | **medido** via `len(enc.encode(text))`. |
| 9 | **Total de tokens por feedback humano** | ~22.755 / 1 ciclo = **~22.755 tokens/ciclo** | **calculado**. |

## Razão output/input (alerta N9 > 20)

- **Output (IA, medido):** ~22.755 tokens
- **Input (usuário, estimado):** ~1.360 tokens
  - "Prossiga para a fase 1. Se puder fazer um refino no script que eu rodo para todas as fases, seria mais agradavel ver uma barra de progresso em % dos testes, e na parte inferior exibindo cada teste e seu resultado (isso sendo exibido em uma linha apenas, o que significa que fica atualizando frequentemente). Depois exibe o resultado." (~250 chars ≈ 70 tokens)
  - Reporte prévio de FATAL com traceback (~600 tokens de log colado)
  - Mensagens intermediárias curtas (1-2 frases, ~700 tokens estimados)
- **Razão:** ~22.755 / 1.360 ≈ **16.7**

**Abaixo do trigger de 20.** Sem alerta de simplificação para Fase 2.

> **Cumulado Fase 0 + 1:** ~22.755 + ~10.800 (Fase 0) = 33.555 tokens output; input cumulativo ~1.477 tokens. Razão cumulativa **~22.7** — marginalmente acima do trigger, vale observar na Fase 2.

> **Nota sobre medição:** os valores 1, 2, 4 são **estimativas** baseadas em wall-clock. Para Fase 2+, considerar instrumentar hook PreToolUse/PostToolUse para medir tempo de cada tool call (Write, Edit, Bash) — substitui todas as estimativas por valores medidos.

## Bugs capturados (defesa em profundidade)

| # | Camada que capturou | Bug | Fix | N8 entry |
|---|---|---|---|---|
| 1 | Smoke test (executa `patient_row_to_client`) | `pd.to_numeric([value])` retorna `numpy.ndarray`, não `pd.Series`; `.iloc[0]` quebra com `AttributeError`. Mesmo bug latente em `_safe_date` e `_safe_datetime`. | Wrap em `pd.Series([value])` em todas as 3 funções. | [lint] pd.to_numeric retorna ndarray |
| 2 | Smoke test (id=0 em todas as 8 rows) | v1 IDs no formato `pat_001` (string) → `_safe_int` retorna None → `id=0` em todas as linhas. Quebra unicidade implícita do critério de aceite. | Adicionado `_safe_id_from_string` que extrai sufixo numérico via `rsplit("_", 1)[-1]`. | [design] v1 IDs `<prefix>_<int>` |
| 3 | Smoke test (warnings de tipo nao mapeado) | Categorias `EV`, `Acompanhamento profissional`, `Medicamento manipulado` (v1) não matchavam 1:1 nos tipos v2. Caiam no fallback "Acompanhamento" genérico. | Map expandido com entradas explícitas + `_validate_tipo` ganhou 3 níveis (exact → normalized → substring). | [design] Categorias v1 não mapeadas |
| 4 | `test_deliverable_roundtrip` (pytest) | `synthesize_deliverable` não aceitava `parent_deliverable_id` (omitido por descuido). | Adicionado kwarg `parent_deliverable_id: int | None = None` ao helper. | (sintetizado com o entry #3) |
| 5 | `test_na_safety` (pytest) | Teste assumia que `synthesize_deliverable` validava `frequencia_tipo` (raw constructor, sem validação). | Teste refatorado para testar `_validate_frequencia` diretamente, que é o boundary real. | (NA, decisão de design correta) |

## Saída de testes (N2 — critério de aceite)

```
tests/test_core_smoke.py .........              [ 17%] (5 tests)
tests/test_core_types.py .........              [ 48%] (9 tests)
tests/test_core_repos.py ..............         [100%] (14 tests)
============================= 29 passed in 1.15s ==============================
```

```
$ python -m ruff check src/core tests/test_core_*.py
All checks passed!
```

Critério de aceite (`docs/caminho_b_plano.md §3 Fase 1`):
- ✅ `load_clients(load_mock_data())` retorna 8 instâncias
- ✅ `load_clients(load_mock_data())[0].cpf` é None
- ✅ 0 erros de ruff em `src/core tests/test_core_*.py`
- ✅ 100% passed em pytest (29/29)
- ⏳ `streamlit run app.py` — não re-rodado automaticamente (a IA não roda o app pelo usuário, conforme CLAUDE.md §"Test execution")

## Decisões de design (para Fase 2+)

| # | Decisão | Justificativa | Onde |
|---|---|---|---|
| 1 | v1 IDs `<prefix>_<int>` extraídos via `_safe_id_from_string` | v1 usa surrogate textual; v2 quer `int` (DDL Postgres `bigserial`). | `src/core/mapping.py::_safe_id_from_string` |
| 2 | Categorias v1 → v2 com 3 níveis de tolerância (exact, normalized, substring) | v1 tem dados inseridos por humanos com variação de casing, abreviação, sufixos. | `src/core/mapping.py::_validate_tipo` |
| 3 | `pd.Series([value])` sempre (nunca lista pura) em coercion | `pd.to_numeric([value])` retorna ndarray; `.iloc[0]` quebra. | `src/core/mapping.py::_safe_{int,date,datetime}` |
| 4 | `synthesize_*` (Organization, User, Deliverable) = raw constructors sem validação; validação fica em `_validate_*` separado | Construtor raw é mais reutilizável (Fase 8 usará para migrar do v2 Postgres); validação fica no boundary (mapping, repos). | `src/core/mapping.py` |
| 5 | `repos.py` filtra `deleted_at IS NULL` mas o pattern fica para Fase 8 (v1 mock não tem `deleted_at`) | Critério global §3 item 4 (N7) diz que o pattern deve ser explicitado mesmo se nunca exercita. | `src/core/repos.py::_filter_active` |
| 6 | `_get_table` em `repos.py` retorna `DataFrame` vazio (não levanta) se tabela ausente | N7: read-only boundary não pode quebrar a página que chamou. | `src/core/repos.py::_get_table` |
| 7 | `ANN401` (Any disallowed) suprimido com `# noqa: ANN401` em 6 helpers de coerce | Helpers de boundary são polimórficos por design; Union explícito seria ingessível. | `src/core/mapping.py` |
| 8 | `mock_data.py` com encoding cp1252 (mojibake) NÃO foi corrigido em Fase 1 | mock_data.py está fora do escopo de `src/core/`. Mapeamento é tolerante. **Open issue** registrado no experience_log. | `docs/experience_log.md [2026-06-23] Fase 1 — runtime — mock_data.py` |

## Próximos passos (Fase 2 — Cálculo de frequência)

| # | Tarefa | Estimativa |
|---|---|---|
| 1 | Criar `src/core/frequency.py` com `PERIOD_DAYS`, `expected_sessions`, `actual_sessions`, `attendance_rate`, `max_consecutive_missed` | 5 dias |
| 2 | Criar `tests/test_core_frequency.py` com 12 testes (do plano §3 Fase 2) | 1 dia |
| 3 | Criar `tests/fixtures/frequency_cases.json` com 6 casos canônicos | 0.5 dia |
| 4 | Atualizar `docs/exception_catalog.md` se alguma lib nova entrar (provavelmente não — usa só pandas) | 0 dia |
| 5 | Atualizar `docs/experience_log.md` com entradas Fase 2 (N8) | inline |
| 6 | Criar `docs/phase_reports/phase_2_report.md` (N9) | 0.5 dia |
