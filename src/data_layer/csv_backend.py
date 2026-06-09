"""CSV-backed implementation of the MAP data layer.

The shell reads/writes one CSV per table under ``data/csv/`` (see
``scripts/seed_csvs.py`` for the seed fixture). All public functions are
re-exported by :mod:`src.data_layer`.

Public API
----------
* :func:`load_all`            — read all 11 CSVs into a ``dict[str, DataFrame]``
* :func:`append_row`          — append a row to one CSV
* :func:`next_id`             — derive the next ``pat_new_NNN`` / ``plan_new_NNN`` … id
* :func:`update_row`          — patch one or more cells in a single row

Path resolution
---------------
The CSV directory is resolved by :func:`csv_dir`, which delegates to
:func:`_csv_dir_callable` so the test suite can monkeypatch the path
without touching the module-level constant. This mirrors the pattern used
in ``src.persistence`` (the previous JSON-based layer) — it keeps the
production code path simple and the test isolation hermetic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import pandas as pd

from src.schemas import EXPECTED_SCHEMAS

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# Prefix used by submit handlers when they generate a new primary key
# (e.g. ``pat_new_001``). Maps the schema's table name to the matching
# id prefix — kept small because only the user-mutable tables need it.
NEW_ID_PREFIX: dict[str, str] = {
    "patients": "pat_new",
    "treatment_plans": "plan_new",
    "treatment_plan_items": "item_new",
    "patient_goals": "goal_new",
    "weight_entries": "w_new",
}

# Column-level type metadata used by ``load_all`` to round-trip through
# CSV without losing dtype information. Only the columns that need a
# specific dtype are listed — everything else is left to pandas' default
# inference (object for strings, int64 for ints, float64 for floats).
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
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_csv_dir() -> Path:
    return _project_root() / "data" / "csv"


# Module-level callable resolved at import time. Tests override it via
# ``monkeypatch.setattr(backend, "_csv_dir_callable", lambda: test_dir)``
# (same pattern as ``src.persistence._get_extras_file`` used to follow).
_csv_dir_callable: Callable[[], Path] = _default_csv_dir


def csv_dir() -> Path:
    """Return the absolute path to the CSV directory used at runtime."""
    return _csv_dir_callable()


def _csv_path(table: str) -> Path:
    return csv_dir() / f"{table}.csv"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _coerce_dtypes(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Apply the per-table dtype map declared at module scope.

    Doing this explicitly (rather than relying on ``pd.read_csv``'s
    inference) keeps the contract stable across pandas versions: dates
    come back as ``pd.Timestamp``, nullable int columns stay ``Int64``
    (so an empty cell is ``<NA>`` not ``NaN``), and booleans stay bool.
    """
    for col in _DATE_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in _BOOL_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = df[col].astype(bool)
    for col in _NULLABLE_INT_COLUMNS.get(table, ()):
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    return df


def load_table(table: str) -> pd.DataFrame:
    """Read a single CSV into a typed DataFrame.

    Returns an empty, correctly-typed DataFrame when the file is missing
    (so a fresh checkout or a wiped fixture doesn't blow up ``load_all``).
    """
    columns = EXPECTED_SCHEMAS[table]
    path = _csv_path(table)
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path)
    # Restore the schema column order so the rest of the app can rely on
    # positional access in tests / iteration helpers.
    df = df.reindex(columns=columns)
    return _coerce_dtypes(df, table)


def load_all() -> dict[str, pd.DataFrame]:
    """Read all 11 CSVs into a fresh ``dict[str, DataFrame]``.

    Returned shape matches what the rest of the app expects from
    ``load_mock_data()`` (the contract in ``src/schemas.py``).
    """
    return {table: load_table(table) for table in EXPECTED_SCHEMAS}


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _row_to_csv_dict(row: dict, columns: list[str]) -> dict:
    """Coerce a Python-side row dict into CSV-friendly scalar values.

    ``pd.DataFrame([row])`` would also work, but Timestamp and nullable
    Int64 values would be passed through as objects and confuse
    ``to_csv``'s NA handling. Normalising here keeps the writer simple.
    """
    out: dict = {}
    for col in columns:
        value = row.get(col, pd.NA)
        if isinstance(value, pd.Timestamp):
            # ISO date (no time) for date columns, full ISO for timestamps
            out[col] = value.date().isoformat() if value.time().isoformat() == "00:00:00" else value.isoformat()
        elif value is pd.NA:
            out[col] = pd.NA
        else:
            out[col] = value
    return out


def append_row(table: str, row: dict) -> None:
    """Append ``row`` to the CSV for ``table``.

    The row must already include the primary key column (use
    :func:`next_id` to compute it). Missing columns are filled with
    ``pd.NA`` so the resulting CSV row has the same width as the schema.

    The caller is responsible for invalidating the Streamlit cache via
    ``st.cache_data.clear()`` after a batch of appends.
    """
    columns = EXPECTED_SCHEMAS[table]
    path = _csv_path(table)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_table(table)
    payload = _row_to_csv_dict(row, columns)
    new_row_df = pd.DataFrame([payload], columns=columns)
    merged = pd.concat([existing, new_row_df], ignore_index=True)
    merged.to_csv(path, index=False)


def update_row(table: str, key_column: str, key_value: str, updates: dict) -> None:
    """Patch one or more cells of the row whose ``key_column == key_value``.

    No-op (silent) if no row matches — the patient-age update path is
    deliberately tolerant so fixture patients that were never registered
    through the add-patient form don't trigger errors.
    """
    columns = EXPECTED_SCHEMAS[table]
    path = _csv_path(table)
    if not path.exists():
        return
    df = load_table(table)
    if df.empty or key_column not in df.columns:
        return
    mask = df[key_column].astype(str) == str(key_value)
    if not mask.any():
        return
    for col, value in updates.items():
        if col not in df.columns:
            # Allow updates to add a previously-empty column
            df[col] = pd.NA
        df.loc[mask, col] = value
    df.to_csv(path, index=False)


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

    Reads the CSV directly (not the cached ``load_all``) so the id is
    derived from the on-disk state at the moment of the call. This
    matches the previous ``_next_patient_id`` / ``_next_plan_id`` helpers
    but removes the session-state coupling.
    """
    prefix = NEW_ID_PREFIX[table]
    df = load_table(table)
    if df.empty:
        return _next_indexed_id(set(), prefix)
    # Find the primary key column for this table. It is always the first
    # column in the schema by convention.
    key_col = EXPECTED_SCHEMAS[table][0]
    used: set[str] = set(df[key_col].dropna().astype(str).tolist())
    return _next_indexed_id(used, prefix)
