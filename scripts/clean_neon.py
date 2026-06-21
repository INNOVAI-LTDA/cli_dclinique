"""scripts/clean_neon.py -- TRUNCATE de todas as tabelas do data layer Neon.

Esvazia as 11 tabelas do schema (patients, treatment_plans, etc.) com
um unico ``TRUNCATE ... RESTART IDENTITY``. RESET IDENTITY zera as
sequences associadas (o projeto nao usa sequences -- os surrogate ids
sao gerados por ``next_id()`` que faz MAX() na coluna -- mas o flag e'
o default seguro).

ATENCAO: destrutivo. Os dados NAO voltam. Usar somente contra um banco
Neon de dev/homolog, nunca contra o banco que tem dados reais do
Cliente. O script chama TRUNCATE -- se voce rodar contra o Neon de
PRD, o Cliente perde tudo.

Seguranca (defense in depth, na ordem em que sao aplicadas)
-----------------------------------------------------------
1. Resolve o DSN via ``src.data_layer.connection._read_dsn()`` -- mesma
   fonte canonica do app (st.secrets -> NEON_DSN -> DCLINIQUE_DSN).
2. Imprime o host:porta/db (sem credenciais) do DSN alvo ANTES de
   qualquer acao destrutiva. Se voce nao reconheceu, Ctrl-C.
3. Faz ``SELECT COUNT(*)`` em cada uma das 11 tabelas e imprime a
   contagem. Da' pra ver o que vai sumir antes de sumir.
4. Por padrao, exige confirmacao interativa: voce precisa digitar
   exatamente ``TRUNCATE`` (case-sensitive) e dar Enter.
5. ``--dry-run`` (-n) aborta ANTES do TRUNCATE -- mostra so' as
   contagens e sai com exit 0.
6. ``--yes`` (-y) pula a confirmacao interativa. Use em CI / scripts
   de automacao. SEMPRE combine com algo que mostre as contagens
   antes (o script ja' faz).
7. Log do evento (UTC timestamp, host, contagens, contagens pos-truncate)
   em ``data/test_logs/neon_clean_<UTC>.log`` -- trilha de auditoria
   minima.

Uso
---
    # INTERATIVO: pede confirmacao. Recomendado para uso manual.
    DCLINIQUE_BACKEND=postgres \\
        NEON_DSN="postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require" \\
        .venv/Scripts/python.exe scripts/clean_neon.py

    # DRY-RUN: so' mostra contagens, nao trunca.
    .venv/Scripts/python.exe scripts/clean_neon.py --dry-run

    # NAO-INTERATIVO: CI / script de automacao.
    .venv/Scripts/python.exe scripts/clean_neon.py --yes

Conveniencias de dev:
  - Se voce tem um ``.env`` na raiz do worktree com ``NEON_DSN=``,
    carregue-o antes (mesmo esquema do validate_neon.py).

Exit codes:
  0 -- OK (tabelas vazias)
  1 -- DSN nao configurado
  2 -- falha de conectividade (rede, TLS, auth, SELECT 1)
  3 -- usuario abortou a confirmacao (digitou algo diferente de TRUNCATE)
  4 -- TRUNCATE explodiu
  5 -- verificacao pos-truncate falhou (alguma tabela ainda tem linhas)
  99 -- erro nao tratado (top-level catch)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from src.data_layer.connection import _read_dsn, get_engine


# Palavra exata que o usuario precisa digitar para confirmar a limpeza.
# Case-sensitive. Hardcoded como constante pra que mudancas sejam
# visiveis em code review (decisao de UX, nao de implementacao).
CONFIRMATION_WORD = "TRUNCATE"


# Estado do log em arquivo. Mesmo padrao do validate_neon.py.
_log_path: Path | None = None
_log_fh: TextIO | None = None


def _fmt_value(v: Any) -> str:
    """Renderiza um valor de campo de log. Quota se contem espaco,
    aspas, tab, ou ``=``; escapa ``\\\\`` e ``"`` internos. Caso
    contrario devolve a representacao ``str()`` crua.
    """
    s = str(v)
    if any(c in s for c in ' "\\t='):
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return s


def _log(level: str, msg: str, **fields: Any) -> None:
    """Emite uma linha de log estruturada no stream + (opcional) arquivo.

    Stream: stdout para INFO, stderr para WARN/ERROR.
    Arquivo (se ``_log_fh`` nao for None): mesma linha, append + flush.
    Falha de escrita no arquivo NAO quebra o script -- apenas perde
    aquela linha no log file.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [f"[{ts}]", level, "clean-neon", msg]
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
            pass


def _open_log_file() -> Path | None:
    """Abre ``data/test_logs/neon_clean_<UTC>.log`` para write.

    Retorna o Path em caso de sucesso, ou None em caso de falha
    (nao-fatal: continua com log so' no stream). Mesmo padrao do
    ``validate_neon.py`` -- trilha de auditoria minima.
    """
    global _log_path, _log_fh
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = Path("data/test_logs") / f"neon_clean_{ts}.log"
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


def _dsn_target_label(dsn: str) -> str:
    """Extrai host:porta/db do DSN para exibicao (sem credenciais).

    ``postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech:5432/db?sslmode=require``
    vira ``ep-xxx-pooler.region.aws.neon.tech:5432/db (sslmode=require)``.

    O objetivo e' o usuario saber PRA ONDE o script esta' apontando
    antes de qualquer acao destrutiva -- se voce nao reconhece esse
    host, Ctrl-C.
    """
    try:
        parsed = urlparse(dsn)
    except Exception:
        # Fallback bruto: se o parse falhar, mostra o DSN truncado.
        return f"<unparseable DSN, starts with {dsn[:20]!r}>"

    host = parsed.hostname or "<no host>"
    port = parsed.port or 5432
    db = (parsed.path or "/").lstrip("/") or "<no db>"
    query = parsed.query
    # O query string ja' vem completo (ex.: "sslmode=require"); so'
    # prefixamos com "?" se nao estiver vazio para nao duplicar a
    # chave "sslmode=".
    suffix = f"?{query}" if query else ""
    return f"{host}:{port}/{db}{suffix}"


def _dsn_configured() -> bool:
    """Checa se o DSN foi resolvido de alguma fonte. So' verifica
    presenca, nao tenta abrir conexao."""
    if os.environ.get("NEON_DSN") or os.environ.get("DCLINIQUE_DSN"):
        return True
    try:
        import streamlit as st  # lazy: dev pode nao ter streamlit

        secrets = getattr(st, "secrets", None)
        if secrets and "postgres" in secrets:
            return True
    except Exception:
        pass
    return False


def _count_rows(engine, tables: list[str]) -> dict[str, int]:
    """Roda ``SELECT COUNT(*) FROM <table>`` para cada tabela.

    Retorna dict ``{table: count}``. Falha em uma tabela NAO interrompe
    o loop -- se o SELECT der erro, registra 0 e segue, para que o
    relatorio seja o mais completo possivel (e o TRUNCATE em si
    reportara' a falha real).
    """
    counts: dict[str, int] = {}
    for table in tables:
        try:
            with engine.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
        except Exception as e:
            _log(
                "WARN", "count_failed",
                table=table,
                error=type(e).__name__, err_msg=str(e),
            )
            counts[table] = -1  # sentinela: erro
    return counts


def _truncate_all(engine, tables: list[str]) -> tuple[bool, str]:
    """Roda ``TRUNCATE <tabelas> RESTART IDENTITY`` em um unico statement.

    Sem FKs declaradas no schema (ver src/data_layer/schema.py), um
    unico TRUNCATE cobre todas as 11 tabelas atomicamente. ``RESTART
    IDENTITY`` zera sequences (o projeto nao usa, mas e' o default
    seguro e barato).

    Se uma das tabelas nao existir, o statement inteiro aborta com
    um erro -- o caller deve logar e sair com exit 4. Nao usamos
    truncate-table-por-tabela porque perderiamos a atomicidade: em
    caso de falha, ficariamos com um subset truncado e outro
    intacto, sem como reverter (TRUNCATE e' autocommit no psycopg
    com autocommit=True).
    """
    # Identifiers seguros: nomes vem de EXPECTED_SCHEMAS (codigo), nao
    # de input do usuario, entao format() e' ok (sem SQL injection).
    table_list = ", ".join(tables)
    sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY"
    try:
        with engine.cursor() as cur:
            cur.execute(sql)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _verify_empty(engine, tables: list[str]) -> tuple[bool, list[str]]:
    """Re-roda ``SELECT COUNT(*) FROM <table>`` e exige 0 em cada.

    Belt-and-suspenders: TRUNCATE bem-sucedido deveria garantir 0,
    mas se algum trigger ou hook tiver injetado dados de volta, o
    usuario precisa ver. Tambem detecta permissions issues (se o
    SELECT der permission denied, o TRUNCATE provavelmente tambem
    deu, mas queremos a mensagem).
    """
    problems: list[str] = []
    for table in tables:
        try:
            with engine.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                got = cur.fetchone()[0]
        except Exception as e:
            problems.append(f"{table}: select failed: {type(e).__name__}: {e}")
            continue
        if got != 0:
            problems.append(f"{table}: {got} rows remain (expected 0)")
    return (len(problems) == 0, problems)


def _parse_args() -> argparse.Namespace:
    """CLI args. Tudo opcional -- sem args = modo interativo (o mais
    seguro)."""
    p = argparse.ArgumentParser(
        prog="clean_neon.py",
        description=(
            "TRUNCATE de todas as 11 tabelas do data layer Postgres (Neon). "
            "DESTRUTIVO -- nao ha rollback. Use --dry-run para apenas "
            "visualizar as contagens."
        ),
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Pula a confirmacao interativa (use em CI).",
    )
    g.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Mostra as contagens e sai sem truncar.",
    )
    return p.parse_args()


def main() -> int:
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas

    args = _parse_args()
    tables = list(EXPECTED_SCHEMAS.keys())  # ordem deterministica

    # Abre o log file ANTES de qualquer outra coisa.
    log_path = _open_log_file()
    try:
        _log(
            "INFO", "starting",
            log_file=str(log_path) if log_path else "stream-only",
            dry_run=args.dry_run,
            skip_confirm=args.yes,
            table_count=len(tables),
        )

        # Pre-check 0: DSN configurado? Antes mesmo de chamar get_engine.
        if not _dsn_configured():
            _log(
                "ERROR", "FAIL",
                step="0", op="dsn_check",
                expected="NEON_DSN or DCLINIQUE_DSN or st.secrets['postgres']['dsn'",
                got="none of the sources set",
                fix=(
                    "export NEON_DSN=... ou DCLINIQUE_DSN=... "
                    "ou set em .streamlit/secrets.toml"
                ),
            )
            return 1

        # Mostra o destino ANTES de qualquer query. Sem credenciais.
        # Se o usuario nao reconhece o host, Ctrl-C aqui.
        dsn = _read_dsn()
        target = _dsn_target_label(dsn)
        _log("INFO", "target_dsn", host_target=target)
        print(f"\n>>> ALVO: {target}\n", file=sys.stderr, flush=True)

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
                fix="checar DSN (NEON_DSN / DCLINIQUE_DSN / st.secrets), "
                    "rede, TLS/SSLmode, auth",
            )
            return 2
        try:
            with engine.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
        except Exception as e:
            _log(
                "ERROR", "FAIL",
                step="1", op="select_1",
                error=type(e).__name__, err_msg=str(e),
                expected="(1,)", got=f"unhandled {type(e).__name__}",
                fix="checar DSN, rede, TLS, auth; o pooler Neon exige "
                    "sslmode=require (sem channel_binding)",
            )
            return 2
        if row != (1,):
            _log(
                "ERROR", "FAIL",
                step="1", op="select_1",
                expected="(1,)", got=str(row),
                fix="o DSN nao aponta para o banco certo",
            )
            return 2
        _log("INFO", "[OK] SELECT 1 returned (1,)")

        # 2. CONTAGEM PRE-TRUNCATE
        _log("INFO", "[2/4] count rows per table (pre-truncate)")
        before = _count_rows(engine, tables)
        total_before = sum(v for v in before.values() if v >= 0)
        errored_before = [t for t, v in before.items() if v < 0]
        for table, n in before.items():
            _log(
                "INFO", "count",
                table=table, rows=n,
                status="error" if n < 0 else "ok",
            )
        _log(
            "INFO", "count_total",
            total_rows=total_before,
            errored_tables=len(errored_before),
        )

        # Mostra ao usuario o que vai sumir. stdout para o terminal,
        # nao-stderr: o usuario precisa ver isso claramente.
        print("\n>>> CONTAGEM PRE-TRUNCATE:", flush=True)
        for table, n in before.items():
            status = f"ERRO" if n < 0 else f"{n} linhas"
            print(f"    {table:30s} {status}", flush=True)
        print(f"    {'TOTAL':30s} {total_before} linhas\n", flush=True)

        # DRY-RUN: terminou aqui.
        if args.dry_run:
            _log("INFO", "dry_run_complete", note="no destructive action taken")
            print(
                ">>> --dry-run: nenhuma acao destrutiva foi tomada.\n",
                flush=True,
            )
            return 0

        # 3. CONFIRMACAO INTERATIVA
        if not args.yes:
            print(
                f">>> Para truncar TODAS as {len(tables)} tabelas "
                f"({total_before} linhas no total), digite "
                f"exatamente: {CONFIRMATION_WORD}",
                file=sys.stderr, flush=True,
            )
            try:
                response = input(f"{CONFIRMATION_WORD}> ")
            except (EOFError, KeyboardInterrupt):
                print("\n>>> abortado pelo usuario (Ctrl-C/EOF).", flush=True)
                _log("INFO", "aborted_by_user", reason="Ctrl-C or EOF")
                return 3
            if response != CONFIRMATION_WORD:
                print(
                    f">>> confirmacao falhou: esperado {CONFIRMATION_WORD!r}, "
                    f"recebido {response!r}. Nada foi feito.",
                    flush=True,
                )
                _log(
                    "INFO", "aborted_by_user",
                    expected=CONFIRMATION_WORD, got=response,
                )
                return 3
            _log("INFO", "user_confirmed")

        # 4. TRUNCATE
        _log("INFO", "[3/4] TRUNCATE (destructive)", tables=len(tables))
        ok, err = _truncate_all(engine, tables)
        if not ok:
            _log(
                "ERROR", "FAIL",
                step="3", op="truncate",
                expected="TRUNCATE executed on all tables",
                got=err,
                fix="checar permissoes DDL no DSN; rodar SELECT COUNT(*) "
                    "manualmente para ver o estado",
            )
            return 4
        _log("INFO", "[OK] TRUNCATE executed")

        # 5. VERIFICACAO POS-TRUNCATE
        _log("INFO", "[4/4] verify (post-truncate counts)")
        empty, problems = _verify_empty(engine, tables)
        if not empty:
            _log(
                "ERROR", "FAIL",
                step="4", op="verify",
                expected="0 rows in all tables",
                got="; ".join(problems),
                fix="algum trigger/hook injetou dados de volta, ou o "
                    "TRUNCATE foi parcial. Rodar SELECT COUNT(*) "
                    "manualmente para investigar.",
            )
            return 5
        for table in tables:
            _log("INFO", "count", table=table, rows=0, status="ok")
        _log(
            "INFO", "verify_total",
            total_rows=0, tables=len(tables), all_empty=True,
        )

        _log("INFO", "PASSED", rows_wiped=total_before, status="OK")
        print(
            f"\n>>> OK: {total_before} linhas removidas de "
            f"{len(tables)} tabelas.\n",
            flush=True,
        )
        return 0
    except Exception as e:
        import traceback as _tb
        try:
            _log(
                "ERROR", "FAIL",
                step="top", op="main",
                error=type(e).__name__, err_msg=str(e),
                tb=_tb.format_exc().replace("\n", " | "),
                expected="clean complete", got=f"unhandled {type(e).__name__}",
                fix="erro nao tratado no fluxo principal; veja `tb` para o traceback",
            )
        except Exception:
            pass
        return 99
    finally:
        _close_log_file()


if __name__ == "__main__":
    sys.exit(main())
