"""Unit tests for the wizard's read-model projection.

The PDF import wizard writes to ``patients`` / ``treatment_plans`` /
``treatment_plan_items`` (the source-of-truth tables), but the ficha
page reads from a different set:

* ``patient_goals`` — drives the ficha's info row ("Objetivo", "Peso
  meta") and the summary / observações card.
* ``execution_summary`` — drives the ficha's "Plano de tratamento"
  table (one row per item, with sessions_expected /
  sessions_completed / sessions_remaining and the status pill).

Before June 2026 the wizard did NOT project the plan into these two
satellite tables, so imported patients rendered as empty cards in the
ficha even when the import succeeded. These tests pin the projection
in place so the regression can't come back.

The tests run in CSV mode (``csv_dir`` fixture) so they don't require
a live Neon DSN — the same projection logic is exercised end-to-end
against the CSV backend, which is identical to the postgres backend's
public API.
"""
from __future__ import annotations

import pandas as pd
import pytest


def _candidate(
    *,
    name: str = "Claudia Helena Teste",
    cpf: str | None = "987.654.321-00",
    rg: str | None = "1234567",
    address: str | None = "SQN 102, Brasília/DF",
    main_goal: str = "Emagrecimento",
    notes: str = "Plano pós-parto, foco em drenagem.",
    end_date: str | None = "2026-09-01",
    item_count: int = 2,
):
    """Build a validate-ready candidate dict for the tests."""
    items = []
    for i in range(item_count):
        items.append(
            {
                "raw_name": f"Procedimento {i + 1}",
                "category": "Drenagem" if i == 0 else "Massagem",
                "sessions_expected": 10 + i,
                "frequency_text": "1x/semana",
                "frequency_type": "Semanal",
                "needs_manual_review": False,
            }
        )
    return {
        "filename": "fixture.pdf",
        "patient": {
            "name": name,
            "normalized_name": name.lower(),
            "medical_record": "8887777",
            "phone": "(61) 99999-1234",
            "age": 42,
            "cpf": cpf,
            "rg": rg,
            "address": address,
            "created_at": "2026-06-21",
        },
        "plan": {
            "budget_code": "",
            "issue_date": "2026-06-01",
            "start_date": "2026-06-01",
            "end_date": end_date,
            "status": "Ativo",
            "main_goal": main_goal,
            "is_renewal": False,
            "notes": notes,
        },
        "items": items,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Insert path
# ---------------------------------------------------------------------------


def test_insert_writes_goal_row(csv_dir, monkeypatch):
    """After persist_rows in the insert path, patient_goals has a row."""
    from src.pdf_importer import validate_rows, persist_rows

    # streamlit.cache_data.clear is a no-op in csv mode but the
    # wizard calls it unconditionally; the fake_streamlit fixture
    # below is enough for that.
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    candidate = _candidate()
    validate_rows(candidate)
    assert candidate["status"] != "Erro"

    result = persist_rows(candidate)
    pid = result["patient_id"]
    plan_id = result["plan_id"]

    from src.data_layer import load_table

    goals = load_table("patient_goals")
    rows = goals[goals["patient_id"] == pid]
    assert len(rows) == 1, f"expected 1 patient_goals row for {pid}, got {len(rows)}"
    row = rows.iloc[0]
    assert row["plan_id"] == plan_id
    assert row["goal_type"] == "Emagrecimento"
    assert row["goal_notes"] == "Plano pós-parto, foco em drenagem."
    # PDF doesn't carry weight data → both weight fields are NULL.
    assert pd.isna(row["initial_weight"])
    assert pd.isna(row["target_weight"])


def test_insert_writes_one_execution_row_per_item(csv_dir, monkeypatch):
    """After persist_rows in the insert path, execution_summary has
    one row per plan item (not zero)."""
    from src.pdf_importer import validate_rows, persist_rows
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    candidate = _candidate(item_count=3)
    validate_rows(candidate)
    result = persist_rows(candidate)
    pid = result["patient_id"]
    plan_id = result["plan_id"]

    from src.data_layer import load_table

    execs = load_table("execution_summary")
    rows = execs[execs["patient_id"] == pid]
    assert len(rows) == 3, f"expected 3 execution_summary rows for {pid}, got {len(rows)}"
    assert (rows["plan_id"] == plan_id).all()
    # The wizard can't observe sessions completed (no appointments yet),
    # so every row starts at zero with status "Aguardando início".
    assert (rows["sessions_completed"] == 0).all()
    assert (rows["status"] == "Aguardando início").all()
    # Remaining equals expected for every row.
    assert (rows["sessions_remaining"] == rows["sessions_expected"]).all()
    # Procedure names land in procedure_raw.
    assert sorted(rows["procedure_raw"].tolist()) == [
        "Procedimento 1",
        "Procedimento 2",
        "Procedimento 3",
    ]
    # frequency_type is projected from the item's dropdown value
    # (June 2026 — added so the ficha can build the
    # "Frequência de Aplicação" column from the satellite view).
    # The _candidate helper uses "Semanal" capitalized; the
    # execution row preserves it verbatim (no implicit
    # lowercasing).
    assert (rows["frequency_type"] == "Semanal").all(), (
        f"frequency_type not projected; got {rows['frequency_type'].tolist()}"
    )


def test_insert_persists_cpf_rg_address(csv_dir, monkeypatch):
    """The wizard extracts CPF/RG/address from the PDF; they must land
    in the patients row (otherwise the ficha can't show them — the
    original bug)."""
    from src.pdf_importer import validate_rows, persist_rows
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    candidate = _candidate()
    validate_rows(candidate)
    result = persist_rows(candidate)
    pid = result["patient_id"]

    from src.data_layer import load_table

    patients = load_table("patients")
    row = patients[patients["patient_id"] == pid].iloc[0]
    # Use ``str(...)`` so the assertion is robust to CSV-mode dtype
    # inference: pandas reads a column of numeric-looking strings
    # (RG) as int64 by default. Postgres keeps it as TEXT, so the
    # real-world path doesn't see this round-trip. The test only
    # cares that the value made it into the row.
    assert str(row["cpf"]) == "987.654.321-00"
    assert str(row["rg"]) == "1234567"
    assert str(row["address"]) == "SQN 102, Brasília/DF"


def test_insert_with_empty_end_date_still_writes_goal(csv_dir, monkeypatch):
    """A PDF without an explicit end date (``end_date=None``) must
    not crash the projection; the goal row should still be written
    with ``target_date`` NULL. The psycopg binding for NULL goes
    through ``_sanitize_param`` so this also guards that path."""
    from src.pdf_importer import validate_rows, persist_rows
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    candidate = _candidate(end_date=None)
    validate_rows(candidate)
    result = persist_rows(candidate)
    pid = result["patient_id"]

    from src.data_layer import load_table

    goals = load_table("patient_goals")
    rows = goals[goals["patient_id"] == pid]
    assert len(rows) == 1
    assert pd.isna(rows.iloc[0]["target_date"])


# ---------------------------------------------------------------------------
# Replace path
# ---------------------------------------------------------------------------


def test_replace_plan_clears_old_execution_rows(csv_dir, monkeypatch):
    """When the wizard replaces a plan (``(patient_id, issue_date)``
    collides), the OLD execution_summary rows for the existing plan
    must be cleared before the new ones are inserted — otherwise the
    ficha's plan table would show the previous item list alongside
    the new one.

    The data-layer ``replace_plan`` clears ``treatment_plan_items``
    and ``patient_goals`` but NOT the satellite execution view; this
    test pins the wizard's responsibility to do that clear."""
    from src.pdf_importer import validate_rows, persist_rows
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    # 1. First import: 2 items
    candidate_v1 = _candidate(item_count=2)
    validate_rows(candidate_v1)
    persist_rows(candidate_v1)
    pid = candidate_v1["patient_id"] if "patient_id" in candidate_v1 else None

    # Re-load to find the actual id (the helper doesn't put it back
    # on the candidate dict)
    from src.data_layer import load_table

    patients = load_table("patients")
    target = patients[patients["name"] == "Claudia Helena Teste"].iloc[0]
    pid = target["patient_id"]

    plans = load_table("treatment_plans")
    plan_id_v1 = plans[plans["patient_id"] == pid].iloc[0]["plan_id"]

    execs_v1 = load_table("execution_summary")
    assert len(execs_v1[execs_v1["plan_id"] == plan_id_v1]) == 2

    # 2. Re-import with a different item list (3 items) — the natural
    # key (patient_id, issue_date) collides with the first import, so
    # the wizard takes the replace_plan path.
    candidate_v2 = _candidate(item_count=3)
    candidate_v2["patient"]["cpf"] = "987.654.321-00"  # same CPF → reuse patient
    # Mark the candidate as a replace (validate_rows will compute this
    # from the dup_patient_id/dup_plan_id keys after we re-validate
    # with the same CPF).
    validate_rows(candidate_v2)
    # Tell validate the existing CPF matches (so dedup fires).
    # validate_rows only sets dup_patient_id when the CPF matches a
    # row already in patients; since we just inserted, this should be
    # true. We can verify by inspecting the candidate.
    assert candidate_v2.get("dup_patient_id") == pid, (
        f"expected dup_patient_id={pid}, got {candidate_v2.get('dup_patient_id')!r}"
    )

    dedup_action = {
        "replace_patient": False,  # user accepted reuse, not replace
        "replace_plan": True,      # same issue_date → replace plan
    }
    persist_rows(candidate_v2, dedup_action=dedup_action)

    # 3. After replace: only the NEW items show up.
    execs_v2 = load_table("execution_summary")
    rows_after = execs_v2[execs_v2["plan_id"] == plan_id_v1]
    assert len(rows_after) == 3, (
        f"expected 3 execution rows after replace, got {len(rows_after)}"
    )
    # The procedure names are from the new import (Procedimento 1, 2, 3)
    assert sorted(rows_after["procedure_raw"].tolist()) == [
        "Procedimento 1",
        "Procedimento 2",
        "Procedimento 3",
    ]

    # The patient_goals row was also recreated (data-layer
    # ``replace_plan`` clears it; the wizard writes the new one).
    goals_v2 = load_table("patient_goals")
    goals_rows = goals_v2[goals_v2["plan_id"] == plan_id_v1]
    assert len(goals_rows) == 1


# ---------------------------------------------------------------------------
# id minting
# ---------------------------------------------------------------------------


def test_execution_ids_are_unique(csv_dir, monkeypatch):
    """The wizard mints one execution_id per item; they must all be
    distinct (regression guard for the ``next_id_with_prefix``
    hardcoded-scan bug that returned the same id for every call)."""
    from src.pdf_importer import validate_rows, persist_rows
    import streamlit as st
    monkeypatch.setattr(st, "cache_data", type("X", (), {"clear": staticmethod(lambda: None)})(), raising=False)
    monkeypatch.setattr(st, "session_state", {}, raising=False)

    candidate = _candidate(item_count=5)
    validate_rows(candidate)
    persist_rows(candidate)

    from src.data_layer import load_table

    execs = load_table("execution_summary")
    ids = execs["execution_id"].tolist()
    assert len(ids) == len(set(ids)), f"duplicate execution_ids: {ids}"
    # All ids match the exec_new_NNN pattern.
    import re

    pat = re.compile(r"^exec_new_\d{3}$")
    assert all(pat.match(i) for i in ids), f"unexpected id shape: {ids}"