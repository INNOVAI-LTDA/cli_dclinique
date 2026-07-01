"""Postgres-backed data layer for the MAP shell (Neon).

This module mirrors the public API of :mod:`csv_backend` 1:1, but
reads/writes from a Postgres database (Neon in production). The
``src.data_layer`` package re-exports the active backend's API based
on ``DCLINIQUE_BACKEND`` (default ``postgres``); the rest of the app
imports from :mod:`src.data_layer` and is unaware of the switch.

Public API (identical to :mod:`csv_backend`):
* :func:`load_all`            — read all 11 tables into ``dict[str, DataFrame]``
* :func:`load_table`          — read one table into a DataFrame
* :func:`append_row`          — INSERT one row
* :func:`update_row`          — UPDATE one row
* :func:`next_id`             — derive the next ``pat_new_NNN`` / ``plan_new_NNN`` … id
* :func:`data_dir`            — sentinel Path (``postgres://neon``); CSV backend
                                returns the on-disk CSV directory. Tests use
                                this to detect which backend is active.

Transitive imports (all LAZY — ver SCRUM_BOARD "Rigor & Quality Gates"):
  - :mod:`psycopg`         — loaded only when a connection is opened (via
                             ``src.data_layer.connection.get_engine``)
  - :mod:`streamlit`       — loaded only inside ``connection._read_dsn`` for
                             the ``st.secrets`` path
  - :mod:`pandas`          — loaded only when a function builds a DataFrame
  - :mod:`src.schemas`     — loaded only when a function needs the column
                             list (``_columns_for`` / ``_validate_table``)

Consequence: ``import src.data_layer.postgres_backend`` does NOT trigger
any DB connection or external import. The first DB call happens on the
first ``load_table`` / ``append_row`` / etc.

SQL safety
----------
Table and column names are restricted to a known set (``EXPECTED_SCHEMAS``)
validated by :func:`_validate_table` and :func:`_columns_for`. Parameter
values are passed through psycopg's ``%s`` placeholders (no string
interpolation of user data).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.data_layer.connection import get_engine, reset_engine
from src.data_layer.connection import _with_retry_on_dead_conn  # noqa: F401
from src.data_layer.schema import to_ddl as _to_ddl  # re-exported for tests

# Mirror of csv_backend.NEW_ID_PREFIX. Kept inline (not imported) to avoid
# pulling csv_backend's eager `import pandas as pd` (csv_backend.py:28).
NEW_ID_PREFIX: dict[str, str] = {
    "patients": "pat_new",
    "treatment_plans": "plan_new",
    "treatment_plan_items": "item_new",
    "patient_goals": "goal_new",
    "weight_entries": "w_new",
    # ``execution_summary`` rows are minted by the PDF import
    # wizard's read-model projection; the prefix needs to be
    # unique across all primary-key columns so dedup scans
    # (which inspect every pk in the schema) don't collide with
    # patient/plan ids.
    "execution_summary": "exec_new",
    # --- MVP Jornada Clínica (Fase 1) ---
    # ``service_catalog`` PK = service_code (TEXT, fornecido pelo
    # import — não passa por next_id; o código é externo).
    # ``service_review_queue`` PK = id (gerado por next_id).
    "service_review_queue": "srv_new",
}

# Per-table dtype maps (mirror de csv_backend._DATE_COLUMNS etc.).
# Usados por _coerce_dtypes para restaurar o dtype pandas depois
# de SELECT * -- sem isso, colunas TIMESTAMP voltam como object
# (datetime do psycopg) ao inves de datetime64, e o downstream
# (metrics.patient_summary, charts, etc.) quebra com
# `TypeError: unsupported operand type(s) for -: 'ndarray' and 'Timestamp'`.
# O map em schema.py e' tuple-based (para DDL); este aqui e' per-table
# (para coerção pandas). Refactor para um modulo compartilhado e'
# TODO -- os dois estao em sync manual por enquanto.
_DATE_COLUMNS: dict[str, set[str]] = {
    "patients": {"created_at"},
    "treatment_plans": {"issue_date", "start_date", "end_date"},
    "execution_summary": {"plan_created_at"},
    "appointments": {"appointment_start", "appointment_end"},
    "appointment_items": {"appointment_start"},
    "patient_goals": {"target_date"},
    "weight_entries": {"measurement_date"},
    "satisfaction_entries": {"date"},
    "alerts": {"created_at"},
    # --- MVP Jornada Clínica (Fase 1) ---
    "service_catalog": {"created_at"},
    "service_review_queue": {"first_seen_at", "last_seen_at"},
}
_BOOL_COLUMNS: dict[str, set[str]] = {
    "treatment_plans": {"is_renewal"},
    "treatment_plan_items": {"needs_manual_review"},
}
_NULLABLE_INT_COLUMNS: dict[str, set[str]] = {
    "patients": {"age"},
    "treatment_plan_items": {"sessions_expected"},
    "execution_summary": {"sessions_expected", "sessions_completed", "sessions_remaining"},
    "satisfaction_entries": {"score"},
    # --- MVP Jornada Clínica (Fase 1) ---
    "service_catalog": {"default_periodicity_days"},
    "service_review_queue": {"occurrences"},
}
# psycopg retorna float Python para DOUBLE PRECISION; pandas infere
# float64 sem coerce. Mantemos o map explicito para documentacao e
# para o caso futuro de o driver mudar.
_FLOAT_COLUMNS: dict[str, set[str]] = {
    "weight_entries": {"weight"},
    "patient_goals": {"initial_weight", "target_weight"},
}

# Module-level cache of EXPECTED_SCHEMAS. Populated lazily on first
# access by :func:`_columns_for`; cleared if the test patches the
# underlying schema. Keeps validation O(1) after the first call.
_SCHEMAS_CACHE: dict[str, list[str]] | None = None


def data_dir() -> Path:
    """Sentinel path. Postgres has no on-disk data directory.

    Returns ``Path("postgres-neon")``. The actual DB location is the
    DSN resolved by :func:`src.data_layer.connection.get_engine` (env
    var or ``st.secrets``). Tests that need to know which backend is
    active check this value rather than the module name.

    Why "postgres-neon" (not "postgres://neon" or "postgres:neon"):
      - On Windows, ``Path("postgres://neon")`` parses the ``//`` as a
        UNC path prefix and returns ``WindowsPath('postgres:/neon')``
        (single slash), making the value platform-dependent.
      - ``Path("postgres:neon")`` is parsed as a drive-letter path
        (``postgres:`` as drive, ``neon`` as path) — also platform-specific.
      - ``Path("postgres-neon")`` is a plain relative path, identical
        on POSIX and Windows. Tests should check the ``.name`` or
        ``str()`` of the result, not the literal ``//`` form.
    """
    return Path("postgres-neon")


def _import_pandas():
    """Lazy import of pandas. Returns the module.

    Centralized so tests can stub ``sys.modules["pandas"]`` once and
    have every DataFrame construction site see the same stub.
    """
    import pandas as pd
    return pd


def _columns_for(table: str) -> list[str]:
    """Column list for ``table`` from ``EXPECTED_SCHEMAS`` (lazy import).

    Raises :class:`ValueError` if ``table`` is not in the schema catalog.
    """
    global _SCHEMAS_CACHE
    if _SCHEMAS_CACHE is None:
        from src.schemas import EXPECTED_SCHEMAS
        _SCHEMAS_CACHE = dict(EXPECTED_SCHEMAS)
    try:
        return _SCHEMAS_CACHE[table]
    except KeyError:
        raise ValueError(
            f"unknown table: {table!r}. "
            f"Valid tables: {sorted(_SCHEMAS_CACHE.keys())}"
        )


def _validate_table(table: str) -> str:
    """Validate ``table`` is a known table name. Defense in depth.

    Same effect as :func:`_columns_for` but returns the table name
    unchanged for use as an f-string interpolation point. The table
    name is restricted to a known set, so f-string interpolation is
    safe; user-supplied values are always passed via ``%s`` placeholders.
    """
    _columns_for(table)  # raises ValueError if unknown
    return table


def _coerce_dtypes(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Restore os pandas dtypes depois de um SELECT * do Postgres.

    psycopg devolve datetime/Timestamp como ``datetime.datetime``
    (objeto Python), e boolean como ``bool`` (objeto Python), e
    inteiros como ``int`` (objeto Python). Sem coerce, o pandas
    infere dtype ``object`` para essas colunas, e o downstream
    quebra: ``Series - Timestamp`` falha com TypeError, e
    ``Series / Series`` nao consegue distinguir int de NaN.

    O csv_backend aplica o mesmo coerce no load (ver
    csv_backend._coerce_dtypes); o espelhamos aqui para manter
    a paridade de tipos entre os dois backends. Idempotente:
    se a coluna ja' tem o dtype certo, ``pd.to_datetime`` e'
    no-op, ``astype(bool)`` e' no-op, ``astype('Int64')`` e' no-op.
    """
    for col in _DATE_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = _import_pandas().to_datetime(df[col], errors="coerce")
    for col in _BOOL_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = df[col].astype(bool)
    for col in _NULLABLE_INT_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    return df


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@_with_retry_on_dead_conn
def load_table(table: str) -> Any:
    """Read a single table into a DataFrame.

    Returns an empty DataFrame with the schema's columns if the table
    is empty (e.g., first boot with no patients). Mirrors
    :func:`csv_backend.load_table` semantics.

    Connection handling: opens a cursor, executes ``SELECT * FROM
    <table>``, fetches all rows, builds a DataFrame, and reindexes
    to the schema's column order. No explicit transaction needed for
    a read; the cursor context closes the implicit transaction on
    exit.
    """
    table = _validate_table(table)
    columns = _columns_for(table)
    pd = _import_pandas()

    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(f"SELECT * FROM {table}")
        desc = cur.description
        if desc is None:
            # Table doesn't exist yet (very first boot before init_schema).
            return pd.DataFrame(columns=columns)
        col_names = [d[0] for d in desc]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=col_names)
    # Restaura os dtypes pandas (TIMESTAMP -> datetime64, etc.) para
    # casar com o que o csv_backend entrega. Sem isso, colunas
    # TIMESTAMP vem como object (datetime do psycopg) e quebram o
    # downstream (metrics.patient_summary, charts, etc.).
    df = _coerce_dtypes(df, table)
    return df.reindex(columns=columns)


def load_all() -> dict[str, Any]:
    """Read all 11 tables into a fresh ``dict[str, DataFrame]``.

    Returned shape matches :func:`csv_backend.load_all` and the
    contract in :mod:`src.schemas` (the same shape the rest of the
    app expects from ``load_mock_data()`` historically).
    """
    from src.schemas import EXPECTED_SCHEMAS
    return {table: load_table(table) for table in EXPECTED_SCHEMAS}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _sanitize_param(value: Any) -> Any:
    """Coerce pandas-specific sentinels into values psycopg can bind.

    Two pandas values trip the psycopg adapters and write a
    far-future timestamp that then breaks the read-back path
    (psycopg's ``TimestampLoader`` rejects years past 10K with
    ``DataError: timestamp too large``):

    * ``pd.NaT`` (the missing-date sentinel) — psycopg binds it
      to ``'48113-11-21 00:00:01'`` (year 48113, derived from
      ``NaT.timestamp()``). Coerce to ``None`` so it lands as
      SQL NULL.
    * ``float('nan')`` / ``pd.NA`` — same family of "missing
      numeric" sentinels. Coerce to ``None`` for the same reason
      (NULL in an INTEGER / DOUBLE PRECISION column is the
      canonical "missing" representation).

    Other values pass through unchanged. The CSV backend does
    not need this because pandas' ``to_csv`` already maps NaT
    and NaN to the empty string (which ``_coerce_dtypes`` then
    turns into ``NaT`` / ``NaN`` again on the read — no far-future
    date).
    """
    # ``pd.NaT`` is a pandas-specific value; importing pandas at
    # module top would defeat the lazy-import design of this
    # module. The ``pd`` reference is the local alias from
    # ``_import_pandas`` — never top-level.
    pd = _import_pandas()
    try:
        if value is pd.NaT:
            return None
    except (TypeError, ValueError):
        # Some objects (e.g. ``None``, ``int``) reject ``is``
        # comparison with pd.NaT. Fall through to the next check.
        pass
    if value is None:
        return None
    # ``float('nan')`` and ``pd.NA`` are detected by ``pd.isna``
    # without requiring a pandas import beyond the helper above.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        # Objects that don't support ``pd.isna`` (custom classes,
        # arbitrary Python objects) are left alone.
        return value
    return value


@_with_retry_on_dead_conn
def append_row(table: str, row: dict) -> None:
    """INSERT one row into ``table``.

    The row must already include the primary key column (use
    :func:`next_id` to compute it). Columns in the row that are not
    in the schema are silently dropped; columns in the schema that
    are missing from the row are filled with NULL.

    Caller is responsible for invalidating the Streamlit cache via
    ``st.cache_data.clear()`` after a batch of inserts.

    SQL: ``INSERT INTO <table> (col1, col2, ...) VALUES (%s, %s, ...)``
    — column names are restricted to the schema catalog (safe);
    values are passed through psycopg's ``%s`` placeholder (parameterized).

    Each value is run through :func:`_sanitize_param` so that
    pandas-specific missing sentinels (``pd.NaT``, ``pd.NA``,
    ``float('nan')``) become SQL NULL — without this, psycopg
    binds ``pd.NaT`` to a far-future timestamp and the next
    ``SELECT *`` blows up on the read.
    """
    table = _validate_table(table)
    columns = _columns_for(table)

    safe_cols = [c for c in columns if c in row]
    if not safe_cols:
        raise ValueError(
            f"append_row({table!r}, ...): row nao tem nenhuma coluna "
            f"do schema {columns}"
        )

    col_list = ", ".join(safe_cols)
    placeholders = ", ".join(["%s"] * len(safe_cols))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    params = tuple(_sanitize_param(row[c]) for c in safe_cols)

    engine = get_engine()
    # NAO usar `with engine:` -- psycopg 3 fecha a conexao no
    # `__exit__` (a menos que venha de ConnectionPool). Com
    # autocommit=True, o INSERT e' auto-committed; o context
    # manager do engine nao e' necessario e quebra a proxima
    # operacao no engine cacheado.
    with engine.cursor() as cur:
        cur.execute(sql, params)


@_with_retry_on_dead_conn
def update_row(table: str, key_column: str, key_value: str, updates: dict) -> None:
    """UPDATE one row of ``table``.

    Patches the row whose ``key_column == key_value`` with the cells
    in ``updates``. No-op (silent) if no row matches — matches
    :func:`csv_backend.update_row` semantics (tolerant for the
    patient-age update path).

    Columns in ``updates`` not in the schema are silently dropped.
    An empty ``updates`` dict is a no-op. Values are run through
    :func:`_sanitize_param` for the same reason as in
    :func:`append_row` (pd.NaT and friends → SQL NULL).
    """
    table = _validate_table(table)
    columns = _columns_for(table)

    safe_updates = {c: v for c, v in updates.items() if c in columns}
    if not safe_updates:
        return  # no-op

    set_clause = ", ".join(f"{c} = %s" for c in safe_updates)
    sql = (
        f"UPDATE {table} SET {set_clause} "
        f"WHERE {key_column} = %s"
    )
    params = tuple(_sanitize_param(v) for v in safe_updates.values()) + (
        key_value,
    )

    engine = get_engine()
    # NAO usar `with engine:` -- ver comentario em append_row.
    with engine.cursor() as cur:
        cur.execute(sql, params)


@_with_retry_on_dead_conn
def delete_rows(table: str, key_column: str, key_value: str) -> int:
    """DELETE rows of ``table`` whose ``key_column == key_value``.

    Returns the rowcount (0 when no match). Mirrors
    :func:`csv_backend.delete_rows`. The wizard's ``persist.py``
    calls it to clear ``execution_summary`` rows when a plan is
    being replaced (the data-layer ``replace_plan`` only clears
    ``treatment_plan_items`` and ``patient_goals``; the satellite
    execution view is the wizard's responsibility).

    The key column and value are bound as parameters
    (``WHERE {key_column} = %s``) — psycopg treats the column
    identifier as a value because we interpolate it via
    f-string. The column is validated against the schema catalog
    by :func:`_validate_table` plus an in-set check, so a hostile
    ``key_column`` cannot reach the SQL string.
    """
    table = _validate_table(table)
    columns = _columns_for(table)
    if key_column not in columns:
        raise ValueError(
            f"delete_rows({table!r}, {key_column!r}, ...): "
            f"coluna nao existe no schema. Validas: {columns}"
        )

    sql = f"DELETE FROM {table} WHERE {key_column} = %s"
    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(sql, (key_value,))
        return cur.rowcount or 0


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


_ID_SUFFIX_RE = re.compile(r"^.*_(\d+)$")


def _next_indexed_id(used: set[str], prefix: str) -> str:
    """Return ``{prefix}_{counter:03d}`` for the smallest unused counter."""
    counter = 1
    while f"{prefix}_{counter:03d}" in used:
        counter += 1
    return f"{prefix}_{counter:03d}"


@_with_retry_on_dead_conn
def next_id(table: str) -> str:
    """Return the next available ``{prefix}_NNN`` id for ``table``.

    ``SELECT``s the primary key column from ``table`` and returns
    the next free ``{prefix}_NNN`` counter. Matches
    :func:`csv_backend.next_id` semantics (in particular: ``pat_new_001``
    on an empty patients table).
    """
    table = _validate_table(table)
    prefix = NEW_ID_PREFIX[table]
    pk_col = _columns_for(table)[0]

    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(f"SELECT {pk_col} FROM {table}")
        rows = cur.fetchall()

    used: set[str] = {str(r[0]) for r in rows if r[0] is not None}
    return _next_indexed_id(used, prefix)


@_with_retry_on_dead_conn
def next_id_with_prefix(prefix: str) -> str:
    """Return the next available ``{prefix}_NNN`` id for an arbitrary prefix.

    Used by the PDF importer to mint ``orc_new_NNN`` budget codes.
    Mirrors :func:`csv_backend.next_id_with_prefix`: scans the
    ``treatment_plans.budget_code`` column for any value already
    starting with this prefix and returns the next free counter.
    """
    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(
            "SELECT budget_code FROM treatment_plans "
            "WHERE budget_code LIKE %s",
            (f"{prefix}_%",),
        )
        rows = cur.fetchall()

    used: set[str] = {str(r[0]) for r in rows if r[0] is not None}
    return _next_indexed_id(used, prefix)


# ---------------------------------------------------------------------------
# Plan replace flow (used by PDF import for natural-key dedup)
# ---------------------------------------------------------------------------


def _delete_rows(table: str, key_column: str, key_value: str) -> int:
    """Delete rows from ``table`` where ``key_column == key_value``.

    Returns the rowcount (0 when no match). Mirrors
    :func:`csv_backend._delete_rows` semantics.
    """
    table = _validate_table(table)
    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(
            f"DELETE FROM {table} WHERE {key_column} = %s",
            (key_value,),
        )
        return cur.rowcount


@_with_retry_on_dead_conn
def find_plan_by_issue_date(patient_id: str, issue_date: str) -> dict | None:
    """Return the first plan row whose ``(patient_id, issue_date)`` matches.

    Mirrors :func:`csv_backend.find_plan_by_issue_date`. ``issue_date``
    is matched as a string because the parser always emits ISO
    ``YYYY-MM-DD`` and Postgres' ``DATE`` column serialises the same
    way for round-trip equality.
    """
    engine = get_engine()
    with engine.cursor() as cur:
        cur.execute(
            "SELECT * FROM treatment_plans "
            "WHERE patient_id = %s AND issue_date = %s "
            "LIMIT 1",
            (patient_id, issue_date),
        )
        row = cur.fetchone()
        if row is None:
            return None
        desc = cur.description
        col_names = [d[0] for d in desc]
        return dict(zip(col_names, row))


@_with_retry_on_dead_conn
def replace_plan(
    patient_id: str,
    issue_date: str,
    new_plan_row: dict,
    new_items: list[dict],
) -> str | None:
    """Replace an existing plan in place: clear items + goal, patch
    the plan row, insert new items under the same plan_id.

    Atomic via a single ``Connection.transaction()`` block so the
    four steps either all commit or all roll back. Mirrors
    :func:`csv_backend.replace_plan` semantics — returns the
    existing ``plan_id`` on success, ``None`` when no plan matches
    (so the caller can fall back to a normal insert).
    """
    existing = find_plan_by_issue_date(patient_id, issue_date)
    if existing is None:
        return None

    existing_plan_id = str(existing.get("plan_id", ""))
    if not existing_plan_id:
        return None

    plan_columns = _columns_for("treatment_plans")
    item_columns = _columns_for("treatment_plan_items")

    engine = get_engine()
    with engine.transaction(), engine.cursor() as cur:
        # 1+2. Clear out the plan's children before patching the plan row.
        cur.execute(
            "DELETE FROM treatment_plan_items WHERE plan_id = %s",
            (existing_plan_id,),
        )
        cur.execute(
            "DELETE FROM patient_goals WHERE plan_id = %s",
            (existing_plan_id,),
        )

        # 3. Patch the plan row. Only mutable fields (everything except
        # ``plan_id`` / ``patient_id``) are taken from ``new_plan_row``.
        updates: dict = {
            c: v for c, v in new_plan_row.items()
            if c in plan_columns and c not in {"plan_id", "patient_id"}
        }
        if updates:
            set_clause = ", ".join(f"{c} = %s" for c in updates)
            cur.execute(
                f"UPDATE treatment_plans SET {set_clause} "
                f"WHERE plan_id = %s",
                tuple(_sanitize_param(v) for v in updates.values())
                + (existing_plan_id,),
            )

        # 4. Append the new items under the same plan_id, minting a
        # fresh ``plan_item_id`` per row inside the transaction so
        # consecutive items never collide.
        for item in new_items:
            item_id = next_id("treatment_plan_items")
            item_with_id = {
                **item,
                "plan_id": existing_plan_id,
                "plan_item_id": item_id,
            }
            safe_cols = [c for c in item_columns if c in item_with_id]
            if not safe_cols:
                continue
            col_list = ", ".join(safe_cols)
            placeholders = ", ".join(["%s"] * len(safe_cols))
            cur.execute(
                f"INSERT INTO treatment_plan_items ({col_list}) "
                f"VALUES ({placeholders})",
                tuple(_sanitize_param(item_with_id[c]) for c in safe_cols),
            )

    return existing_plan_id
