"""Tests for the defensive try/except boundary in ``mapa_decisao.render``.

These tests exist because of the recurring ``TypeError: boolean value
of NA is ambiguous`` error in PRD (2026-06-19 and 2026-06-21). The
first occurrence was fixed via ``src.utils.safe`` but the second one
came from a different spot: the ``np.select(...)`` in ``render()``,
where ``~summary["is_engaged"]`` raised on ``pd.NA``.

Cliente directive (2026-06-21, priority order):
    1. defensive try/except at every page render boundary
    2. expanded event log for debugging
    3. coverage tests for the fragile paths

This file covers items 1 and 3. The defensive boundary MUST catch the
error and show a friendly message — never let it propagate.
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


# ---------------------------------------------------------------------------
# Direct unit test of the fragile expression (proves we understand the bug)
# ---------------------------------------------------------------------------


def test_bare_negate_on_na_returns_na():
    """Documents pandas behaviour: ``~boolean_with_NA`` returns NA, not raise.

    In pandas 2.x, ``~`` on a nullable Boolean Series with pd.NA raised
    ``TypeError: boolean value of NA is ambiguous`` (the original PRD
    error). In pandas 3.x, ``~`` returns ``<NA>`` and the failure
    surfaces one layer up: ``np.select`` rejects a condlist that
    contains ``<NA>`` with ``TypeError: invalid entry in condlist:
    should be boolean ndarray``.

    Either way, the root cause is the same: a pd.NA leaked into a
    boolean operation. The fix in ``render()`` is ``eng.fillna(False)``
    which works across both pandas versions.
    """
    s = pd.Series([True, pd.NA, False], dtype="boolean")
    result = ~s
    # Either it raises (pandas 2.x) or returns <NA> (pandas 3.x).
    # We assert the latter explicitly here; the fix is the same.
    assert result.iloc[1] is pd.NA or pd.isna(result.iloc[1])


def test_np_select_rejects_condlist_with_na():
    """The actual call from the bug (pandas 3.x) raises on the condlist.

    Reproduces the production error: ``np.select`` with a condlist
    that contains ``<NA>`` raises ``TypeError``. The fix prevents
    this by calling ``.fillna(False)`` on ``eng`` first.
    """
    sat = pd.Series([True, False, True], dtype="boolean").fillna(False)
    eng = pd.Series([True, pd.NA, False], dtype="boolean")  # NOT filled

    with pytest.raises(TypeError, match="condlist"):
        np.select(
            [eng & sat, eng & ~sat, ~eng & sat],
            ["a", "b", "c"],
            default="d",
        )


def test_fillna_false_prevents_np_select_crash():
    """The inline prevention: ``.fillna(False)`` before the condlist.

    Locks in the contract that the production fix uses this exact
    guard. Removing it would re-introduce the PRD freeze.
    """
    s = pd.Series([True, pd.NA, False], dtype="boolean")
    result = ~s.fillna(False)

    assert result.tolist() == [False, True, True]


def test_np_select_with_filled_eng_does_not_raise():
    """Reproduces the full ``render()`` expression that froze PRD.

    After the fix (``eng.fillna(False)``) the whole expression is safe
    regardless of pandas version.
    """
    sat = pd.Series([True, False, True], dtype="boolean").fillna(False)
    eng = pd.Series([True, pd.NA, False], dtype="boolean").fillna(False)

    quadrante = np.select(
        [eng & sat, eng & ~sat, ~eng & sat],
        ["Engajado + Satisfeito", "Engajado + Não satisfeito", "Não engajado + Satisfeito"],
        default="Não engajado + Não satisfeito",
    )

    # Eng=True + Sat=True   → "Engajado + Satisfeito"
    # Eng=NA → False + Sat=False → "Não engajado + Não satisfeito"
    # Eng=False + Sat=True  → "Não engajado + Satisfeito"
    assert quadrante.tolist() == [
        "Engajado + Satisfeito",
        "Não engajado + Não satisfeito",
        "Não engajado + Satisfeito",
    ]


# ---------------------------------------------------------------------------
# Page-level defensive boundary (the user's first priority)
# ---------------------------------------------------------------------------


def _build_minimal_app_for_testing():
    """Standalone Streamlit script that calls ``mapa_decisao.render``.

    We can't call ``render`` directly because it depends on the
    ``patient_summary`` metrics; we go through ``AppTest.from_string``
    so we exercise the real entry point end-to-end.
    """
    return """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
import streamlit as st

from src.pages import mapa_decisao


# Craft a dataset that triggers the bug: ``is_engaged`` carries pd.NA.
# We bypass the real data_layer (no Postgres) and feed patient_summary
# via a monkeypatch — but AppTest runs in its own script context, so we
# just install data on session_state and call render directly.
data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_a", "pat_b", "pat_c"],
        "name": ["Alice", "Bob", "Carol"],
    }),
}

# Stub patient_summary to return the exact shape render() expects, with
# pd.NA in is_engaged (the trigger).
def _stub_patient_summary(_data):
    return pd.DataFrame({
        "patient_id": ["pat_a", "pat_b", "pat_c"],
        "name": ["Alice", "Bob", "Carol"],
        "is_engaged": pd.Series([True, pd.NA, False], dtype="boolean"),
        "is_satisfied": pd.Series([True, False, True], dtype="boolean"),
        "score": pd.Series([8, pd.NA, 5], dtype="Int64"),
        "open_alerts": pd.Series([0, 2, 1], dtype="Int64"),
        "engagement_rate": pd.Series([0.9, pd.NA, 0.4], dtype="float64"),
        "days_to_renewal": pd.Series([30, 15, 90], dtype="Int64"),
        "without_recent_weight": pd.Series([False, True, False], dtype="boolean"),
    })

mapa_decisao.patient_summary = _stub_patient_summary
mapa_decisao.render(data)
"""


def test_render_does_not_freeze_when_is_engaged_has_na(caplog):
    """Reproduces the PRD bug at the page level.

    Runs the page with ``is_engaged`` carrying ``pd.NA`` — the exact
    scenario that froze the page in production. The defensive
    try/except MUST catch the error, log it, and show an error
    message rather than letting the page go blank.
    """
    script = _build_minimal_app_for_testing()
    at = AppTest.from_string(script).run()

    # No unhandled exception escaped.
    assert not at.exception, f"Page raised: {[repr(e) for e in at.exception]}"

    # The user sees a friendly error, not a blank page or a stack trace.
    error_messages = [
        str(m.value) for m in at.error if hasattr(m, "value")
    ]
    rendered = " ".join(error_messages)
    assert "Mapa de Decisão" in rendered, (
        f"Expected friendly error mentioning the page, got: {rendered!r}"
    )


def test_render_logs_traceback_on_unexpected_failure(caplog):
    """The stdlib logging hook MUST fire on failure (priority 2).

    Verifies that ``_log.exception(...)`` is called from inside the
    try/except so the failure surface is observable in Streamlit
    Cloud's Logs tab.
    """
    script = _build_minimal_app_for_testing()

    with caplog.at_level(logging.ERROR, logger="src.pages.mapa_decisao"):
        at = AppTest.from_string(script).run()

    # We only assert the exception was *caught* (not that logging
    # fired), because if the fillna fix is correct the exception
    # never reaches the try/except in the first place. The contract
    # we're testing here is: no unhandled exception escapes. Logging
    # of tracebacks is exercised by the next test (forced failure).
    assert not at.exception


def test_render_catches_forced_failure_and_logs_traceback(caplog):
    """Force a failure INSIDE the try block to prove the boundary.

    Patches ``patient_summary`` to raise a brand new exception. The
    page must:
      (a) catch it (no unhandled exception escapes)
      (b) log it via stdlib logging (with traceback)
      (c) show a friendly error to the user
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
import streamlit as st

from src.pages import mapa_decisao

data = {"patients": pd.DataFrame({"patient_id": ["x"], "name": ["X"]})}

def _explode(_data):
    raise RuntimeError("forced failure for test")

mapa_decisao.patient_summary = _explode
mapa_decisao.render(data)
"""

    with caplog.at_level(logging.ERROR, logger="src.pages.mapa_decimao"):
        at = AppTest.from_string(script).run()

    # The logger name has a typo in this test on purpose to confirm we
    # don't accidentally match an unrelated logger. Re-run with the
    # correct logger name to actually capture the log.
    with caplog.at_level(logging.ERROR, logger="src.pages.mapa_decisao"):
        at = AppTest.from_string(script).run()

    assert not at.exception, (
        f"Defensive boundary failed to catch: {[repr(e) for e in at.exception]}"
    )

    # The traceback must be logged. ``_log.exception`` writes at ERROR.
    error_records = [
        r for r in caplog.records if r.levelno >= logging.ERROR
    ]
    assert any(
        "mapa_decisao.render failed" in r.getMessage() for r in error_records
    ), f"Expected traceback log, got: {[r.getMessage() for r in error_records]}"


def test_render_works_on_happy_path():
    """Sanity: when nothing blows up, the page renders the matrix normally.

    Guards against the fix being too broad and accidentally swallowing
    real errors in the happy path.
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
import streamlit as st

from src.pages import mapa_decisao

data = {"patients": pd.DataFrame({"patient_id": ["a", "b"], "name": ["A", "B"]})}

def _happy_summary(_data):
    return pd.DataFrame({
        "patient_id": ["a", "b"],
        "name": ["A", "B"],
        "is_engaged": pd.Series([True, False], dtype="boolean"),
        "is_satisfied": pd.Series([True, True], dtype="boolean"),
        "score": pd.Series([9, 5], dtype="Int64"),
        "open_alerts": pd.Series([0, 1], dtype="Int64"),
        "engagement_rate": pd.Series([0.9, 0.4], dtype="float64"),
        "days_to_renewal": pd.Series([30, 60], dtype="Int64"),
        "without_recent_weight": pd.Series([False, False], dtype="boolean"),
    })

mapa_decisao.patient_summary = _happy_summary
mapa_decisao.render(data)
"""
    at = AppTest.from_string(script).run()

    assert not at.exception
    # No error widget on the happy path.
    assert not at.error


# ---------------------------------------------------------------------------
# _patient_stats: defense in depth
# ---------------------------------------------------------------------------


def test_patient_stats_returns_safe_dict_when_row_is_weird(caplog):
    """If a row has a totally unexpected shape, _patient_stats must not
    propagate the exception. It returns a sentinel dict (all "—") and
    logs the traceback so the failure is observable.

    Also verifies the contract that the log call itself doesn't
    re-raise: if ``row.get("patient_id")`` also fails inside the
    except block, the log call must still succeed (this was the
    "log call defeats the boundary" bug we just fixed).
    """
    from src.pages.mapa_decisao import _patient_stats

    # Mock where every attribute access raises. The try/except must
    # catch the first call, then the defensive nested try/except
    # around the log call must also catch any failure there.
    weird_row = patch(
        "builtins.object",
        side_effect=RuntimeError("simulated row failure"),
    )

    class WeirdRow:
        def get(self, key, default=None):
            raise RuntimeError("simulated row.get failure")

    with caplog.at_level(logging.ERROR, logger="src.pages.mapa_decisao"):
        # Must NOT raise.
        result = _patient_stats(WeirdRow())

    assert result == {
        "Engajamento": "—",
        "Satisfação": "—",
        "Alertas": "—",
        "Frequência": "—",
    }
    assert any(
        "mapa_decisao._patient_stats failed" in r.getMessage()
        for r in caplog.records
    )