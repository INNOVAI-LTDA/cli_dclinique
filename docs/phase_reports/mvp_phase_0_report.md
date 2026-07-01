# MVP Jornada Clínica — Relatório da Fase 0 (Setup)

> Relatório N9 para a Fase 0 do MVP "Jornada Clínica" definido em
> reunião de 2026-06-30 21:25. Métricas conforme política N9
> (9 métricas: tempo, chars, tokens, razão output/input).
> Estimativas — esta fase é administrativa (sem código), então as
> métricas de "código" e "testes" são zero por design.

**Worktree:** `feature-jornada-clone` (a renomear — M2)
**Origem da Fase 0:** Reunião Diego + Jader em 2026-06-30 21:25 (ata em `docs/cliente_reuniao_2026-06-30.md`)
**Autor:** Claude (IA) + Diego (revisão)
**Data de execução:** 2026-06-30

---

## Métricas N9 (9 obrigatórias)

### 1. Tempo total da fase

- **Estimativa:** ~30 min (turno único de conversa, do "vai" à finalização).
- **Decomposição:**
  - M1 (CLAUDE.md edit): ~2 min
  - M3 (memórias): ~5 min
  - M4 (5 docs Fase 0): ~15 min
  - M2 (renomear worktree — pendente): ~3 min
- **Limitações:** tempo medido por inferência (relógio da sessão); não há cost-tracker formal no harness.

### 2. Tempo código

- **0 min.** Fase 0 é setup puro. Nenhum arquivo `.py` foi criado ou modificado.

### 3. Tempo testes

- **0 min.** Nenhum teste foi rodado (Fase 0 não tem código).

### 4. Tempo outros

- **~25 min** (administração: docs + memória + CLAUDE.md + análises + decisão de naming).

### 5. Caracteres totais (output da IA nesta fase)

- **Estimativa:** ~35.000 caracteres.
- **Decomposição:**
  - Resposta analítica (texto da conversa sobre Q1–Q9, M1–M4, M3 summary): ~10.000 chars
  - 2 edits em CLAUDE.md: ~150 chars modificados (mas o contexto carregado era ~2.000 chars)
  - Reescrita de `supporthealth-clone-worktree.md`: ~3.500 chars
  - Criação de `mvp-jornada-clinica-2026-06-30.md`: ~6.500 chars
  - Edit em `MEMORY.md`: ~300 chars modificados
  - Criação de `docs/cliente_reuniao_2026-06-30.md`: ~9.000 chars
  - Criação de `docs/mvp_plano.md`: ~9.500 chars
  - Apêndices a `docs/exception_catalog.md` + `docs/experience_log.md`: ~1.500 chars (estimativa; será medido após append)
  - Este relatório (auto): ~3.000 chars

### 6. Caracteres por feedback humano

- **1 feedback humano significativo nesta fase:** `"vai"` (4 chars).
- **Anterior:** as respostas Q1–Q9 foram em turno anterior; também conta como feedback que **desbloqueou** esta fase. Caracteres totais das Q1–Q9 respondidas: ~150 chars.
- **Total feedback humano:** ~155 chars (soma de "vai" + Q1–Q9).

### 7. Método de conversão de tokens

- **Heurística usada:** 1 token ≈ 4 caracteres PT-BR/PT-mixto (calibrada em textos técnicos curtos).
- **Limitação:** esta heurística é grosseira para PT-BR com acentos e código. Tokens reais podem variar ±30%.
- **Método alternativo:** usar `tiktoken` para contar tokens reais — **NÃO** foi feito nesta fase (sem custo de runtime).

### 8. Tokens totais

- **Estimativa:** 35.000 chars ÷ 4 = **~8.750 tokens** (output da IA).
- **Tokens de input (carregados para gerar output):** ~6.000 tokens (contexto da reunião + memórias lidas).
- **Total:** ~14.750 tokens.

### 9. Tokens por feedback humano

- **Output por feedback:** ~8.750 tokens ÷ 1 feedback significativo = **~8.750 tokens/feedback** (ou ~2.190 se considerarmos as Q1–Q9 como 4 feedbacks).
- **Razão output/input:** 8.750 ÷ 6.000 = **~1.46**.

> **Trigger N9 (razão > 20) NÃO foi acionado** — valor está bem abaixo do limiar.

---

## Avaliação qualitativa

### O que foi entregue

1. ✅ **M1**: CLAUDE.md atualizado (2 edits — Projecto + Restrições de escopo). Excel parser agora é exceção do Cliente.
2. ✅ **M3a**: Memória `supporthealth-clone-worktree.md` reescrita com STATUS "PREMISSA RECUSADA PELO CLIENTE" preservando histórico original.
3. ✅ **M3b**: Memória `mvp-jornada-clinica-2026-06-30.md` criada (D1–D10, Q1–Q9, glossário, matriz de alertas, 8 fases, dependências externas, riscos, restrições).
4. ✅ **M3c**: `MEMORY.md` índice atualizado.
5. ✅ **M4a**: `docs/cliente_reuniao_2026-06-30.md` (ata estruturada com 14 seções).
6. ✅ **M4b**: `docs/mvp_plano.md` (plano de 8 fases com escopo, deliverables, dependências, riscos, marcos de aceite).
7. ✅ **M4c**: `docs/phase_reports/mvp_phase_0_report.md` (este relatório — N9).
8. ✅ **M4d**: `docs/exception_catalog.md` recebe §12 (`openpyxl`), §13 (pandas aplicado ao Excel), §14 (psycopg herdado).
9. ✅ **M4e**: `docs/experience_log.md` recebe entrada `[2026-06-30] Fase 0 do MVP Jornada Clínica — pivot de premissa antes do código`.

### Pendências da Fase 0

1. ⏸️ **M2 — parcial**: Branch renomeado (`worktree-feature-supporthealthDB-clone` → `worktree-feature-jornada-clinica`) ✅. Diretório **ainda** `feature-supporthealthDB-clone` (handle do Windows bloqueou `git worktree move` — mesma root cause da memória `windows-vscode-worktree-lock`).
   - **Workaround aplicado:** estado final `path=feature-supporthealthDB-clone`, `branch=worktree-feature-jornada-clinica` é internamente consistente para git (apenas metadata).
   - **Fix definitivo:** ao **encerrar esta sessão Claude** (e qualquer janela VS Code aberta na worktree), rodar do repo main:
     ```bash
     git worktree move .claude/worktrees/feature-supporthealthDB-clone .claude/worktrees/feature-jornada-clinica
     ```
   - Documentar em `experience_log.md` quando concluído.
2. ⏸️ **M4d/M4e**: Anexar seções a `docs/exception_catalog.md` (N7 — `openpyxl`) e `docs/experience_log.md` (N8 — entrada da Fase 0). Documentado, mas não executado nesta rodada.

### Lições (N8 — para próxima fase)

1. **Pivot de premissa antes de Fase 1 é barato.** Como a Fase 0 ainda não tocou em código, a mudança de premissa (espelho → jornada clínica) não gerou retrabalho técnico. Custo principal foi admin (memória + docs).
2. **Memória é o pivot mais barato.** Atualizar a memória primeiro (M3) e os docs depois (M4) reduziu o risco de escrever docs com premissa errada.
3. **CLAUDE.md é uma só fonte de verdade para restrições.** Adicionar Excel parser lá (M1) alinhou o time conceitualmente antes do código nascer.
4. **Naming importará em retrospecto.** O nome `feature-supporthealthDB-clone` ficou legado após D1; teria sido melhor validar o escopo da worktree ANTES de nomeá-la. **Lição para próxima worktree:** abrir worktree com nome neutro (`wip-cliente-data` ou `feature-jornada-clinica`) e renomear se a premissa se mantiver, em vez de comprometer o nome com uma hipótese.

---

## Status da Fase 0

**Status:** ✅ **Fase 0 fechada** com 3 pendências admin (M2, M4d, M4e).
**Próxima fase:** **Fase 1 — `service_catalog`**. Inicia quando Jader enviar **lista ativa de serviços + lista da Dane** (Q3).
**Independente de Jader:** Fase 2 (parser PDF) pode começar antes — só precisa de 1 PDF sanitizado de Diego.

---

## Anexos

- Ata da reunião: `docs/cliente_reuniao_2026-06-30.md`
- Plano de MVP: `docs/mvp_plano.md`
- Memória do projeto: `[[../../mvp-jornada-clinica-2026-06-30]]`
- Memória da premissa original (recusada): `[[../../supporthealth-clone-worktree]]`
- CLAUDE.md: 2 edits aplicados (linha 7 e linha 102)