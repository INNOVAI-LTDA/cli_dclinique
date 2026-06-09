# DEPLOY — Guia de release no Streamlit Community Cloud

> **Status desta versão:** os artefatos para deploy estão **preparados**
> (`.python-version`, `requirements.txt` com pinos, `.streamlit/config.toml`,
> `.streamlit/secrets.toml.example`, `scripts/scan_pii.py`, este guia).
> **Nenhum deploy efetivo foi feito.** O deploy real só deve acontecer
> depois que o gate de LGPD abaixo for fechado.

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
2. Preencher apenas as seções que o código realmente consome. Hoje
   nenhuma (o `src/` não chama `st.secrets` em lugar nenhum) — esta
   etapa é preventiva para a fase de Supabase.
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

O rollback **não** afeta os dados de `data/csv/` — eles vivem no repo
versionado, não no servidor do Streamlit.

## 8. Limites conhecidos

- **Cold start ≈ 2,5 s** — limitação do framework Streamlit (não do
  código). Detalhes em `SLA_REPORT.md` §5.
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
| `requirements.txt` | Pinos com compatible release para build reprodutível |
| `.streamlit/config.toml` | Postura de produção: `headless`, `gatherUsageStats=false`, `maxUploadSize=50` |
| `.streamlit/secrets.toml.example` | Documenta o formato dos secrets (o real é gitignored) |
| `.gitignore` | Exclui `secrets.toml`, `.env`, `data/private/` |
| `scripts/scan_pii.py` | Ferramenta auxiliar do gate de LGPD |
| `DEPLOY.md` (este) | Guia de release |
| `README.md` | Aponta para este guia na seção "Deploy" |
| `CLAUDE.md` | **Não** toca em deploy — restrição permanece até o release real |
