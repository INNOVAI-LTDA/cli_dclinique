"""Unit tests for ``src.pages.ficha_paciente`` helper functions.

The ficha plan table gained a "Frequência de Aplicação" column in
June 2026. The cell is built by ``_format_frequencia_aplicacao``
from the satellite ``execution_summary`` row. The empty-state
guard for the weight chart lives in ``_has_weight_data``. Both
helpers are pure functions of their input DataFrame / Series, so
they can be tested without a Streamlit runtime.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.pages.ficha_paciente import (
    _chart_empty_state_html,
    _format_age,
    _format_frequencia_aplicacao,
    _format_int,
    _has_weight_data,
    _is_missing,
    _or_dash,
)


# ---------------------------------------------------------------------------
# _format_frequencia_aplicacao
# ---------------------------------------------------------------------------


def test_frequencia_aplicacao_full_format():
    """Both sessions_expected and frequency_type present —
    cell is "{N} sessões, {frequency_type}"."""
    row = pd.Series(
        {"sessions_expected": 10, "frequency_type": "semanal"}
    )
    assert _format_frequencia_aplicacao(row) == "10 sessões, semanal"


def test_frequencia_aplicacao_drops_sessoes_when_missing():
    """When sessions_expected is missing/NaN, drop the
    "{N} sessões, " prefix but keep the frequency_type."""
    row = pd.Series({"sessions_expected": None, "frequency_type": "semanal"})
    assert _format_frequencia_aplicacao(row) == "semanal"

    row_nan = pd.Series(
        {"sessions_expected": float("nan"), "frequency_type": "semanal"}
    )
    assert _format_frequencia_aplicacao(row_nan) == "semanal"


def test_frequencia_aplicacao_dash_when_frequency_missing():
    """Per the June 2026 spec, missing frequency_type collapses
    the whole cell to '-' (no stray empty comma)."""
    row = pd.Series({"sessions_expected": 10, "frequency_type": None})
    assert _format_frequencia_aplicacao(row) == "-"


def test_frequencia_aplicacao_handles_zero_sessions():
    """0 sessions_expected is a real value (not missing) — the
    cell renders '0 sessões, X'. The ficha distinguishes 'no
    sessions' from 'no data' (which the helper also handles)."""
    row = pd.Series({"sessions_expected": 0, "frequency_type": "dose única"})
    assert _format_frequencia_aplicacao(row) == "0 sessões, dose única"


# ---------------------------------------------------------------------------
# _has_weight_data
# ---------------------------------------------------------------------------


def test_has_weight_data_true_with_rows():
    df = pd.DataFrame(
        {
            "weight_id": ["w1"],
            "patient_id": ["pat_001"],
            "measurement_date": pd.to_datetime(["2026-06-01"]),
            "weight": [70.5],
        }
    )
    assert _has_weight_data(df, "pat_001") is True


def test_has_weight_data_false_when_empty():
    df = pd.DataFrame(columns=["weight_id", "patient_id", "measurement_date", "weight"])
    assert _has_weight_data(df, "pat_001") is False


def test_has_weight_data_false_for_other_patient():
    """The chart is per-patient — entries for a different
    patient should not flip the guard."""
    df = pd.DataFrame(
        {
            "weight_id": ["w1"],
            "patient_id": ["pat_other"],
            "measurement_date": pd.to_datetime(["2026-06-01"]),
            "weight": [70.5],
        }
    )
    assert _has_weight_data(df, "pat_001") is False


def test_has_weight_data_false_when_all_dates_missing():
    """A row with NaT measurement_date doesn't count — the
    chart can't plot it. Guards against a malformed row
    bypassing the empty state."""
    df = pd.DataFrame(
        {
            "weight_id": ["w1"],
            "patient_id": ["pat_001"],
            "measurement_date": pd.to_datetime([None]),
            "weight": [70.5],
        }
    )
    assert _has_weight_data(df, "pat_001") is False


def test_has_weight_data_handles_none_input():
    """Defensive: a None DataFrame (edge case in tests) is
    treated as 'no data' instead of raising."""
    assert _has_weight_data(None, "pat_001") is False


# ---------------------------------------------------------------------------
# _format_age / _or_dash
# ---------------------------------------------------------------------------


def test_format_age_real_value():
    assert _format_age(42) == "42 anos"


def test_format_age_missing_returns_empty_string():
    """Per the spec, missing age renders as '' (no '-', no
    'anos') — the info row already reserves the slot."""
    assert _format_age(None) == ""
    assert _format_age(float("nan")) == ""


def test_format_age_zero_treated_as_missing():
    """Age <= 0 is treated as 'no real age' (matches wizard's
    coerce_int_or_none guard and the patient_header._age_text
    behavior)."""
    assert _format_age(0) == ""


def test_or_dash_missing_value():
    assert _or_dash(None) == "-"
    assert _or_dash(float("nan")) == "-"


def test_or_dash_real_value():
    assert _or_dash("Maria") == "Maria"


# ---------------------------------------------------------------------------
# _format_int
# ---------------------------------------------------------------------------


def test_format_int_real_value():
    assert _format_int(10) == "10"


def test_format_int_missing_returns_dash():
    """Per the June 2026 spec, missing session counts render
    as '-' (not '0'). The operator distinguishes 'no data'
    from 'zero completed'."""
    assert _format_int(None) == "-"
    assert _format_int(float("nan")) == "-"


def test_format_int_zero_is_zero():
    """0 is a real value — render as '0', not '-'."""
    assert _format_int(0) == "0"


# ---------------------------------------------------------------------------
# _chart_empty_state_html
# ---------------------------------------------------------------------------


def test_chart_empty_state_html_contains_caption():
    """The empty state HTML must include the literal phrase
    'Não há dados para exibição.' (June 2026 spec)."""
    html = _chart_empty_state_html()
    assert "Não há dados para exibição." in html


def test_chart_empty_state_html_contains_svg():
    """The empty state uses an inline SVG (not a remote
    image), so the HTML carries a ``<svg>`` element."""
    html = _chart_empty_state_html()
    assert "<svg" in html
    assert "</svg>" in html


def test_chart_empty_state_html_no_external_image():
    """Defensive: we want the empty state to render even if
    the deploy is missing ``data/images/...``. The HTML must
    not reference a remote image src."""
    html = _chart_empty_state_html()
    assert "<img" not in html
    assert "src=" not in html
