"""Unit tests for ``src.components.patient_header`` helper functions.

The helpers (``_or_dash``, ``_is_missing``, ``_age_text``) are the
non-Streamlit surface of the header. They govern the "missing value"
contract that the ficha relies on — every place the ficha used to
render ``"None"`` or ``"nan"`` (the June 2026 regression) now uses
one of these helpers. Pure-function tests, no Streamlit runtime.
"""
from __future__ import annotations

import math

import pandas as pd

from src.components.patient_header import _age_text, _is_missing, _or_dash


# ---------------------------------------------------------------------------
# _is_missing
# ---------------------------------------------------------------------------


def test_is_missing_none():
    assert _is_missing(None) is True


def test_is_missing_empty_string():
    assert _is_missing("") is True


def test_is_missing_whitespace_string():
    assert _is_missing("   ") is True


def test_is_missing_nan_float():
    assert _is_missing(float("nan")) is True


def test_is_missing_pandas_nat():
    assert _is_missing(pd.NaT) is True


def test_is_missing_real_value():
    assert _is_missing("123.456.789-00") is False
    assert _is_missing(42) is False
    assert _is_missing(0) is False  # 0 is a real age, not missing


def test_is_missing_arbitrary_object_does_not_raise():
    # A custom object that doesn't support pd.isna() shouldn't
    # trip the helper — falls through to False.
    class Weird:
        pass

    assert _is_missing(Weird()) is False


# ---------------------------------------------------------------------------
# _or_dash
# ---------------------------------------------------------------------------


def test_or_dash_returns_dash_for_none():
    assert _or_dash(None) == "-"


def test_or_dash_returns_dash_for_nan():
    assert _or_dash(float("nan")) == "-"


def test_or_dash_returns_dash_for_empty_string():
    assert _or_dash("") == "-"


def test_or_dash_returns_stripped_value():
    assert _or_dash("  8887777  ") == "8887777"


def test_or_dash_passes_through_real_value():
    assert _or_dash("123.456.789-00") == "123.456.789-00"
    assert _or_dash(42) == "42"


# ---------------------------------------------------------------------------
# _age_text
# ---------------------------------------------------------------------------


def test_age_text_empty_when_none():
    """Per the June 2026 spec the header hides 'anos' entirely
    when there's no real age — and does NOT show '-'. The empty
    string is intentional."""
    assert _age_text(None) == ""


def test_age_text_empty_when_nan():
    assert _age_text(float("nan")) == ""


def test_age_text_empty_when_zero():
    """Age 0 (e.g. newborn) is rare in this casca but should
    still hide the suffix when the value is 0 from the CSV —
    we treat <=0 as 'no real age' to match the wizard's
    `_coerce_int_or_none` guard."""
    assert _age_text(0) == ""


def test_age_text_real_age_includes_anos():
    assert _age_text(42) == "42 anos"
    assert _age_text(30) == "30 anos"


def test_age_text_handles_pandas_int():
    """The header receives the patient dict from
    ``patient_summary`` which sometimes wraps ints in
    ``numpy.int64`` / ``pd.Int64``. The helper coerces them
    to Python int via ``int(value)``."""
    assert _age_text(pd.Series([42]).iloc[0]) == "42 anos"
    assert _age_text(math.floor(35.7)) == "35 anos"


def test_age_text_returns_empty_for_garbage_string():
    """A non-numeric string isn't a real age — render empty."""
    assert _age_text("not a number") == ""
