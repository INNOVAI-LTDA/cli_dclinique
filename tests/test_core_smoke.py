"""Smoke tests: importability + fixture sanity for Phase 0.

These tests are intentionally minimal — Phase 0 only validates that the
infrastructure (linter, pytest, fixtures, conftest) works. Phase 1+ adds the
real roundtrip and unit tests for ``src/core/repos.py``, ``types.py``, etc.

If any of these tests fail, the *infrastructure* is broken — not the code
under test. Fix the infrastructure first (script, venv, pyproject, conftest)
before debugging domain code.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd


def test_imports() -> None:
    """All submodules of ``src.core`` can be imported without ImportError.

    N4 / N7: catches missing imports at the smoke layer so a typo in a
    module name surfaces here rather than at runtime in a page.
    """
    for module_name in ("src.core", "src.core._typing"):
        module = importlib.import_module(module_name)
        assert module is not None, f"Failed to import {module_name}"


def test_version_exposed() -> None:
    """``src.core`` exposes a ``__version__`` string (criterion de aceite §3)."""
    import src.core

    assert hasattr(src.core, "__version__"), "src.core.__version__ missing"
    assert isinstance(src.core.__version__, str)
    # Fase 4 (consumo de ``attendance_rate`` em ``mapa_decisao.py`` como 3a
    # dimensao visual -- 5a classe "Sem comparecimento") bumpara para
    # v0.4.0. Historico:
    #   v0.1.0 (Fase 1, types + repos)
    #   v0.2.0 (Fase 2, frequency)
    #   v0.3.0 (Fase 3, alerts + persistence)
    # Manter atualizado a cada fase -- o numero e' parte do criterio
    # de aceite (N9: o version bump e' parte do phase report).
    assert src.core.__version__ == "0.4.0"


def test_typing_exposes_data_dict() -> None:
    """``src.core._typing`` exposes ``DataDict`` as a generic alias."""
    from src.core._typing import DataDict

    assert DataDict is not None
    # ``DataDict`` is a ``dict[str, pd.DataFrame]`` alias; instantiation works
    # even when no real DataFrames are present (Phase 0 uses empty dict).
    sample: DataDict = {"x": pd.DataFrame()}
    assert isinstance(sample, dict)
    assert isinstance(sample["x"], pd.DataFrame)


def test_conftest_data_dict_fixture(
    data_dict: dict[str, pd.DataFrame],
    expected_schemas: dict[str, list[str]],
) -> None:
    """``data_dict`` fixture returns 11 DataFrames with columns per schema.

    Validates the conftest plumbing end-to-end: ``src.data_layer.load_all``
    is reachable, returns a dict, and each table has the expected columns.
    """
    assert isinstance(data_dict, dict)
    for table_name, expected_columns in expected_schemas.items():
        assert table_name in data_dict, f"Missing table: {table_name}"
        df = data_dict[table_name]
        assert isinstance(df, pd.DataFrame), f"{table_name} is not a DataFrame"
        for col in expected_columns:
            assert col in df.columns, f"Column '{col}' missing in {table_name}"


def test_conftest_backend_fixture(backend: str) -> None:
    """``backend`` fixture returns ``'csv'`` (default in dev) or ``'postgres'``."""
    assert backend in ("csv", "postgres"), f"Unexpected backend: {backend!r}"


def test_conftest_tmp_csv_dir(tmp_csv_dir: Path) -> None:
    """``tmp_csv_dir`` fixture provides an isolated, writable directory."""
    assert tmp_csv_dir.exists()
    assert tmp_csv_dir.is_dir()
    probe = tmp_csv_dir / "probe.txt"
    probe.write_text("ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok"
