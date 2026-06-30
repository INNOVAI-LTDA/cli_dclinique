# Modelo de Dados — MAP / SupportHealth

> **Status:** Proposta (junho/2026) — não implementado.
> **Decisão pendente:** caminho A (apenas ajustes pontuais), B (refactor incremental) ou C (refactor big-bang). Ver §11.
> **Substitui (em caso de aprovação):** o schema procedural atual de 11 tabelas em `src/schemas.py:EXPECTED_SCHEMAS` (versão 1).
> **Relacionado:** `data/reports/relatorio_estrutura_dados_alertas_frequencia_2026-06-23.md` (motivação cliente) e `CLAUDE.md` (escopo do projeto).

---

## 1. Motivação

O schema atual do MAP é **procedural** — modela o fluxo clínico (Plano → Itens → Execução) e a operação do dia-a-dia (Agendamentos → Status). Isso funciona para a casca navegável, mas tem três limitações concretas que ficaram evidentes ao tentar implementar a regra de "relatório de frequência → alerta" para o Mapa de Decisão:

1. **Polimorfismo implícito** — `treatment_plans` e `treatment_plan_items` têm o mesmo `patient_id` e `budget_code`; a fronteira entre "plano" e "item" mora só no status do `plan_id` pai, não na forma da linha.
2. **Acoplamento forte a uma clínica** — não há `organization_id` em lugar nenhum; multi-clínica exigiria reprojetar tudo.
3. **Catálogo de procedimentos duplicado** — `frequency_text` e `frequency_type` ficam em `treatment_plan_items` por cliente, em vez de viverem no catálogo de Deliverables (que é compartilhado).

A proposta abaixo é um **modelo de entidades + associações** inspirado em como CRMs/ERPs/sistemas clínicos maduros (Epic, Cerner, Salesforce Health Cloud) modelam o domínio.

---

## 2. Princípios

| # | Princípio | Consequência prática |
|---|---|---|
| P1 | **4 substantivos, N verbos** | 4 entidades (Organization, Users, Deliverables, Clients) + N associações explícitas. |
| P2 | **Catálogo separado de operação** | `deliverables` (catálogo) ≠ `client_deliverables` (operação). A "Injetável EV Semanal" vive no catálogo; a "Maria comprou Injetável EV" vive na operação. |
| P3 | **Polimorfismo via `tipo` + `metadata` jsonb** | `deliverables.tipo` enum + `metadata` jsonb carrega campos específicos. Evita explosão de tabelas. |
| P4 | **Hierarquia via self-FK** | Plano → Item é `parent_deliverable_id` (self-FK). Sem tabela intermediária. |
| P5 | **Audit trail em tudo** | `criado_em`, `atualizado_em`, `ativo`, `deleted_at` em toda tabela. |
| P6 | **Multi-tenant gratuito** | `organization_id` em todas as entidades e associações. |
| P7 | **Identidade via natural-key + surrogate** | `id` (surrogate) + `cpf`/`cnpj`/`codigo` (natural). |
| P8 | **Status como atributo da associação** | Não há tabela `status`; cada associação carrega o seu (Plano tem `status`, Sessão tem `status`, Alerta tem `status`). |
| P9 | **Histórico temporal é first-class** | `weight_records`, `satisfaction_records` são associações com timestamp, não snapshots. |
| P10 | **Dados sensíveis separados** | LGPD gate (ver `DEPLOY.md`): campos sensíveis (`cpf`, `telefone`, `email`) podem ser mascarados em logs/exports. |

---

## 3. As 4 Entidades Fundamentais

### 3.1. `organizations` — A Clínica

| Coluna | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `id` | uuid / bigserial | sim | PK |
| `nome` | text | sim | Razão social ou nome fantasia |
| `cnpj` | text | sim | Validado por DV |
| `endereco` | text | não | Texto livre no MAP; pode virar jsonb depois |
| `telefone` | text | não | Validado por regex BR |
| `url` | text | não | Site institucional |
| `config` | jsonb | não | Preferências locais (timezone, idioma, templates) |
| `ativo` | boolean | sim (default true) | Soft delete |
| `criado_em` | timestamptz | sim (default now()) | |
| `atualizado_em` | timestamptz | sim (default now()) | |
| `deleted_at` | timestamptz nullable | não | Audit |

No MAP, há **1 registro** (DClinique). No SupportHealth, pode haver N.

### 3.2. `users` — Provider + Admin (STI por `tipo`)

| Coluna | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `id` | uuid / bigserial | sim | PK |
| `tipo` | enum [Provider, Admin] | sim | STI — sem tabela polimórfica |
| `nome` | text | sim | |
| `cpf` | text | sim | Validado por DV; **natural-key** |
| `registro_especial` | text | não | CRM, COREN, CRN, CRO, etc. |
| `tipo_registro` | enum [CRM, COREN, CRN, CRO, Outro] | não | Para validação cruzada |
| `telefone` | text | não | |
| `email` | text | não | |
| `funcao` | text | não | "Nutróloga", "Enfermeira", "Recepção" |
| `organization_id` | FK → organizations | sim | Provider/Admin pertence a uma clínica |
| `ativo` | boolean | sim | |
| `criado_em` | timestamptz | sim | |
| `atualizado_em` | timestamptz | sim | |
| `deleted_at` | timestamptz nullable | não | |

**Mapeamento dos 5 profissionais do `Agendamentos.csv` (worktree report-frequencia-alertas):**
- Dayane Junqueira Vilela (Nutróloga) → Provider
- Deborah Daniele Ribeiro (Enfermeira) → Provider
- Livia Negreiro Leao → Provider
- Madalena Costa → Provider
- Elika Almeida Cunha → Provider
- Morena Gontijo De Araujo (Recepção, "Agendado por") → Admin

**Por que `password_hash` não está aqui:** fora do escopo do MAP (Cliente confirmou que login próprio não é prioridade). Campo fica reservado para evolução futura.

### 3.3. `deliverables` — Catálogo de produtos/serviços

| Coluna | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `id` | uuid / bigserial | sim | PK |
| `titulo` | text | sim | Ex.: "Injetáveis EV", "Medicamento Manipulado Emagrecimento" |
| `tipo` | enum | sim | Ver §3.3.1 |
| `descricao` | text | sim | Forma de aplicação, instruções, observações |
| `parent_deliverable_id` | FK → deliverables (self) nullable | não | Hierarquia (Plano → Item) |
| `organization_id` | FK → organizations | sim | Catálogo por clínica |
| `frequencia_tipo` | enum [Diário, Semanal, Quinzenal, Mensal, Única, Outro] nullable | não | Fica no catálogo, não no cliente |
| `frequencia_texto` | text nullable | não | Texto livre complementar |
| `metadata` | jsonb | não | Campos específicos por `tipo` (ver §3.3.2) |
| `ativo` | boolean | sim | |
| `criado_em` | timestamptz | sim | |
| `atualizado_em` | timestamptz | sim | |
| `deleted_at` | timestamptz nullable | não | |

#### 3.3.1. Enum `deliverables.tipo`

Valores identificados a partir do `Relatorio de frequencia.csv` + do `pdf_importer/parse.py`:

| `tipo` | Descrição | `metadata` exemplo |
|---|---|---|
| `Plano de Tratamento` | Container de itens | `{"duracao_padrao_dias": 90}` |
| `Injetável` | Aplicação EV/IM/SC | `{"via": "EV", "dose_ml": 5, "aplicador_id": 1}` |
| `Medicamento Manipulado` | Fórmula manipulada | `{"formula_id": "...", "posologia": "1x/dia"}` |
| `Implante` | Implante subcutâneo | `{"area": "glúteo", "duracao_meses": 6}` |
| `Consulta` | Sessão avulsa com profissional | `{"duracao_min": 60}` |
| `Acompanhamento` | Acompanhamento contínuo (nutrição, etc.) | `{"profissional_tipo": "Nutricionista"}` |
| `Exame` | Exame laboratorial | `{"laboratorio": "..."}` |
| `Meta` | Meta clínica (peso, IMC) | `{"valor_inicial": 82, "valor_target": 74, "unidade": "kg"}` |

#### 3.3.2. Por que `metadata` jsonb em vez de colunas específicas

| Alternativa | Prós | Contras |
|---|---|---|
| Colunas específicas por `tipo` (`dose_ml`, `posologia`, `duracao_min`, ...) | Validação no DB | Explosão de colunas nullable; migração cara a cada novo `tipo` |
| **Tabela polimórfica `deliverable_<tipo>`** (`deliverable_injetavel`, `deliverable_medicamento`, ...) | Validação no DB; queries específicas | N tabelas; joins por `tipo` |
| **`metadata` jsonb** (proposta) | Um schema; flexível | Validação no app, não no DB |

Para o MAP (8 tipos × ~3 campos cada), **jsonb é o sweet spot**. O Postgres tem `jsonb_typeof` e validação parcial via `CHECK (jsonb_typeof(metadata->>'dose_ml') = 'number')` se necessário.

### 3.4. `clients` — Pacientes

| Coluna | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `id` | uuid / bigserial | sim | PK |
| `nome` | text | sim | Nome completo |
| `cpf` | text | sim | **Natural-key** (validado por DV) |
| `rg` | text | não | |
| `data_nascimento` | date | sim | Substitui o `age` atual (mais preciso) |
| `telefone` | text | não | |
| `endereco` | text | não | |
| `email` | text | não | |
| `origem` | enum [Manual, PDF, CSV, SupportHealth, Indicação, Instagram, Outro] | não | Lead source |
| `consentimento_lgpd` | boolean | sim (default false) | Gate do `DEPLOY.md` |
| `consentimento_lgpd_em` | timestamptz nullable | não | Quando foi concedido |
| `observacoes` | text | não | Anotações livres |
| `created_via` | enum [manual, pdf_import, csv_import, supporthealth_sync] | sim | Audit de proveniência |
| `ativo` | boolean | sim | |
| `criado_em` | timestamptz | sim | |
| `atualizado_em` | timestamptz | sim | |
| `deleted_at` | timestamptz nullable | não | |

**Substitui:** a tabela `patients` atual. Campo `age` sai (a idade passa a ser `today - data_nascimento` calculado).

---

## 4. Associações (o coração do sistema)

### 4.1. `organization_users` — Quem trabalha onde

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `organization_id` | FK → organizations | |
| `user_id` | FK → users | |
| `cargo` | text | "Sócia", "Contratada", "Recepção" |
| `data_inicio` | date | |
| `data_fim` | date nullable | Vigência |
| `criado_em` | timestamptz | |
| `atualizado_em` | timestamptz | |

Permite que um Provider atenda em N clínicas (futuro multi-tenant).

### 4.2. `client_deliverables` — **A TABELA CENTRAL**

Esta tabela **substitui `treatment_plans` + `treatment_plan_items` + `execution_summary`** por uma única estrutura polimórfica. A sacada: **um Plano é um `client_deliverable` filho de nenhum, e cada Item é um `client_deliverable` filho do Plano**. Árvore self-referential numa única tabela.

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_id` | FK → clients | |
| `deliverable_id` | FK → deliverables | O item do catálogo (Plano OU Item) |
| `parent_client_deliverable_id` | FK → client_deliverables (self) nullable | Se for item-de-plano, aponta pro plano |
| `organization_id` | FK → organizations | |
| `status` | enum [Ativo, Pausado, Aguardando, Finalizado, Cancelado, Não iniciado] | Lifecycle do vínculo |
| `orcamento` | text | Código do orçamento (vem do CSV/SupportHealth) |
| `is_renovacao` | boolean | |
| `data_inicio` | date | |
| `data_fim` | date nullable | |
| `sessions_expected` | int | Vem do Deliverable + janela |
| `sessions_completed` | int default 0 | Mantido por trigger ou pela sessão |
| `sessions_remaining` | int | Gerado = expected - completed |
| `metadata` | jsonb | Campos específicos do caso |
| `criado_em` | timestamptz | |
| `atualizado_em` | timestamptz | |
| `deleted_at` | timestamptz nullable | |

**Exemplo real (Kelly Cristina do `Relatorio de frequencia.csv`):**

```
client_deliverable #1 (Plano)
  ├── deliverable_id = D_PLANO_KELLY (Plano de Tratamento)
  ├── parent_client_deliverable_id = NULL
  ├── orcamento = "4622306"
  ├── status = Ativo
  └── sessions_expected = 12

client_deliverable #2 (Item: Injetáveis EV)
  ├── deliverable_id = D_INJ_EV (Injetável, frequencia_tipo=Semanal)
  ├── parent_client_deliverable_id = #1
  ├── sessions_expected = 4
  └── sessions_completed = 1

client_deliverable #3 (Item: Acompanhamento)
  ├── deliverable_id = D_ACOMP (Acompanhamento)
  ├── parent_client_deliverable_id = #1
  ├── sessions_expected = 2
  └── sessions_completed = 0
```

**Resolve N2 do CSV (`Orçamento` multi-valor):** cada `client_session` é N:N com `client_deliverables` via `client_session_items` (§4.3).

### 4.3. `client_sessions` — Agendamentos / Consultas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_id` | FK → clients | |
| `provider_id` | FK → users (tipo=Provider) | |
| `agendado_por_id` | FK → users (tipo=Admin) nullable | Quem registrou |
| `organization_id` | FK → organizations | |
| `session_start` | timestamptz | |
| `session_end` | timestamptz | |
| `status` | enum [Agendado, Confirmado, Atendido, Atrasado, Cancelado, Reagendado] | **Mesma enum do `appointments.status` atual** |
| `session_type` | text | Texto livre ("9º Sessão EV", "Consulta Nutróloga NOVA/AVULSA") |
| `codigo_origem` | text | Código do CSV/SupportHealth (audit) |
| `metadata` | jsonb | Campos extras |
| `criado_em` | timestamptz | |
| `atualizado_em` | timestamptz | |
| `deleted_at` | timestamptz nullable | |

#### 4.3.1. `client_session_items` — N:N entre sessão e deliverables

Resolve o caso "uma sessão cobre múltiplos itens do plano":

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_session_id` | FK → client_sessions | |
| `client_deliverable_id` | FK → client_deliverables | O item consumido |
| `status` | enum (mesmo da sessão) | Status desse item específico |
| `criado_em` | timestamptz | |

### 4.4. `deliverable_hierarchy` (auto-FK em `deliverables`)

Modelado via `parent_deliverable_id` em `deliverables` (ver §3.3). Sem tabela intermediária.

### 4.5. `client_alerts` — Alertas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_id` | FK → clients | |
| `plan_id` | FK → client_deliverables nullable | Alerta de plano |
| `session_id` | FK → client_sessions nullable | Alerta de sessão |
| `category` | enum [Enfermagem, Médica, Comercial, Nutrição, Frequência, Sistema] | **+ "Frequência"** vs schema atual |
| `alert_type` | text | |
| `description` | text | |
| `priority` | enum [Alta, Média, Baixa] | |
| `status` | enum [Aberto, Em análise, Resolvido] | |
| `created_at` | timestamptz | |
| `resolved_at` | timestamptz nullable | |
| `comment` | text | |

**Mudança vs. atual:** `category` ganha o valor `Frequência` para alertas automáticos de comparecimento. `plan_id` agora aponta para um `client_deliverable` (que pode ser o Plano ou um Item).

### 4.6. `satisfaction_records` — NPS / Satisfação

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_id` | FK → clients | |
| `client_deliverable_id` | FK → client_deliverables nullable | Vínculo ao plano |
| `date` | timestamptz | |
| `satisfaction_status` | enum [Satisfeito, Neutro, Insatisfeito, Não informado] | |
| `score` | int (0-10) | |
| `notes` | text | |
| `criado_em` | timestamptz | |

### 4.7. `weight_records` — Medições de peso

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid / bigserial | PK |
| `client_id` | FK → clients | |
| `client_deliverable_id` | FK → client_deliverables nullable | Vinculado à Meta (Plano de peso) |
| `measurement_date` | timestamptz | |
| `weight` | numeric(5,2) | |
| `source` | text | "Dados manuais", "PDF", "API SupportHealth" |
| `notes` | text | |
| `criado_em` | timestamptz | |

### 4.8. `data_quality_issues` — Auditoria de dados

Inalterado em forma (já existe no schema atual). Ganha `client_id` como FK explícita (hoje é texto livre).

---

## 5. Modelo relacional (diagrama textual)

```
organizations (1) ─────────< organization_users >────────── (1) users
                                                          (tipo: Provider | Admin)
                                                               │
                                                               │ provider_id
                                                               │
clients (1) ─────────< client_alerts                        client_sessions
   │                       ▲                                    │
   │                       └── plan_id (FK client_deliverables) │
   │                                                            │
   ├──< satisfaction_records                                   ├──< client_session_items
   ├──< weight_records                                          │         │
   │                                                             │         │
   └──< client_deliverables (a tabela central) ◄─────────────────┘         │
              │                                                            │
              │ deliverable_id                                             │
              ▼                                                            │
       deliverables (catálogo, self-FK via parent_deliverable_id)         │
              │                                                            │
              └── hierarchy: Plano → Itens → Sub-itens (se houver)        │
                                                                           │
       (sessions_expected / completed / remaining) <── trigger ou app ────┘
```

---

## 6. Schema SQL (Postgres DDL de referência)

> **Status:** referência, **não executar automaticamente**. A ser adaptado pelo caminho de migração escolhido (ver §11).

```sql
-- =====================================================================
-- Enums
-- =====================================================================
CREATE TYPE user_tipo AS ENUM ('Provider', 'Admin');
CREATE TYPE user_registro_tipo AS ENUM ('CRM', 'COREN', 'CRN', 'CRO', 'Outro');

CREATE TYPE deliverable_tipo AS ENUM (
  'Plano de Tratamento', 'Injetável', 'Medicamento Manipulado',
  'Implante', 'Consulta', 'Acompanhamento', 'Exame', 'Meta'
);
CREATE TYPE deliverable_frequencia AS ENUM (
  'Diário', 'Semanal', 'Quinzenal', 'Mensal', 'Única', 'Outro'
);

CREATE TYPE client_deliverable_status AS ENUM (
  'Ativo', 'Pausado', 'Aguardando', 'Finalizado', 'Cancelado', 'Não iniciado'
);

CREATE TYPE session_status AS ENUM (
  'Agendado', 'Confirmado', 'Atendido', 'Atrasado', 'Cancelado', 'Reagendado'
);

CREATE TYPE alert_category AS ENUM (
  'Enfermagem', 'Médica', 'Comercial', 'Nutrição', 'Frequência', 'Sistema'
);
CREATE TYPE alert_priority AS ENUM ('Alta', 'Média', 'Baixa');
CREATE TYPE alert_status AS ENUM ('Aberto', 'Em análise', 'Resolvido');

CREATE TYPE satisfaction_status AS ENUM (
  'Satisfeito', 'Neutro', 'Insatisfeito', 'Não informado'
);

CREATE TYPE client_origem AS ENUM (
  'Manual', 'PDF', 'CSV', 'SupportHealth', 'Indicação', 'Instagram', 'Outro'
);
CREATE TYPE client_created_via AS ENUM (
  'manual', 'pdf_import', 'csv_import', 'supporthealth_sync'
);

-- =====================================================================
-- Entidades
-- =====================================================================
CREATE TABLE organizations (
  id              bigserial PRIMARY KEY,
  nome            text NOT NULL,
  cnpj            text NOT NULL,
  endereco        text,
  telefone        text,
  url             text,
  config          jsonb,
  ativo           boolean NOT NULL DEFAULT true,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz
);
CREATE UNIQUE INDEX idx_organizations_cnpj ON organizations(cnpj) WHERE deleted_at IS NULL;

CREATE TABLE users (
  id                  bigserial PRIMARY KEY,
  tipo                user_tipo NOT NULL,
  nome                text NOT NULL,
  cpf                 text NOT NULL,
  registro_especial   text,
  tipo_registro       user_registro_tipo,
  telefone            text,
  email               text,
  funcao              text,
  organization_id     bigint NOT NULL REFERENCES organizations(id),
  ativo               boolean NOT NULL DEFAULT true,
  criado_em           timestamptz NOT NULL DEFAULT now(),
  atualizado_em       timestamptz NOT NULL DEFAULT now(),
  deleted_at          timestamptz
);
CREATE UNIQUE INDEX idx_users_cpf_org ON users(cpf, organization_id) WHERE deleted_at IS NULL;

CREATE TABLE deliverables (
  id                    bigserial PRIMARY KEY,
  titulo                text NOT NULL,
  tipo                  deliverable_tipo NOT NULL,
  descricao             text NOT NULL,
  parent_deliverable_id bigint REFERENCES deliverables(id),
  organization_id       bigint NOT NULL REFERENCES organizations(id),
  frequencia_tipo       deliverable_frequencia,
  frequencia_texto      text,
  metadata              jsonb,
  ativo                 boolean NOT NULL DEFAULT true,
  criado_em             timestamptz NOT NULL DEFAULT now(),
  atualizado_em         timestamptz NOT NULL DEFAULT now(),
  deleted_at            timestamptz
);
CREATE INDEX idx_deliverables_parent ON deliverables(parent_deliverable_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_deliverables_org_tipo ON deliverables(organization_id, tipo) WHERE deleted_at IS NULL;

CREATE TABLE clients (
  id                      bigserial PRIMARY KEY,
  nome                    text NOT NULL,
  cpf                     text NOT NULL,
  rg                      text,
  data_nascimento         date NOT NULL,
  telefone                text,
  endereco                text,
  email                   text,
  origem                  client_origem,
  consentimento_lgpd      boolean NOT NULL DEFAULT false,
  consentimento_lgpd_em   timestamptz,
  observacoes             text,
  created_via             client_created_via NOT NULL DEFAULT 'manual',
  organization_id         bigint NOT NULL REFERENCES organizations(id),
  ativo                   boolean NOT NULL DEFAULT true,
  criado_em               timestamptz NOT NULL DEFAULT now(),
  atualizado_em           timestamptz NOT NULL DEFAULT now(),
  deleted_at              timestamptz
);
CREATE UNIQUE INDEX idx_clients_cpf_org ON clients(cpf, organization_id) WHERE deleted_at IS NULL;

-- =====================================================================
-- Associações
-- =====================================================================
CREATE TABLE organization_users (
  id              bigserial PRIMARY KEY,
  organization_id bigint NOT NULL REFERENCES organizations(id),
  user_id         bigint NOT NULL REFERENCES users(id),
  cargo           text,
  data_inicio     date NOT NULL,
  data_fim        date,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id, data_inicio)
);

CREATE TABLE client_deliverables (
  id                              bigserial PRIMARY KEY,
  client_id                       bigint NOT NULL REFERENCES clients(id),
  deliverable_id                  bigint NOT NULL REFERENCES deliverables(id),
  parent_client_deliverable_id    bigint REFERENCES client_deliverables(id),
  organization_id                 bigint NOT NULL REFERENCES organizations(id),
  status                          client_deliverable_status NOT NULL DEFAULT 'Aguardando',
  orcamento                       text,
  is_renovacao                    boolean NOT NULL DEFAULT false,
  data_inicio                     date NOT NULL,
  data_fim                        date,
  sessions_expected               int NOT NULL DEFAULT 0,
  sessions_completed              int NOT NULL DEFAULT 0,
  sessions_remaining              int GENERATED ALWAYS AS
                                  (sessions_expected - sessions_completed) STORED,
  metadata                        jsonb,
  criado_em                       timestamptz NOT NULL DEFAULT now(),
  atualizado_em                   timestamptz NOT NULL DEFAULT now(),
  deleted_at                      timestamptz
);
CREATE INDEX idx_cd_client ON client_deliverables(client_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_cd_parent ON client_deliverables(parent_client_deliverable_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_cd_deliverable ON client_deliverables(deliverable_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_cd_status ON client_deliverables(status) WHERE deleted_at IS NULL;

CREATE TABLE client_sessions (
  id                bigserial PRIMARY KEY,
  client_id         bigint NOT NULL REFERENCES clients(id),
  provider_id       bigint NOT NULL REFERENCES users(id),
  agendado_por_id   bigint REFERENCES users(id),
  organization_id   bigint NOT NULL REFERENCES organizations(id),
  session_start     timestamptz NOT NULL,
  session_end       timestamptz,
  status            session_status NOT NULL DEFAULT 'Agendado',
  session_type      text,
  codigo_origem     text,
  metadata          jsonb,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  deleted_at        timestamptz
);
CREATE INDEX idx_cs_client ON client_sessions(client_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_cs_provider ON client_sessions(provider_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_cs_status ON client_sessions(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_cs_start ON client_sessions(session_start) WHERE deleted_at IS NULL;

CREATE TABLE client_session_items (
  id                       bigserial PRIMARY KEY,
  client_session_id        bigint NOT NULL REFERENCES client_sessions(id),
  client_deliverable_id    bigint NOT NULL REFERENCES client_deliverables(id),
  status                   session_status,
  criado_em                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE client_alerts (
  id              bigserial PRIMARY KEY,
  client_id       bigint NOT NULL REFERENCES clients(id),
  plan_id         bigint REFERENCES client_deliverables(id),
  session_id      bigint REFERENCES client_sessions(id),
  category        alert_category NOT NULL,
  alert_type      text NOT NULL,
  description     text NOT NULL,
  priority        alert_priority NOT NULL,
  status          alert_status NOT NULL DEFAULT 'Aberto',
  created_at      timestamptz NOT NULL DEFAULT now(),
  resolved_at     timestamptz,
  comment         text
);
CREATE INDEX idx_alerts_client ON client_alerts(client_id);
CREATE INDEX idx_alerts_status ON client_alerts(status);
CREATE INDEX idx_alerts_created ON client_alerts(created_at DESC);

CREATE TABLE satisfaction_records (
  id                       bigserial PRIMARY KEY,
  client_id                bigint NOT NULL REFERENCES clients(id),
  client_deliverable_id    bigint REFERENCES client_deliverables(id),
  date                     timestamptz NOT NULL,
  satisfaction_status      satisfaction_status NOT NULL,
  score                    int,
  notes                    text,
  criado_em                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weight_records (
  id                       bigserial PRIMARY KEY,
  client_id                bigint NOT NULL REFERENCES clients(id),
  client_deliverable_id    bigint REFERENCES client_deliverables(id),
  measurement_date         timestamptz NOT NULL,
  weight                   numeric(5,2) NOT NULL,
  source                   text,
  notes                    text,
  criado_em                timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE data_quality_issues (
  id          bigserial PRIMARY KEY,
  source      text NOT NULL,
  severity    text NOT NULL,
  issue_type  text NOT NULL,
  description text NOT NULL,
  client_id   bigint REFERENCES clients(id),
  field_name  text,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
```

---

## 7. Mapeamento de migração (schema atual → novo)

| Tabela atual (v1) | Tabela nova (v2) | Observação sobre migração |
|---|---|---|
| `patients` | `clients` | `age` (int) → `data_nascimento` (date); requer input externo ou inferência (anos_a_tras = hoje - issue_date do plan mais antigo) |
| `treatment_plans` | `client_deliverables` (com `deliverable.tipo='Plano de Tratamento'`) | `status` enums casam; `orcamento` vira coluna |
| `treatment_plan_items` | `client_deliverables` (filhos do plano) | `parent_client_deliverable_id` aponta pro plano; `frequency_type`/`frequency_text` migram para `deliverables.frequencia_*` no catálogo |
| `execution_summary` | **deletada** — derivada de `client_deliverables` + `client_sessions` | `sessions_expected/completed/remaining` ficam em `client_deliverables`; agregação por `COUNT(client_sessions WHERE status='Atendido')` |
| `appointments` | `client_sessions` | `budget_codes` (string) explode em `client_session_items` (N:N com `client_deliverables`); `scheduled_by` vira `agendado_por_id` (FK users tipo=Admin) |
| `appointment_items` | `client_session_items` | Direto |
| `patient_goals` | `client_deliverables` (com `deliverable.tipo='Meta'`) | `initial_weight`/`target_weight` viram `metadata` jsonb |
| `weight_entries` | `weight_records` | Direto; ganha FK `client_deliverable_id` (a meta) |
| `satisfaction_entries` | `satisfaction_records` | Direto; ganha FK `client_deliverable_id` (o plano) |
| `alerts` | `client_alerts` | `plan_id` agora FK para `client_deliverables`; `category` ganha valor `Frequência` |
| `data_quality_issues` | `data_quality_issues` | `patient_id` (texto) → `client_id` (FK) |

**Saldo:** 11 tabelas → **4 entidades + 8 associações + 2 audit standalone** = **14 tabelas** (3 a mais que hoje, mas com semântica explícita).

---

## 8. Impacto na regra de frequência (a motivação original)

Hoje (v1) — `src/metrics.py:patient_summary`:
```python
engagement_rate = sessions_completed / sessions_expected  # de execution_summary
```

Proposta (v2) — `src/core/frequency.py`:
```python
def expected_sessions(client_deliverable_id: int, as_of: date) -> int:
    """Calcula quantas sessões DEVERIAM ter ocorrido até `as_of`."""
    cd = load_client_deliverable(client_deliverable_id)
    d = load_deliverable(cd.deliverable_id)
    if d.frequencia_tipo is None:
        return cd.sessions_expected
    period_days = {"Diário": 1, "Semanal": 7, "Quinzenal": 14, "Mensal": 30}[d.frequencia_tipo]
    elapsed = (as_of - cd.data_inicio).days
    return min(cd.sessions_expected, max(0, elapsed // period_days))

def actual_sessions(client_deliverable_id: int, as_of: date) -> int:
    """Conta sessões com status='Atendido' até `as_of`."""
    return count(
        client_sessions cs
        JOIN client_session_items csi ON csi.client_session_id = cs.id
        WHERE csi.client_deliverable_id = :cd_id
          AND cs.status = 'Atendido'
          AND cs.session_start <= :as_of
    )

def generate_frequency_alerts(organization_id: int, as_of: date) -> list[ClientAlert]:
    """Regra: comparecimento abaixo de 70% E >= 2 faltas consecutivas."""
    alerts = []
    for cd in active_client_deliverables(organization_id):
        # Apenas itens de plano (filhos), não os planos
        if cd.parent_client_deliverable_id is None:
            continue
        expected = expected_sessions(cd.id, as_of)
        actual = actual_sessions(cd.id, as_of)
        if expected == 0:
            continue
        rate = actual / expected
        consecutive_missed = max_consecutive_non_attended(cd.id, as_of)
        if consecutive_missed >= 2:
            alerts.append(alert(cd.client_id, cd.id, "Frequência", "Alta",
                                f"{consecutive_missed} sessões consecutivas não atendidas"))
        elif rate < 0.7:
            alerts.append(alert(cd.client_id, cd.id, "Frequência", "Média",
                                f"Comparecimento de {rate:.0%} no ciclo atual"))
    return alerts
```

**O que melhorou:**
- A regra vira **1 query** em vez de heurística multi-tabela.
- O `expected_sessions` virou **função determinística** que respeita `frequencia_tipo` do catálogo (resolve C3 do relatório).
- O `consecutive_missed` calcula direto da `client_sessions` (resolve C4).
- O alerta referencia tanto o `client_deliverable` (item) quanto pode ser estendido a apontar para a `client_session` específica (resolve C7).

---

## 9. Casos de uso cobertos

| Caso de uso | Tabelas envolvidas | Caminho B |
|---|---|---|
| Cadastrar paciente com CPF | `clients` | Fase 1 |
| Importar PDF de plano (caso atual `importar_pdf_wizard`) | `clients` + `deliverables` (catálogo) + `client_deliverables` (Plano + Itens) | Fase 3 |
| Importar CSV `Relatorio de frequencia.csv` | `clients` + `deliverables` + `client_deliverables` | Fase 4 |
| Importar CSV `Agendamentos.csv` | `clients` + `users` + `client_sessions` + `client_session_items` + `client_deliverables` | Fase 4 |
| Mostrar Mapa de Decisão | `client_sessions` (frequência real) + `client_deliverables` (frequência esperada) + `satisfaction_records` | Fase 5 |
| Mostrar Alertas (com categoria `Frequência`) | `client_alerts` (gerado por `generate_frequency_alerts`) | Fase 5 |
| Mostrar Ficha do Paciente | Todas as 14, agregadas por `client_id` | Fase 6 |
| Multi-clínica (futuro) | filtro por `organization_id` em todas as queries | Já suportado pelo schema |

---

## 10. Pontos em aberto (precisam do cliente)

1. **Confirmação do modelo 4 classes** (§3) — antes do caminho B, validar com o cliente que essa abstração casa com a visão do SupportHealth.
2. **Enum `deliverables.tipo`** — os 8 valores propostos (§3.3.1) cobrem o catálogo atual? Faltam? Sobram?
3. **Enum `frequencia_tipo`** — `Diário/Semanal/Quinzenal/Mensal/Única/Outro` é suficiente? O cliente tem casos "2x por semana", "3x por semana" que exigiriam refinar?
4. **`metadata` jsonb vs. colunas específicas** — a proposta é jsonb; o cliente prefere validação no DB (colunas)?
5. **Multi-tenant desde já ou depois?** — adicionar `organization_id` em tudo é barato agora; remover depois é caro. Recomendação: já incluir.
6. **Campos extras em `clients`** — o cliente tem campos que o MAP ainda não captura? (convênio, profissão, contato de emergência, etc.)
7. **Quem provisiona o catálogo `deliverables`?** — o MAP importa de PDF; o SupportHealth tem o próprio; como reconciliar? Catálogo por `organization_id` resolve, mas exige processo de sync.

---

## 11. Caminho de implementação

| Caminho | Descrição | Custo | Risco | Recomendação |
|---|---|---|---|---|
| **A** | Apenas ajustes pontuais (adicionar `plan_item_id` em `appointments`, criar `expected_sessions()`, criar `generate_frequency_alerts()`) | 1 sprint | Baixo | Se o cliente quer **só** a regra de frequência |
| **B** | Refactor incremental — `src/core/` com 4 classes que mapeiam para o schema v1; refactor página a página | 3-4 sprints | Médio | **Recomendado** se o cliente quer a regra **e** preparar terreno para SupportHealth |
| **C** | Refactor big-bang — substituir schema e reescrever tudo de uma vez | 6-8 sprints | Alto | Não recomendado mid-MAP |

**O caminho B é o que seguimos nesta proposta.** Detalhamento das fases e plano de testes estão em `docs/caminho_b_plano.md` (a ser criado na próxima iteração).
