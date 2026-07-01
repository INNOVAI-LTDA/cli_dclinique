# Ata da Reunião de Controle — Briefing 2026-07-01

> Documento curto com 10 pontos derivados da conversa Diego + Jader em
> 2026-07-01. Complementa `docs/cliente_reuniao_2026-06-30.md` (ata
> longa da reunião inicial de escopo); aqui ficam apenas os pivots e
> decisões operacionais da Fase 2.5.

**Data:** 2026-07-01
**Participantes:** Diego Duarte Menescal, Jader Braz
**Tema:** Briefing sobre `expected_appointments` + descarte de `budget_id`

---

## 1. `budget_id` (`orc_new_NNN`) descartado

**Decisão:** coluna `budget_code` permanece nullable em
`EXPECTED_SCHEMAS` (não DROP COLUMN), mas **nenhum fluxo** mais
persiste valor sintético. PDF wizard (Fase 2), cadastro manual da
Ficha, `src/csv_importer/*` e demais pontos de entrada passam a
gravar `NULL` em `budget_code`. Valores legados em snapshots
pre-Fase-2.5 permanecem válidos. DROP COLUMN pode acontecer em
migration futura, sem quebra de leitura.

**Implicação:** tabela de orçamento sintético some do processo.
Toda leitura subsequente deve ignorar a coluna (ou tratá-la como
opaca).

## 2. Plano de frequência esperada materializado em `expected_appointments`

**Decisão:** PDF wizard gera **N rows** em `expected_appointments` por
item: 1 row por sessão esperada, com `expected_date = issue_date +
(i-1) × periodicity_days`. Tabela substitui o conceito de "vetor
estático gerado uma vez" previsto para Fase 4 — agora promovido para
Fase 2.5.

**Casos cobertos:**
- Item com `sessions_expected` e `periodicity_days`: gera N rows.
- Item sem `periodicity_days` (`dose única` / sem `frequency_type`):
  gera 1 row com `expected_date = issue_date`.
- Item sem `sessions_expected`: skip (0 rows).

## 3. `data_inicio_plano` (PDF) ≠ `data_inicio_agendamento` (XLSX)

**Decisão:** manter **duas colunas distintas** no fluxo:
- `data_inicio_plano` = `treatment_plans.issue_date` (PDF, base para
  geração de `expected_date`).
- `data_inicio_agendamento` = `appointments.appointment_start` (XLSX,
  fonte da verdade operacional).

**Implicação:** o matching XLSX (Fase 3) usa as duas — `data_inicio_plano`
para o offset inicial e `data_inicio_agendamento` para o "primeiro
atendimento real" que pode ser diferente do esperado.

## 4. Lista de suspensão do wizard XLSX: `st.selectbox` único

**Decisão:** o wizard XLSX (Fase 3) usa `st.selectbox` único para
seleção de `patient_id` (com busca), em vez de `st.multiselect` ou
lista suspensa múltipla. Razão: a planilha Excel entra para atualizar
a realidade de UM paciente por vez, não múltiplos em batch.

## 5. `status` enum em `appointments.status`: `Literal`

**Decisão:** `status` declarado como `Literal[...]` (não `Enum`),
valores:

```
{"planned", "agendado", "atendido", "atrasado",
 "confirmado", "reagendado", "cancelado"}
```

Referência: matriz de decisão §9 da ata 2026-06-30 + status.Enum do
wizard XLSX (Fase 3).

## 6. Pivot do propósito do `CLAUDE.md` § Projecto

**Decisão:** `CLAUDE.md` § Projecto deve explicitar que o MAP é:
- Casca navegável Streamlit para acompanhamento de pacientes.
- **E** gerador/gestor de alertas (papel principal pós-Fase 5).

Ambos coexistem: navegação é a UX; alertas são o output primário.

## 7. Ata curta `docs/cliente_reuniao_2026-07-01.md`

**Decisão:** este documento vira referência oficial do briefing,
em paralelo à ata longa de 2026-06-30. Documentos curtos para
briefings ágeis; documentos longos para reuniões iniciais de
escopo.

## 8. Periodicidade "quinzenal" = 15 dias (não 14)

**Decisão:** PT-BR categórico: "quinzenal" = literalmente "quinze
dias", não "duas semanas". Fix aplicado em
`src/pdf_importer/frequency.py::PERIOD_DAYS["quinzenal"] = 15`.

Aplicar mesmo cuidado a "bimestral" (60 vs 61), "trimestral" (90 vs
91), "semestral" (180 vs 181) se forem adicionados.

## 9. Resumo de números

- **Tabelas:** 14 (13 antigas + `expected_appointments`).
- **Colunas novas:** 12 (todas em `expected_appointments`).
- **Colunas removidas:** 0 (`budget_code` permanece nullable).
- **Tests:** +11 (8 pure-function + 3 end-to-end).
- **Pytest:** 438/438 verde.

## 10. Próximos passos

- **Fase 2.5 (atual):** criar `expected_appointments` + parar de
  persistir `budget_code`. ✅ Concluído.
- **Fase 3 (próxima):** XLSX wizard com `st.selectbox` único +
  matching em `(patient, plan_item, data_inicio_plano)`.
- **Fase 4:** alertas com justificativa obrigatória (matriz §9 ata
  2026-06-30).
- **Fase 5:** painel de alertas + acções de classificar/ignorar.