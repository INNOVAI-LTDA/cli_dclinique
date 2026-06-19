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

from src.data_layer.connection import get_engine
from src.data_layer.schema import to_ddl as _to_ddl  # re-exported for tests

# Mirror of csv_backend.NEW_ID_PREFIX. Kept inline (not imported) to avoid
# pulling csv_backend's eager `import pandas as pd` (csv_backend.py:28).
NEW_ID_PREFIX: dict[str, str] = {
    "patients": "pat_new",
    "treatment_plans": "plan_new",
    "treatment_plan_items": "item_new",
    "patient_goals": "goal_new",
    "weight_entries": "w_new",
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


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


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
    params = tuple(row[c] for c in safe_cols)

    engine = get_engine()
    # NAO usar `with engine:` -- psycopg 3 fecha a conexao no
    # `__exit__` (a menos que venha de ConnectionPool). Com
    # autocommit=True, o INSERT e' auto-committed; o context
    # manager do engine nao e' necessario e quebra a proxima
    # operacao no engine cacheado.
    with engine.cursor() as cur:
        cur.execute(sql, params)


def update_row(table: str, key_column: str, key_value: str, updates: dict) -> None:
    """UPDATE one row of ``table``.

    Patches the row whose ``key_column == key_value`` with the cells
    in ``updates``. No-op (silent) if no row matches — matches
    :func:`csv_backend.update_row` semantics (tolerant for the
    patient-age update path).

    Columns in ``updates`` not in the schema are silently dropped.
    An empty ``updates`` dict is a no-op.
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
    params = tuple(safe_updates.values()) + (key_value,)

    engine = get_engine()
    # NAO usar `with engine:` -- ver comentario em append_row.
    with engine.cursor() as cur:
        cur.execute(sql, params)


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
