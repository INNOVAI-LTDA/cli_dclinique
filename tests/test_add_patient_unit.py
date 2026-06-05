"""Unit tests for ``src.components.add_patient`` helpers.

These tests run with ``st.session_state`` replaced by ``FakeSessionState``
(``conftest.py``), so they do not need a Streamlit runtime. They cover
the merge contract, ID generation, and the submit handler in isolation.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.components import add_patient as ap
from src.components.add_patient import (
    _ensure_state,
    _existing_name_keys,
    _next_patient_id,
    merge_extra_patients,
    reset_extra_patients,
)


# ---------------------------------------------------------------------------
# Session-state init & reset
# ---------------------------------------------------------------------------


def test_ensure_state_seeds_default_keys(fake_session_state):
    _ensure_state()
    assert "extra_patients" in fake_session_state
    assert "add_patient_open" in fake_session_state
    assert fake_session_state["add_patient_open"] is False
    assert fake_session_state["extra_patients"] == []


def test_ensure_state_is_idempotent(fake_session_state):
    _ensure_state()
    fake_session_state["extra_patients"].append({"patient_id": "pat_new_001"})
    fake_session_state["add_patient_open"] = True
    _ensure_state()  # second call must not clobber the existing state
    assert len(fake_session_state["extra_patients"]) == 1
    assert fake_session_state["add_patient_open"] is True


def test_reset_clears_session_state(fake_session_state):
    fake_session_state["extra_patients"] = [{"patient_id": "pat_new_001"}]
    fake_session_state["add_patient_open"] = True
    reset_extra_patients()
    assert fake_session_state["extra_patients"] == []
    assert fake_session_state["add_patient_open"] is False


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


def test_next_patient_id_starts_at_001_when_no_extras(base_data):
    assert _next_patient_id(base_data) == "pat_new_001"


def test_next_patient_id_increments_when_first_id_is_taken(base_data):
    used = base_data["patients"].copy()
    extras_row = pd.DataFrame(
        [{"patient_id": "pat_new_001", "name": "X", "normalized_name": "x",
          "medical_record": None, "phone": None, "age": None,
          "created_at": pd.Timestamp.today().normalize()}]
    )
    used = pd.concat([used, extras_row], ignore_index=True)
    new_data = dict(base_data)
    new_data["patients"] = used
    assert _next_patient_id(new_data) == "pat_new_002"


def test_next_patient_id_also_considers_session_extras(fake_session_state, base_data):
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_001", "name": "a", "normalized_name": "a",
         "medical_record": None, "phone": None, "age": None,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    assert _next_patient_id(base_data) == "pat_new_002"


def test_next_patient_id_avoids_session_extras(fake_session_state, base_data):
    """The returned id must never collide with anything in session state."""
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_005", "name": "a", "normalized_name": "a",
         "medical_record": None, "phone": None, "age": None,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    new_id = _next_patient_id(base_data)
    # Must not collide with what's already in the session
    assert new_id != "pat_new_005"
    # Must be a fresh, well-formed pat_new_NNN id
    assert new_id.startswith("pat_new_")
    # And the same call must be deterministic — two calls yield the same id
    assert _next_patient_id(base_data) == new_id


# ---------------------------------------------------------------------------
# Existing-name keys
# ---------------------------------------------------------------------------


def test_existing_name_keys_combines_base_and_session(fake_session_state, base_data):
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_001", "name": "Carlos Novo", "normalized_name": "carlos novo",
         "medical_record": None, "phone": None, "age": None,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    keys = _existing_name_keys(base_data)
    # base fixture already has normalised names like 'kelly cristina amorim'
    assert "kelly cristina amorim" in keys
    assert "carlos novo" in keys


def test_existing_name_keys_handles_missing_data(fake_session_state):
    assert _existing_name_keys(None) == set()


# ---------------------------------------------------------------------------
# merge_extra_patients
# ---------------------------------------------------------------------------


def test_merge_returns_same_dict_when_no_extras(fake_session_state, base_data):
    out = merge_extra_patients(base_data)
    assert out is base_data  # same instance — keeps @st.cache_data warm


def test_merge_returns_new_dict_with_appended_patients(fake_session_state, base_data):
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_001", "name": "Maria", "normalized_name": "maria",
         "medical_record": "M1", "phone": "(00) 0", "age": 30,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    out = merge_extra_patients(base_data)
    assert out is not base_data
    assert len(out["patients"]) == len(base_data["patients"]) + 1
    assert out["patients"].iloc[-1]["patient_id"] == "pat_new_001"
    assert out["patients"].iloc[-1]["name"] == "Maria"
    # other tables should be the same instances (no unnecessary copies)
    assert out["treatment_plans"] is base_data["treatment_plans"]


def test_merge_pads_missing_columns_with_nan(fake_session_state, base_data):
    """Extras that omit optional fields should not break the merge."""
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_001", "name": "Maria", "normalized_name": "maria",
         "medical_record": None, "phone": None, "age": None,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    out = merge_extra_patients(base_data)
    last = out["patients"].iloc[-1].to_dict()
    assert last["name"] == "Maria"
    assert pd.isna(last["age"]) or last["age"] is None


# ---------------------------------------------------------------------------
# _handle_submit
# ---------------------------------------------------------------------------


def test_handle_submit_rejects_empty_name(fake_session_state, base_data):
    _ensure_state()
    fake_session_state["add_patient_name"] = ""
    fake_session_state["add_patient_age"] = 0
    result = ap._handle_submit(base_data)
    assert result is False
    assert fake_session_state["extra_patients"] == []


def test_handle_submit_rejects_duplicate_name(fake_session_state, base_data):
    _ensure_state()
    fake_session_state["add_patient_name"] = "Kelly Cristina Amorim"  # already in fixture
    fake_session_state["add_patient_age"] = 30
    result = ap._handle_submit(base_data)
    assert result is False
    assert fake_session_state["extra_patients"] == []


def test_handle_submit_appends_valid_patient(fake_session_state, base_data):
    _ensure_state()
    fake_session_state["add_patient_name"] = "Maria Nova"
    fake_session_state["add_patient_record"] = "REC-1"
    fake_session_state["add_patient_phone"] = "(00) 90000-0000"
    fake_session_state["add_patient_age"] = 42

    result = ap._handle_submit(base_data)

    assert result is True
    extras = fake_session_state["extra_patients"]
    assert len(extras) == 1
    row = extras[0]
    assert row["patient_id"] == "pat_new_001"
    assert row["name"] == "Maria Nova"
    assert row["normalized_name"] == "maria nova"
    assert row["medical_record"] == "REC-1"
    assert row["phone"] == "(00) 90000-0000"
    assert row["age"] == 42
    # Side effects on session state
    assert fake_session_state["add_patient_open"] is False
    assert fake_session_state["patients_page"] == 1


def test_handle_submit_coerces_invalid_age_to_none(fake_session_state, base_data):
    _ensure_state()
    fake_session_state["add_patient_name"] = "Sem Idade"
    fake_session_state["add_patient_age"] = -3  # should be coerced to None

    ap._handle_submit(base_data)

    row = fake_session_state["extra_patients"][0]
    assert row["age"] is None


def test_handle_submit_keeps_form_open_on_rejection(fake_session_state, base_data):
    """A rejected submit must NOT close the form — user must be able to fix the field."""
    _ensure_state()
    fake_session_state["add_patient_name"] = ""  # empty → rejected
    fake_session_state["add_patient_open"] = True

    ap._handle_submit(base_data)

    assert fake_session_state["add_patient_open"] is True
    assert fake_session_state["extra_patients"] == []


def test_handle_submit_uses_next_id_avoiding_existing(fake_session_state, base_data):
    _ensure_state()
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_001", "name": "Pre", "normalized_name": "pre",
         "medical_record": None, "phone": None, "age": None,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    fake_session_state["add_patient_name"] = "Maria 2"
    fake_session_state["add_patient_age"] = 30

    ap._handle_submit(base_data)

    assert len(fake_session_state["extra_patients"]) == 2
    assert fake_session_state["extra_patients"][-1]["patient_id"] == "pat_new_002"
