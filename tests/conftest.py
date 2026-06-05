"""Pytest configuration and shared fixtures for the MAP shell test suite.

The MAP shell is a Streamlit app with no traditional test runner. These
tests rely on two complementary strategies:

1.  ``FakeSessionState`` + ``monkeypatch`` — pure unit tests that
    substitute ``st.session_state`` with a dict-like object. This lets us
    exercise the merge helpers, ID generators, and submit handlers
    without spinning up a Streamlit runtime.

2.  ``streamlit.testing.v1.AppTest`` — integration tests that run the
    real ``app.py`` script in an in-process simulator, asserting on the
    widgets, session state, and rendered markup.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import pytest


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
def base_data():
    """Return the canonical ``load_mock_data()`` snapshot."""
    from src.mock_data import load_mock_data

    return load_mock_data()


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


def patient_rows_with_extras(base: dict[str, pd.DataFrame], extras: list[dict]) -> pd.DataFrame:
    """Helper: build a patients DataFrame that includes the given extras
    (matches what ``merge_extra_patients`` returns)."""
    from src.schemas import EXPECTED_SCHEMAS

    extras_df = pd.DataFrame(extras, columns=EXPECTED_SCHEMAS["patients"])
    extras_df["created_at"] = pd.to_datetime(extras_df["created_at"], errors="coerce")
    return pd.concat([base["patients"], extras_df], ignore_index=True)
