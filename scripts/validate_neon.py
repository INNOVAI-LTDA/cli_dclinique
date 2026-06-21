"""scripts/validate_neon.py -- Smoke test end-to-end para o data layer Neon.

Faz 4 checks contra um banco Neon real (NAO contra mocks):

  1. CONECTIVIDADE -- abre um psycopg.Connection via
     `src.data_layer.connection.get_engine()` e roda `SELECT 1`.
  2. SCHEMA        -- chama `src.data_layer.schema.init_schema()` (idempotente)
     e confirma que as 11 tabelas estao presentes em `pg_tables`.
  3. CRUD          -- para cada uma das 11 tabelas:
       a. INSERT  -- `append_row(...)` com um registro sintetico cujo
                    `patient_id` aponta para um "test patient" compartilhado
                    (cleanup por `patient_id LIKE 'pat_test%'`).
       b. UPDATE  -- `update_row(...)` em uma coluna TEXT nao-PK; verifica
                    via SELECT que a mudanca persistiu.
       c. DELETE  -- DELETE direto no cursor; verifica que a linha sumiu.
  4. CLEANUP       -- varredura final com DELETE defensivo em todas as
     tabelas (chaveado por `patient_id LIKE 'pat_test%'`), e confirmacao
     via COUNT(*) de que nao restou registro de teste.

O script e' nao-destrutivo: o bloco try/finally em `main()` garante
que o cleanup rode mesmo que o CRUD exploda no meio, deixando o banco
no mesmo estado em que entrou.

Log estruturado
---------------
Toda linha emitida vai para dois destinos:
  1. Stream: stdout para INFO, stderr para WARN/ERROR.
  2. Arquivo: `data/test_logs/neon_validate_<UTC-timestamp>.log`
     (criado em `data/test_logs/`; se a escrita falhar, segue so'
     no stream -- o warning aparece no stderr).

Formato:
  `[ISO timestamp] LEVEL validate-neon <message> [k=v k="v with spaces" ...]`

Valores que contem espaco, aspas, tab, ou `=` sao quotados com aspas
duplas; o `\\` e `"` internos sao escapados. Grep-friendly: `grep
'step=3' <log>` lista todas as linhas do step 3; `grep op=append_row`
filtra por operacao.

Mensagens de erro
-----------------
Cada ERROR carrega pelo menos: `step`, `op`, `expected`, `got`, `fix`.
Quando o erro e' de uma tabela especifica, tambem `table` (e `col`
quando o erro e' numa coluna). Segue a convencao do SCRUM_BOARD
(Learnings T10/T11: "FAIL messages com `Expected:` / `Got:` / `Fix:`
-- copiaveis para o log e identificaveis pelo agente"). Os valores
sao projetados para serem uteis tanto para humanos (terminal) quanto
para o agente que vai ler o log depois.

Uso:
  cd .claude/worktrees/feature-neon-data-layer
  DCLINIQUE_BACKEND=postgres \\
    NEON_DSN="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require" \\
    .venv/Scripts/python.exe scripts/validate_neon.py

  # O arquivo de log e' escrito em:
  #   data/test_logs/neon_validate_<UTC-timestamp>.log

Conveniencias de dev:
  - Se voce tem um `.env` na raiz do worktree com `NEON_DSN=` (ou
    `DCLINIQUE_DSN=`), carregue-o antes:
        bash:  set -a; source .env; set +a
        pwsh:  Get-Content .env | ForEach-Object { $kv = $_ -split '=',2; set-item -path "env:$($kv[0])" -value $kv[1] }
  - `DCLINIQUE_BACKEND=postgres` ativa o data layer Postgres (default
    no router e' csv; aqui forçamos postgres para validar o backend novo).

Wrapper PowerShell (recomendado para Windows)
---------------------------------------------
O script `scripts/run_validate_neon.ps1` automatiza o preparo
completo em PowerShell: cria `.venv` se faltar, instala
`requirements.txt` se pandas/psycopg nao estiverem presentes,
carrega o `.env`, seta `DCLINIQUE_BACKEND=postgres` e roda este
script. Idempotente (re-rodar e' seguro).

    # Do worktree root:
    pwsh scripts/run_validate_neon.ps1
    echo $LASTEXITCODE       # 0..5, mesma escala deste script

    # Com .env alternativo:
    pwsh scripts/run_validate_neon.ps1 -DsnPath .env.dev

    # Sem reinstalar (venv ja' tem tudo):
    pwsh scripts/run_validate_neon.ps1 -SkipInstall

Se o sistema bloquear a execucao do .ps1 por politica de seguranca:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

Exit codes:
  0 -- todos os checks passaram
  1 -- DSN nao configurado (env var ausente)
  2 -- falha de conectividade (rede, TLS, auth, SELECT 1 inesperado)
  3 -- falha de schema (init_schema explodiu ou tabela faltando)
  4 -- falha de CRUD (insert/update/delete em alguma tabela)
  5 -- falha de cleanup (registro de teste ficou no banco)

Transitive imports (todos lazy via `src.data_layer.*`):
  - psycopg       -- lazy em connection.get_engine
  - pandas        -- lazy em postgres_backend (DataFrame construction)
  - src.schemas   -- lazy em schema.init_schema e postgres_backend._columns_for

Carregar este script NAO dispara nenhum import externo alem de
`src.data_layer.*` (que tambem sao lazy). A primeira query acontece
quando `get_engine()` e' chamado em `main()`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from src.data_layer.connection import get_engine
from src.data_layer.postgres_backend import append_row, next_id, update_row
from src.data_layer.schema import init_schema

# `from src.schemas import EXPECTED_SCHEMAS` e' LAZY: feito dentro das
# funcoes que precisam do catalogo (`_check_schema`, `_check_crud`,
# `_row_for_table`, `_cleanup`). Carregar `src.schemas` no top-level
# dispararia `import pandas as pd` (de src/schemas.py:4) antes do
# `main()` rodar -- violaria o Rigor & Quality Gates do SCRUM_BOARD.


# Prefixo comum a todos os patient_id de teste. Cleanup usa isso como
# chave de varredura (LIKE 'pat_test%'). Manter prefixo curto e
# reconhecivel para que um eventual registro residual seja achado por
# um `SELECT * FROM patients WHERE patient_id LIKE 'pat_test%'`.
TEST_PATIENT_ID = "pat_test_001"
TEST_PLAN_ID = "plan_test_001"
TEST_PATIENT_PREFIX = "pat_test"

# PKs fixos por tabela, usados pelo _row_for_table. Os 5 surrogate
# prefixes do data layer (pat_new, plan_new, item_new, goal_new,
# w_new) NAO cobrem as 6 tabelas-satellite (execution_summary,
# appointments, appointment_items, satisfaction_entries, alerts,
# data_quality_issues) -- nessas tabelas o id vem de outro sistema
# (PDF importer, plan_items FK, etc.) e nao e' gerado por
# `next_id(table)`. Para o smoke test, hardcodamos um id por tabela
# e marcamos `patient_id` (e `plan_id` quando existir) com os
# TEST_* globais, para que a cleanup varredura
# `DELETE ... WHERE patient_id LIKE 'pat_test%'` apague tudo.
TEST_PKS: dict[str, str] = {
    "patients": "pat_test_001",
    "treatment_plans": "plan_test_001",
    "treatment_plan_items": "item_test_001",
    "execution_summary": "exec_test_001",
    "appointments": "appt_test_001",
    "appointment_items": "appt_item_test_001",
    "patient_goals": "goal_test_001",
    "weight_entries": "weight_test_001",
    "satisfaction_entries": "sat_test_001",
    "alerts": "alert_test_001",
    "data_quality_issues": "issue_test_001",
}


# Estado do log em arquivo. Setado por `_open_log_file()`, limpo por
# `_close_log_file()`. Se `_log_fh` for None, `_log()` escreve apenas
# no stream (caso a abertura do arquivo tenha falhado).
_log_path: Path | None = None
_log_fh: TextIO | None = None


def _fmt_value(v: Any) -> str:
    """Renderiza um valor de campo de log. Quota se contem espaco,
    aspas, tab, ou `=`; escapa `\\` e `"` internos. Caso contrario
    devolve a representacao `str()` crua (sem aspas), o que mantem o
    log limpo para valores simples como ids e contadores.
    """
    s = str(v)
    if any(c in s for c in ' "\t='):
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return s


def _log(level: str, msg: str, **fields: Any) -> None:
    """Emite uma linha de log estruturada no stream + (opcional) arquivo.

    Stream: stdout para INFO, stderr para WARN/ERROR.
    Arquivo (se `_log_fh` nao for None): mesma linha, append + flush.
    Falha de escrita no arquivo NAO quebra o script -- apenas perde
    aquela linha no log file.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [f"[{ts}]", level, "validate-neon", msg]
    if fields:
        kv = " ".join(f"{k}={_fmt_value(v)}" for k, v in fields.items())
        parts.append(kv)
    line = " ".join(parts)

    out = sys.stderr if level in ("WARN", "ERROR") else sys.stdout
    print(line, file=out, flush=True)

    if _log_fh is not None:
        try:
            _log_fh.write(line + "\n")
            _log_fh.flush()
        except Exception:
            # Nao derruba o script por causa de uma falha de IO no log.
            pass


def _open_log_file() -> Path | None:
    """Abre `data/test_logs/neon_validate_<UTC>.log` para write.

    Retorna o Path em caso de sucesso, ou None em caso de falha
    (nao-fatal: continua com log so' no stream). A primeira linha
    de log apos a abertura sera o `starting` no `main()`.
    """
    global _log_path, _log_fh
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = Path("data/test_logs") / f"neon_validate_{ts}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        _log_fh = path.open("w", encoding="utf-8", newline="\n")
        _log_path = path
        return path
    except Exception as e:
        print(
            f"[WARN] could not open log file: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        _log_fh = None
        _log_path = None
        return None


def _close_log_file() -> None:
    """Fecha o handle do log file. Idempotente."""
    global _log_path, _log_fh
    if _log_fh is not None:
        try:
            _log_fh.close()
        except Exception:
            pass
    _log_fh = None
    _log_path = None


def _check_connectivity(engine) -> tuple[bool, str]:
    """Abre um cursor e roda SELECT 1. Espera exatamente (1,)."""
    try:
        with engine.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
        if row != (1,):
            return False, f"SELECT 1 returned {row!r}, expected (1,)"
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _check_schema(engine) -> tuple[bool, str]:
    """Roda init_schema() e confirma 11 tabelas em pg_tables."""
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    try:
        init_schema(engine)
    except Exception as e:
        return False, f"init_schema: {type(e).__name__}: {e}"
    try:
        with engine.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            present = {r[0] for r in cur.fetchall()}
    except Exception as e:
        return False, f"pg_tables query: {type(e).__name__}: {e}"
    expected = set(EXPECTED_SCHEMAS.keys())
    missing = expected - present
    if missing:
        return False, f"tables missing after init_schema: {sorted(missing)}"
    return True, ""


def _row_for_table(table: str) -> dict:
    """Constroi um registro sintetico para `table` casando o schema.

    Estrategia: PK vem de `TEST_PKS[table]` (hardcoded, evita
    dependencia em `next_id` que so' funciona para 5 das 11 tabelas
    -- ver comentario em TEST_PKS). `patient_id` e `plan_id` (quando
    presentes no schema) sao fixos no test patient/plan, para que
    cleanup use `patient_id LIKE 'pat_test%'` em uma unica varredura.
    Demais colunas recebem NULL -- nenhum schema declara NOT NULL
    fora da PK, entao o INSERT e' valido em todas as 11 tabelas.
    """
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    columns = EXPECTED_SCHEMAS[table]
    row: dict = {columns[0]: TEST_PKS[table]}
    for col in columns[1:]:
        if col == "patient_id":
            row[col] = TEST_PATIENT_ID
        elif col == "plan_id":
            row[col] = TEST_PLAN_ID
        else:
            row[col] = None
    return row


def _check_crud(engine) -> tuple[bool, list[str]]:
    """INSERT/UPDATE/DELETE por tabela usando a API de producao.

    Para cada tabela:
      1. append_row com a row sintetica (production code path).
      2. SELECT para confirmar que a linha foi persistida.
      3. update_row em uma coluna TEXT nao-PK (se houver) e SELECT
         para confirmar a mudanca.
      4. DELETE direto no cursor; SELECT para confirmar que sumiu.

    Em caso de erro em uma tabela, coleta a mensagem e segue para a
    proxima (nao aborta o loop) para que o cleanup final tenha chance
    de rodar. Cada erro e' logado com `step=3 op=<acao> table=<tabela>
    expected=... got=... fix=...`.
    """
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    errors: list[str] = []
    for table in EXPECTED_SCHEMAS:
        try:
            row = _row_for_table(table)
            pk_col = EXPECTED_SCHEMAS[table][0]
            pk_val = row[pk_col]

            # 1. INSERT (production code path: append_row)
            try:
                append_row(table, row)
            except Exception as e:
                _log(
                    "ERROR", "FAIL",
                    step="3", op="append_row", table=table, pk=pk_val,
                    error=type(e).__name__, err_msg=str(e),
                    expected="INSERT executed",
                    got=f"{type(e).__name__}: {e}",
                    fix="checar tipos de coluna, conflitos de PK, permissoes DML no DSN",
                )
                errors.append(f"{table}: append_row: {type(e).__name__}: {e}")
                continue

            # 2. Verify INSERT
            with engine.cursor() as cur:
                cur.execute(
                    f"SELECT {pk_col} FROM {table} WHERE {pk_col} = %s",
                    (pk_val,),
                )
                if cur.fetchone() is None:
                    _log(
                        "ERROR", "FAIL",
                        step="3", op="select_after_insert", table=table, pk=pk_val,
                        sql=f"SELECT {pk_col} FROM {table} WHERE {pk_col} = %s",
                        expected="row found",
                        got="None",
                        fix="checar se a transacao foi commitada; psycopg usa autocommit=False, append_row usa `with engine:` que faz commit no success",
                    )
                    errors.append(f"{table}: INSERT nao persistiu (pk={pk_val!r})")
                    continue

            # 3. UPDATE: pega a primeira coluna TEXT nao-PK, nao-FK.
            # Usa o type map canonico de src.data_layer.schema pra
            # pular colunas TIMESTAMP/BOOLEAN/INTEGER/DOUBLE PRECISION --
            # o valor de teste (string) so' faz sentido em TEXT.
            from src.data_layer.schema import _postgres_type  # lazy
            text_cols = [
                c for c in EXPECTED_SCHEMAS[table][1:]
                if c not in ("patient_id", "plan_id")
                and _postgres_type(table, c) == "TEXT"
            ]
            if text_cols:
                target = text_cols[0]
                new_value = f"updated_{target}"
                try:
                    update_row(table, pk_col, pk_val, {target: new_value})
                except Exception as e:
                    _log(
                        "ERROR", "FAIL",
                        step="3", op="update_row", table=table, col=target,
                        pk=pk_val, new_value=new_value,
                        error=type(e).__name__, err_msg=str(e),
                        expected="UPDATE executed",
                        got=f"{type(e).__name__}: {e}",
                        fix=f"checar se a coluna {target!r} existe no schema; update_row ignora colunas fora de EXPECTED_SCHEMAS",
                    )
                    errors.append(
                        f"{table}: update_row: {type(e).__name__}: {e}"
                    )
                    continue
                with engine.cursor() as cur:
                    cur.execute(
                        f"SELECT {target} FROM {table} WHERE {pk_col} = %s",
                        (pk_val,),
                    )
                    got = cur.fetchone()
                if got is None or got[0] != new_value:
                    _log(
                        "ERROR", "FAIL",
                        step="3", op="select_after_update", table=table,
                        col=target, pk=pk_val, new_value=new_value,
                        expected=f"{target}={new_value}",
                        got=str(got[0] if got else None),
                        fix="update_row usa `with engine:` que faz commit no success; se got e' o valor antigo, a transacao nao foi commitada",
                    )
                    errors.append(
                        f"{table}: UPDATE nao persistiu "
                        f"(target={target!r}, got={got!r})"
                    )
                    continue

            # 4. DELETE (raw cursor; append_row/update_row nao expoem DELETE).
            # NAO usar `with engine:` -- psycopg 3 fecha a conexao no
            # `__exit__` (a menos que venha de ConnectionPool), o que
            # quebra a proxima iteracao. Com autocommit=True, o DELETE
            # e' auto-committed; so' precisamos do cursor.
            try:
                with engine.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {table} WHERE {pk_col} = %s",
                        (pk_val,),
                    )
            except Exception as e:
                _log(
                    "ERROR", "FAIL",
                    step="3", op="delete", table=table, pk=pk_val,
                    sql=f"DELETE FROM {table} WHERE {pk_col} = %s",
                    error=type(e).__name__, err_msg=str(e),
                    expected="DELETE executed",
                    got=f"{type(e).__name__}: {e}",
                    fix="checar constraints/FKs que bloqueiem o delete; coluna referenciada em outra tabela",
                )
                errors.append(f"{table}: delete: {type(e).__name__}: {e}")
                continue
            with engine.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {table} WHERE {pk_col} = %s",
                    (pk_val,),
                )
                if cur.fetchone() is not None:
                    _log(
                        "ERROR", "FAIL",
                        step="3", op="select_after_delete", table=table, pk=pk_val,
                        expected="row gone", got="row still present",
                        fix="DELETE foi executado em `with engine:` (commit on success); se a linha persiste, conferir transacao aberta em outro lugar",
                    )
                    errors.append(f"{table}: linha ainda presente apos DELETE")
        except Exception as e:
            _log(
                "ERROR", "FAIL",
                step="3", op="crud_loop", table=table,
                error=type(e).__name__, err_msg=str(e),
                expected="CRUD iter OK",
                got=f"{type(e).__name__}: {e}",
                fix="erro inesperado no loop; checar traceback completo (talvez schema/connection)",
            )
            errors.append(f"{table}: {type(e).__name__}: {e}")
    return (len(errors) == 0, errors)


def _cleanup(engine) -> tuple[bool, str]:
    """Varredura final: apaga qualquer registro de teste residual.

    Itera as 11 tabelas e roda DELETE direto onde `patient_id LIKE
    'pat_test%'`. Cada DELETE roda em sua propria transacao (`with
    engine:` por iteracao) -- se uma tabela falhar, as outras ainda
    commitam. Fazer a varredura em todas as tabelas (e nao so' em
    `patients`) porque as FKs logicas fazem com que tabelas-satellite
    possam ter `patient_id` mesmo sem o paciente existir.
    """
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    try:
        for table in EXPECTED_SCHEMAS:
            if "patient_id" in EXPECTED_SCHEMAS[table]:
                # NAO usar `with engine:` -- ver comentario no DELETE
                # do _check_crud. Cada DELETE e' auto-committed.
                with engine.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {table} "
                        f"WHERE patient_id LIKE %s",
                        (f"{TEST_PATIENT_PREFIX}%",),
                    )
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _dsn_configured() -> bool:
    """Checa se o DSN foi resolvido de alguma fonte (env, secrets, .env).

    Nao tenta abrir conexao aqui -- so' verifica presenca. `_read_dsn()`
    em `connection.py` e' o resolvedor canonico, mas reimportar so' pra
    checar a configuracao e' overkill; `os.environ` ja da' o sinal.
    """
    if os.environ.get("NEON_DSN") or os.environ.get("DCLINIQUE_DSN"):
        return True
    # Streamlit secrets: mesmo stub que o connection.py usa.
    try:
        import streamlit as st  # lazy: dev mode pode nao ter streamlit

        secrets = getattr(st, "secrets", None)
        if secrets and "postgres" in secrets:
            return True
    except Exception:
        pass
    return False


def main() -> int:
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    import traceback

    # Abre o log file ANTES de qualquer outra coisa, para que ate' o
    # cenario "DSN nao configurado" seja capturado no arquivo.
    log_path = _open_log_file()
    try:
        _log(
            "INFO", "starting",
            log_file=str(log_path) if log_path else "stream-only",
            backend=os.environ.get("DCLINIQUE_BACKEND", "postgres"),
        )

        # Pre-check 0: DSN configurado? Antes mesmo de chamar get_engine.
        if not _dsn_configured():
            _log(
                "ERROR", "FAIL",
                step="0", op="dsn_check",
                expected="NEON_DSN or DCLINIQUE_DSN or st.secrets['postgres']['dsn'",
                got="none of the sources set",
                fix="export NEON_DSN=... ou DCLINIQUE_DSN=... ou set em .streamlit/secrets.toml",
            )
            return 1

        # 1. CONECTIVIDADE
        _log("INFO", "[1/4] connectivity")
        try:
            engine = get_engine()
        except Exception as e:
            _log(
                "ERROR", "FAIL",
                step="1", op="get_engine",
                error=type(e).__name__, err_msg=str(e),
                expected="psycopg.Connection open",
                got=f"{type(e).__name__}: {e}",
                fix="checar DSN (NEON_DSN / DCLINIQUE_DSN / st.secrets), rede, TLS/SSLmode, auth",
            )
            return 1
        ok, err = _check_connectivity(engine)
        if not ok:
            _log(
                "ERROR", "FAIL",
                step="1", op="select_1",
                expected="(1,)", got=err,
                fix="a query 'SELECT 1' retornou algo inesperado; checar se o DSN aponta para o banco certo",
            )
            return 2
        _log("INFO", "[OK] SELECT 1 returned (1,)")

        try:
            # 2. SCHEMA
            _log("INFO", "[2/4] schema (init_schema + pg_tables)")
            try:
                schema_ok, schema_err = _check_schema(engine)
            except Exception as e:
                _log(
                    "ERROR", "FAIL",
                    step="2", op="_check_schema",
                    error=type(e).__name__, err_msg=str(e),
                    tb=traceback.format_exc().replace("\n", " | "),
                    expected="11 tables present", got=f"unhandled {type(e).__name__}",
                    fix="este erro nao deveria acontecer; veja `tb` acima para o traceback completo",
                )
                return 3
            if not schema_ok:
                # Distingue init_schema-explodiu vs tabelas-faltando para
                # mensagem de fix mais acionavel.
                if "init_schema" in schema_err:
                    _log(
                        "ERROR", "FAIL",
                        step="2", op="init_schema",
                        expected="CREATE TABLE IF NOT EXISTS for 11 tables",
                        got=schema_err,
                        fix="checar permissoes DDL no DSN; checar se o DB existe; rodar scripts/init_neon_schema.py separado para mais detalhe",
                    )
                else:
                    _log(
                        "ERROR", "FAIL",
                        step="2", op="pg_tables",
                        expected="11 tabelas em public", got=schema_err,
                        fix="init_schema foi chamado mas tabelas sumiram; rodar init_schema novamente (idempotente)",
                    )
                return 3
            _log("INFO", "[OK] schema", tables=len(EXPECTED_SCHEMAS))

            # 3. CRUD
            _log("INFO", "[3/4] CRUD (insert/update/delete per table)")
            crud_ok, crud_errors = _check_crud(engine)
            for table in EXPECTED_SCHEMAS:
                failed = [e for e in crud_errors if e.startswith(f"{table}:")]
                if failed:
                    _log(
                        "ERROR", "FAIL",
                        step="3", op="summary", table=table,
                        detail=failed[0],
                        expected="CRUD OK", got="FAIL",
                        fix=f"ver linhas com step=3 op=* table={table} acima",
                    )
                else:
                    _log("INFO", "[OK]", step="3", op="summary", table=table)
            if not crud_ok:
                _log(
                    "ERROR", "FAIL",
                    step="3", op="crud_total",
                    expected="0 erros", got=f"{len(crud_errors)} erros",
                    fix="ver linhas com step=3 acima; cada erro tem expected/got/fix",
                )
                return 4
        finally:
            # 4. CLEANUP (sempre, mesmo se 2 ou 3 explodiu)
            _log("INFO", "[4/4] cleanup (defensive sweep)")
            cleanup_ok, cleanup_err = _cleanup(engine)
            if not cleanup_ok:
                _log(
                    "ERROR", "FAIL",
                    step="4", op="cleanup_sweep",
                    expected="DELETE executed for all 11 tables",
                    got=cleanup_err,
                    fix="checar permissoes; rodou SELECT manual depois para confirmar estado",
                )
                return 5
            with engine.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM patients "
                    "WHERE patient_id LIKE %s",
                    (f"{TEST_PATIENT_PREFIX}%",),
                )
                leftover = cur.fetchone()[0]
            if leftover > 0:
                _log(
                    "ERROR", "FAIL",
                    step="4", op="count_verify",
                    expected="0 test patients",
                    got=f"{leftover} remaining",
                    fix=f"rodar DELETE manual: DELETE FROM patients WHERE patient_id LIKE '{TEST_PATIENT_PREFIX}%'",
                )
                return 5
            _log("INFO", "[OK] no test rows remain")

        # Se chegou aqui sem return antecipado, tudo passou.
        _log("INFO", "PASSED", checks=4, status="OK")
        return 0
    except Exception as e:
        # Top-level catch: loga QUALQUER excecao nao tratada (com traceback
        # completo) e retorna exit 99 ("unhandled"). Sem isso, um bug no
        # data layer (ex.: conexao caiu mid-flight) faria o script sair
        # silenciosamente com traceback no stderr e nada no log file.
        import traceback as _tb
        try:
            _log(
                "ERROR", "FAIL",
                step="top", op="main",
                error=type(e).__name__, err_msg=str(e),
                tb=_tb.format_exc().replace("\n", " | "),
                expected="4 checks passed", got=f"unhandled {type(e).__name__}",
                fix="erro nao tratado no fluxo principal; veja `tb` para o traceback",
            )
        except Exception:
            # Ultimo recurso: se ate' o _log falhar, nao temos como reportar
            pass
        return 99
    finally:
        _close_log_file()


if __name__ == "__main__":
    sys.exit(main())
