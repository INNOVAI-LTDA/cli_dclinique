"""Pytest configuration and shared fixtures for the MAP shell test suite.

The MAP shell is a Streamlit app with no traditional test runner. These
tests rely on two complementary strategies:

1.  ``FakeSessionState`` + ``monkeypatch`` — pure unit tests that
    substitute ``st.session_state`` with a dict-like object. This lets us
    exercise the submit handlers and id-generation helpers without
    spinning up a Streamlit runtime.

2.  ``streamlit.testing.v1.AppTest`` — integration tests that run the
    real ``app.py`` script in an in-process simulator, asserting on the
    widgets, session state, and rendered markup.

CSV isolation
-------------
Every test gets a fresh copy of the seed ``data/csv/`` directory under
``tmp_path``. The data layer's ``_csv_dir_callable`` is monkeypatched
to return that copy, so any ``append_row`` / ``update_row`` call during
the test writes there instead of touching the developer's local
checkout. After the test, ``tmp_path`` is wiped by pytest — the next
test starts from a clean seed again.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

CSV_DIR = Path(__file__).resolve().parents[1] / "data" / "csv"


class FakeSessionState(dict):
    """Dict that mimics the subset of Streamlit session_state used by helpers."""

    def setdefault(self, key: str, default: Any) -> Any:  # type: ignore[override]
        if key not in self:
            self[key] = default
        return self[key]

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return dict.get(self, key, default)


@pytest.fixture
def fake_session_state(monkeypatch):
    """Replace ``streamlit.session_state`` with a FakeSessionState.

    Returns the FakeSessionState instance so tests can pre-populate keys
    or inspect them after the helper runs.
    """
    import streamlit as st

    state = FakeSessionState()
    monkeypatch.setattr(st, "session_state", state)
    return state


@pytest.fixture
def base_data(csv_dir):
    """Return the canonical snapshot of the seed CSVs via the data layer.

    Reloading via ``load_all`` (not the cached ``get_data``) ensures the
    fixture reflects the test's isolated tmp directory.
    """
    from src.data_layer import load_all

    return load_all()


@pytest.fixture
def csv_dir(tmp_path, monkeypatch):
    """Copy the seed ``data/csv/`` to ``tmp_path/csv`` and redirect the data layer.

    The redirect is in effect for the duration of the test, so any
    ``append_row`` / ``update_row`` / ``load_table`` call writes to the
    tmp directory. The cleanup is handled by pytest's ``tmp_path``
    fixture (the directory is removed after the test).
    """
    import src.data_layer.csv_backend as backend

    test_dir = tmp_path / "csv"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    shutil.copytree(CSV_DIR, test_dir)
    monkeypatch.setattr(backend, "_csv_dir_callable", lambda: test_dir)
    return test_dir


@pytest.fixture
def app_path(tmp_path, monkeypatch):
    """Return an absolute path to app.py for AppTest to load."""
    import os

    return os.path.abspath("app.py")


@pytest.fixture
def workdir():
    """Pin cwd to the worktree root for the duration of the test."""
    import os

    original = os.getcwd()
    yield os.path.abspath(".")
    os.chdir(original)


@pytest.fixture(autouse=True)
def _isolate_streamlit_cache():
    """Reset Streamlit's memoised caches between tests so state from
    one test never leaks into another."""
    try:
        from streamlit.runtime import caching

        caching.cache_data.clear()
    except Exception:
        pass
    yield
    try:
        from streamlit.runtime import caching

        caching.cache_data.clear()
    except Exception:
        pass


def patient_rows_only(base: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Helper: just the patients DataFrame from a base data dict."""
    return base["patients"]
