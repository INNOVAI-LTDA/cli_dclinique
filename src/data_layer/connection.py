"""Connection layer para o data layer Postgres (Neon).

Dois pontos de entrada:
  - get_engine(): cached, lazy; usado dentro do Streamlit (um conn por processo)
  - _make_engine(): one-shot, sem cache; usado por scripts/CI/tests

DSN resolvido na seguinte ordem:
  1. st.secrets["postgres"]["dsn"]   (PRD via Streamlit Cloud; dev via secrets.toml)
  2. NEON_DSN env var                (CI, scripts, manual)
  3. DCLINIQUE_DSN env var           (alias, conveniência)

`import psycopg` é lazy dentro de _import_psycopg(). Em Streamlit, o cold
start do framework (~2.5 s) domina; o psycopg em si não adiciona nada
significativo, mas a indireção mantém o módulo "barato" pra importar
(importante pra testes que carregam a módulo mas não conectam).
"""
import os
from typing import Any

# Cache em escopo de módulo. Streamlit roda um processo por sessão,
# então um único conn por processo é o modelo certo. _engine é resetado
# por reset_engine() (uso interno dos testes; não chamar em produção).
_engine: "Any | None" = None


def _import_psycopg():
    """Lazy import do psycopg (psycopg 3). Mantém cold start plano."""
    import psycopg
    return psycopg


def _read_dsn() -> str:
    """Resolve o DSN. Levanta RuntimeError se nada estiver configurado.

    Ordem de resolução:
      1. Streamlit secrets: st.secrets["postgres"]["dsn"]
      2. Env var NEON_DSN
      3. Env var DCLINIQUE_DSN
    """
    # 1. Streamlit secrets (PRD + .streamlit/secrets.toml em dev)
    try:
        import streamlit as st
        secrets = getattr(st, "secrets", None)
        if secrets and "postgres" in secrets:
            return secrets["postgres"]["dsn"]
    except (ImportError, FileNotFoundError, KeyError, AttributeError):
        # Sem streamlit, sem secrets.toml, ou sem bloco [postgres]: cai pra env
        pass

    # 2. Env vars (CI, scripts, manual)
    for var in ("NEON_DSN", "DCLINIQUE_DSN"):
        dsn = os.environ.get(var)
        if dsn:
            return dsn

    # 3. Nada configurado — erro explícito com a próxima ação
    raise RuntimeError(
        "Postgres DSN nao configurado. Defina em uma das opcoes:\n"
        "  - Streamlit secrets: st.secrets['postgres']['dsn']\n"
        "  - Env var: NEON_DSN (ou DCLINIQUE_DSN)\n"
        "Exemplo:\n"
        "  NEON_DSN='postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require'"
    )


def _make_engine():
    """Cria um psycopg.Connection novo. Sem cache; caller faz close.

    ``autocommit=True`` porque o DSN do Neon aponta para o
    ``*-pooler`` endpoint (PgBouncer em transaction mode). Em
    transaction mode, o pooler recolhe a conexão server-side apos
    cada COMMIT, e o proximo statement do cliente recebe
    "OperationalError: the connection is closed" (reproduzido em
    init_schema -> SELECT pg_tables no smoke test de 2026-06-19).

    Com autocommit, cada statement e' sua propria transacao
    implicita -- o pooler nao tem onde "cortar". E' seguro para
    todas as operacoes do data layer: load_table/next_id fazem
    um unico SELECT; append_row/update_row fazem um unico
    INSERT/UPDATE. Nenhuma operacao depende de multi-statement
    transaction.
    """
    pg = _import_psycopg()
    dsn = _read_dsn()
    return pg.connect(dsn, autocommit=True)


def get_engine():
    """Retorna um psycopg.Connection cacheado por processo.

    Primeira chamada cria a conexão; chamadas subsequentes reusam.
    Para uso dentro do Streamlit (app.py:get_data).
    Caller NÃO deve fechar a conexão — ela vive enquanto o processo vive.
    """
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def reset_engine():
    """Limpa o cache do engine. Apenas para testes.

    Em produção, manter o conn aberto pelo tempo de vida do processo é
    o comportamento correto (evita reconectar a cada rerun do Streamlit).
    """
    global _engine
    if _engine is not None:
        try:
            _engine.close()
        except Exception:
            pass
    _engine = None
