"""Unit tests for ``src.data_layer.postgres_backend._sanitize_param``.

The sanitizer protects the data layer from pandas-specific
"missing" sentinels (``pd.NaT``, ``pd.NA``, ``float('nan')``)
that psycopg would otherwise bind to a far-future timestamp —
year 48113 — and the next ``SELECT *`` would then blow up on
the read because ``psycopg``'s ``TimestampLoader`` rejects years
past 10K with ``DataError: timestamp too large``.

The bug it guards against surfaced in 2026-06 when the PDF
importer wrote ``pd.NaT`` as ``treatment_plans.end_date``
because the source PDF did not carry an explicit end date, the
parser didn't extract one, and ``_to_date_or_nat`` fell back
to ``pd.NaT`` per its contract. Without this sanitizer, every
follow-up render of the app crashed with the ``DataError``
above.

These tests are pure (no DB connection, no Streamlit runtime)
so they can run in the CSV-backend dev environment.
"""
from __future__ import annotations

import math

import pandas as pd

from src.data_layer.postgres_backend import _sanitize_param


def test_sanitize_nat_becomes_none():
    """``pd.NaT`` is the canonical "missing date" sentinel; it must
    bind as SQL NULL, not as a far-future timestamp."""
    assert _sanitize_param(pd.NaT) is None


def test_sanitize_nan_becomes_none():
    """``float('nan')`` and ``pd.NA`` follow the same rule."""
    assert _sanitize_param(float("nan")) is None
    assert _sanitize_param(pd.NA) is None


def test_sanitize_none_passes_through():
    """``None`` is already the canonical "missing" value."""
    assert _sanitize_param(None) is None


def test_sanitize_real_timestamp_passes_through():
    """A real ``pd.Timestamp`` is left as-is so psycopg can bind
    it to a TIMESTAMP column."""
    ts = pd.Timestamp("2026-05-30")
    assert _sanitize_param(ts) is ts


def test_sanitize_real_int_passes_through():
    """Numeric values are not touched."""
    assert _sanitize_param(42) == 42
    assert _sanitize_param(0) == 0
    assert _sanitize_param(-1) == -1


def test_sanitize_real_string_passes_through():
    """Strings are not touched (the parser / wizard pre-trim them)."""
    assert _sanitize_param("Bruno") == "Bruno"
    assert _sanitize_param("") == ""


def test_sanitize_real_float_passes_through():
    """Finite floats (weights, scores) are not touched."""
    assert _sanitize_param(72.5) == 72.5
    assert _sanitize_param(0.0) == 0.0
    # ``math.inf`` is a "real" value from the data layer's POV;
    # the column would reject it, but that's the caller's concern.
    assert _sanitize_param(math.inf) == math.inf


def test_sanitize_unusual_object_does_not_raise():
    """Custom objects (e.g., a list or a dict slipped in by
    accident) must not crash the sanitizer — they pass through."""
    sentinel = object()
    assert _sanitize_param(sentinel) is sentinel
    assert _sanitize_param({"a": 1}) == {"a": 1}
    assert _sanitize_param([1, 2, 3]) == [1, 2, 3]
