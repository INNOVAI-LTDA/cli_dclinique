# MVP Jornada Clínica — Plano de Implementação

> ## ⚠️ RASCUNHO v0.1 — pendente de validação com Diego
>
> Este plano decorre da reunião de 2026-06-30 21:25 (Diego + Jader) — ata
> completa em `docs/cliente_reuniao_2026-06-30.md`. Decisões D1–D10 e
> respostas Q1–Q9 aplicadas na arquitetura. Mudanças pendentes devem ser
> combinadas antes de promover a versão para estável.

**Origem:** Reunião Diego + Jader em 2026-06-30 21:25 (ata em `docs/cliente_reuniao_2026-06-30.md`)
**Premissa:** Premissa original de espelho SupportHealth ([[../../supporthealth-clone-worktree]]) foi **recusada em D1**; substituída por este MVP cirúrgico.
**Worktree:** `feature-jornada-clinica` (a renomear — M2 da execução autorizada em 2026-06-30)
**Total de fases:** 8 (Fase 0 = setup; Fases 1–8 = implementação)

---

## 1. Visão geral

**Objetivo:** módulo de controle da jornada do paciente, com importação de PDFs de planos de acompanhamento, importação de relatórios Excel de agendamento, parametrização de serviços ativos e geração de alertas operacionais com justificativa obrigatória.

**Não-objetivo:** espelhar sistema atual (D1), resolver homônimos/CPF/duplicatas (§10), usar ID do orçamento como chave central (§10), automatizar remarcação externa (§10), interpretação semântica agressiva de nomenclatura (§7).

**Pilar técnico:**
- PDF continua sendo peça-chave (memória `pdf-importer-is-client-requirement`).
- **Excel parser é agora exceção do Cliente** (CLAUDE.md atualizado — M1).
- Schema v1 (11 tabelas) preservado; MVP **adiciona colunas** em `alerts` e **cria 3 tabelas novas** (`service_catalog`, `service_review_queue`, `alert_audit_log`).
- `src/data_layer/` (Postgres/CSV router) é o alvo — sem mudança de API.
- `src/core/` (Caminho B v2) fica como camada de tradução. `Deliverables` pode modelar `service_catalog` se evoluir schema.
- **N7/N8/N9 obrigatórios** (try/except PT-BR, `experience_log.md` append-only, `phase_reports/` por fase).

---

## 2. Princípios não-negociáveis

| Princípio | Descrição |
|---|---|
| **N7 — Exceção em PT-BR** | Toda chamada externa envolvida em try/except específico. Mensagem em português, log via `logging`, sem stacktrace bruto. Catálogo em `docs/exception_catalog.md`. |
| **N8 — Acumulação de experiência** | Todo teste (passou ou falhou) vira entrada em `docs/experience_log.md` (append-only). A IA lê o log **inteiro** no início de cada fase. |
| **N9 — Auditoria de tokens** | Cada fim de fase produz `docs/phase_reports/phase_N_report.md` (ou `mvp_phase_N_report.md` para o MVP) com 9 métricas. Razão output/input > 20 = trigger para simplificar próxima fase. |
| **LGPD** | Dados reais do Cliente NUNCA são commitados. Dumps em `data/new/` (gitignored). |
| **CSV header-only** | CSVs em `data/csv/` permanecem header-only após carga (convenção preservada). |
| **Justificativa bloqueante** | Alerta só sai de `open` para `closed` com `justification_text` preenchida. |

---

## 3. Fases (8 total)

### Fase 0 — Setup (esta fase)

**Escopo:** transcrição estruturada da ata + plano MVP + 4 docs obrigatórios N7/N8/N9 + edição em CLAUDE.md + atualização de memória.

**Deliverables (todos entregues nesta execução):**
- `docs/cliente_reuniao_2026-06-30.md` (ata estruturada)
- `docs/mvp_plano.md` (este arquivo)
- `docs/exception_catalog.md` (N7 — seção nova sobre `openpyxl`)
- `docs/experience_log.md` (N8 — entrada inicial)
- `docs/phase_reports/mvp_phase_0_report.md` (N9 — relatório Fase 0)
- `CLAUDE.md` (Edit — parser Excel agora é exceção)
- Memória: `supporthealth-clone-worktree.md` (marcada como pivoted)
- Memória: `mvp-jornada-clinica-2026-06-30.md` (criada)

**Dependências externas:** nenhuma.

### Fase 1 — `service_catalog`

**Escopo:** tabela nova + import CSV + classificação (active/rare/obsolete).

**Deliverables:**
- Schema DDL: `service_catalog(service_code PK, name, classification, category, default_periodicity_days, created_at)`.
- Schema DDL: `service_review_queue(id PK, service_name, source, first_seen_at)`.
- `src/data_layer/schema.py` (adicionar ao `EXPECTED_SCHEMAS`).
- CSV header em `data/csv/service_catalog.csv` e `data/csv/service_review_queue.csv` (header-only).
- `scripts/import_service_catalog.py --csv=...` (CLI, header validation, dry-run, idempotente).
- UI: `src/pages/catalogo_servicos.py` (visualização simples; sem CRUD — Q7).
- `tests/test_service_catalog.py` (cobre N7 + edge cases).

**Dependências externas:**
- Jader envia **lista ativa de serviços** + **lista usada pela Dane** (em `.xlsx` ou CSV).

**Riscos:** divergência entre "lista ativa" e "lista da Dane"; nomes sem categoria definida. Mitigação: classificação default = `active` + fila de revisão para nomes ambíguos.

### Fase 2 — PDF importer estendido

**Escopo:** extrair do PDF a quantidade por item + frequência (frequency_text + frequency_type derivado: Semanal→7, Quinzenal→14, Mensal→30) + split por vírgula em descrições compostas.

**Deliverables:**
- `src/pdf_importer/quantity.py` (extrai "X sessões", "X aplicações" etc.).
- `src/pdf_importer/frequency.py` (deriva `frequency_type` + `periodicity_days`).
- `src/pdf_importer/split.py` (split por vírgula em descrições compostas — D5).
- Estender `data/import_zones/default.json` se necessário.
- Testes: `tests/test_pdf_quantity.py`, `tests/test_pdf_frequency.py`, `tests/test_pdf_split.py`.

**Dependências externas:**
- Diego valida parser em **1 PDF real** (sanitizado — sem PII).

**Riscos:** layout do PDF pode variar entre clínicas. Mitigação: zone-based parser já presente; tentar layout A, cair para B com warning; linha cai em fila `pdf_review_queue` se nenhum layout casar.

**Não-escopo desta fase:** extração de data de início do plano (já temos data do rodapé — Q4). Estender parser para isso seria trabalho sem ganho.

### Fase 3 — `excel_importer`

**Escopo:** parser para `.xlsx` de agendamentos, single layout (Q2 confirmado).

**Deliverables:**
- `src/excel_importer/__init__.py`
- `src/excel_importer/schema.py` (1 schema fixo; colunas canônicas inferidas: `Paciente`, `Data`, `Serviço`, `Status`, `Profissional`, `Observação` — **a confirmar com 1 amostra de Jader**).
- `src/excel_importer/parse.py` (lê `.xlsx` via `openpyxl`, normaliza colunas, split por vírgula em serviço se multi-valor).
- `src/excel_importer/persist.py` (resolve paciente por `normalize_name`; insere em `appointments` + `appointment_items`).
- `scripts/import_excel_schedule.py --xlsx=...` (CLI, dry-run, idempotente por `appointment_code`).
- `tests/test_excel_importer.py` (cobre N7 + edge cases).

**Dependências externas:**
- Jader envia **1 amostra Excel** + **dicionário de colunas** (nomes exatos).

**Riscos:** colunas do Excel com nomes diferentes do esperado; status fora do conjunto `{Agendado, Atendido, Cancelado, Atrasado}`. Mitigação: schema validation report no dry-run; status fora do conjunto vai para `service_review_queue`.

### Fase 4 — `jornada` (expected_dates rolantes)

**Escopo:** gerar e manter `expected_appointments(patient_id, plan_item_id, expected_date, source, computed_at)`, com regra rolante do Q9.

**Deliverables:**
- `src/jornada/__init__.py`
- `src/jornada/expected_dates.py` (função `compute_rolling_expected_date(patient_id, plan_item_id, today)`).
- `src/jornada/persistence.py` (CRUD em `expected_appointments`).
- Schema DDL: `expected_appointments(expected_id PK, patient_id FK, plan_item_id FK, expected_date, source, computed_at)`.
- Testes: `tests/test_jornada_rolling.py` (cobre edge case: antecipação, lacuna, mudança de periodicidade).

**Regra rolante (Q9):**
```
estado inicial:  expected_date_0 = data do rodapé do PDF
sessão real #1:  next_expected = last_real_date + periodicity
                 (recalcula; "anda pra frente" mesmo se antecipada)
alerta:          dispara a partir do último next_expected
```

**Dependências externas:** Fases 1+2+3 (catálogo + PDF + Excel).

**Riscos:** corrida entre import Excel e recálculo de `expected_date` (transient inconsistency). Mitigação: `computed_at` permite reprocessar; recálculo é idempotente.

### Fase 5 — Geração de `alerts`

**Escopo:** cruzar `expected_appointments` × `appointments` reais → gerar `alerts` com `severity` + `owner_role`.

**Deliverables:**
- Schema DDL: `alerts` extend (adicionar colunas — ver §5 abaixo).
- `src/alerts/__init__.py`
- `src/alerts/generator.py` (`generate_alerts_from_jornada(jornada_df, appointments_df, today)`).
- `src/alerts/severity.py` (regras de classificação — matriz do §9 da ata).
- Testes: `tests/test_alerts_generator.py`.

**Dependências externas:** Fases 3+4.

**Riscos:** duplicação de alertas entre reloads (mesma ausência gera alerta novo). Mitigação: idempotência por `(patient_id, plan_item_id, expected_date, status)` — se já existe `alert` aberto para essa chave, atualizar `last_checked_at` em vez de criar novo.

### Fase 6 — UI de alertas com justificativa obrigatória

**Escopo:** tela/painel onde a equipe vê alertas, justifica, fecha. **Workflow bloqueante**: `closed` exige `justification_text`.

**Deliverables:**
- `src/alerts/justification.py` (validação: texto não-vazio, ≥10 chars, contém tag de categoria — viagem / remarcação / erro / outro).
- `src/alerts/workflow.py` (state machine: `open → justified → closed`, com `closed → reopened`).
- `src/alerts/audit.py` (escreve em `alert_audit_log` — append-only).
- `src/pages/alertas.py` (estender — adicionar botões "Justificar", "Reabrir", "Ver histórico").
- Schema DDL: `alert_audit_log(audit_id PK, alert_id FK, action, actor, timestamp, payload)`.
- `tests/test_alerts_justification.py`, `tests/test_alerts_workflow.py`.

**Dependências externas:** Fase 5.

**Riscos:** UI fica complexa com 4 estados visuais. Mitigação: agrupar por status (Abertos / Justificados / Fechados / Reabertos) em tabs.

### Fase 7 — Carga histórica + calibragem

**Escopo:** ingestão controlada de PDFs jan/2026→hoje (lotes) + Excel do mesmo período. Modo "soft" para alertas (não bloqueiam workflow na primeira leva).

**Deliverables:**
- `scripts/import_pdf_history.py --window=2026-01-01:2026-06-30 --batch-size=50`.
- `scripts/import_excel_schedule.py --window=2026-01-01:2026-06-30`.
- Hash de arquivo (SHA-256) para idempotência de re-import.
- Modo soft: flag `--dry-run-alerts` (gera CSV de alertas sem inserir no DB).
- Relatório de calibragem: quantos alertas por severidade; ajuste de threshold por categoria.

**Dependências externas:**
- Jader envia PDFs jan/2026→hoje (lotes).
- Jader envia Excel do mesmo período.

**Riscos:** muitos alertas gerados (time ignora o sistema — risco do §12 da ata). Mitigação: alertas em modo "soft" durante calibragem; só ativam workflow bloqueante após aprovação de Diego.

### Fase 8 — Recorrência semanal

**Escopo:** job semanal (cron / Streamlit button) que importa Excel + recalcula `expected_date` + gera alertas.

**Deliverables:**
- `scripts/run_weekly_import.py` (orquestra Fase 3 + Fase 4 + Fase 5).
- UI: `src/pages/atualizacao_dados.py` (botão "Rodar importação semanal").
- Relatório semanal: `logs/weekly_import_<date>.log` + `logs/weekly_import_<date>.json`.

**Dependências externas:** Fases 1–7 calibradas.

**Riscos:** Job roda em horário de pico. Mitigação: agendamento para domingo 02:00 + lock distribuído.

---

## 4. Schema novo (resumo)

**Colunas adicionadas em `alerts`:**
```sql
ALTER TABLE alerts ADD COLUMN severity TEXT CHECK (severity IN ('high', 'medium', 'low'));
ALTER TABLE alerts ADD COLUMN owner_role TEXT CHECK (owner_role IN ('enfermagem', 'agendamento', 'admin'));
ALTER TABLE alerts ADD COLUMN status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'justified', 'closed', 'reopened'));
ALTER TABLE alerts ADD COLUMN justification_text TEXT;
ALTER TABLE alerts ADD COLUMN justification_by TEXT;
ALTER TABLE alerts ADD COLUMN justification_at TIMESTAMP;
ALTER TABLE alerts ADD COLUMN reopen_reason TEXT;
CREATE INDEX idx_alerts_severity_status ON alerts(severity, status);
```

**Tabelas novas:**
```sql
CREATE TABLE service_catalog (
  service_code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  classification TEXT NOT NULL CHECK (classification IN ('active', 'rare', 'obsolete')),
  category TEXT CHECK (category IN ('injectable', 'professional', 'other')),
  default_periodicity_days INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE service_review_queue (
  id TEXT PRIMARY KEY,
  service_name TEXT NOT NULL,
  source TEXT,
  first_seen_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE alert_audit_log (
  audit_id TEXT PRIMARY KEY,
  alert_id TEXT NOT NULL,
  action TEXT NOT NULL,
  actor TEXT,
  timestamp TIMESTAMP DEFAULT NOW(),
  payload TEXT
);

CREATE TABLE expected_appointments (
  expected_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  plan_item_id TEXT NOT NULL,
  expected_date TIMESTAMP NOT NULL,
  source TEXT,
  computed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_expected_patient_item ON expected_appointments(patient_id, plan_item_id);
CREATE INDEX idx_expected_date ON expected_appointments(expected_date);
```

---

## 5. Dependências externas por fase (resumo)

| Fase | Jader | Diego | Equipe clínica |
|---|---|---|---|
| 0 | — | — | — |
| 1 | lista ativa + lista da Dane | — | — |
| 2 | — | 1 PDF sanitizado para validação | — |
| 3 | 1 amostra Excel + dicionário | — | — |
| 4 | — | — | — |
| 5 | — | — | — |
| 6 | — | — | feedback de UX |
| 7 | PDFs jan/2026→hoje + Excel do período | acompanhar calibragem | treinar no fluxo |
| 8 | Excel semanal | — | usar fluxo |

---

## 6. Riscos macro (consolidados)

| # | Risco | Mitigação primária | Fase que aborda |
|---|---|---|---|
| R1 | PDF layout instável | Parser com múltiplos layouts + fila de revisão | 2 |
| R2 | Nomenclatura inconsistente | Whitelist ativa + `service_review_queue` | 1, 3 |
| R3 | Status manual não atualizado | Alertas cobram atualização (§9 ata) | 5, 6 |
| R4 | Mudança de nome do paciente | Aceito como limitação MVP | (pós-MVP) |
| R5 | Carga histórica com sobreposição | Hash de arquivo + janela de datas | 7 |
| R6 | Excesso de alertas iniciais | Modo "soft" na calibragem + separar severidade | 5, 6, 7 |
| R7 | Race entre Excel import e recálculo | `computed_at` + recálculo idempotente | 4 |
| R8 | UI complexa com 4 estados | Tabs por status | 6 |

---

## 7. Marcos de aceite por fase (resumo)

| Fase | Marco de aceite |
|---|---|
| 1 | `import_service_catalog.py` roda idempotentemente em CSV de 200 serviços; `tests/test_service_catalog.py` 100% |
| 2 | Parser extrai quantidade + frequência de 1 PDF real (sanitizado); `tests/test_pdf_*.py` 100% |
| 3 | `import_excel_schedule.py` importa 200 linhas Excel; status fora do conjunto vai para `service_review_queue`; `tests/test_excel_importer.py` 100% |
| 4 | `compute_rolling_expected_date` testada com 5 cenários (sem comparecimento, 1 comparecimento, antecipação, mudança de periodicidade, sessão fora de ordem); `tests/test_jornada_rolling.py` 100% |
| 5 | `generate_alerts_from_jornada` produz alertas consistentes com matriz do §9; `tests/test_alerts_generator.py` 100% |
| 6 | UI permite justificar alerta; `closed` exige `justification_text` ≥10 chars; `alert_audit_log` registra cada transição; `tests/test_alerts_*.py` 100% |
| 7 | Carga histórica jan/2026→hoje concluída; relatório de calibragem gerado; alertas revisados com Diego |
| 8 | Job semanal roda 4 semanas consecutivas sem erro; alertas gerados em volume estável |

---

## 8. Política de execução

- **Quem roda os testes:** o usuário (`pwsh scripts/run_core_tests.ps1`). A IA **não** roda os testes pelo usuário.
- **Em caso de falha:** o usuário cola o log (`logs/test_core_<ts>.log` ou `.json`) na conversa; IA diagnostica.
- **LGPD:** dados reais do Cliente NUNCA são commitados. Fica em `data/new/` (gitignored). Para Fase 2 (parser PDF), usar PDF sintético até Jader enviar 1 real.
- **Naming:** worktree será renomeada de `feature-supporthealthDB-clone` → `feature-jornada-clinica` em M2 (TBD).