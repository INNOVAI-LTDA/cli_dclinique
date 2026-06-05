"""Unit tests for ``src.components.add_patient`` helpers.

These tests run with ``st.session_state`` replaced by ``FakeSessionState``
(``conftest.py``) and the data layer pointed at a per-test tmp directory
(the ``csv_dir`` fixture), so they do not need a Streamlit runtime. They
cover id generation, the duplicate-name check, and the submit handler
in isolation.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.components import add_patient as ap
from src.components.add_patient import (
    _existing_normalized_names,
    _handle_submit,
)
from src.data_layer import load_table, next_id


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


def test_next_patient_id_starts_at_001_when_no_extras(csv_dir):
    # The seed CSVs have pat_001..pat_008 but no pat_new_* yet
    assert next_id("patients") == "pat_new_001"


def test_next_patient_id_increments_after_append(csv_dir):
    from src.data_layer import append_row

    append_row(
        "patients",
        {
            "patient_id": "pat_new_001",
            "name": "Maria",
            "normalized_name": "maria",
            "medical_record": None,
            "phone": None,
            "age": 30,
            "created_at": pd.Timestamp.today().normalize(),
        },
    )
    assert next_id("patients") == "pat_new_002"


def test_next_patient_id_is_deterministic(csv_dir):
    """Two calls without an intervening append yield the same id."""
    first = next_id("patients")
    second = next_id("patients")
    assert first == second
    assert first == "pat_new_001"


# ---------------------------------------------------------------------------
# Existing-name keys
# ---------------------------------------------------------------------------


def test_existing_normalized_names_includes_seed_patients(csv_dir):
    keys = _existing_normalized_names()
    assert "kelly cristina amorim" in keys
    assert "ana maria souza" in keys


def test_existing_normalized_names_reflects_appends(csv_dir):
    from src.data_layer import append_row

    append_row(
        "patients",
        {
            "patient_id": "pat_new_001",
            "name": "Carlos Novo",
            "normalized_name": "carlos novo",
            "medical_record": None,
            "phone": None,
            "age": None,
            "created_at": pd.Timestamp.today().normalize(),
        },
    )
    keys = _existing_normalized_names()
    assert "carlos novo" in keys


# ---------------------------------------------------------------------------
# _handle_submit
# ---------------------------------------------------------------------------


def test_handle_submit_rejects_empty_name(fake_session_state, csv_dir):
    fake_session_state["add_patient_name"] = ""
    fake_session_state["add_patient_age"] = 0
    result = _handle_submit()
    assert result is False
    # No new row in the CSV
    assert len(load_table("patients")) == 8  # seed only


def test_handle_submit_rejects_duplicate_name(fake_session_state, csv_dir):
    fake_session_state["add_patient_name"] = "Kelly Cristina Amorim"  # already in seed
    fake_session_state["add_patient_age"] = 30
    result = _handle_submit()
    assert result is False
    assert len(load_table("patients")) == 8


def test_handle_submit_appends_valid_patient(fake_session_state, csv_dir):
    fake_session_state["add_patient_name"] = "Maria Nova"
    fake_session_state["add_patient_record"] = "REC-1"
    fake_session_state["add_patient_phone"] = "(00) 90000-0000"
    fake_session_state["add_patient_age"] = 42

    result = _handle_submit()

    assert result is True
    df = load_table("patients")
    assert len(df) == 9  # 8 seed + 1 new
    new_row = df.iloc[-1]
    assert new_row["patient_id"] == "pat_new_001"
    assert new_row["name"] == "Maria Nova"
    assert new_row["normalized_name"] == "maria nova"
    assert new_row["medical_record"] == "REC-1"
    assert new_row["phone"] == "(00) 90000-0000"
    assert int(new_row["age"]) == 42
    # Side effects on session state
    assert fake_session_state["add_patient_open"] is False
    assert fake_session_state["patients_page"] == 1


def test_handle_submit_coerces_invalid_age_to_none(fake_session_state, csv_dir):
    fake_session_state["add_patient_name"] = "Sem Idade"
    fake_session_state["add_patient_age"] = -3  # should be coerced to None

    _handle_submit()

    new_row = load_table("patients").iloc[-1]
    # pandas uses pd.NA for nullable Int64 — both `is None` and `isna()` are valid
    assert pd.isna(new_row["age"])


def test_handle_submit_keeps_form_open_on_rejection(fake_session_state, csv_dir):
    """A rejected submit must NOT close the form — user must be able to fix the field."""
    fake_session_state["add_patient_name"] = ""  # empty → rejected
    fake_session_state["add_patient_open"] = True

    _handle_submit()

    assert fake_session_state["add_patient_open"] is True
    assert len(load_table("patients")) == 8


def test_handle_submit_uses_next_id_avoiding_existing(fake_session_state, csv_dir):
    from src.data_layer import append_row

    append_row(
        "patients",
        {
            "patient_id": "pat_new_001",
            "name": "Pre",
            "normalized_name": "pre",
            "medical_record": None,
            "phone": None,
            "age": None,
            "created_at": pd.Timestamp.today().normalize(),
        },
    )
    fake_session_state["add_patient_name"] = "Maria 2"
    fake_session_state["add_patient_age"] = 30

    _handle_submit()

    df = load_table("patients")
    assert len(df) == 10  # 8 + 1 pre-existing + 1 new
    assert df.iloc[-1]["patient_id"] == "pat_new_002"
