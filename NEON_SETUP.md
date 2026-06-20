# NEON_SETUP — Runbook de provisionamento e configuração do Neon

> **Objetivo:** guia passo-a-passo para provisionar o Neon Serverless
> Postgres que serve o `cli_dclinique` em PRD, configurar o ambiente
> local para falar com ele, e validar o caminho end-to-end.
>
> **Audiência:** operador que vai fazer o deploy pela primeira vez (ou
> recriar o ambiente). Supõe conhecimento do gate de LGPD documentado
> em `DEPLOY.md` §2.
>
> **Escopo:** cobre o **caminho feliz** (provisionamento + bootstrap +
> smoke + testes + secrets) e o **caminho de erro** (troubleshooting
> dos 7 erros mais comuns). Não cobre: tuning avançado, replica
> read-only, branch protection, migration de dados existentes.
>
> **Shell:** todos os comandos nesta documentação são **PowerShell**
> (Windows). Se você usa git bash / WSL, adapte a sintaxe (ver
> `§0. Convenções de shell` abaixo).

## Índice

0. [Convenções de shell](#0-convenções-de-shell)
1. [Visão geral](#1-visão-geral)
2. [Pre-requisitos](#2-pre-requisitos)
3. [Decisão de região (LGPD)](#3-decisão-de-região-lgpd)
4. [Provisionamento do projeto no Neon](#4-provisionamento-do-projeto-no-neon)
5. [Captura das credenciais](#5-captura-das-credenciais)
6. [Configuração local (`.env`)](#6-configuração-local-env)
7. [Bootstrap do schema](#7-bootstrap-do-schema)
8. [Smoke test do data layer](#8-smoke-test-do-data-layer)
9. [Setup dos testes de integração](#9-setup-dos-testes-de-integração)
10. [Configuração do Streamlit Cloud (PRD)](#10-configuração-do-streamlit-cloud-prd)
11. [Cold start — latência esperada e mitigação](#11-cold-start--latência-esperada-e-mitigação)
12. [Limites operacionais e upgrade](#12-limites-operacionais-e-upgrade)
13. [Rotação de credenciais](#13-rotação-de-credenciais)
14. [Troubleshooting](#14-troubleshooting)
15. [Checklist de pre-flight](#15-checklist-de-pre-flight)
16. [Referências](#16-referências)

---

## 0. Convenções de shell

**Esta documentação assume PowerShell** (o shell padrão do Windows
11). O ambiente alvo do `cli_dclinique` é Windows; o gate de LGPD
em `DEPLOY.md` §2 e o smoke em §6 deste runbook foram validados em
PowerShell 5.1 (default Windows 11).

### 0.1 Diferenças chave (PowerShell vs bash)

| Operação | PowerShell | bash (git bash / WSL) |
|---|---|---|
| Setar env var (escopo processo) | `$env:VAR = "value"` | `export VAR="value"` |
| Setar inline no mesmo comando | `$env:VAR = "x"; cmd.exe arg` | `VAR=x cmd arg` |
| Ler env var | `$env:VAR` | `$VAR` |
| Deletar env var | `Remove-Item env:VAR` | `unset VAR` |
| Carregar `.env` | `Get-Content .env \| ForEach-Object {...}` (snippet em §6.3) | `set -a; source .env; set +a` |
| Ativar venv | `.\.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| Concatenar comandos | `cmd1; cmd2` (sempre roda cmd2) ou `cmd1 && cmd2` (só se sucesso) | `cmd1 && cmd2` |
| Echo / print | `Write-Host "x"` ou `echo "x"` | `echo "x"` |
| Conferir se string está em arquivo | `Select-String -Path file -Pattern "regex"` | `grep -E "regex" file` |
| Adicionar linha a arquivo | `Add-Content -Path file -Value "linha"` | `echo "linha" >> file` |

> **Importante:** o Python em si **não muda** entre shells.
> `.venv/Scripts/python.exe scripts/foo.py` funciona igual em
> PowerShell e bash. O que muda é como você **seta as env vars
> antes** de invocar o Python.

### 0.2 Prompt de detecção

Para confirmar que está em PowerShell:

```powershell
$PSVersionTable.PSVersion
# Esperado: Major=5 (Windows PowerShell) ou Major=7 (PowerShell Core)
```

Se o output mostrar `$` (sem `PS C:\>`), você está em bash.

### 0.3 Quando o output parecer diferente

PowerShell renderiza listas e dicts Python com quebras de linha
diferentes de bash. Se o smoke em §8.2 mostrar saída "estranha"
(múltiplas linhas em vez de uma), é o `print` do Python —
**não é erro**. A informação está lá, só está quebrada em mais
linhas. Para forçar uma única linha:

```powershell
$env:DCLINIQUE_BACKEND = "postgres"
.venv/Scripts/python.exe -c "from src.data_layer import load_all; d=load_all(); import json; print(json.dumps({'keys': list(d.keys()), 'counts': {k: len(v) for k,v in d.items()}}))"
```

---

---

## 1. Visão geral

Em PRD, o `cli_dclinique` lê e escreve em um projeto **Neon Serverless
Postgres** (não nos CSVs de `data/csv/`, que viraram só schema reference).
O fluxo end-to-end é:

```
[cliente]
   │  browser
   ▼
[Streamlit Community Cloud] ──── app.py ──── get_data()
   │                                          │
   │                                  st.cache_data
   │                                          │
   │                                  data_layer.load_all()
   │                                          │
   │                                  DCLINIQUE_BACKEND=postgres
   │                                          │
   │                                  postgres_backend.py
   │                                          │
   │                                  psycopg → connection.py
   │                                          │
   │                                  st.secrets["postgres"]["dsn"]
   ▼
[Neon Serverless Postgres]
   │
   ├── branch "main" (produção)
   └── branches efêmeros (criados em tests/conftest.py:db_branch)
```

A configuração tem 3 lados:

- **Lado Neon:** projeto, branch `main`, database `dclinique`, role, schema.
- **Lado app:** env var `DCLINIQUE_BACKEND=postgres` + DSN via
  `st.secrets["postgres"]["dsn"]` (PRD) ou `NEON_DSN` (local).
- **Lado testes:** `NEON_API_KEY` + `NEON_PROJECT_ID` no `.env` (local)
  para o fixture `db_branch` criar/deletar branches efêmeros.

---

## 2. Pre-requisitos

Antes de começar, confirme que tem:

| # | Item | Como verificar |
|---|---|---|
| 1 | Conta Neon (plano free é suficiente para o piloto) | <https://console.neon.tech> |
| 2 | Email corporativo (cada email vira 1 viewer no Streamlit Cloud) | confirmado com o cliente |
| 3 | `git` e `python -m venv` funcionando no worktree | `git --version` + `python --version` |
| 4 | `.venv` instalado com `requirements.txt` | `pip install -r requirements.txt` |
| 5 | `psycopg[binary]>=3.2,<4` instalado | `.venv/Scripts/python.exe -c "import psycopg; print(psycopg.__version__)"` |
| 6 | Acesso à raiz do worktree `feature-neon-data-layer` | confirmado |
| 7 | (PRD) conta no Streamlit Community Cloud com permissão no repo `INNOVAI-LTDA/cli_dclinique` | <https://share.streamlit.io> |
| 8 | Gate de LGPD `DEPLOY.md` §2 item 5 marcado como "pode prosseguir" | sign-off do responsável |
| 9 | PowerShell 5.1+ (default Windows 11) | `$PSVersionTable.PSVersion.Major` retorna `5` ou `7` |
| 6 | Acesso à raiz do worktree `feature-neon-data-layer` | confirmado |
| 7 | (PRD) conta no Streamlit Community Cloud com permissão no repo `INNOVAI-LTDA/cli_dclinique` | <https://share.streamlit.io> |
| 8 | Gate de LGPD `DEPLOY.md` §2 item 5 marcado como "pode prosseguir" | sign-off do responsável |

**Tempo estimado:** 15-20 min para provisionar + bootstrap. O
auto-suspend do Neon adiciona ~30 s no primeiro request de cada
sessão nova (ver §11).

---

## 3. Decisão de região (LGPD)

LGPD classifica dados de saúde como **sensíveis** (Art. 5º, II) e
exige que o controlador avalie a adequação da transferência
internacional (Art. 33). O Neon tem regiões em vários continentes;
escolher a região errada tem implicações jurídicas, não só de
latência.

**Tabela de decisão:**

| Código Neon | Região AWS | LGPD | Latência BR | Recomendação |
|---|---|---|---|---|
| `aws-sa-east-1` | São Paulo, BR | ✅ Dados não saem do país | ~20-50 ms | **Preferida** (quando disponível) |
| `aws-us-east-2` | Ohio, US | ⚠️ Transferência internacional — exige sign-off | ~120-180 ms | **Fallback** (se SP indisponível) |
| `aws-us-east-1` | Virginia, US | ⚠️ Idem | ~140-200 ms | Evitar |
| `aws-eu-west-1` | Irlanda, EU | ❌ Adequação questionável, distância maior | ~200-250 ms | Evitar para o caso BR |

**Procedimento antes de provisionar:**

1. Verificar disponibilidade de `aws-sa-east-1` no console Neon
   (New Project → Region dropdown). O plano free pode ter
   catálogo limitado de regiões.
2. Se SP indisponível, usar `aws-us-east-2` (Ohio é a região AWS
   com menor latência para o Brasil depois de SP).
3. **Confirmar com o cliente** (decisão humana, não automática) e
   registrar o sign-off no gate `DEPLOY.md` §2 item 5.
4. Anotar a região escolhida em local seguro (1Password, vault) —
   vai ser usada na string de conexão e em troubleshooting.

> **Atenção:** a região é **imutável** após a criação do projeto.
> Trocar de região = criar projeto novo + migrar dados (não há
> migration automatizada para esta casca).

---

## 4. Provisionamento do projeto no Neon

Passo-a-passo do console Neon (versão web em
<https://console.neon.tech>):

### 4.1 Criar conta / logar

1. Acessar <https://console.neon.tech>.
2. **Sign up** com email corporativo ou **Sign in** se já tem conta.
3. Se for primeira vez: GitHub OAuth é o caminho mais rápido.

### 4.2 Criar o projeto

1. No dashboard, clicar **"New Project"**.
2. Preencher:
   - **Name:** `dclinique-prod`
   - **Region:** a região escolhida na §3 (ex.: `aws-sa-east-1`).
   - **Postgres version:** deixar no default (atualmente 16 ou 17).
   - **Branch name:** `main` (default, não mudar).
3. Clicar **"Create Project"**.
4. Aguardar ~30 s. O console vai mostrar "Provisioning..." e depois
   "Active".

### 4.3 Validar o branch `main`

1. No menu lateral, **"Branches"** deve mostrar 1 branch: `main`.
2. Clicar em `main`. Em **"Compute"** deve estar **"Active"** com
   **"Auto-suspend"** configurado (default: 5 min — manter).

### 4.4 Anotar o nome do database

1. Em **"Databases"** (na barra lateral), deve haver 1 database:
   `neondb` (default do Neon).
2. **Recomendação:** criar um database `dclinique` em vez de usar o
   `neondb` default — fica mais óbvio em logs e em strings de
   conexão. Para criar:
   - Clicar em **"New Database"**.
   - **Name:** `dclinique`.
   - **Owner:** `neondb_owner` (default role do Neon).
3. **Anotar:** o database name (vai na DSN).

### 4.5 Validar a role

1. Em **"Roles"** (na barra lateral), deve haver 1 role:
   `neondb_owner`.
2. **Anotar:** o role name (vai na DSN como `user`).

> **Não criar roles adicionais.** Esta casca tem 1 role só. Se
> aparecer necessidade de role com permissões reduzidas (read-only
> para relatórios, por exemplo), é tarefa separada — não escopo
> desta documentação.

---

## 5. Captura das credenciais

O `cli_dclinique` precisa de **3 credenciais** do projeto Neon:

| Credencial | Onde achar | Como é usada | Onde armazenar |
|---|---|---|---|
| **DSN** (connection string) | **Dashboard** → connection details | `st.secrets["postgres"]["dsn"]` (PRD) ou `NEON_DSN` (local) | 1Password + Streamlit Secrets |
| **API key** | **Settings** → **API Keys** → **Generate API Key** | `NEON_API_KEY` (criação/deleção de branches em testes) | 1Password + `.env` local |
| **Project ID** | **Settings** → **General** | `NEON_PROJECT_ID` (mesma função da API key) | 1Password + `.env` local |

### 5.1 DSN (connection string)

1. Voltar ao **Dashboard** do projeto `dclinique-prod`.
2. No card **"Connection Details"**, escolher:
   - **Database:** `dclinique` (o que criamos na §4.4).
   - **Role:** `neondb_owner`.
   - **Branch:** `main`.
   - **Pooled connection:** **ON** (recomendado para o app — o
     pooler do Neon gerencia conexões para o compute que acorda
     e dorme).
3. Clicar no ícone de **copy** ao lado da string. A string tem
   formato:
   ```
   postgresql://neondb_owner:<password>@ep-xxx-pooler.<region>.neon.tech/dclinique?sslmode=require
   ```
4. **NÃO colar essa string em lugar nenhum versionado** (nem
   `.env` commitado, nem `secrets.toml` commitado, nem chat).
   Tratar como senha.

> **Pooled vs Direct:** o Neon oferece dois endpoints. O **pooled**
> (sufixo `-pooler`) é o caminho pgsql nativo com connection
> pooling — usar para o app. O **direct** (sem `-pooler`) é
> conexão direta ao compute — usar para o `init_schema.py` e
> para migrations manuais, porque alguns comandos DDL não
> funcionam em connection pooler (e.g., `CREATE DATABASE`).

### 5.2 API key

1. Menu lateral → **"Settings"** → **"API Keys"**.
2. Clicar **"Generate new API key"**.
3. **Name:** `cli-dclinique-test-runner` (claro para qual
   propósito é).
4. **Scopes:** marcar `Projects:Read` e `Branches:Manage` (o
   fixture `db_branch` só precisa criar/deletar branches).
5. Clicar **"Create"**.
6. **Copiar a chave IMEDIATAMENTE** — o Neon só mostra ela 1×.
7. **NÃO commitar, NÃO colar em chat.** Armazenar em 1Password.

### 5.3 Project ID

1. Menu lateral → **"Settings"** → **"General"**.
2. Em **"Project ID"**, copiar o UUID (formato
   `ep-xxx-yyy-zzz` ou `random-uuid`).
3. Armazenar em 1Password junto com a API key.

### 5.4 Onde NÃO anotar

| Local | Pode? | Por quê |
|---|---|---|
| 1Password / vault | ✅ | Cifrado, auditável |
| `.env` local (gitignored) | ✅ | Fora do repo |
| `st.secrets` do Streamlit Cloud | ✅ | Cifrado em trânsito e em repouso |
| `.streamlit/secrets.toml` commitado | ❌ | Vai para o repo público |
| `CLAUDE.md` / `DEPLOY.md` / `README.md` | ❌ | Documentação é pública |
| Chat / email / issue tracker | ❌ | Logs permanentes |
| Slack / Teams | ❌ | Histórico pesquisável |

---

## 6. Configuração local (`.env`)

### 6.1 Estrutura do `.env`

Criar (ou editar) `.env` na raiz do worktree:

```bash
# .env — gitignored. NAO COMMITE.
# Credenciais do Neon para dev local e tests.

# DSN do projeto dclinique-prod. Copiar do Neon console
# (Dashboard → Connection Details, com pooled=ON, branch=main).
NEON_DSN="postgresql://neondb_owner:<password>@ep-xxx-pooler.<region>.neon.tech/dclinique?sslmode=require"

# API key do Neon (Settings → API Keys). Usada por tests/conftest.py
# para criar/deletar branches efemeros durante a suite de testes.
NEON_API_KEY="<api-key-do-painel>"

# Project ID do Neon (Settings → General). UUID do projeto.
NEON_PROJECT_ID="<project-id-do-painel>"
```

### 6.2 Validar `.gitignore`

Confirmar que `.env` está no `.gitignore` da raiz do worktree:

```powershell
Select-String -Path .gitignore -Pattern "^\.env$"
```

Saída esperada: 1 linha com `.env` (e a linha do `.gitignore` que
contém). Se não retornar nada, **adicionar** antes de qualquer
commit:

```powershell
Add-Content -Path .gitignore -Value ".env"
```

### 6.3 Carregar `.env` para o processo atual

PowerShell **não tem `source`**. O snippet abaixo lê `.env` linha
por linha e seta cada `KEY=VALUE` no escopo do processo (válido
só para a janela PowerShell atual; não persiste entre janelas).

> **Recomendação:** rodar este snippet uma vez no início de cada
> sessão PowerShell em que for usar o Neon. Salvar como
> `scripts/_load_env.ps1` para reusar.

```powershell
# Carrega .env → env vars do processo atual
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#') { return }   # ignora comentarios
    if ($_ -match '^\s*$') { return }   # ignora linhas vazias
    if ($_ -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        Write-Host "  $key = $($value.Substring(0, [Math]::Min(20, $value.Length)))..."
    }
}

# Conferir
Write-Host ""
Write-Host "NEON_DSN: $($env:NEON_DSN.Substring(0, [Math]::Min(30, $env:NEON_DSN.Length)))..."
```

Saída esperada: 3 linhas `KEY = ...` (uma por variável) e 1 linha
`NEON_DSN: postgresql://neondb_owner:...`.

> **Versão bash (git bash / WSL)**, se você usa esses shells:
> ```bash
> set -a; source .env; set +a
> echo "NEON_DSN: ${NEON_DSN:0:30}..."
> ```

### 6.4 Validar visibilidade pelo Python

```powershell
.venv/Scripts/python.exe -c "import os; print('DSN OK:', os.environ['NEON_DSN'][:20]); print('KEY OK:', os.environ['NEON_API_KEY'][:8] + '...'); print('PID OK:', os.environ['NEON_PROJECT_ID'][:8] + '...')"
```

Saída esperada: 3 linhas, cada uma com o prefixo da variável. Se
algum `KeyError`, voltar para §6.3 e re-rodar o snippet de
carregamento.

---

## 7. Bootstrap do schema

`scripts/init_neon_schema.py` cria as 11 tabelas em `dclinique` a
partir do schema em `src/schemas.py:EXPECTED_SCHEMAS`. É idempotente
— rodar múltiplas vezes é seguro.

### 7.1 Comando

```powershell
# 1. Carregar .env (snippet da §6.3) — se ainda nao rodou nesta sessao
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

# 2. Setar backend e rodar o bootstrap
$env:DCLINIQUE_BACKEND = "postgres"
.venv/Scripts/python.exe scripts/init_neon_schema.py
```

> **Versão bash (git bash / WSL):**
> ```bash
> set -a; source .env; set +a
> DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe scripts/init_neon_schema.py
> ```

### 7.2 Saída esperada

```
[INFO] 11 tabelas a criar em dclinique
[OK]   CREATE TABLE IF NOT EXISTS patients (...)
[OK]   CREATE TABLE IF NOT EXISTS treatment_plans (...)
[OK]   CREATE TABLE IF NOT EXISTS treatment_plan_items (...)
[OK]   CREATE TABLE IF NOT EXISTS execution_summary (...)
[OK]   CREATE TABLE IF NOT EXISTS appointments (...)
[OK]   CREATE TABLE IF NOT EXISTS appointment_items (...)
[OK]   CREATE TABLE IF NOT EXISTS patient_goals (...)
[OK]   CREATE TABLE IF NOT EXISTS weight_entries (...)
[OK]   CREATE TABLE IF NOT EXISTS satisfaction_entries (...)
[OK]   CREATE TABLE IF NOT EXISTS alerts (...)
[OK]   CREATE TABLE IF NOT EXISTS data_quality_issues (...)
[OK]   11/11 tables created (or already exist)
```

Exit code **0** = sucesso.

### 7.3 Exit codes

| Code | Significado | Ação |
|---|---|---|
| 0 | Sucesso — 11 tabelas criadas ou já existiam | prosseguir para §8 |
| 1 | `NEON_DSN` ausente | voltar para §6.3 |
| 2 | DB fora do ar ou DSN errada | ver §14 troubleshooting |
| 3 | Permissão negada (role sem CREATE) | ver §14 troubleshooting |

### 7.4 Validar no console Neon

Após o bootstrap, no console Neon:

1. **SQL Editor** (menu lateral).
2. Rodar:
   ```sql
   SELECT table_name FROM information_schema.tables
   WHERE table_schema = 'public' ORDER BY table_name;
   ```
3. Esperado: 11 linhas com os nomes `patients`, `treatment_plans`,
   `treatment_plan_items`, `execution_summary`, `appointments`,
   `appointment_items`, `patient_goals`, `weight_entries`,
   `satisfaction_entries`, `alerts`, `data_quality_issues`.

---

## 8. Smoke test do data layer

Confirma que o `load_all()` retorna 11 DataFrames vazios (base
zerada — nenhum paciente importado ainda).

### 8.1 Comando

```powershell
$env:DCLINIQUE_BACKEND = "postgres"
.venv/Scripts/python.exe -c "from src.data_layer import load_all; d = load_all(); print(list(d.keys()), {k: len(v) for k, v in d.items()})"
```

> **Versão bash (git bash / WSL):**
> ```bash
> DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe -c \
>   "from src.data_layer import load_all; d = load_all(); print(list(d.keys()), {k: len(v) for k, v in d.items()})"
> ```

### 8.2 Saída esperada

```
['patients', 'treatment_plans', 'treatment_plan_items', 'execution_summary', 'appointments', 'appointment_items', 'patient_goals', 'weight_entries', 'satisfaction_entries', 'alerts', 'data_quality_issues'] {'patients': 0, 'treatment_plans': 0, 'treatment_plan_items': 0, 'execution_summary': 0, 'appointments': 0, 'appointment_items': 0, 'patient_goals': 0, 'weight_entries': 0, 'satisfaction_entries': 0, 'alerts': 0, 'data_quality_issues': 0}
```

(Tudo em 1 linha, mas separado aqui para legibilidade.)

### 8.3 O que significa cada coisa

- **Lista de 11 chaves** = o router resolveu o backend Postgres e
  listou as 11 tabelas do `EXPECTED_SCHEMAS`.
- **`len == 0` em todas** = base zerada (pronta para o cliente
  importar o primeiro PDF).
- Se qualquer `len > 0` ou faltar chave, ver §14.

---

## 9. Setup dos testes de integração

Os testes em `tests/` (T10-T14) usam o fixture `db_branch` que cria
um **branch Neon efêmero** para a sessão de teste e deleta no
teardown. Isso isola cada `pytest` run do branch `main` de produção.

### 9.1 Variaveis necessárias

| Var | Obrigatória? | Se ausente |
|---|---|---|
| `NEON_DSN` | Não (só para o init schema e smoke) | `db_branch` faz `pytest.skip` |
| `NEON_API_KEY` | **Sim** (para o fixture criar branches) | `db_branch` faz `pytest.skip` |
| `NEON_PROJECT_ID` | **Sim** (para o fixture) | `db_branch` faz `pytest.skip` |

### 9.2 Comportamento do fixture

```python
# tests/conftest.py (resumo)
@pytest.fixture(scope="session")
def db_branch() -> str:
    if not _has_neon_creds():
        pytest.skip("Neon creds ausentes — usando fallback CSV")
    if _should_use_csv():
        pytest.skip("DCLINIQUE_BACKEND=csv — usando fallback CSV")
    branch_id = _create_neon_branch(NEON_PROJECT_ID, NEON_API_KEY)
    yield f"postgresql://...?sslmode=require&branch={branch_id}"
    _delete_neon_branch(NEON_PROJECT_ID, branch_id, NEON_API_KEY)
```

### 9.3 Rodar a suite com Neon

```powershell
# 1. Carregar .env (snippet da §6.3) — garante NEON_API_KEY e NEON_PROJECT_ID
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

# 2. Setar backend e rodar pytest
$env:DCLINIQUE_BACKEND = "postgres"
.venv/Scripts/python.exe -m pytest tests/ -x
```

> **Versão bash (git bash / WSL):**
> ```bash
> set -a; source .env; set +a
> DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe -m pytest tests/ -x
> ```

Esperado: todos os testes passam. O fixture `db_branch` cria 1
branch no setup, roda todos os testes contra ele, e deleta no
teardown. O branch `main` de produção **não é tocado**.

### 9.4 Rodar a suite SEM Neon (fallback CSV)

```powershell
# 1. Limpar credenciais Neon (causam pytest.skip se presentes + DCLINIQUE_BACKEND=csv)
Remove-Item env:NEON_API_KEY -ErrorAction SilentlyContinue
Remove-Item env:NEON_PROJECT_ID -ErrorAction SilentlyContinue

# 2. Setar backend CSV e rodar pytest
$env:DCLINIQUE_BACKEND = "csv"
.venv/Scripts/python.exe -m pytest tests/ -x
```

> **Versão bash (git bash / WSL):**
> ```bash
> unset NEON_API_KEY NEON_PROJECT_ID
> DCLINIQUE_BACKEND=csv .venv/Scripts/python.exe -m pytest tests/ -x
> ```

Esperado: testes passam usando o `csv_dir` fixture (CSVs em
`tests/fixtures/empty_csvs/` ou `data/csv/` zerado). Útil para
dev local sem internet.

### 9.5 Confirmar isolamento

Após `pytest` terminar, conferir no console Neon que **não há
branches novos** com nomes que começam com `test-` (o fixture
deleta automaticamente; se sobrou algum, há bug no teardown).

---

## 10. Configuração do Streamlit Cloud (PRD)

### 10.1 Secrets no painel

1. Abrir <https://share.streamlit.io> e logar.
2. Selecionar o app **`cli-dclinique`** (criado conforme
   `DEPLOY.md` §3).
3. Menu **"Settings"** → **"Secrets"**.
4. Colar (em formato TOML):
   ```toml
   [postgres]
   dsn = "postgresql://neondb_owner:<password>@ep-xxx-pooler.<region>.neon.tech/dclinique?sslmode=require"
   ```
5. Clicar **"Save"**. O app reinicia automaticamente em ~10 s.

> **Atenção:** o `[postgres]` é o único bloco necessário. Os
> blocos comentados em `.streamlit/secrets.toml.example` (`[supabase]`,
> `[integrations]`) **NÃO** devem ser descomentados — Supabase
> não é o backend alvo e as integrações estão fora do escopo
> do `CLAUDE.md`.

### 10.2 Verificação pós-deploy

Após o restart:

1. Abrir o app no URL público.
2. Navegar para **Pacientes**. Esperado: empty-state ("Nenhum
   paciente cadastrado").
3. (Opcional, recomendado) Importar o PDF sintético gerado por
   `scripts/make_synthetic_pdf.py`:
   - **Ações** → **"Importar paciente(s) do PDF"**.
   - Upload do PDF.
   - Esperado: 1 paciente aparece na lista.
4. **Fechar o app, esperar 1 min, reabrir.** Esperado: o paciente
   continua lá (prova de que o dado está no Neon, não no
   filesystem efêmero do Streamlit).

### 10.3 Revogar secrets antigos

Ao rotacionar a DSN (ver §13), o secret antigo **permanece no
histórico de revisões do Streamlit Cloud** até que o painel seja
limpo manualmente. O Streamlit não tem "delete secret revision",
apenas "edit". O secret editado substitui o anterior em runtime
mas o histórico fica. Para deletar de vez:

1. **Settings** → **Secrets** → **"Clear all"** (botão no rodapé).
2. Colar os novos secrets.
3. Save.

**Cuidado:** se o app estiver em uso, "Clear all" deixa ele sem
secrets por ~5 s (durante o save). Planejar a janela.

---

## 11. Cold start — latência esperada e mitigação

### 11.1 O que acontece

O Neon escala o compute a **zero** após **5 min** de inatividade
(config default). O primeiro request após esse intervalo paga:

| Etapa | Latência adicional | Por quê |
|---|---:|---|
| Wakeup do compute | ~300-500 ms | Neon precisa subir o container do Postgres |
| SSL handshake | ~50-100 ms | Pooler valida certificado |
| `SELECT * FROM <table>` × 11 (primeira vez) | ~50-150 ms | Compute frio, sem cache de páginas |
| `psycopg.connect()` (cache miss) | ~20-50 ms | Pool de conexões cliente vazio |
| **Total adicional** | **~500 ms** | — |

Após o wakeup, o compute fica **quente** por 5 min. Requests
subsequentes voltam a pagar ~10-30 ms por query (mesma região).

### 11.2 Cold start vs cold start do Streamlit

| Componente | Cold start | Frequência |
|---|---:|---|
| Framework Streamlit | ~2 500 ms | 1× por deploy (não por sessão) |
| Neon compute | ~500 ms | A cada 5 min de inatividade |
| **Total no pior caso** | **~3 000 ms** | Primeira chamada de uma sessão nova, após 5 min parada |

Em operação contínua, o usuário não sente o cold start do Neon.
Em uso "boletim diário" (cliente abre o app 1× ao dia), ele sente
os ~500 ms adicionais.

### 11.3 Mitigações

| Mitigação | Custo | Recomendação |
|---|---|---|
| Upgrade para Launch tier (~$20/mês) | $ | **Se** o cliente reclamar, fazer. Remove auto-suspend. |
| Ping externo a cada 4 min (GitHub Actions cron) | $0 + complexidade | Workaround. Adiciona dependencia operacional. Não recomendo. |
| Aumentar `compute_idle_timeout` no console Neon | $0 | Configurável até 7 dias. Não é "quente" mas reduz frequência do wakeup. |
| Cachear `load_all()` no app | $0 | **Já feito** — `@st.cache_data` em `app.py:get_data()`. 1× por sessão Streamlit. |

### 11.4 Como medir o cold start em produção

```python
# app.py — adicionar temporariamente em get_data()
import time
t0 = time.perf_counter()
data = load_all()
elapsed_ms = (time.perf_counter() - t0) * 1000
st.sidebar.caption(f"load_all: {elapsed_ms:.0f} ms ({len(data)} tabelas)")
```

Ou usar `streamlit --log-level debug` no Cloud para ver o log
de round-trip do psycopg.

---

## 12. Limites operacionais e upgrade

### 12.1 Free tier (default do piloto)

| Recurso | Limite free |
|---|---|
| Compute time | **191.9 horas/mês** |
| Projetos | 10 (não é gargalo — usamos 1) |
| Branches | 10 (não é gargalo — 1 prod + N efêmeros de teste) |
| Tamanho do database | 0.5 GB |
| Compute size | 0.25 CU (Shared) |
| Auto-suspend | 5 min (default) |
| Storage | 0.5 GB incluído |

**Implicação para o piloto:** 191.9 h/mês ÷ 30 dias = ~6.4 h/dia
de compute ativo. **Mais que suficiente** para o piloto do
cliente (uso típico: 30 min/dia). Se virar gargalo, upgrade é
preventivo, não emergencial.

### 12.2 Launch tier (~$20/mês)

| Recurso | Limite launch |
|---|---|
| Compute time | **ilimitado** (com fair use) |
| Compute size | até 4 CU (dedicated) |
| Auto-suspend | configurável, **pode ser 0** (sempre quente) |
| Storage | 10 GB incluído |

Recomendado quando o cliente começar a usar o app 2+ h/dia ou
quando o cold start incomodar.

### 12.3 Scale tier (sob consulta)

Compute dedicado, read replicas, point-in-time recovery. **Fora
do escopo desta casca** — `CLAUDE.md` restringe integrações.

### 12.4 Monitoramento

| Sinal | Onde olhar | O que fazer |
|---|---|---|
| Compute time gasto | Console Neon → Settings → Usage | Se > 150 h/mês, planejar upgrade |
| Tamanho do DB | Console Neon → SQL Editor → `SELECT pg_database_size('dclinique')` | Se > 0.4 GB (80% do free tier), upgrade |
| Latência do wakeup | `SLA_REPORT.md` §6 (medições em PRD) | Se > 1 s consistentemente, upgrade |
| Número de branches | Console Neon → Branches | Esperado: 1 (`main`) + 0 (testes deleta) |

---

## 13. Rotação de credenciais

### 13.1 Quando rotacionar

| Credencial | Frequência recomendada | Gatilho de emergência |
|---|---|---|
| `NEON_DSN` (senha do role) | 90 dias | Vazamento |
| `NEON_API_KEY` | 90 dias | Ex-membro do time tinha acesso |
| `NEON_PROJECT_ID` | Nunca (imutável) | — |

### 13.2 Como rotacionar a DSN

O Neon não tem "rotate password" nativo. O caminho é:

1. Console Neon → **Settings** → **Roles**.
2. **Reset password** no `neondb_owner`.
3. Copiar a nova DSN (Dashboard → Connection Details).
4. Atualizar em **3 lugares**:
   - **PRD:** Streamlit Cloud → Settings → Secrets.
   - **Local:** `.env` (substituir `NEON_DSN`).
   - **1Password:** atualizar o item.
5. **Smoke test:** rodar §8 com a nova DSN. Esperado: 11 chaves,
   0 linhas (a senha nova não afeta os dados).
6. **Smoke test em PRD:** abrir o app no URL público, conferir
   que carrega sem erro.

### 13.3 Como rotacionar a API key

1. Console Neon → **Settings** → **API Keys**.
2. **Revoke** a chave antiga (NÃO delete — deixa inativa por 24 h
   para reversão).
3. **Generate new API key** com mesmo nome.
4. Atualizar `NEON_API_KEY` em `.env` (local) e 1Password.
5. **Não** afeta PRD — a API key é só usada pelos testes.
6. Rodar `pytest tests/ -x` para validar que o fixture `db_branch`
   ainda funciona com a nova chave.

### 13.4 Checklist de rotação

```
[ ] Senha do role rotacionada no console Neon
[ ] Nova DSN copiada do Dashboard
[ ] Streamlit Cloud → Secrets atualizado
[ ] .env local atualizado
[ ] 1Password atualizado
[ ] Smoke test local (§8) verde
[ ] Smoke test PRD (app público) verde
[ ] API key rotacionada (se aplicável)
[ ] pytest local verde com nova API key
[ ] Antiga DSN/API key revogada (passadas 24h de carência)
```

---

## 14. Troubleshooting

### 14.1 `KeyError: 'postgres'` em `st.secrets`

**Causa:** o bloco `[postgres]` não está nos secrets do app.

**Fix:**
1. Streamlit Cloud → Settings → Secrets.
2. Conferir que tem `[postgres]` (não `[postgre]` ou `[postgresdb]`)
   no topo da seção.
3. Conferir que `dsn = "..."` está dentro do bloco, com indentação
   ou não (TOML aceita ambos).
4. Save → app reinicia.

### 14.2 `NEON_DSN environment variable not set`

**Causa:** rodando local sem carregar o `.env` antes do comando
(o snippet de §6.3).

**Fix:** ver §6.3. Ou setar inline no PowerShell:

```powershell
$env:NEON_DSN = "postgresql://..."
$env:DCLINIQUE_BACKEND = "postgres"
.venv/Scripts/python.exe -c "from src.data_layer import load_all; print(len(load_all()))"
```

> **Versão bash:** `NEON_DSN="..." DCLINIQUE_BACKEND=postgres
> .venv/Scripts/python.exe -c "..."` (uma linha só).

### 14.3 `psycopg.OperationalError: connection to server ... timeout expired`

**Causas possíveis (em ordem de probabilidade):**
1. **DSN errada** (digitação, região trocada, senha antiga).
2. **Região errada** (compute em região A, DSN apontando para
   região B — falha rápida).
3. **Compute suspenso** (não é, na verdade — suspended compute
   acorda em ~500 ms, não dá timeout).
4. **VPN / firewall corporativo** bloqueando a porta 5432.

**Fix:**

```powershell
# 1. Garantir DSN no env (snippet da §6.3)
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

# 2. Testar DSN direto via psycopg (psql nao vem com Windows por default)
.venv/Scripts/python.exe -c "import psycopg; conn = psycopg.connect('$($env:NEON_DSN)', connect_timeout=5); print('OK'); conn.close()"
```

> **Versão bash:** `psql "$NEON_DSN" -c "SELECT 1"` se você tiver
> psql instalado (vem com o Postgres local). Em Windows sem psql,
> o caminho psycopg (acima) é mais portátil.

Se o comando acima falha, o problema é DSN/rede. Se funciona, o
problema é no `connection.py` do app.

### 14.4 `permission denied for schema public`

**Causa:** o role `neondb_owner` deveria ter `CREATE` em `public`
por default. Se falhou, o projeto foi criado com permissões
customizadas.

**Fix:**
```sql
-- Rodar no SQL Editor do console Neon
GRANT ALL ON SCHEMA public TO neondb_owner;
GRANT ALL ON DATABASE dclinique TO neondb_owner;
```

Re-rodar `init_neon_schema.py`. Se persistir, criar projeto novo.

### 14.5 `relation "patients" already exists` no init

**NÃO é erro.** O `init_schema()` usa `CREATE TABLE IF NOT EXISTS`.
A mensagem do Postgres "relation already exists" é **warning**,
não error. O script continua e mostra `[OK] 11/11`.

**Se o script abortou:** o problema é outro. Conferir o output
inteiro, não só a última linha.

### 14.6 Testes skip com "Neon creds ausentes"

**Esperado** se você está rodando `pytest` sem `NEON_API_KEY` /
`NEON_PROJECT_ID` no env. O fixture `db_branch` faz `pytest.skip`
e os testes caem no fallback `csv_dir`.

**Se você TEM as credenciais e mesmo assim skip:** conferir que
as vars estão no env (ver §6.4). Possível causa: o `.env` tem
aspas em volta do valor e o bash source não strip — usar
`source .env` com `set -a` no início, ou psql/psycopg diretos
para debugar.

### 14.7 Cold start > 2 s consistentemente

**Causa:** o compute está acordando do zero (esperado 500 ms,
não 2 s). Possíveis explicações:

1. **Pool de conexões cliente vazio** — psycopg cria conexão
   nova em vez de reusar do pool. Mitigação: garantir
   `@st.cache_resource` em `get_engine()` (já feito).
2. **Região distante** — se o app está em `aws-us-east-2` mas
   o Neon está em `aws-sa-east-1` (ou vice-versa), o round-trip
   adiciona latência. Mitigação: provisionar app e Neon na
   mesma região.
3. **Compute size muito pequeno** — 0.25 CU free tier pode ser
   lento para queries pesadas. Mitigação: upgrade para Launch.

**Como medir:** adicionar o snippet de §11.4 e comparar primeira
chamada vs segunda chamada (mesma sessão).

### 14.8 `init_neon_schema.py` reporta 0/11 tabelas

**Causa:** o DSN aponta para um database errado (provavelmente
`neondb` em vez de `dclinique`).

**Fix:** conferir §4.4 — o database **deve** ser `dclinique`. Se
usou o default `neondb`, a DSN ainda funciona (Postgres conecta
em qualquer database existente) mas o `init_schema()` está
criando as tabelas no database errado.

**Conferir qual database está sendo usado:**
```sql
SELECT current_database();
```

Se for `neondb` em vez de `dclinique`, ajustar a DSN e re-rodar.

### 14.9 `pytest` verde local mas PRD em branco

**Causa:** o `st.secrets["postgres"]["dsn"]` em PRD está
apontando para o branch `main` de produção, mas o
`@st.cache_data` em `get_data()` está cacheado de uma sessão
anterior vazia.

**Fix:** Streamlit Cloud reinicia a cada save de secret. Mas se
não reiniciou, forçar:
1. **Settings** → **Reboot app** (botão no rodapé).
2. Hard refresh no browser (Ctrl+Shift+R).

### 14.10 Logs do Streamlit Cloud

Para ver logs do psycopg em PRD:

1. Streamlit Cloud → app → **"Manage app"** → **"Logs"**.
2. Filtrar por `psycopg` ou `postgres`.
3. Cada request loga ~1 linha com a latência.

**Ativar log detalhado temporariamente** (NÃO recomendado em
produção contínua):
```toml
# Secrets — adicionar temporariamente
[postgres]
dsn = "..."
log_level = "DEBUG"
```

E em `connection.py`, conferir que `log_level` é respeitado.

---

## 15. Checklist de pre-flight

Antes de cada deploy em PRD (ou após qualquer mudança na infra
Neon), validar:

```
[ ] §2  — Gate de LGPD completo (5 itens, incluindo §5)
[ ] §3  — Região do Neon confirmada com o cliente
[ ] §4  — Projeto dclinique-prod provisionado
[ ] §4  — Branch "main" ativo
[ ] §4  — Database "dclinique" criado (não usando "neondb")
[ ] §5  — DSN copiada do console (pooled=ON)
[ ] §5  — API key criada (escopo Branches:Manage)
[ ] §5  — Project ID anotado
[ ] §6  — .env local com as 3 vars
[ ] §6  — .env no .gitignore
[ ] §7  — init_neon_schema.py rodou, exit 0
[ ] §7  — 11 tabelas visíveis no SQL Editor
[ ] §8  — Smoke test: 11 chaves, 0 linhas
[ ] §9  — pytest tests/ -x verde (com Neon OU com CSV fallback)
[ ] §10 — Streamlit Cloud secrets configurados
[ ] §10 — App público carrega empty-state em Pacientes
[ ] §10 — Importar PDF sintético → paciente aparece
[ ] §10 — Fechar e reabrir → paciente persiste (prova de Neon)
[ ] §11 — Cold start aceitável (< 1 s no primeiro request)
[ ] §12 — Compute time do mês < 150 h (folga de 40 h)
[ ] §13 — Última rotação de DSN/API key: < 90 dias
[ ] §14 — Nenhum erro em logs do Streamlit nas últimas 24h
```

Se qualquer item falhar, **NÃO promover para PRD**. Corrigir
e re-validar.

---

## 16. Referências

- [`DEPLOY.md`](DEPLOY.md) — guia de release (gate LGPD, setup
  Streamlit Cloud, rollback).
- [`DEPLOY.md`](DEPLOY.md) §12 — visão geral do Neon (versão
  curta; este doc é a versão detalhada).
- [`SLA_REPORT.md`](SLA_REPORT.md) §6 — cold start do Neon.
- [`SLA_REPORT.md`](SLA_REPORT.md) §9 — impacto da migração no SLA.
- [`README.md`](README.md) — entry point; seção "Deploy" aponta
  para `DEPLOY.md` e este doc.
- [`SCRUM_BOARD.md`](SCRUM_BOARD.md) — T1-T15 que implementaram
  o data layer Postgres.
- [`src/data_layer/connection.py`](src/data_layer/connection.py)
  — `get_engine()` lazy + cache.
- [`src/data_layer/postgres_backend.py`](src/data_layer/postgres_backend.py)
  — implementação do backend.
- [`src/data_layer/schema.py`](src/data_layer/schema.py) — DDL
  das 11 tabelas.
- [`scripts/init_neon_schema.py`](scripts/init_neon_schema.py) —
  bootstrap one-shot.
- [`tests/conftest.py`](tests/conftest.py) — fixture `db_branch`.
- <https://neon.tech/docs> — documentação oficial do Neon.
- <https://www.postgresql.org/docs/16/> — referência do Postgres 16.
- <https://www.psycopg.org/psycopg3/docs/> — documentação do
  psycopg 3.

---

> **Última atualização:** 2026-06-18. Manter este doc em sincronia
> com `DEPLOY.md` §12 e `SLA_REPORT.md` §6/§9 — quando algum desses
> mudar, atualizar aqui também.
