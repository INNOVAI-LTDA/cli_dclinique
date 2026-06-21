# DEPLOY — Guia de release no Streamlit Community Cloud

> **Status desta versão:** os artefatos para deploy estão **preparados**
> (`.python-version`, `requirements.txt` com pinos, `.streamlit/config.toml`,
> `.streamlit/secrets.toml.example`, `scripts/scan_pii.py`, este guia).
> O gate de LGPD abaixo foi **fechado** para o release inicial
> (apontamento em §2). Deploys futuros devem repetir o gate.

## 1. TL;DR

1. Fechar o gate de LGPD (§2).
2. Criar o app no Streamlit Community Cloud apontando para este repo
   (§3).
3. Colar o conteúdo de `.streamlit/secrets.toml.example` (preenchido) em
   Settings → Secrets (§4).
4. Marcar o app como **Private** e adicionar os emails convidados (§5).
5. Validar o boot (§6) e abrir o PR de release.
6. Em caso de problema, seguir o plano de rollback (§7).

## 2. Gate de LGPD (obrigatório antes de publicar)

Os CSVs em `data/csv/` modelam **dados de pacientes**: peso, satisfação,
plano de tratamento, alertas, consultas. Em qualquer deploy público ou
privado do Streamlit Cloud, o snapshot vai para a infraestrutura da
plataforma, e mesmo um app "private" tem o código-fonte versionado
commitado. LGPD classifica dados de saúde como sensíveis.

**Checklist — não prossiga enquanto qualquer item falhar:**

1. **Rodar `scripts/scan_pii.py`** e resolver todos os candidatos.
   ```bash
   .venv/Scripts/python.exe scripts/scan_pii.py
   ```
   Exit 1 é só um sinalizador — a decisão de release continua humana.
2. **Confirmar que `data/csv/*.csv` contém apenas dados sintéticos.**
   Procurar manualmente por: nomes de pacientes, CPF, RG, CNS,
   telefone, e-mail, endereço, data de nascimento real.
3. **Confirmar que `data/pacientes_e_planos/*.pdf` (atualmente untracked)
   NÃO foi adicionado ao repo.** Esse diretório contém PDFs de pacientes
   reais e **nunca** deve ir para o controle de versão.
4. **Confirmar que `data/images/` não tem capturas de tela com dados
   pessoais** (nomes, pesos identificáveis, etc.).
5. **Confirmar que o projeto Neon foi provisionado e o schema foi
   inicializado** — em PRD o backend ativo e' Postgres (Neon), nao CSV.
   O app deve subir com ``DCLINIQUE_BACKEND=postgres`` apontando para a
   DSN em ``st.secrets["postgres"]["dsn"]`` e as 11 tabelas criadas
   (vazias). Ver §13 para o passo a passo de provisionamento + schema
   bootstrap. Item binario: ou o smoke em PRD passa, ou este item falha.

### 2.1 Sign-off do release inicial (2026-06-08)

Auditoria rodada por `dmenescal` (proprietário) e validada nesta data:

- [x] **Item 1** — `scripts/scan_pii.py` rodado em `dev-map` no commit `bd15e39`.
  8 candidatos em `data/csv/patients.csv` (coluna `phone`, linhas 2–9):
  `(62) 99999-0001` a `(62) 99999-0008` — sequência idêntica no mesmo DDD,
  padrão claramente sintético do seed `scripts/seed_csvs.py` → `src.mock_data`.
  **Resolvido como falso-positivo.** Outros 7 candidatos foram nomes em
  filenames de `data/pacientes_e_planos/`, que está untracked e é
  ignorado pelo `.gitignore` (ver §3 do checklist) — também resolvido.
- [x] **Item 2** — `data/csv/*.csv` revisado: 11 tabelas, todas seed do
  `mock_data.py`. Nomes de pacientes, DDD de telefone e datas são
  fictícios por construção. Sem PII real.
- [x] **Item 3** — `data/pacientes_e_planos/` continua untracked e
  **agora também está no `.gitignore`** (reforço contra `git add .`
  acidental). 14 PDFs com nomes reais permanecem no disco do dev,
  fora do repo.
- [x] **Item 4** — `data/images/` contém 7 PNGs nomeados por página
  (`Alertas.png`, `Croquis_SAD_DClinique.png`, `Ficha_paciente.png`,
  `Mapa_decisao.png`, `Pacientes.png`, `Painel_lateral.png`,
  `Qualidade_dados.png`, `Visao_geral.png`) e o diretório
  `icones_Croquis_SVG/`. **Confirmado pelo proprietário em 2026-06-08:**
  conteúdo é fictício (UI/design base), sem dado pessoal.

Se houver necessidade de processar os PDFs de
`data/pacientes_e_planos/`, o pipeline de extração pertence a um
worktree separado, e os artefatos resultantes **não** devem ir para o
repo.

## 3. Setup no Streamlit Community Cloud

1. Acessar <https://share.streamlit.io> e fazer login com a conta que
   hospeda o repositório.
2. **New app** → "From existing repo".
3. Selecionar:
   - **Repository:** `INNOVAI-LTDA/cli_dclinique` (ou fork).
   - **Branch:** `main` (após merge do PR de release).
   - **Main file path:** `app.py`.
   - **App URL:** slug a definir (ex.: `map-pacientes`).
4. Em **Advanced settings**:
   - **Python version:** 3.13 (vem de `.python-version`).
   - **Secrets:** deixar em branco por enquanto (colar em §4).
5. Clicar em **Deploy**. O primeiro build demora ~3-5 min; builds
   subsequentes são mais rápidos.

## 4. Configuração de secrets

Os secrets vivem no painel **Settings → Secrets** do app no Streamlit
Cloud, em formato TOML. O arquivo commitado
`.streamlit/secrets.toml.example` documenta o formato esperado
(chaves vazias e comentadas).

**Passos:**

1. No painel do app no Streamlit Cloud: **Settings → Secrets**.
2. Preencher apenas as seções que o código realmente consome. Em PRD:
   - ``[postgres]`` com a DSN do projeto Neon (ver §13).
   As secoes ``[supabase]`` e ``[integrations]`` continuam comentadas
   — Supabase nao e' mais o backend alvo.
3. Salvar. O app reinicia automaticamente.

**Regras:**

- O arquivo real `.streamlit/secrets.toml` é **gitignored**. Nunca
  commitar.
- No código, ler via `st.secrets["chave"]`, **nunca** via `os.environ` —
  o Streamlit Cloud só os expõe via `st.secrets`.
- Rotação: trocar no painel; commit não é necessário (e seria um
  vazamento).

## 5. Modelo de acesso — privado por lista de emails

A escolha deste projeto é **Private app + lista de emails convidados**,
não autenticação por login/senha. O gate de viewers é nativo do
Streamlit Cloud e **não** conta como "implementar login" do ponto de
vista do `CLAUDE.md`.

**Passos:**

1. No painel do app: **Settings → Sharing**.
2. Selecionar **"Only invited viewers"** (Private).
3. Em **"Invite viewers"**, adicionar o(s) email(s) do(s) cliente(s).
   Eles recebem um convite por e-mail e passam a ter acesso autenticado
   pela própria conta `streamlit.io`.

**Limitações conhecidas:**

- Cada viewer precisa ter (ou criar) uma conta `streamlit.io` com o
  email convidado.
- O plano Community (gratuito) tem **limite de viewers** por app; para
  uma equipe maior é upgrade de plano. Verificar a política atual no
  site da Streamlit.
- Não há grupos/roles; cada email é individual. Se o cliente trocar de
  time, é só remover o email da lista.

## 6. Validação local pré-deploy

Antes de pedir review do PR de release, rodar dentro do worktree:

```bash
# 1) Venv novo para validar pinos
python -m venv .venv-test
.venv-test/Scripts/python.exe -m pip install -r requirements.txt

# 2) Smoke do data layer
.venv-test/Scripts/python.exe -c "from src.data_layer import load_all; d=load_all(); print('OK', list(d.keys()))"

# 3) App sobe (Ctrl+C depois do "You can now view your Streamlit app")
.venv-test/Scripts/python.exe -m streamlit run app.py

# 4) scan_pii — esperado: exit 0 (ou 1 com lista de candidatos a revisar)
.venv-test/Scripts/python.exe scripts/scan_pii.py
```

Se qualquer um desses falhar, **não** publicar. O deploy só tem
significado se o smoke local passa.

## 7. Plano de rollback

O deploy é reversível. Ordem de preferência:

1. **Reverter o PR de release** (mantém histórico; é o caminho padrão).
   ```bash
   git revert <merge-commit-do-release>
   git push
   # O Streamlit Cloud rebuilda automaticamente.
   ```
2. **Deletar o app no Streamlit Cloud** (caso extremo, ou se o repo for
   descontinuado). Settings → Delete app. O snapshot some; o repo
   permanece intacto e pode ser republicado.

O rollback **não** afeta os dados do Neon — eles vivem no projeto
Neon provisionado, nao no servidor do Streamlit. Para desfazer
escritas em runtime (e.g., apagar um paciente), usar o console
Neon (SQL editor) ou restaurar de backup. Em emergencia: deletar
e recriar o branch de teste (testes) ou o schema inteiro (PRD).

## 8. Limites conhecidos

- **Cold start ≈ 2,5 s** — limitação do framework Streamlit (não do
  código). Detalhes em `SLA_REPORT.md` §5.
- **Neon cold start ≈ 500 ms** — o compute do Neon escala a zero
  apos ~5 min de inatividade. O primeiro request apos esse intervalo
  paga o wakeup. Detalhes em `SLA_REPORT.md` §6.
- **Sem login próprio** — o gate é o de viewers do Streamlit Cloud.
  Quando o projeto migrar para Supabase, esse gate provavelmente vira
  desnecessário (o Supabase traz seu próprio auth).
- **HTTPS** é provido pela plataforma; não há domínio customizado
  configurável sem upgrade.
- **Sem parser real de PDF/Excel, Supabase, WhatsApp, Google Drive** —
  continua fora do escopo do `CLAUDE.md`. Esta preparação não muda
  nada disso.

## 9. Arquivos de configuração envolvidos

| Arquivo | Papel no deploy |
|---|---|
| `.python-version` | Streamlit Cloud escolhe Python 3.13 |
| `requirements.txt` | Pinos com compatible release + `psycopg[binary]>=3.2,<4` |
| `.streamlit/config.toml` | Postura de produção: `headless`, `gatherUsageStats=false`, `maxUploadSize=50` |
| `.streamlit/secrets.toml.example` | Documenta o formato dos secrets (o real é gitignored) — agora inclui `[postgres]` |
| `.gitignore` | Exclui `secrets.toml`, `.env`, `data/private/`, `data/pacientes_e_planos/`, `data/test_logs/` |
| `src/data_layer/postgres_backend.py` | Backend Postgres (DCLINIQUE_BACKEND=postgres) — 6 funções públicas idênticas a `csv_backend.py` |
| `src/data_layer/connection.py` | `get_engine()` lazy, cacheado por `@st.cache_resource`, lê DSN de `st.secrets["postgres"]["dsn"]` ou env var |
| `src/data_layer/schema.py` | `to_ddl()` + `init_schema()` — converte `EXPECTED_SCHEMAS` em DDL Postgres idempotente |
| `scripts/init_neon_schema.py` | Bootstrap one-shot do schema no Neon (idempotente) |
| `scripts/make_synthetic_pdf.py` | Gera PDF PII-clean (entregue ao cliente para primeiro teste de import) |
| `scripts/scan_pii.py` | Ferramenta auxiliar do gate de LGPD |
| `DEPLOY.md` (este) | Guia de release + §13 sobre Neon |
| `README.md` | Aponta para este guia na seção "Deploy" |
| `CLAUDE.md` | Marca o deploy como exceção documentada, com gate de LGPD obrigatório |

## 10. Release inicial — 2026-06-08

| Campo | Valor |
|---|---|
| Branch de origem | `dev-map` (após PR `feature-streamlit-deploy-prep` mergeado) |
| Branch de deploy | `main` |
| Slug do app | `deva-dclinique` |
| URL | `https://deva-dclinique.streamlit.app` |
| Modelo de acesso | Private + lista de emails convidados |
| Convidados (self) | `carreira.outlier@gmail.com` |
| Convidados (cliente) | `jaderbraz@gmail.com` |
| Dono / admin | `carreira.outlier@gmail.com` |
| Stack | Python 3.13, Streamlit 1.58.0, pandas 3.0.3, plotly 6.7.0+, openpyxl 3.1.5 |
| Secrets | nenhum configurado (nenhuma chamada a `st.secrets` no `src/`) |

**Plano de acesso gradual:**

1. Após PR mergeado e app criado, **só você** está convidado.
   Valida o boot, navegação, deep-link, latência.
2. Se smoke passa, **convida o cliente** (`jaderbraz@gmail.com`).
3. Cliente interage, dúvidas surgem — você é o ponto de triagem.
4. Próximas rodadas (Supabase, escala, multi-tenant) acontecem **depois**
   desse ciclo, com a base de uso real para guiar decisões.

**Plano de rollback** (caso o smoke falhe): ver §7.

## 11. Atualização de schema em runtime

Alem do gate de LGPD antes de publicar, qualquer mudanca em
``src/schemas.py:EXPECTED_SCHEMAS`` exige:

1. Atualizar o schema do Neon (via ``init_schema()`` que e'
   idempotente — ``CREATE TABLE IF NOT EXISTS``). Para mudancas
   destrutivas (drop column, change type), escrever migration manual
   via SQL editor do Neon.
2. Atualizar os 11 CSVs em ``data/csv/`` (header) para que o backend
   CSV (dev local) e o Postgres (PRD) compartilhem o mesmo schema.
3. Atualizar ``tests/conftest.py`` se algum fixture depender do
   shape das tabelas.

## 12. Como rodar localmente apontando para o Neon

Para dev local com Neon (em vez de CSVs):

```bash
# .env (gitignored)
export NEON_DSN="postgresql://user:pass@ep-xxx.<region>.neon.tech/dclinique?sslmode=require"

# Rodar
DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe -m streamlit run app.py
```

Para dev local sem internet (fallback CSV):

```bash
DCLINIQUE_BACKEND=csv .venv/Scripts/python.exe -m streamlit run app.py
```

## 13. Neon Postgres (fonte de verdade em PRD)

Em PRD o app NAO usa mais os CSVs em ``data/csv/`` — o backend ativo
e' o ``postgres_backend`` (DCLINIQUE_BACKEND=postgres), apontando para
um projeto Neon Serverless Postgres. Os CSVs viraram **schema
reference** (header only, 0 linhas; verifique com
``head -1 data/csv/patients.csv``).

> **Runbook detalhado:** para o passo-a-passo operacional completo
> (provisionamento, DSN/API key/Project ID, .env local, bootstrap
> do schema, smoke test, secrets do Streamlit Cloud, cold start,
> rotação de credenciais, troubleshooting), ver
> [**`NEON_SETUP.md`**](NEON_SETUP.md). Esta seção e' o resumo; o
> runbook e' a referência operacional.

**Provisionamento (manual, fora do codigo):**

1. Criar conta em <https://neon.tech>.
2. Criar projeto ``dclinique-prod``. Regiao sugerida:
   ``aws-sa-east-1`` (Sao Paulo, quando disponivel); fallback
   ``aws-us-east-2`` (Ohio). Confirmar com o usuario antes de
   provisionar — LGPD exige atencao a regiao para dados de saude.
3. No branch ``main``: copiar a **DSN** do painel (Connection
   string → pooler ou direct, ambos funcionam).
4. Criar **API key** (Settings → API keys). Anotar.
5. Anotar o **Project ID** (Settings → General). Usado pelo
   ``db_branch`` fixture em testes para criar branches efemeros.

**Variaveis de ambiente (local; em PRD vao para os secrets do app):**

```bash
NEON_DSN="postgresql://user:pass@ep-xxx.<region>.neon.tech/dclinique?sslmode=require"
NEON_API_KEY="<api-key>"
NEON_PROJECT_ID="<project-id>"
```

**Schema bootstrap (one-shot, apos provisionar):**

```bash
# Dentro do worktree, com NEON_DSN setado:
DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe scripts/init_neon_schema.py
```

Saida esperada: ``[OK] 11/11 tables created (or already exist)``.
Exit code 0 = sucesso; 1 = DSN ausente; 2 = DB fora do ar.

**Smoke test do data layer contra Neon:**

```bash
DCLINIQUE_BACKEND=postgres .venv/Scripts/python.exe -c \
  "from src.data_layer import load_all; d=load_all(); print(list(d.keys()), {k: len(v) for k,v in d.items()})"
```

Esperado: 11 chaves, 0 linhas em cada tabela (base zerada).

**Cold start do Neon (importante):** o compute do Neon escala a zero
apos ~5 min de inatividade. O primeiro request apos esse intervalo
paga **~500 ms adicionais** para acordar o compute (wakeup + SSL
handshake + query). Medir e atualizar ``SLA_REPORT.md §6`` com dados
reais. Mitigacao se virar problema: upgrade do plano Neon para um
tier sem auto-suspend.

**Limites do free tier:** 191.9 horas/mes de compute. Para o piloto
do cliente e' folgado; se virar gargalo, upgrade preventivo
(Launch tier ~$20/mes).

**LGPD — dados em terceiro:** dados reais do cliente vao morar em
Neon. Adicionar item de sign-off (item 5 do gate). Avaliar se a
regiao ``aws-sa-east-1`` (Sao Paulo) e' aceitavel para a operacao
brasileira antes de provisionar.

**Testes de integracao:** ``tests/conftest.py`` ganhou a fixture
``db_branch`` (session-scoped) que cria um branch Neon via API
para a sessao de testes e deleta no teardown. Requer ``NEON_API_KEY``
+ ``NEON_PROJECT_ID`` no env. Sem esses, o fixture faz ``pytest.skip``
e os testes caem no fallback ``csv_dir``.
