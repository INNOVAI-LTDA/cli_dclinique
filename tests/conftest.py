"""Pytest configuration and shared fixtures for the MAP shell test suite.

The MAP shell is a Streamlit app with no traditional test runner. These
tests rely on two complementary strategies:

1.  ``FakeSessionState`` + ``monkeypatch`` -- pure unit tests that
    substitute ``st.session_state`` with a dict-like object. This lets us
    exercise the submit handlers and id-generation helpers without
    spinning up a Streamlit runtime.

2.  ``streamlit.testing.v1.AppTest`` -- integration tests that run the
    real ``app.py`` script in an in-process simulator, asserting on the
    widgets, session state, and rendered markup.

CSV isolation
-------------
Every test gets a fresh copy of the seed ``data/csv/`` directory under
``tmp_path``. The data layer's ``_csv_dir_callable`` is monkeypatched
to return that copy, so any ``append_row`` / ``update_row`` call during
the test writes there instead of touching the developer's local
checkout. After the test, ``tmp_path`` is wiped by pytest -- the next
test starts from a clean seed again.

Neon branching for integration tests
------------------------------------
The ``db_branch`` session-scoped fixture creates an ephemeral Neon
Postgres branch via the Neon HTTP API, exposes its DSN to the test, and
deletes the branch on teardown. The DSN is exported as
``DCLINIQUE_DSN`` so the lazy ``connection.get_engine()`` picks it up.

Skip conditions (fixture is SKIPPED, not failed):
  - ``DCLINIQUE_BACKEND=csv`` is set (dev fallback)
  - ``NEON_API_KEY`` or ``NEON_PROJECT_ID`` missing

The fallback for dev without internet is the existing ``csv_dir``
fixture, which points at the (now zero-row) seed CSVs.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

CSV_DIR = Path(__file__).resolve().parents[1] / "data" / "csv"


# ---------------------------------------------------------------------------
# Helpers used by the db_branch fixture
# ---------------------------------------------------------------------------


def _has_neon_creds() -> bool:
    """True se o ambiente tem ``NEON_API_KEY`` E ``NEON_PROJECT_ID``."""
    return bool(os.environ.get("NEON_API_KEY")) and bool(
        os.environ.get("NEON_PROJECT_ID")
    )


def _should_use_csv() -> bool:
    """True se o backend ativo e' CSV (forcado por env ou falta de creds).

    Ordem de checagem:
      1. ``DCLINIQUE_BACKEND=csv`` explicito -> True.
      2. Falta de creds Neon -> True.
    """
    if os.environ.get("DCLINIQUE_BACKEND") == "csv":
        return True
    if not _has_neon_creds():
        return True
    return False


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


@pytest.fixture(scope="session")
def db_branch():
    """Cria um branch efemero no Neon, yields DSN, deleta no teardown.

    Skip (NAO falha) se o backend ativo for CSV ou se as creds Neon
    estiverem ausentes. Para dev local sem internet, use a fixture
    ``csv_dir`` em vez desta.

    Quando o fixture roda, o DSN do branch fica exportado em
    ``os.environ['DCLINIQUE_DSN']`` para que ``connection.get_engine()``
    resolva sem precisar de ``st.secrets`` (Streamlit context nao existe
    em testes).
    """
    if _should_use_csv():
        pytest.skip(
            "Neon branching desabilitado: "
            "DCLINIQUE_BACKEND=csv ou creds (NEON_API_KEY/NEON_PROJECT_ID) ausentes"
        )

    # Imports lazy: requests so' entra quando o branch e' de fato criado.
    import requests

    api_key = os.environ["NEON_API_KEY"]
    project_id = os.environ["NEON_PROJECT_ID"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base = f"https://console.neon.tech/api/v2/projects/{project_id}"

    # Cria branch efemero (nome unico por PID pra nao colidir entre sessoes)
    create_resp = requests.post(
        f"{base}/branches",
        headers=headers,
        json={"branch": {"name": f"test-ephemeral-{os.getpid()}"}},
        timeout=30,
    )
    create_resp.raise_for_status()
    branch = create_resp.json()["branch"]
    branch_id = branch["id"]

    try:
        # Pega connection URI do branch
        conn_resp = requests.get(
            f"{base}/branches/{branch_id}/connection_uri",
            headers=headers,
            params={"pooled": False, "database_name": "neondb"},
            timeout=30,
        )
        conn_resp.raise_for_status()
        dsn = conn_resp.json()["connection_uri"]
        os.environ["DCLINIQUE_DSN"] = dsn

        yield {"dsn": dsn, "branch_id": branch_id, "project_id": project_id}
    finally:
        # Deleta branch (best-effort; falhas de cleanup nao quebram o test)
        try:
            requests.delete(
                f"{base}/branches/{branch_id}",
                headers=headers,
                timeout=30,
            )
        except Exception:
            pass  # cleanup is best-effort; branch leak tolerated


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
def base_data(csv_dir):
    """Return the canonical snapshot of the seed CSVs via the data layer.

    Reloading via ``load_all`` (not the cached ``get_data``) ensures the
    fixture reflects the test's isolated tmp directory.
    """
    from src.data_layer import load_all

    return load_all()


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


# ---------------------------------------------------------------------------
# Phase 0 fixtures for the path B refactor (docs/caminho_b_plano.md §3)
# ---------------------------------------------------------------------------
# These are additive — they don't conflict with the v1 fixtures above. Tests
# for ``src.core`` (Phase 0+) use the new fixtures; existing v1 tests continue
# to use the v1 fixtures (FakeSessionState, db_branch, csv_dir, base_data).


@pytest.fixture
def data_dict() -> dict[str, pd.DataFrame]:
    """Load all 11 tables via the data layer (CSV backend in dev by default).

    Distinct from ``base_data`` in that it does NOT depend on the ``csv_dir``
    fixture (no seed copy, no monkeypatch) — it just calls ``load_all()``
    against whatever backend ``DCLINIQUE_BACKEND`` resolves to. The PowerShell
    wrapper script forces ``DCLINIQUE_BACKEND=csv`` so this is offline-safe.
    """
    from src.data_layer import load_all

    return load_all()


@pytest.fixture
def backend() -> str:
    """Return the active backend name (``'csv'`` or ``'postgres'``)."""
    return os.environ.get("DCLINIQUE_BACKEND", "csv")


@pytest.fixture
def tmp_csv_dir(tmp_path: Path) -> Path:
    """Provide an isolated, empty CSV directory for Phase 0 smoke tests.

    Distinct from ``csv_dir`` (which copies seed CSVs in); this just gives
    the test a clean subdirectory under ``tmp_path`` to write into.
    """
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    return csv_dir


@pytest.fixture
def expected_schemas() -> dict[str, list[str]]:
    """The expected column lists per table, from ``src/schemas.py``."""
    from src.schemas import EXPECTED_SCHEMAS

    return EXPECTED_SCHEMAS
