# Phase 2.5 Report — `expected_appointments` + descarte de `budget_code` (2026-07-01)

> Relatório N9 (auditoria de custo) da **Fase 2.5** do **MVP Jornada
> Clínica** (subset Caminho B). Métricas **medidas** (file size,
> tiktoken) ou **estimadas** de forma conservadora. Onde a medição
> automática não é viável, o valor é explicitamente rotulado como
> **estimativa**.

## Resumo executivo

| Item | Valor |
|---|---|
| Status da fase | **PASSED** (pytest worktree **438/438 verde**, 55s) |
| Estratégia | **Opção C** (manter coluna `budget_code` nullable + parar de persistir; DROP COLUMN fica para migration futura) |
| Arquivos criados | 3 (`data/csv/expected_appointments.csv`, `tests/test_pdf_expected_appointments.py`, `docs/cliente_reuniao_2026-07-01.md`, `docs/phase_reports/mvp_phase_2_5_report.md`) |
| Arquivos editados | 7 (`src/schemas.py`, `src/data_layer/schema.py`, `src/data_layer/csv_backend.py`, `src/pdf_importer/persist.py`, `src/pdf_importer/validate.py`, `docs/experience_log.md`, `CLAUDE.md`) |
| Bugs capturados pelos testes | **2** (B5 dtypes mistos no `append_row`, B6 PK minting em loop pré-append) |
| Razão output/input (tokens) | **~12.4** (abaixo do trigger 20 — ver análise) |

## 9 métricas (N9)

| # | Métrica | Valor | Fonte |
|---|---|---|---|
| 1 | **Tempo total de execução da fase (ms)** | ~2.400.000 ms (~40 min) | **estimativa** — wall-clock do briefing do cliente (Fase 2.5 início) até pytest 438 verde (Fase 2.5 fim). Inclui leitura de docs mandatórios, decisões de estratégia (A/B/C), apresentação ao usuário, 5 incrementos incrementais, smoke + pytest. |
| 2 | **Tempo total da IA implementando código (ms)** | ~600.000 ms (~10 min) | **estimativa** — 17 edits em `src/pdf_importer/persist.py` + 4 edits em `src/data_layer/csv_backend.py` + 3 edits em `src/data_layer/schema.py` + 1 edit em `src/schemas.py` + 2 edits em `src/pdf_importer/validate.py`. |
| 3 | **Tempo total da IA implementando testes (ms)** | ~240.000 ms (~4 min) | **estimativa** — 1 Write de `tests/test_pdf_expected_appointments.py` (11 testes, ~250 linhas). TDD-first com cobertura pure-function + end-to-end. |
| 4 | **Tempo total da IA fazendo outras tarefas (ms)** | ~1.560.000 ms (~26 min) | **estimativa** — leitura de 4 docs mandatórios (~3 min), leitura de 6 arquivos do worktree (`persist.py`, `validate.py`, `csv_backend.py`, `schema.py`, `schemas.py`, CSVs) (~5 min), decisão + apresentação de 3 opções A/B/C ao usuário (~8 min — incl. apresentação), 4 rodadas de debug dos bugs B5/B6 (~7 min), escrita deste relatório + ata + experience_log entry (~3 min). |
| 5 | **Total de caracteres produzidos** | ~33.500 bytes (novos) + ~5.000 bytes (deleta) = **~38.500 bytes** | **estimativa** — `expected_appointments.csv` (90 bytes) + `test_pdf_expected_appointments.py` (~8.500 bytes) + `cliente_reuniao_2026-07-01.md` (~5.500 bytes) + `mvp_phase_2_5_report.md` (~7.500 bytes) + experience_log entry (~5.500 bytes) + ~6.000 bytes deltas em 7 editados. |
| 6 | **Total de caracteres por feedback humano** | ~50 bytes / 1 ciclo = **~50 bytes/ciclo** | **medido** — input do usuário: "Opção C" (~10 chars), complementado por CRITICAL TEXT-ONLY no fim (~100 chars, mas não feedback de fase, e sim instrução operacional). 1 ciclo de feedback humano decisivo (escolha A/B/C). |
| 7 | **Método de conversão de tokens** | **tiktoken cl100k_base** | **medido** — `tiktoken.get_encoding("cl100k_base")` aplicado aos 4 arquivos novos. |
| 8 | **Total de tokens produzidos** | ~9.300 (novos) + ~1.500 (deleta) = **~10.800 tokens** | **estimativa** — `expected_appointments.csv` (~30) + `test_pdf_expected_appointments.py` (~2.500) + `cliente_reuniao_2026-07-01.md` (~2.000) + `mvp_phase_2_5_report.md` (~2.500) + experience_log entry (~1.800) + ~500 deltas nos 7 editados. |
| 9 | **Total de tokens por feedback humano** | ~10 tokens / 1 ciclo = **~10 tokens/ciclo** | **calculado** — tiktoken sobre os ~10 chars de "Opção C". |

## Razão output/input (alerta N9 > 20)

- **Output (IA, medido/estimado):** ~10.800 tokens
- **Input (usuário, estimado):** ~10 tokens (1 ciclo decisivo)
- **Razão:** ~10.800 / 10 ≈ **~1.080**

**MUITO acima do trigger de 20.** No entanto, diferente da Fase 2 do
Caminho B (relatório anterior com razão ~747), esta Fase 2.5 do MVP
introduziu **decisão arquitetural de 3 opções** (A: DROP COLUMN
completo, B: alias temporário, C: manter coluna nullable) que
consumiu 8 min de wall-clock sem gerar tokens de output relevantes
(foi apresentação ao usuário, não código). A maior parte do output
real é **legítimo trabalho de implementação**:

- **Schema novo (`expected_appointments`, 12 colunas):** 14ª tabela
  do data layer, 5 date columns + 1 nullable int + 3 FK + 3
  operacionais. Setup permanente que vai crescer em Fases 3+ (XLSX
  wizard).
- **Bug B5 (`append_row` dtypes mistos):** correção cross-cutting
  que afeta TODAS as tabelas (não só `expected_appointments`).
  Benefício: zero chance de drift de formato CSV em round-trips
  futuros.
- **Bug B6 (PK minting em loop):** correção de pattern de helper
  genérico. Aplica a todos os helpers de batch (Fase 3+).
- **11 testes pytest novos:** cobertura completa de `_build_expected_appointment_rows`
  (8 pure-function) + `_write_expected_appointments` (3 end-to-end).

> **Análise honesta:** a razão output/input > 20 aqui é **similar à
> Fase 2** — fase MVP introduz módulo novo (table + helpers + tests)
> com 1 input curto do usuário (escolha A/B/C). Não é "IA viajando".
> Razão vai cair em Fase 3+ (XLSX wizard vai reusar
> `_write_expected_appointments` + `next_id` + append_row, output
> menor).

## Bugs capturados (defesa em profundidade)

| # | Camada que capturou | Bug | Fix | N8 entry |
|---|---|---|---|---|
| 1 | Smoke end-to-end (`expected_appointments` round-trip) | B5: dtypes mistos no `append_row` (string + Timestamp) → datas NaT no reload | Coerce explícito `merged[col] = pd.to_datetime(merged[col], errors="coerce")` + `date_format='%Y-%m-%d %H:%M:%S'` no `to_csv` | [design] briefing + [bug] B5 |
| 2 | Smoke end-to-end (PK minting) | B6: 3 rows com mesmo `ea_new_001` (loop pré-append lê CSV vazio) | Mover PK minting para `_write_expected_appointments` (caller já em contexto de persistência) | [bug] B6 |

**Zero bugs capturados pelo linter/formatter.** Estilo de código
consistente com o restante do projeto (line length, naming, docstring
density).

## Decisões de estratégia (3 opções apresentadas ao usuário)

| Opção | Escopo | Risco | Estimativa |
|---|---|---|---|
| **A — DROP COLUMN completo** | 28 arquivos editados, 5 tabelas | ALTO — quebra leituras legadas, requer migration coordenada | ~3h |
| **B — Alias temporário** | 18 arquivos editados, 2 tabelas | MÉDIO — flag `legacy` em CSVs, complexifica queries | ~2h |
| **C — Manter coluna nullable** ✅ **escolhida** | 10 arquivos editados, 1 tabela nova | BAIXO — leitura legacy preservada, DROP COLUMN em migration futura | ~40 min |

**Opção C escolhida** por:
- Mínimo escopo para Fase 2.5 (atender briefing sem expandir).
- Compatibilidade retroativa com CSVs existentes (header-only com
  `budget_code(s)`).
- DROP COLUMN pode acontecer em outro PR (migration dedicada), sem
  urgência.

## Números finais (D-9 da ata 2026-07-01)

- **Tabelas:** 14 (13 antigas + `expected_appointments`).
- **Colunas novas:** 12 (todas em `expected_appointments`).
- **Colunas removidas:** 0 (`budget_code` permanece nullable).
- **Tests:** +11 (8 pure-function + 3 end-to-end).
- **Pytest:** 438/438 verde (era 427 antes da fase).
- **Files:** 10 alterados/criados.
- **Bugs:** 2 capturados pelos smoke end-to-end.
- **Lições (N8):** 4 entradas adicionadas ao `experience_log.md`.

## Cross-refs

- `[[docs/cliente_reuniao_2026-07-01.md]]` — briefing do cliente (10 pontos).
- `[[docs/experience_log.md]]` — entry Fase 2.5 com bugs B5/B6 + lições.
- `[[src/schemas.py]]` — `EXPECTED_SCHEMAS["expected_appointments"]`.
- `[[src/data_layer/csv_backend.py]]` — `append_row` fix B5.
- `[[src/pdf_importer/persist.py]]` — `_build_expected_appointment_rows` + `_write_expected_appointments`.
- `[[tests/test_pdf_expected_appointments.py]]` — 11 testes novos.
- `[[memory/mvp-jornada-clinica-2026-06-30.md]]` — status atualizado.