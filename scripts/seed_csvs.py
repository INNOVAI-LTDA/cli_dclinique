"""Regenerate the 11 reference CSVs in ``data/csv/`` from ``load_mock_data``.

This script is a one-shot seed for the new on-disk data layer. It is
intentionally NOT called at runtime — the app reads the CSVs directly via
``src.data_layer.load_all``. Run it only when the schema or seed fixture
changes, and commit the resulting CSVs to the repo so the shell has
something to read on a fresh checkout.

Usage (from the project root, with the project venv on PATH):

    python scripts/seed_csvs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``src.*`` importable when this script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.mock_data import load_mock_data
from src.schemas import EXPECTED_SCHEMAS

CSV_DIR = PROJECT_ROOT / "data" / "csv"


def _normalise(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Reorder to the schema column order and fill missing columns with NaN.

    The CSVs are written in the canonical column order from
    ``EXPECTED_SCHEMAS`` so ``pd.read_csv`` (which preserves order) lines
    up with the rest of the app without surprises. Extra columns (none
    today) are dropped to keep the file shape honest.
    """
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    return df[columns]


def main() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    data = load_mock_data()

    written: list[str] = []
    for table, columns in EXPECTED_SCHEMAS.items():
        if table not in data:
            print(f"  ! skip {table}: not in load_mock_data()", file=sys.stderr)
            continue
        df = _normalise(data[table], columns)
        path = CSV_DIR / f"{table}.csv"
        # index=False keeps the row order stable across regenerations.
        df.to_csv(path, index=False)
        written.append(f"{table}.csv ({len(df)} rows)")

    print(f"Wrote {len(written)} CSVs to {CSV_DIR}:")
    for line in written:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
