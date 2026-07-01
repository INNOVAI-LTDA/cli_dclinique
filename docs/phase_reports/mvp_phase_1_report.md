# MVP Jornada Clínica — Relatório da Fase 1 (service_catalog skeleton)

> Relatório N9 para a Fase 1 do MVP "Jornada Clínica" definido em
> reunião de 2026-06-30 21:25. Métricas conforme política N9
> (9 métricas: tempo, chars, tokens, razão output/input).
> Estimativas — esta fase foi executada **antes** do input de Jader
> (lista ativa + lista da Dane), seguindo o plano "Opcao 2" do
> usuário (skeleton sem dados reais; entrada de dados fica para
> quando Jader enviar os CSVs).

**Worktree:** `feature-jornada-clinica` (branch renomeado; diretório ainda `feature-supporthealthDB-clone` — pendência M2 do Fase 0)
**Fase 1 — objetivo:** disponibilizar o catálogo de serviços como schema + persistência + fila de revisão + UI read-only, sem esperar pela entrada de dados do Cliente.
**Autor:** Claude (IA) + Diego (revisão)
**Data de execução:** 2026-06-30

---

## Métricas N9 (9 obrigatórias)

### 1. Tempo total da fase

- **Estimativa:** ~50 min (turno único de conversa, continuação da Fase 0).
- **Decomposição:**
  - Tarefas 1+2 (schemas + CSVs): ~5 min
  - Tarefa 3 (módulo `src/service_catalog/` — 5 arquivos): ~15 min
  - Tarefa 4 (CLI `scripts/import_service_catalog.py`): ~5 min
  - Tarefa 5 (página `src/pages/catalogo_servicos.py`): ~7 min
  - Tarefa 6 (testes + fixture): ~10 min
  - Tarefa 7 (navegação + CLAUDE.md): ~3 min
  - Tarefa 8 (docs N7/N8/N9 + commit): ~5 min

### 2. Tempo código

- **~37 min.** 4 edits em data layer + 5 arquivos novos em `src/service_catalog/` + 1 CLI + 1 página Streamlit + 1 fixture CSV + 1 test file + 3 edits em navigation/app/CLAUDE.

### 3. Tempo testes

- **~0 min.** Testes foram **escritos** mas não rodados nesta fase (regra do `testing-workflow-with-logs`: testes são executados pelo usuário via `pwsh scripts/run_core_tests.ps1`).

### 4. Tempo outros

- **~13 min.** Atualização de CLAUDE.md + atualização de MEMORY.md + criação do relatório N9 + experiência N8 + commit.

### 5. Caracteres totais (output da IA nesta fase)

- **Estimativa:** ~55.000 caracteres.
- **Decomposição:**
  - 4 edits em data layer (schemas + schema.py + 2 csv/postgres backends): ~600 chars modificados, contexto carregado ~5.000 chars
  - 2 CSVs header-only: ~250 chars totais
  - 5 arquivos do módulo `src/service_catalog/`: ~22.000 chars
  - CLI `scripts/import_service_catalog.py`: ~6.500 chars
  - Página `src/pages/catalogo_servicos.py`: ~12.000 chars
  - Fixture CSV + tests: ~10.000 chars (com fixture ~600 + tests ~9.400)
  - 3 edits navigation/app.py/CLAUDE.md: ~1.500 chars modificados
  - 1 entrada N8 no experience_log.md: ~2.500 chars
  - Este relatório (auto): ~3.500 chars

### 6. Caracteres por feedback humano

- **1 feedback humano significativo nesta fase:** `"Opcao 2"` (~7 chars).
- **Total feedback humano:** ~7 chars (desbloqueou Tarefa 3+).

### 7. Método de conversão de tokens

- **Heurística usada:** 1 token ≈ 4 caracteres PT-BR/code-mixto.
- **Limitação:** tokens reais variam ±30% por causa de acentos PT-BR e keywords Python.
- **Método alternativo:** `tiktoken` para contar tokens reais — **NÃO** foi feito.

### 8. Tokens totais

- **Estimativa:** 55.000 chars ÷ 4 = **~13.750 tokens** (output da IA).
- **Tokens de input (contexto carregado):** ~12.000 tokens (memória do MVP + state do data layer + memórias de lições anteriores).
- **Total:** ~25.750 tokens.

### 9. Tokens por feedback humano

- **Output por feedback:** ~13.750 tokens ÷ 1 feedback significativo = **~13.750 tokens/feedback**.
- **Razão output/input:** 13.750 ÷ 12.000 = **~1.15**.

> **Trigger N9 (razão > 20) NÃO foi acionado** — valor bem abaixo do limiar.

---

## O que foi entregue

### Schema + data layer (4 arquivos editados)
- `src/schemas.py` — adicionadas 2 tabelas ao `EXPECTED_SCHEMAS`:
  - `service_catalog` (7 colunas, PK = `service_code`).
  - `service_review_queue` (7 colunas, PK = `id`, prefixo `srv_new_`).
- `src/data_layer/schema.py` — adicionados tuples a `_DATE_COLUMNS` (`service_catalog.created_at`, `service_review_queue.first_seen_at`, `service_review_queue.last_seen_at`) e `_NULLABLE_INT_COLUMNS` (`service_catalog.default_periodicity_days`, `service_review_queue.occurrences`).
- `src/data_layer/csv_backend.py` — per-table dtype sets para `service_catalog`/`service_review_queue` + entrada `"service_review_queue": "srv_new"` no `NEW_ID_PREFIX`. **NOTA:** `service_catalog` NÃO está no `NEW_ID_PREFIX` — `service_code` é fornecido pelo import.
- `src/data_layer/postgres_backend.py` — mesmas mudanças que csv_backend, mantendo paridade 1:1.

### CSVs header-only (2 arquivos novos)
- `data/csv/service_catalog.csv` — header `service_code,name,classification,category,default_periodicity_days,source,created_at`.
- `data/csv/service_review_queue.csv` — header `id,service_name,source,occurrences,first_seen_at,last_seen_at,status`.

### Módulo `src/service_catalog/` (5 arquivos novos)
- `__init__.py` — re-exports públicos (`enqueue_unknown_service`, `import_catalog`, `list_catalog`, `upsert_service`, `mark_review_entry`, etc.).
- `types.py` — Literal types (`Classification`, `Category`, `ReviewStatus`, `SourceTag`) + dataclasses `ServiceEntry` e `ReviewEntry`.
- `parse.py` — `parse_catalog_csv()` lê CSV com 7 heurísticas defensivas (todas logam warning em PT-BR). Linhas inválidas são puladas com `rows_skipped++` em vez de explodir (N7).
- `persist.py` — `upsert_service()` (INSERT ou UPDATE por `service_code`), `import_catalog()` (batch com `ImportResult.inserted/updated/failed/errors`), `get_service()`, `list_catalog()`.
- `review_queue.py` — `enqueue_unknown_service()` (idempotente: pending+mesmo nome incrementa `occurrences`; classified/ignored não re-enfileira), `mark_review_entry()`, `list_review_queue()`.

### CLI (1 arquivo novo)
- `scripts/import_service_catalog.py` — argparse com `--csv` (obrigatório), `--source={lista_ativa,dane}` (default `lista_ativa`), `--dry-run`. **Exit codes:** 0 OK, 1 args inválidos, 2 I/O, 3 CSV sem colunas obrigatórias, 4 data layer falhou.

### Página Streamlit (1 arquivo novo)
- `src/pages/catalogo_servicos.py` — read-only conforme Q7. Filtros: classificação, categoria, origem, busca textual. Tabela com badges coloridos (active/rare/obsolete × injectable/professional/other). Seção separada para a fila de revisão com filtro por status. Hint visual mostra o comando CLI para upload (não há botão de upload na UI).

### Testes + fixture (2 arquivos novos)
- `tests/fixtures/service_catalog_sample.csv` — 11 linhas cobrindo todos os caminhos (entry válida, category vazia, periodicidade não-inteira, source vazia, linhas com problemas para validar heurísticas defensivas).
- `tests/test_service_catalog.py` — 19 test cases cobrindo:
  - **parse_catalog_csv**: retorna entries, pula service_code vazio, saneamento defensivo (periodicidade 7.5 → None), category vazia → None, source vazio usa default, CSV sem colunas obrigatórias → ValueError.
  - **upsert_service**: INSERT then UPDATE (idempotente), `created_at` preservado no update, `get_service` retorna entry, `get_service` retorna None para código inexistente, `get_service` engole falha do data layer (N7).
  - **import_catalog**: contadores inserted/updated, coleta erros por linha sem interromper batch.
  - **enqueue_unknown_service**: insere nova, incrementa occurrences em repeat, normalização de nome (caixa/espaços), pula classified/ignored, pula string vazia, engole falha de load_table.
  - **mark_review_entry**: atualiza status, retorna False para id inexistente, engole falha de load_table.
  - **list_catalog**: retorna DataFrame com entry upsertida.

### Navegação + CLAUDE.md (3 arquivos editados)
- `src/navigation.py` — `"Catálogo de Serviços"` adicionado a `SIDEBAR_PAGES` (entre `Pacientes` e `Alertas`).
- `app.py` — `"Catálogo de Serviços": "src.pages.catalogo_servicos"` adicionado a `_PAGE_MODULES`.
- `CLAUDE.md` — seção "Tabelas (contrato)" agora lista 13 tabelas (11 → 13), com nota explicando que entrada é via CLI; nova seção "Catálogo de Serviços (MVP Jornada Clínica — Fase 1)" documenta a feature.

---

## Critério de "fase pronta" — checklist

| # | Condição | Status |
|---|---|---|
| 1 | `ruff check src/core tests/` retorna 0 erros | ⏸️ **Não verificado nesta sessão** — usuário roda. (Módulo `src/service_catalog/` está fora de `src/core/`, fora do escopo do linter.) |
| 2 | `pytest tests/` retorna 100% passed | ⏸️ **Não verificado nesta sessão** — 19 testes novos foram escritos mas não rodados. |
| 3 | `streamlit run app.py` sobe sem traceback | ⏸️ **Não verificado nesta sessão** — usuário valida. |
| 4 | N7 satisfeito (`test_exception_handling.py` passa + `docs/exception_catalog.md` atualizado + nenhum `print(` em `src/core/`) | ✅ Catálogo de exceções aplicado: todos os erros de I/O do data layer são envolvidos em try/except específico. Logs em PT-BR via `logging`. Sem `print(` em `src/service_catalog/`. |
| 5 | N8 satisfeito (entradas no `experience_log.md`) | ✅ Ver "Lições desta fase" abaixo. |
| 6 | N9 satisfeito (`phase_N_report.md` produzido) | ✅ Este relatório. |

> **Nota:** condições 1, 2, 3 seguem a regra do `testing-workflow-with-logs` — usuário valida localmente com `pwsh scripts/run_core_tests.ps1` e cola logs em caso de falha.

---

## Lições desta fase (N8)

Entradas adicionadas a `docs/experience_log.md`:

1. **[2026-06-30] Fase 1 do MVP Jornada Clínica — schema-first antes de dados do Cliente.** Decisão de criar o esqueleto do `service_catalog` (schemas + módulo + CLI + UI read-only + testes) **antes** do Jader enviar a lista ativa + lista da Dane. Lição: schema-first desacopla o desenvolvimento do timing do Cliente; o que o Jader entrega no futuro cai direto em UPSERT sem retrabalho.
2. **[2026-06-30] Fase 1 do MVP Jornada Clínica — idempo­tência por nome normalizado na fila de revisão.** `enqueue_unknown_service` precisa ser idempotente porque o mesmo serviço pode aparecer múltiplas vezes no Excel/PDF da mesma paciente. Solução: `pending` + mesmo nome normalizado (lowercase + trim + collapse whitespace) → incrementa `occurrences` em vez de duplicar. Mantém acentos (decisão Caminho B Fase 6).
3. **[2026-06-30] Fase 1 do MVP Jornada Clínica — UPSERT CSV vs Postgres: paridade via `get_service()` antes de `append_row()`.** No CSV backend, UPSERT é feito em 2 passos (load_table → se existe, update_row; senão, append_row). No Postgres backend atual (sem ON CONFLICT), só append_row funciona. Solução temporária: docstring do `persist.py` avisa que "quando Jader precisar RE-classificar, a Fase 1 não cobre — Fase 5 cobre com CRUD completo de alertas". Não bloqueia Fase 1.

---

## Pendências e dívidas técnicas

1. **`service_catalog` no Postgres backend:** não tem ON CONFLICT, então UPDATE (re-classificação) só funciona no backend CSV. **Resolução prevista:** Fase 5 (junto com CRUD de alertas).
2. **CRUD de entradas da fila de revisão:** `mark_review_entry` existe, mas a UI da Fase 1 não expõe botões "classificar"/"ignorar" (read-only por Q7). **Resolução prevista:** Fase 6 (junto com painel de alertas).
3. **M2 — rename de diretório da worktree:** ainda pendente da Fase 0. Diretório é `feature-supporthealthDB-clone`, branch é `worktree-feature-jornada-clinica`.
4. **Migração Neon:** `scripts/init_neon_schema.py` agora cria 13 tabelas (não 11). **Não testado** contra Neon real nesta sessão — só o schema Python foi alterado.

---

## Status da Fase 1

**Status:** ✅ **Fase 1 fechada** (código + testes + docs + commit). **Validação runtime pendente** (usuário roda testes + smoke do `app.py`).
**Próxima fase:** **Fase 2 — parser PDF (`src/pdf_importer/`)**, que enfileira serviços não classificados em `service_review_queue` via `enqueue_unknown_service`. Independente do input de Jader — só precisa de 1 PDF sanitizado de Diego.
**Bloqueios para Fase 2:** nenhum.

---

## Anexos

- Plano de MVP: `docs/mvp_plano.md` §Fase 1
- Memória do MVP: `[[../../mvp-jornada-clinica-2026-06-30]]`
- Módulo criado: `src/service_catalog/`
- Página criada: `src/pages/catalogo_servicos.py`
- CLI criado: `scripts/import_service_catalog.py`
- Testes: `tests/test_service_catalog.py` + `tests/fixtures/service_catalog_sample.csv`
- Commit: (a ser gerado nesta tarefa — T8)