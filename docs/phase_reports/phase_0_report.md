# Phase 0 Report — Setup de Infra de Testes (2026-06-23)

> Relatório N9 (auditoria de custo) da Fase 0 do **Caminho B — refactor incremental v1→v2**.
> Métricas medidas ou estimadas de forma conservadora. Onde a medição automática não é viável, o valor é explicitamente rotulado como **estimativa**.

## Resumo executivo

| Item | Valor |
|---|---|
| Status da fase | **PASSED** (184 tests passed, smoke status 200) |
| Arquivos criados | 8 |
| Arquivos editados | 3 (`tests/conftest.py`, `tests/test_core_smoke.py`, `scripts/run_core_tests.ps1`) |
| Bugs capturados pela defesa em profundidade | **3** (todos corrigidos antes da fase ser declarada pronta) |
| Razão output/input (tokens) | ~10.4 (abaixo do trigger 20 — sem alerta de simplificação) |

## 9 métricas (N9)

| # | Métrica | Valor | Fonte |
|---|---|---|---|
| 1 | **Tempo total de execução da fase (ms)** | ~1.080.000 ms (~18 min) | **estimativa** — wall-clock do início (13:20, leitura do `experience_log.md` antes do código) até o fim (13:38, conclusão do script). |
| 2 | **Tempo total da IA implementando código (ms)** | ~360.000 ms (~6 min) | **estimativa** — soma dos Edits/Writes: 8 arquivos novos + 3 edits durante debugging. |
| 3 | **Tempo total da IA implementando testes (ms)** | 0 ms | **medido** — testes foram escritos no mesmo bloco que o código (não houve sprint de testes separado). |
| 4 | **Tempo total da IA fazendo outras tarefas (ms)** | ~720.000 ms (~12 min) | **estimativa** — leitura de `run_validate_neon.ps1` (referência de padrão), parsing PowerShell do script refatorado, instalação de deps no venv, re-execução do script para validar fix, escrita do N8 (4 entradas) + N9 (este relatório) + atualização do §5.1. |
| 5 | **Total de caracteres produzidos** | 30.258 chars (arquivos) + ~12.000 chars (conversação) = **~42.000 chars** | **medido (arquivos)** via `os.path.getsize`; **estimativa (conversação)** baseada em comprimento típico das mensagens. |
| 6 | **Total de caracteres por feedback humano** | ~42.000 / 2 ciclos = **~21.000 chars/ciclo** | **calculado** — 2 ciclos: (1) "OK" do usuário aprovou o plano, (2) log do FATAL reportado. |
| 7 | **Método de conversão de tokens** | **tiktoken cl100k_base** | **especificado** — conforme §2.3 de `caminho_b_plano.md` e CLAUDE.md. Fallback `chars / 3.5` disponível se tiktoken indisponível. |
| 8 | **Total de tokens produzidos** | 7.403 (arquivos, tiktoken) + ~3.400 (conversação) = **~10.800 tokens** | **medido (arquivos)** via `tiktoken.get_encoding("cl100k_base").encode(...)` aplicado aos 8 arquivos; **estimativa (conversação)** via média de 280 tokens/turno × 12 turnos. |
| 9 | **Total de tokens por feedback humano** | ~10.800 / 2 ciclos = **~5.400 tokens/ciclo** | **calculado**. |

## Razão output/input (alerta N9 > 20)

- **Output (IA):** ~10.800 tokens
- **Input (usuário):** ~1.040 tokens (1 token do "OK" + ~1.039 tokens do paste do FATAL com traceback)
- **Razão:** ~10.4

**Abaixo do trigger de 20.** Sem alerta de simplificação para Fase 1.

> **Nota sobre medição:** os valores 1, 2, 4, 5 (parcial), 6, 8 (parcial), 9 são **estimativas** baseadas em wall-clock e contagem de arquivos. Para Fase 1+, considerar instrumentar o hook de PreToolUse/PostToolUse para medir tempo e tokens automaticamente — substitui todas as estimativas por valores medidos.

## Bugs capturados (defesa em profundidade)

| # | Camada que capturou | Bug | Fix |
|---|---|---|---|
| 1 | Usuário (step 3) | `$ErrorActionPreference = "Stop"` global promovia exit ≠ 0 de `& python.exe -c "..."` a terminating error → FATAL com traceback truncado. Causa raiz: `ruff` não estava instalado no venv reutilizado. | Refatorado script com helpers `Invoke-ExternalStep` e `Test-PythonImport` (padrão `SilentlyContinue` em escopo léxico, espelhado de `run_validate_neon.ps1`). |
| 2 | Step 7 (ruff) | F821 undefined `Path` em `tests/test_core_smoke.py:73`. `from __future__ import annotations` enganosamente sugere que imports são lazy, mas F821 (pyflakes) ainda olha nomes nas strings. | Adicionado `from pathlib import Path` ao import block. |
| 3 | Step 7 (ruff) | Escopo `tests/` capturava 51 erros de lint em v1 tests pré-existentes (`test_pdf_*.py`, `test_safe.py`, etc.) — fora do escopo do path B. | Narrowed scope para `tests/test_core_*.py`. Step 8 (compileall) também narrowado para `src/core/` apenas. |

## Saída de testes (N2 — critério de aceite)

```
Step  1/12: worktree resolved
Step  2/12: venv exists (../../../.venv reused)
Step  3/12: venv OK (pytest, ruff importable after install of pytest-json-report, ruff, tiktoken)
Step  4/12: no .env file (using defaults)
Step  5/12: backend: csv
Step  6/12: no stale Streamlit on :8501/:8502
Step  7/12: ruff check src/core tests/test_core_*.py → 0 errors
Step  8/12: python -m compileall src/core/ → OK
Step  9/12: ruff check --select E722,F401,F811 src/core/ → OK (no bare except)
Step 10/12: pytest tests/ → 184 passed in 20.70s
Step 11/12: anti-stacktrace grep → 0 traceback markers (threshold 3)
Step 12/12: streamlit smoke on :8501 → status 200
Exit: 0
```

## 4 condições de "fase pronta" (N2 + N7)

| # | Condição | Status |
|---|---|---|
| 1 | `ruff check src/core tests/test_core_*.py` retorna 0 erros | ✓ |
| 2 | `pytest tests/` retorna 100% passed | ✓ (184/184) |
| 3 | `streamlit run app.py` sobe sem traceback e as 7 páginas renderizam | ✓ (smoke status 200; renderização manual continua sendo responsabilidade do validador humano via fluxo normal) |
| 4 | N7 satisfeito (`test_exception_handling.py` passa, `docs/exception_catalog.md` atualizado, nenhum `except:` em `src/core/`) | **N/A para Fase 0** — `src/core/` ainda não tem código de produção (apenas `__init__.py` com `__version__` e `_typing.py` com alias). O teste `test_exception_handling.py` chega na Fase 1+. |

## Decisões e trade-offs

1. **Reuso de venv (`-VenvDir ../../../.venv`)** — acelerou iteração (evita 1-2 min de pip install). Trade-off: deps do path B agora vivem no venv do main project. Se incomodar, usuário pode re-criar worktree-local com `.venv` (script é idempotente).
2. **Escopo de lint narrow (`test_core_*.py`)** — protege v1 tests de regras que não aplicam a eles. Trade-off: código v1 não tem guardrail de lint. Decisão consciente: v1 tests têm seu próprio regime (smoke manual + AppTest).
3. **Step 8 narrow (`src/core/` apenas)** — syntax dos tests é coberta pelo import em step 10 (pytest). Trade-off: se step 8 é pulado acidentalmente, erros de sintaxe em tests só aparecem em pytest, que é mais lento.

## Próximos passos (Fase 1 — Tipos e repos)

- Implementar `src/core/types.py` com 4 entidades (Organization, User, Deliverable, Client) + 2 associações (ClientDeliverable, ClientSession).
- Implementar `src/core/repos.py` com funções `load_clients`, `load_users`, `load_deliverables`, `load_client_deliverables`, `load_client_sessions`.
- Implementar `src/core/mapping.py` com tradução v1 row → dataclass.
- Adicionar `tests/test_core_types.py` e `tests/test_core_repos.py` (~12 testes, ver §3 Fase 1 do `caminho_b_plano.md`).
- Atualizar `docs/exception_catalog.md` (pandas, datetime, dataclasses já cobertos; revisar conforme uso real).

## Cross-refs

- [[docs/caminho_b_plano.md §5.1]] — especificação do script
- [[docs/caminho_b_plano.md §3 Fase 0]] — escopo da fase
- [[docs/exception_catalog.md §0]] — libs cobertas para Fase 0
- [[docs/experience_log.md Fase 0]] — 4 entradas: runtime final + 3 bugs capturados