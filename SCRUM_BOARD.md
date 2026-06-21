# Scrum Board — PRD Cleanup (Neon Postgres)

Última atualização: 2026-06-18

## Visão
Trocar a fonte de verdade de CSVs para Postgres no Neon, deixar as 11 tabelas
vazias no primeiro boot, atualizar 8 testes e a documentação de release.

## Definition of Done (DoD)
- `python scripts/run_scrum_tests.py` retorna exit 0
- Log em `data/test_logs/scrum_<timestamp>.log` sem entradas `FAIL`
- `python scripts/scan_pii.py` retorna exit 0
- `DEPLOY.md` tem §12 (Neon) e §2 item 5 (sign-off) preenchidos
- App roda em PRD: `DCLINIQUE_BACKEND=postgres streamlit run app.py`
  com DSN em `st.secrets["postgres"]["dsn"]`, 11 tabelas vazias

## Convenções
- Cada task atômica = ≤ 1 arquivo novo OU ≤ 1 arquivo modificado (exceto T15)
- Cada task tem 1 test script em `scripts/test_TN.py`
- O test runner (`scripts/run_scrum_tests.py`) orquestra todos
- Log estruturado: `[ISO timestamp] LEVEL TID message` por linha
- `Expected:` vs `Got:` em todo FAIL, para o agente ler do log
- Tasks independentes podem ser batched; dependências em "Ordem" abaixo

## Rigor & Quality Gates

Aplicado a partir de T3 (após erros de T2 "module not found" e T3 "module
not found pandas"). O objetivo é prevenir replicação da natureza dos erros:
**deps transitivas escondidas no import graph que só explodem no test**.

### Princípios para o código de produção (`src/`, `scripts/`)

1. **Sem imports eager de pacotes pesados.** `psycopg`, `streamlit`,
   `pandas`, `requests`, etc. ficam dentro de funções, não no topo do
   módulo. Já aplicado:
   - `connection.py`: `_import_psycopg()` e `import streamlit as st` em
     `_read_dsn()` são lazy.
   - `schema.py` (T3 retroativo): `from src.schemas import EXPECTED_SCHEMAS`
     foi movido para dentro de `init_schema()`. O módulo agora carrega sem
     pandas.

2. **Import graph documentado no docstring.** Cada novo módulo traz no
   docstring a lista de deps que o `import` do módulo dispara
   transitivamente. Exemplo em `schema.py`:
   > "Transitive imports: src.schemas é lazy (dentro de init_schema) para
   > que carregar este módulo NÃO puxe pandas via `src/schemas.py:4`."

3. **Erros explícitos.** Funções públicas levantam exceções com tipo
   específico (`RuntimeError`, `ValueError`, `KeyError`) e mensagem
   acionável (menciona o que o caller deve checar/configurar).

### Princípios para os scripts de teste (`scripts/test_TN.py`)

1. **Mock de deps transitivas em `sys.modules` ANTES do load.** Stub
   mínimo (apenas os atributos que o módulo target usa em type hints
   ou em runtime).

2. **`spec_from_file_location`, não `importlib.import_module`.** O
   subprocess do runner tem `sys.path[0] = scripts/`, não a raiz do
   worktree.

3. **Adicionar raiz do worktree ao `sys.path` cedo.** Para que
   `from src.x import y` resolva o pacote `src`.

4. **Helpers compartilhados em `scripts/_test_harness.py`** (criado em
   T3 retroativo):
   - `load_module_for_test(file, name, stubs)` — carrega o módulo
     aplicando stubs em `sys.modules` antes do `exec_module`.
   - `make_pandas_stub()` — `sys.modules["pandas"]` mínimo, com
     `DataFrame` exposto (suficiente para type hints).
   - `make_psycopg_stub()` — `sys.modules["psycopg"]` mínimo, com
     `connect`, `Connection`, `Cursor` (suficiente para `import psycopg`).
   - `make_streamlit_stub()` — `sys.modules["streamlit"]` mínimo, com
     `secrets`, `cache_data`, `cache_resource` como no-ops.

5. **FAIL messages com `Expected:` / `Got:` / `Fix:`** — copiáveis para
   o log e identificáveis pelo agente.

### Pre-análise de import graph (rodar antes de escrever cada arquivo)

Antes de criar `xxx.py`, listar mentalmente:
  - O que o módulo importa diretamente?
  - O que cada import dispara transitivamente?
  - Quais dessas deps podem não estar no venv de teste?
  - Quais precisam de mock no `sys.modules`?

A análise concreta para T4 (`postgres_backend.py`) está na seção
"T4 import graph" abaixo.

## Ordem de execução
```
T1 (deps) → T2 (connection) → T3 (schema) → T4 (backend) → T5 (init script)
T6 (synthetic PDF) — depende de T1
T7 (router) → T8 (wire app) → T9 (wipe CSVs)
T10 (conftest) → T11-T14 (test updates)
T15 (docs) — independente, fazer por último
```

## Backlog
*(vazio — todas as tasks estão priorizadas no Sprint)*

## Todo
- [x] **T1** Adicionar `psycopg[binary]>=3.2,<4` em `requirements.txt`
- [x] **T2** Criar `src/data_layer/connection.py` com `get_engine()` lazy + cache
- [x] **T3** Criar `src/data_layer/schema.py` com `to_ddl()` e `init_schema()`
- [x] **T4** Criar `src/data_layer/postgres_backend.py` (6 funções públicas: `load_all`, `load_table`, `append_row`, `update_row`, `next_id`, `csv_dir` — API idêntica a `csv_backend.py`)
- [x] **T5** Criar `scripts/init_neon_schema.py` (bootstrap one-shot)
- [x] **T6** Criar `scripts/make_synthetic_pdf.py` (PDF PII-clean para o cliente)
- [x] **T7** Atualizar `src/data_layer/__init__.py` (router Postgres/CSV)
- [x] **T8** Verificar `app.py:get_data()` (sem mudança esperada)
- [x] **T9** Limpar `data/csv/*.csv` (11 arquivos → header only, 0 linhas)
- [x] **T10** Atualizar `tests/conftest.py` (fixture `db_branch` Neon API)
- [x] **T11** Atualizar `tests/test_add_patient_unit.py` (assertions de count)
- [x] **T12** Atualizar `tests/test_pdf_importer.py` (assertions de count)
- [x] **T13** Atualizar `tests/test_integration.py` (substituir `pat_001` por setup)
- [x] **T14** Atualizar `tests/test_ficha_unit.py` (seed-dependência no setup)
- [x] **T15** Atualizar `DEPLOY.md` + `secrets.toml.example` + `SLA_REPORT.md` + `README.md`

## Doing
*(vazio — sprint completo)*

## Learnings
- **T2 — `spec_from_file_location` em vez de `importlib.import_module`.** O subprocess do
  runner tem `sys.path[0] = scripts/`, não a raiz do worktree. `importlib.import_module("src.x")`
  falha por não encontrar `src` (namespace package). Usar
  `importlib.util.spec_from_file_location(mod_name, str(FILE.resolve()))` carrega o arquivo
  diretamente. Adicionar também a raiz do worktree ao `sys.path` antes do load, para que
  dependências transitivas (`from src.schemas import ...`) resolvam o pacote `src`.
- **T3 — mockar deps transitivas em `sys.modules` antes do load.** Quando o módulo target
  importa transitivamente um pacote que não está instalado (ex.: `schema.py` →
  `src.schemas` → `import pandas as pd`), o test quebra antes de qualquer asserção. Stub
  mínimo em `sys.modules[<dep>] = types.ModuleType(...)` antes do
  `spec.loader.exec_module(mod)` satisfaz o `import` sem exigir o pacote real. O stub só
  precisa expor o que o módulo target usa em type hints / atributos (ex.: `pd.DataFrame`).
  Aplicar o mesmo padrão em T4 (`postgres_backend.py` → `connection.py` → `import psycopg`
  via lazy, mas vale mockar pra garantir; também `app.py` → `load_all` → etc.).
- **T4 — semântica de `pathlib.Path` é platform-specific.** `Path("postgres://neon")` no
  POSIX retorna `PosixPath('postgres://neon')` (preserva `//`); no Windows
  interpreta `//` como UNC path prefix e retorna `WindowsPath('postgres:/neon')`
  (uma barra só). `Path("postgres:neon")` no Windows é drive letter. Para sentinels
  que precisam funcionar em ambos: usar path relativo sem `:` nem `//` (ex.:
  `Path("postgres-neon")`). Testes que checam `str(data_dir())` precisam conhecer
  essa diferença.
- **T7 — stdout do Windows usa cp1252 por padrão.** `print(f"... → ...")` com `→`
  (U+2192) ou `—` (U+2014) levanta `UnicodeEncodeError: 'charmap' codec can't
  encode character` quando o console do Windows e' cp1252. Comentarios e
  docstrings aceitam Unicode (Python le o .py como UTF-8); o problema e'
  APENAS no print. Fix: usar ASCII em prints — `->` em vez de `→`, `--` em
  vez de `—`, `...` em vez de `…`. Validei com grep em todos os test_T*.py.

## T4 import graph (postgres_backend.py)

Análise concreta feita antes de escrever T4, conforme a seção "Rigor &
Quality Gates". Resultado: o import graph do `postgres_backend.py` alvo
puxa apenas deps lazy, mas o test T4 ainda precisa mockar `psycopg` e
`streamlit` para garantir isolamento.

```
postgres_backend.py
├── from src.data_layer.connection import get_engine, reset_engine
│   └── _import_psycopg()    — lazy (não dispara no import do módulo)
│   └── import streamlit as st (em _read_dsn) — lazy
├── from src.data_layer.schema import init_schema, to_ddl
│   └── from src.schemas import EXPECTED_SCHEMAS (em init_schema) — lazy
│       └── import pandas as pd  — lazy (só dispara se init_schema for chamado)
└── (sem outros imports eager)
```

**Conclusão:**
- Carregar `postgres_backend.py` no test NÃO deve disparar nenhum import
  de psycopg/pandas/streamlit (todos são lazy). Mas:
- O test T4 deve mockar `psycopg`, `streamlit` e (por defesa) `pandas` em
  `sys.modules` ANTES do load, usando `load_module_for_test` do
  `scripts/_test_harness.py`.
- Se a regra "sem imports eager" for quebrada em algum ponto futuro, o
  test T4 quebra imediatamente, expondo o problema.

**Mock requirements para test_T4.py:**
```python
from _test_harness import load_module_for_test, make_pandas_stub
from _test_harness import make_psycopg_stub, make_streamlit_stub

mod = load_module_for_test(
    Path("src/data_layer/postgres_backend.py"),
    "src.data_layer.postgres_backend",
    stubs={
        "pandas": make_pandas_stub(),
        "psycopg": make_psycopg_stub(),
        "streamlit": make_streamlit_stub(),
    },
)
```

## Done
- [x] **T1** Adicionar `psycopg[binary]>=3.2,<4` em `requirements.txt`
- [x] **T2** Criar `src/data_layer/connection.py` com `get_engine()` lazy + cache
   - **Learning T2:** testes rodam como subprocess (`subprocess.run(..., cwd=ROOT)`),
     e o `sys.path[0]` do subprocess é `scripts/`, não a raiz. Não usar
     `importlib.import_module("src.x.y")` — usar `importlib.util.spec_from_file_location`
     e também adicionar a raiz do worktree ao `sys.path` pra resolver
     dependências transitivas (`from src.schemas import ...`).
- [x] **T3** Criar `src/data_layer/schema.py` com `to_ddl()` e `init_schema()`
   - **Learning T3:** quando o módulo target importa transitivamente um pacote
     não instalado (ex.: `schema.py` → `src.schemas` → `import pandas as pd`),
     o test quebra antes de qualquer asserção. Stub em `sys.modules[<dep>]`
     ANTES de `spec.loader.exec_module` resolve sem instalar nada. O stub só
     precisa expor o que o módulo target usa (ex.: `pd.DataFrame` para type
     hints). Padrão vale para T4-T14.
   - **Refactor retroativo:** `from src.schemas import EXPECTED_SCHEMAS` foi
     movido de top-level para dentro de `init_schema()`. O módulo agora
     carrega sem pandas; só a chamada a `init_schema()` precisa do catálogo.
- [x] **T4** Criar `src/data_layer/postgres_backend.py` (6 funções públicas)
   - **Learning T4 — pathlib.Path é platform-specific.** `Path("postgres://neon")` no
     POSIX preserva `//`; no Windows interpreta como UNC path e retorna
     `WindowsPath('postgres:/neon')` (uma barra). `Path("postgres:neon")` no Windows
     é drive letter. Para sentinels cross-platform, evitar `:` e `//` no path literal.
   - **Rigor aplicada:** spy em `psycopg.connect` no test confirma que carregar
     o módulo não dispara conexão (todos os imports de deps pesadas são lazy).
     _validate_table/_columns_for rejeitam nomes fora de EXPECTED_SCHEMAS
     (defesa contra SQL injection via nome de tabela).
- [x] **T5** Criar `scripts/init_neon_schema.py` (bootstrap one-shot)
   - Idempotente (CREATE TABLE IF NOT EXISTS). Exit codes: 0/1/2 para
     sucesso/DSN-ausente/DB-down. Test usa FakeEngine + patch.object para
     validar os 3 caminhos sem DB real.
- [x] **T6** Criar `scripts/make_synthetic_pdf.py` (PDF PII-clean para o cliente)
   - Dados hardcoded (Maria Teste da Silva, 12345678, Emagrecimento) —
     commitaveis sem risco LGPD. PyMuPDF (fitz) lazy. `make_fitz_stub()`
     adicionado ao harness (FakeDoc com `save()` que escreve %PDF-1.4
     para que o test verifique o header).
- [x] **T7** Atualizar `src/data_layer/__init__.py` (router Postgres/CSV)
   - Router lazy com cache por processo; 7 wrappers; `reset_backend_cache()`
     para testes. Rigor check: apos load, nenhum backend em sys.modules.
   - **Learning T7 — stdout do Windows usa cp1252 por padrao.** `print(f"... → ...")`
     levanta `UnicodeEncodeError` no console. Comentarios e docstrings aceitam
     Unicode; APENAS prints vao para stdout e quebram. Fix: ASCII em prints
     (`->` em vez de `→`, `--` em vez de `—`, `...` em vez de `…`). Validado
     com grep em todos os test_T*.py.
- [x] **T8** Verificar `app.py:get_data()` (sem mudança esperada)
   - Sem mudanca de codigo. Test verifica que o router do T7 e' transparente
     para o app.py: `from src.data_layer import load_all` continua funcionando
     e resolve para o backend ativo.
   - **Learning T8 — `inspect.getsource()` para verificar lazy import.** Testes
     comportamentais nao distinguem "load acontece no import" de "load acontece
     na primeira chamada da funcao". Para verificar que `from X import Y` esta'
     dentro do corpo da funcao (e nao no top-level), usar `inspect.getsource(fn)`
     e checar a string do source.
- [x] **T9** Limpar `data/csv/*.csv` (11 -> header only, 0 linhas)
   - Destructive but idempotent. CSVs agora sao so' schema reference; Postgres
     e' a fonte de verdade em PRD. `seed_csvs.py` ainda funciona pra repopular
     (uso de dev local).
- [x] **T10** Atualizar `tests/conftest.py` (fixture `db_branch` Neon API)
   - Helpers `_has_neon_creds()` e `_should_use_csv()` decidem CSV vs Neon.
     Fixture `db_branch` e' session-scoped: cria branch via Neon API, exporta
     DSN como `DCLINIQUE_DSN`, deleta no teardown. `pytest.skip` quando CSV
     mode ou sem creds (NAO falha — teste cai no fallback `csv_dir`).
   - **Learning T10 — `pytest.fixture` decorator precisa de stub mais
     completo.** T10 falhou com `ModuleNotFoundError: No module named 'pytest'`
     porque o conftest importa pytest no top-level. Stub minimo adicionado
     ao harness: `make_pytest_stub()` expoe `pytest.fixture(scope=...)` e
     `pytest.skip(msg)`. O decorator retorna wrapper com
     `_pytestfixturefunction.scope` e `__wrapped__` para que tests
     detectem fixtures via `getattr(fn, '_pytestfixturefunction')` e leiam
     o source via `inspect.getsource(fn.__wrapped__)`. Vale pra T11-T14
     (outros tests em `tests/test_*.py` tambem importam pytest).
   - **Learning T10b — `pytest.fixture` tem 2 call patterns.** Em Python,
     `@pytest.fixture` e' sugar para `func = pytest.fixture(func)`, ou
     seja, a funcao e' passada como primeiro arg posicional. O stub
     precisa detectar isso: se o primeiro arg for callable e nao houver
     kwargs, retorna o wrapper direto; caso contrario, retorna um
     decorator que captura `scope` e ignora outros kwargs (autouse,
     params, ids, name).
- [x] **T11** Atualizar `tests/test_add_patient_unit.py` (assertions de count)
   - 6 assertions de count atualizadas: 8/9/10 -> 0/1/2. Test
     `includes_seed_patients` reescrito como `starts_empty` (verifica
     `keys == set()`). Test `rejects_duplicate_name` reescrito:
     pre-existencia agora e' construida via `append_row` no setup.
   - **Learning T11a — regex para `len(...) == N` quebra com parenteses
     aninhados.** Pattern `len\([^)]*\) == N` para no primeiro `)`,
     entao `len(load_table("patients")) == 0` nao casa. Solucao:
     abordagem por linha — para cada linha com `len(` e `==`, extrai
     o N depois do `==` (nao tenta casar o `len(...)` completo).
   - **Learning T11b — `if name in text_lower` em test estrutural
     tambem pega comentarios/docstrings.** O test rejeitava qualquer
     ocorrencia de "kelly" no arquivo, inclusive em docstrings que
     explicavam a mudanca. Solucao: docstrings devem ser reescritas
     sem mencionar nomes PII do seed por nome proprio, mesmo que
     seja em contexto historico.
- [x] **T12** Atualizar `tests/test_pdf_importer.py` (N/A — arquivo nao existe)
   - O plan referenciava ``tests/test_pdf_importer.py`` mas o arquivo
     NAO existe neste worktree. O wizard de import de PDF e' um
     placeholder visual (``st.file_uploader(..., help="...os arquivos
     nao serao lidos.")`` em ``src/pages/atualizacao_dados.py:12``).
     Cobertura automatizada do wizard vive em outros worktrees
     (``feature-pdf-ingest``), NAO aqui. Test_T12 serve como audit
     trail documentando a ausencia e o motivo.
- [x] **T13** Atualizar `tests/test_integration.py` (substituir `pat_001` por setup)
   - 3 tests reescritos: `link_targets_ficha_when_patient_already_has_ficha`,
     `cadastro_redirects_to_ficha_if_patient_already_has_one`,
     `add_patient_form_rejects_duplicate_name`. Todos agora constroem a
     pre-existencia via `_register_patient_via_form` (e o redirect test
     tambem via `append_row` para o plan pre-existente).
   - **Learning T13 — mesma licao de T11b.** Docstrings que explicam a
     mudanca nao podem mencionar nomes PII do seed por nome proprio.
     Usar descricao generica ("um paciente do seed") em vez do nome.
- [x] **T14** Atualizar `tests/test_ficha_unit.py` (seed-dependencia no setup)
   - Refactor massivo: adicionado helper ``_register_patient(name, age) -> pid``
     que substitui a dependencia do ``pat_001`` do seed. 14 tests reescritos;
     counts atualizados (8/9/15/16/17/19 -> 0/1/2). ``test_next_item_id_avoids_
     existing_seed_ids`` agora pre-popula com item_new_001 e verifica que
     next_id retorna item_new_002 (prova real, nao trivial).
   - **Learning T14 — Edit em arquivo longo pode duplicar conteudo.** T14
     falhou na primeira tentativa com "pat_001" ainda aparecendo. Causa:
     o ``old_string`` no Edit cobria as primeiras 225 linhas mas o arquivo
     tinha sido modificado e o match foi parcial, deixando o conteudo
     antigo no final. Sintoma: arquivo com 498 linhas (2x do esperado).
     Solucao: usar ``Write`` (full rewrite) em vez de ``Edit`` quando o
     refactor toca mais de 70% do arquivo.
- **T15 — extrair body de secao com regex, nao ``re.search().group(0)``.** A
  primeira versao do test_T15.py usava ``re.search(REGEX, text).group(0)`` para
  capturar o corpo de uma secao. Isso so' retorna o trecho *que deu match* —
  nao tudo ate' a proxima secao. Sintoma: "sec6 nao menciona 500 ms" mesmo
  com "500 ms" presente no arquivo. Solucao: extrair o corpo com
  ``re.compile(rf"^##\s+{n}\.\s+.*?(?=^##\s+\d+\.\s+|\Z)", re.DOTALL|MULTILINE)``
  — o ``.*?`` lazy garante que o match para na proxima secao ``## N.``.
- **T15 — `re.escape` emeca padroes regex que o caller nao pretendia.** O helper
  ``_has_section(text, anchor)`` chamava ``re.escape(anchor)`` mesmo quando o
  caller passava um padrao regex (``r"Atualiza.{0,3}o"``). Resultado: o
  ``.`` virou ``\.`` e as chaves viraram ``\{0,3\}`` — nunca casava com
  "Atualizacao". Solucao: helper de busca por secao usa um substring
  literal (nao regex) e o caller passa texto simples, nao padroes.
