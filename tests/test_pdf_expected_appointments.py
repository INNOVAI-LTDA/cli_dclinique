"""Tests for the ``expected_appointments`` projection (MVP Jornada Clinica, Fase 2.5).

The PDF import wizard now materializes a "plano de frequencia esperada"
into the ``expected_appointments`` table -- one row per session expected
per item. The ``(patient, plan_item, expected_date)`` triple is what the
Fase 3 XLSX wizard uses to reconcile real appointments against the
expected plan (rolante Q9: cada sessao real anda a janela para frente).

These tests pin the projection in place so the schema, arithmetic and
status sentinels can't drift without breaking a test.

Fixtures:
- :func:`tests.conftest.csv_dir` -- isolated CSV dir under ``tmp_path``
  for end-to-end tests that touch the data layer.
- All other tests use the pure function ``_build_expected_appointment_rows``
  directly (no fixture needed).
"""
from __future__ import annotations

import pandas as pd

from src.pdf_importer.persist import (
    _build_expected_appointment_rows,
    _write_expected_appointments,
)


# ---------------------------------------------------------------------------
# Pure-function: _build_expected_appointment_rows
# ---------------------------------------------------------------------------


def test_empty_items_returns_zero_rows() -> None:
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[],
        issue_date="2026-07-01",
    )
    assert rows == []


def test_item_without_sessions_is_skipped() -> None:
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_a", "sessions_expected": 0, "periodicity_days": 7},
        ],
        issue_date="2026-07-01",
    )
    assert rows == []


def test_item_with_negative_sessions_is_skipped() -> None:
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_a", "sessions_expected": -3, "periodicity_days": 7},
        ],
        issue_date="2026-07-01",
    )
    assert rows == []


def test_dose_unica_creates_single_row_at_issue_date() -> None:
    """``periodicity_days=None`` (``dose unica`` / sem frequency_type)
    gera 1 row com ``expected_date == issue_date`` (a sessao
    esperada "unica" -- sentinela, licao Caminho B Fase 6)."""
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_b", "sessions_expected": 5, "periodicity_days": None},
        ],
        issue_date="2026-07-01",
    )
    assert len(rows) == 1
    assert rows[0]["session_index"] == 1
    assert str(rows[0]["expected_date"].date()) == "2026-07-01"
    assert rows[0]["plan_item_id"] == "item_b"


def test_three_sessions_weekly_create_three_rows_with_arithmetic() -> None:
    """3 sessoes com periodicidade 7 -> datas em offsets 0/7/14 dias."""
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_c", "sessions_expected": 3, "periodicity_days": 7},
        ],
        issue_date="2026-07-01",
    )
    assert len(rows) == 3
    assert [str(r["expected_date"].date()) for r in rows] == [
        "2026-07-01",
        "2026-07-08",
        "2026-07-15",
    ]
    assert [r["session_index"] for r in rows] == [1, 2, 3]


def test_two_items_total_rows() -> None:
    """2 items (2 sessoes + 3 sessoes) -> 5 rows com ``plan_item_id`` correto."""
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_d1", "sessions_expected": 2, "periodicity_days": 7},
            {"plan_item_id": "item_d2", "sessions_expected": 3, "periodicity_days": 14},
        ],
        issue_date="2026-07-01",
    )
    assert len(rows) == 5
    # Items do item_d1 primeiro (offsets 0, 7) -- sessoes 1, 2.
    assert [r["plan_item_id"] for r in rows[:2]] == ["item_d1", "item_d1"]
    # Items do item_d2 depois (offsets 0, 14, 28) -- sessoes 1, 2, 3.
    assert [r["plan_item_id"] for r in rows[2:]] == ["item_d2", "item_d2", "item_d2"]
    # Datas quinzenais do item_d2 partem do issue_date.
    assert str(rows[2]["expected_date"].date()) == "2026-07-01"
    assert str(rows[3]["expected_date"].date()) == "2026-07-15"
    assert str(rows[4]["expected_date"].date()) == "2026-07-29"


def test_status_source_initial_sentinels() -> None:
    """Todas as rows tem ``status='planned'`` e ``source='pdf_wizard'``."""
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_e", "sessions_expected": 2, "periodicity_days": 7},
        ],
        issue_date="2026-07-01",
    )
    assert all(r["status"] == "planned" for r in rows)
    assert all(r["source"] == "pdf_wizard" for r in rows)
    # ``actual_date`` / ``last_actual_date`` ficam vazios no insert;
    # o XLSX wizard (Fase 3) preenche quando casa em
    # ``(patient, plan_item, data_inicio_plano)``.
    for r in rows:
        assert pd.isna(r["actual_date"])
        assert pd.isna(r["last_actual_date"])


def test_missing_issue_date_falls_back_to_today() -> None:
    """``issue_date=None`` -> usa ``pd.Timestamp.today()`` como offset 0."""
    rows = _build_expected_appointment_rows(
        plan_id="plan_x",
        patient_id="pat_x",
        items_with_ids=[
            {"plan_item_id": "item_f", "sessions_expected": 1, "periodicity_days": 7},
        ],
        issue_date=None,
    )
    assert len(rows) == 1
    # Off-by-one protection: row gerada com timestamp de hoje (nao
    # deveria dar NaT nem 1970).
    assert pd.notna(rows[0]["expected_date"])
    assert rows[0]["expected_date"].year >= 2026


# ---------------------------------------------------------------------------
# End-to-end (data layer): _write_expected_appointments + csv_dir
# ---------------------------------------------------------------------------


def test_write_expected_appointments_persists_to_csv(csv_dir) -> None:
    """_write_expected_appointments grava no CSV header-only state.

    Usa a fixture :func:`tests.conftest.csv_dir` para isolar o state em
    ``tmp_path/csv`` (data layer redirecionado). Verifica que 3 rows
    sao gravadas com IDs unicos e datas corretas.
    """
    from src.data_layer import delete_rows, load_table

    items_with_ids = [
        {"plan_item_id": "item_e2e1", "sessions_expected": 2, "periodicity_days": 7},
        {"plan_item_id": "item_e2e2", "sessions_expected": 1, "periodicity_days": None},
    ]
    n = _write_expected_appointments(
        plan_id="plan_e2e",
        patient_id="pat_e2e",
        items_with_ids=items_with_ids,
        issue_date="2026-07-01",
        clear_existing=True,
        logger=None,
    )
    assert n == 3  # 2 sessoes + 1 dose unica

    ea = load_table("expected_appointments")
    assert len(ea) == 3

    # IDs unicos (PK mintada por append, nao in-loop)
    ids = ea["expected_appointment_id"].tolist()
    assert len(set(ids)) == 3, f"IDs duplicados: {ids}"
    assert all(i.startswith("ea_new_") for i in ids)

    # Datas: item_e2e1 sessoes 1 e 2 -> 2026-07-01 e 2026-07-08
    rows_e1 = ea[ea["plan_item_id"] == "item_e2e1"].sort_values("session_index")
    assert str(rows_e1.iloc[0]["expected_date"].date()) == "2026-07-01"
    assert str(rows_e1.iloc[1]["expected_date"].date()) == "2026-07-08"

    # item_e2e2 dose unica -> 2026-07-01
    rows_e2 = ea[ea["plan_item_id"] == "item_e2e2"]
    assert len(rows_e2) == 1
    assert str(rows_e2.iloc[0]["expected_date"].date()) == "2026-07-01"

    # Cleanup (csv_dir e' tmp, mas explicito para isolar o teste).
    delete_rows("expected_appointments", "plan_id", "plan_e2e")
    assert len(load_table("expected_appointments")) == 0


def test_write_expected_appointments_clears_existing(csv_dir) -> None:
    """``clear_existing=True`` apaga rows do mesmo ``plan_id`` antes."""
    from src.data_layer import delete_rows, load_table

    items_with_ids = [
        {"plan_item_id": "item_clr", "sessions_expected": 2, "periodicity_days": 7},
    ]

    # 1a escrita: 2 rows
    _write_expected_appointments(
        plan_id="plan_clr",
        patient_id="pat_clr",
        items_with_ids=items_with_ids,
        issue_date="2026-07-01",
        clear_existing=True,
        logger=None,
    )
    ea_first = load_table("expected_appointments")
    assert len(ea_first[ea_first["plan_id"] == "plan_clr"]) == 2

    # 2a escrita com mais 1 sessao: 3 rows (nao 5)
    items_with_ids[0]["sessions_expected"] = 3
    _write_expected_appointments(
        plan_id="plan_clr",
        patient_id="pat_clr",
        items_with_ids=items_with_ids,
        issue_date="2026-07-01",
        clear_existing=True,
        logger=None,
    )
    ea_second = load_table("expected_appointments")
    rows_clr = ea_second[ea_second["plan_id"] == "plan_clr"]
    assert len(rows_clr) == 3, f"clear_existing falhou: {len(rows_clr)} rows (esperava 3)"

    delete_rows("expected_appointments", "plan_id", "plan_clr")


def test_write_expected_appointments_no_clear_appends(csv_dir) -> None:
    """``clear_existing=False`` NAO apaga -- ideal para append incremental."""
    from src.data_layer import delete_rows, load_table

    items_with_ids = [
        {"plan_item_id": "item_nc", "sessions_expected": 1, "periodicity_days": 7},
    ]

    _write_expected_appointments(
        plan_id="plan_nc",
        patient_id="pat_nc",
        items_with_ids=items_with_ids,
        issue_date="2026-07-01",
        clear_existing=False,
        logger=None,
    )
    _write_expected_appointments(
        plan_id="plan_nc",
        patient_id="pat_nc",
        items_with_ids=items_with_ids,
        issue_date="2026-07-01",
        clear_existing=False,
        logger=None,
    )
    ea = load_table("expected_appointments")
    rows_nc = ea[ea["plan_id"] == "plan_nc"]
    assert len(rows_nc) == 2, "sem clear, deveria ter acumulado 2 rows"

    delete_rows("expected_appointments", "plan_id", "plan_nc")