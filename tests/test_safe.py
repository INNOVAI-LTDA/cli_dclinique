"""Unit tests for ``src.utils.safe``.

These helpers exist because the legacy pattern ``x == x`` (NaN-check)
raises ``TypeError: boolean value of NA is ambiguous`` when ``x`` is
``pd.NA`` — the sentinel carried by ``Int64`` / ``boolean`` / ``string``
pandas nullable columns coming out of the Postgres backend. The
``safe_*`` helpers centralize the NA-safety contract.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.utils.safe import is_missing, safe_float, safe_int, safe_pct, safe_str


# ---------------------------------------------------------------------------
# is_missing
# ---------------------------------------------------------------------------


def test_is_missing_none():
    assert is_missing(None) is True


def test_is_missing_nan_float():
    assert is_missing(float("nan")) is True


def test_is_missing_numpy_nan():
    assert is_missing(np.nan) is True


def test_is_missing_pandas_na():
    """The headline bug: ``pd.NA`` must NOT raise."""
    assert is_missing(pd.NA) is True


def test_is_missing_pandas_nat():
    assert is_missing(pd.NaT) is True


def test_is_missing_empty_string():
    assert is_missing("") is True


def test_is_missing_whitespace_string():
    assert is_missing("   ") is True
    assert is_missing("\n\t  ") is True


def test_is_missing_real_value():
    assert is_missing("Maria") is False
    assert is_missing(42) is False
    assert is_missing(0) is False  # 0 is a real value, not missing
    assert is_missing(False) is False


def test_is_missing_arbitrary_object_does_not_raise():
    """Defensive: arbitrary user classes that ``pd.isna`` doesn't
    understand fall through to False rather than raising."""

    class Weird:
        pass

    assert is_missing(Weird()) is False


# ---------------------------------------------------------------------------
# safe_int
# ---------------------------------------------------------------------------


def test_safe_int_real_int():
    assert safe_int(42) == 42
    assert safe_int(0) == 0  # 0 is a real value


def test_safe_int_real_float():
    assert safe_int(42.7) == 42  # int() truncates


def test_safe_int_missing_returns_default():
    """The headline case: pd.NA must NOT raise; returns the default."""
    assert safe_int(pd.NA) == 0
    assert safe_int(None) == 0
    assert safe_int(float("nan")) == 0


def test_safe_int_custom_default():
    assert safe_int(pd.NA, default="-") == "-"
    assert safe_int(None, default="—") == "—"


def test_safe_int_uncastable_returns_default():
    """A non-numeric string is not a real int — return default."""
    assert safe_int("not a number") == 0
    assert safe_int("not a number", default="-") == "-"


def test_safe_int_pandas_nullable_int():
    """Int64 (nullable) values pass through correctly."""
    s = pd.Series([1, pd.NA, 3], dtype="Int64")
    assert safe_int(s.iloc[0]) == 1
    assert safe_int(s.iloc[1]) == 0  # NA → default
    assert safe_int(s.iloc[2]) == 3


def test_safe_int_numpy_int64():
    """numpy int64 (from DataFrame .iloc[0]) must round-trip through int()."""
    arr = np.array([42], dtype=np.int64)
    assert safe_int(arr[0]) == 42


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------


def test_safe_float_real_float():
    assert safe_float(3.14) == pytest.approx(3.14)


def test_safe_float_missing_returns_default():
    assert safe_float(pd.NA) == 0.0
    assert safe_float(None) == 0.0


def test_safe_float_custom_default():
    assert safe_float(pd.NA, default=0.5) == 0.5
    assert safe_float(pd.NA, default="-") == "-"


def test_safe_float_uncastable_returns_default():
    assert safe_float("not a number") == 0.0
    assert safe_float("not a number", default="-") == "-"


# ---------------------------------------------------------------------------
# safe_str
# ---------------------------------------------------------------------------


def test_safe_str_real_value():
    assert safe_str("Maria") == "Maria"
    assert safe_str(42) == "42"


def test_safe_str_strips_whitespace():
    assert safe_str("  8887777  ") == "8887777"


def test_safe_str_missing_returns_default():
    assert safe_str(pd.NA) == ""
    assert safe_str(None) == ""
    assert safe_str(float("nan")) == ""


def test_safe_str_empty_string_treated_as_missing():
    assert safe_str("") == ""
    assert safe_str("   ") == ""


def test_safe_str_custom_default():
    assert safe_str(pd.NA, default="-") == "-"
    assert safe_str(None, default="—") == "—"


def test_safe_str_does_not_render_na_literal():
    """Critical: ``str(pd.NA)`` returns ``'<NA>'``. ``safe_str`` must not."""
    assert "<NA>" not in safe_str(pd.NA)


# ---------------------------------------------------------------------------
# safe_pct
# ---------------------------------------------------------------------------


def test_safe_pct_real_fraction():
    assert safe_pct(0.85) == "85%"
    assert safe_pct(1.0) == "100%"
    assert safe_pct(0.0) == "0%"


def test_safe_pct_missing_returns_default():
    assert safe_pct(pd.NA) == "0%"
    assert safe_pct(None) == "0%"


def test_safe_pct_custom_default():
    assert safe_pct(pd.NA, default="—") == "—"


def test_safe_pct_uncastable_returns_default():
    assert safe_pct("not a number") == "0%"
    assert safe_pct("not a number", default="-") == "-"


def test_safe_pct_rounds_correctly():
    assert safe_pct(0.855) == "86%"  # rounds up
    assert safe_pct(0.844) == "84%"  # rounds down


# ---------------------------------------------------------------------------
# Regression test for the PRD bug (mapa_decisao.py:243)
# ---------------------------------------------------------------------------


def test_mapa_decisao_score_na_does_not_raise():
    """Regression: ``score == score`` raised TypeError on pd.NA in PRD
    (2026-06-21). The fix uses ``safe_int`` instead. This test simulates
    the row that caused the bug: a patient with no satisfaction_entries,
    so ``score`` comes back as ``pd.NA``.
    """
    row = pd.Series(
        {
            "patient_id": "pat_new_001",
            "name": "Maria",
            "engagement_rate": 0.5,
            "score": pd.NA,  # the trigger
            "open_alerts": 2,
        }
    )

    # The exact operations the original _patient_stats performed,
    # rewritten NA-safe. None must raise.
    score_display = f"{safe_int(row.get('score'))}"
    alerts_display = str(safe_int(row.get("open_alerts")))
    engagement_display = safe_pct(row.get("engagement_rate"))

    assert score_display == "0"
    assert alerts_display == "2"
    assert engagement_display == "50%"
