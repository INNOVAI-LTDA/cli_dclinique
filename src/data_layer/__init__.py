"""CSV-backed data layer for the MAP shell.

This package replaces the previous in-memory ``src.mock_data`` flow with an
on-disk CSV store under ``data/csv/``. The full public surface is
re-exported from :mod:`src.data_layer` itself, so the rest of the app can
just ``from src.data_layer import load_all, append_row, next_id, update_row``.

The CSVs are the single source of truth at runtime. The Streamlit cache
(``@st.cache_data`` on ``app.get_data``) is invalidated by the submit
handlers via ``st.cache_data.clear()`` after each ``append_row`` /
``update_row`` call, so a subsequent render re-reads the CSVs.
"""
from __future__ import annotations

from .csv_backend import (
    append_row,
    csv_dir,
    load_all,
    load_table,
    next_id,
    update_row,
)

__all__ = ["append_row", "csv_dir", "load_all", "load_table", "next_id", "update_row"]
