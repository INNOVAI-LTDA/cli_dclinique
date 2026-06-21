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

Reciclagem de conexão (June 2026)
---------------------------------
O DSN do Neon aponta para o endpoint ``*-pooler`` (PgBouncer em
transaction mode). O pooler recicla conexões ociosas server-side
após alguns minutos; o objeto :class:`psycopg.Connection` cacheado
no módulo fica então com um socket morto, e a próxima
``connection.cursor()`` levanta ``OperationalError: the connection
is closed``.

Defendemos em duas camadas:

1. **Proativa** — :func:`get_engine` checa ``connection.closed``
   antes de retornar o engine cacheado. Se a conexão morreu, faz
   ``close()`` defensivo e reconstrói via :func:`_make_engine`.
   Cobre 99% dos casos (idle timeout, recycle do pooler, blip de
   rede): o ``closed`` flag é setado pelo psycopg no momento que
   o socket é detectado como morto, então o check é confiável.

2. **Reativa** — :func:`_with_retry_on_dead_conn` envolve cada
   função pública em :mod:`postgres_backend` e captura
   ``OperationalError("the connection is closed")`` que escapa
   da camada proativa (race entre o check e o uso). Reseta o
   engine cacheado e roda a função uma segunda vez antes de
   propagar o erro. É uma defesa em profundidade — a proativa
   deve bastar para 99% dos cenários.
"""
import functools
import os
from typing import Any, Callable, TypeVar

# Cache em escopo de módulo. Streamlit roda um processo por sessão,
# então um único conn por processo é o modelo certo. _engine é resetado
# por reset_engine() (uso interno dos testes; não chamar em produção).
_engine: "Any | None" = None


# Frase canônica que o psycopg usa quando detecta o socket fechado.
# Usada por :func:`_with_retry_on_dead_conn` para decidir se vale
# a pena tentar de novo; qualquer outra ``OperationalError`` propaga
# direto (deadlock, serialization failure, etc. — não se resolve
# com retry cego).
_DEAD_CONN_MSG = "the connection is closed"


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

    Auto-reset em conexão morta
    ---------------------------
    Antes de retornar o engine cacheado, checa o flag ``closed``.
    Quando o pooler do Neon recicla a conexão server-side (idle
    timeout, recycle programado, etc.), o psycopg marca o objeto
    como ``closed=True``; nesse caso a função descarta a conexão
    morta, reconstrói via :func:`_make_engine` e devolve a nova
    instância. A página do usuário não vê nenhum erro — a próxima
    ``load_table()`` simplesmente reconecta.
    """
    global _engine
    if _engine is None or getattr(_engine, "closed", False):
        # O engine cacheado sumiu (reset entre testes) OU o pooler
        # reciclou a conexão. Em qualquer caso, defendemos com um
        # close() defensivo (idempotente) e reconstruímos.
        if _engine is not None:
            try:
                _engine.close()
            except Exception:
                pass
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


# ---------------------------------------------------------------------------
# Retry-on-dead-conn wrapper
# ---------------------------------------------------------------------------

_F = TypeVar("_F", bound=Callable[..., Any])


def _with_retry_on_dead_conn(func: _F) -> _F:
    """Decorator: roda ``func`` uma vez; em ``OperationalError("the
    connection is closed")`` reseta o engine cacheado e tenta de novo.

    Cobre a race condition entre a checagem proativa de
    :func:`get_engine` (``connection.closed``) e o uso real da
    conexão: se o socket morre *depois* do check mas *durante* a
    operação (Tabela vazia retornada de um SELECT depois o pooler
    recicla, por exemplo), a chamada cai com
    ``OperationalError("the connection is closed")``. O decorator
    pega essa exceção específica, faz ``reset_engine()`` para
    forçar reconexão, e reexecuta a função exatamente uma vez. Se
    a segunda tentativa também falhar — ou se a exceção for
    qualquer outra ``OperationalError`` (deadlock, etc.) —
    propaga.

    O decorator é aplicado a cada função pública de
    :mod:`postgres_backend` que faz I/O. As funções internas
    (``_columns_for``, ``_validate_table``, ``_coerce_dtypes``,
    etc.) não tocam conexão e não precisam do wrapper.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            # Filtra pelo tipo E pela string: queremos só
            # ``OperationalError`` do psycopg com a mensagem canônica
            # ``"the connection is closed"``. Outros ``OperationalError``
            # (deadlock, serialization failure, etc.) não se resolvem
            # com retry cego — propagam direto. Mensagens iguais em
            # outras exceções (ex.: ``RuntimeError``) também não
            # devem disparar retry.
            pg = _import_psycopg()
            if not isinstance(exc, pg.OperationalError):
                raise
            if _DEAD_CONN_MSG not in str(exc):
                raise
            # Reset e retry uma vez. Se a segunda tentativa também
            # morrer, propaga sem novo retry (evita loop infinito
            # em caso de DSN inválido / pooler fora do ar).
            reset_engine()
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
