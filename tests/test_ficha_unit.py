"""Unit tests for ``src.components.ficha`` helpers.

Mirrors the add-patient unit test suite: covers session-state seeding,
ID generation, the merge contract, ``patient_has_ficha``, and the
``_handle_ficha_submit`` handler. Uses ``FakeSessionState`` from
``conftest.py`` so no Streamlit runtime is required.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.components import ficha as fc
from src.components.ficha import (
    _ensure_state,
    _next_goal_id,
    _next_item_id,
    _next_plan_id,
    _next_weight_id,
    merge_extra_fichas,
    patient_has_ficha,
    reset_extra_fichas,
)


# ---------------------------------------------------------------------------
# Session-state init & reset
# ---------------------------------------------------------------------------


def test_ensure_state_seeds_default_keys(fake_session_state):
    _ensure_state()
    for key in (
        "extra_treatment_plans",
        "extra_treatment_plan_items",
        "extra_patient_goals",
        "extra_weight_entries",
    ):
        assert fake_session_state[key] == []


def test_reset_clears_all_ficha_state(fake_session_state):
    fake_session_state["extra_treatment_plans"] = [{"plan_id": "plan_new_001"}]
    fake_session_state["extra_patient_goals"] = [{"goal_id": "goal_new_001"}]
    fake_session_state["extra_treatment_plan_items"] = [{"plan_item_id": "item_new_001"}]
    fake_session_state["extra_weight_entries"] = [{"weight_id": "w_new_001"}]

    reset_extra_fichas()

    assert fake_session_state["extra_treatment_plans"] == []
    assert fake_session_state["extra_patient_goals"] == []
    assert fake_session_state["extra_treatment_plan_items"] == []
    assert fake_session_state["extra_weight_entries"] == []


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


def test_next_plan_id_starts_at_001(base_data):
    assert _next_plan_id(base_data) == "plan_new_001"


def test_next_goal_id_starts_at_001(base_data):
    assert _next_goal_id(base_data) == "goal_new_001"


def test_next_item_id_starts_at_001(base_data):
    assert _next_item_id(base_data) == "item_new_001"


def test_next_weight_id_starts_at_001(base_data):
    assert _next_weight_id(base_data) == "w_new_001"


def test_next_plan_id_increments_with_session_extras(fake_session_state, base_data):
    fake_session_state["extra_treatment_plans"] = [
        {"plan_id": "plan_new_001", "patient_id": "pat_001", "budget_code": "x",
         "issue_date": pd.Timestamp.today().normalize(),
         "start_date": pd.Timestamp.today().normalize(),
         "end_date": pd.Timestamp.today().normalize(),
         "status": "Ativo", "main_goal": "g", "is_renewal": False, "notes": ""}
    ]
    assert _next_plan_id(base_data) == "plan_new_002"


def test_next_item_id_avoids_existing_fixture_ids(base_data):
    # base fixture has item_001..item_N; ensure we don't collide
    new_id = _next_item_id(base_data)
    assert not base_data["treatment_plan_items"]["plan_item_id"].astype(str).eq(new_id).any()


# ---------------------------------------------------------------------------
# patient_has_ficha
# ---------------------------------------------------------------------------


def test_patient_has_ficha_true_for_existing_plan(base_data):
    # pat_001 has a plan in the fixture
    assert patient_has_ficha("pat_001", base_data) is True


def test_patient_has_ficha_false_for_missing_patient(base_data):
    assert patient_has_ficha("pat_does_not_exist", base_data) is False


def test_patient_has_ficha_false_when_no_plan_in_base_data(base_data):
    """pat_001 has a plan, but if we filter it out, the helper says False."""
    pruned = dict(base_data)
    pruned["treatment_plans"] = base_data["treatment_plans"].iloc[0:0]
    assert patient_has_ficha("pat_001", pruned) is False


def test_patient_has_ficha_handles_empty_data():
    assert patient_has_ficha("pat_001", {}) is False
    assert patient_has_ficha("pat_001", None) is False


def test_patient_has_ficha_uses_session_extras(fake_session_state, base_data):
    fake_session_state["extra_treatment_plans"] = [
        {"plan_id": "plan_new_001", "patient_id": "pat_new_999",
         "budget_code": "x", "issue_date": pd.Timestamp.today().normalize(),
         "start_date": pd.Timestamp.today().normalize(),
         "end_date": pd.Timestamp.today().normalize(),
         "status": "Ativo", "main_goal": "g", "is_renewal": False, "notes": ""}
    ]
    merged = merge_extra_fichas(base_data)
    assert patient_has_ficha("pat_new_999", merged) is True


# ---------------------------------------------------------------------------
# merge_extra_fichas
# ---------------------------------------------------------------------------


def test_merge_fichas_returns_same_dict_when_no_extras(fake_session_state, base_data):
    out = merge_extra_fichas(base_data)
    assert out is base_data


def test_merge_fichas_appends_plan_goal_item_weight(fake_session_state, base_data):
    fake_session_state["extra_treatment_plans"] = [
        {"plan_id": "plan_new_001", "patient_id": "pat_new_999", "budget_code": "orc_x",
         "issue_date": pd.Timestamp.today().normalize(),
         "start_date": pd.Timestamp.today().normalize(),
         "end_date": pd.Timestamp.today().normalize(),
         "status": "Ativo", "main_goal": "Emagrecimento", "is_renewal": False, "notes": "ok"}
    ]
    fake_session_state["extra_patient_goals"] = [
        {"goal_id": "goal_new_001", "patient_id": "pat_new_999", "plan_id": "plan_new_001",
         "goal_type": "Emagrecimento", "initial_weight": 80.0, "target_weight": 70.0,
         "target_date": pd.Timestamp.today().normalize(), "goal_notes": "ok"}
    ]
    fake_session_state["extra_treatment_plan_items"] = [
        {"plan_item_id": "item_new_001", "plan_id": "plan_new_001", "patient_id": "pat_new_999",
         "budget_code": "orc_x", "raw_name": "Consulta", "category": "Avaliação",
         "sessions_expected": 1, "frequency_text": "1 sessão - mensal", "frequency_type": "Mensal",
         "source": "Dados manuais", "needs_manual_review": False}
    ]
    fake_session_state["extra_weight_entries"] = [
        {"weight_id": "w_new_001", "patient_id": "pat_new_999", "plan_id": "plan_new_001",
         "measurement_date": pd.Timestamp.today().normalize(), "weight": 79.5,
         "source": "Dados manuais", "notes": "ok"}
    ]
    out = merge_extra_fichas(base_data)
    assert out is not base_data
    assert len(out["treatment_plans"]) == len(base_data["treatment_plans"]) + 1
    assert len(out["patient_goals"]) == len(base_data["patient_goals"]) + 1
    assert len(out["treatment_plan_items"]) == len(base_data["treatment_plan_items"]) + 1
    assert len(out["weight_entries"]) == len(base_data["weight_entries"]) + 1
    # The new plan row should preserve the booleans/dates types
    new_plan = out["treatment_plans"].iloc[-1].to_dict()
    assert new_plan["is_renewal"] is False or new_plan["is_renewal"] is False
    assert isinstance(new_plan["status"], str)


# ---------------------------------------------------------------------------
# _handle_ficha_submit
# ---------------------------------------------------------------------------


def test_handle_ficha_submit_writes_plan_and_goal(fake_session_state, base_data):
    """End-to-end: filling the form values and calling the submit handler
    should create plan/goal rows and navigate to the Ficha page."""
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_999", "name": "Maria", "normalized_name": "maria",
         "medical_record": None, "phone": None, "age": 30,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    fake_session_state["cadastro_ficha_age"] = 30
    fake_session_state["cadastro_ficha_objetivo"] = "Emagrecimento"
    fake_session_state["cadastro_ficha_peso_inicial"] = 80.0
    fake_session_state["cadastro_ficha_peso_atual"] = 79.5
    fake_session_state["cadastro_ficha_peso_meta"] = 70.0
    fake_session_state["cadastro_ficha_status"] = "Ativo"
    fake_session_state["cadastro_ficha_orcamento"] = "orc_test_001"
    fake_session_state["cadastro_ficha_renovacao"] = False
    fake_session_state["cadastro_ficha_resumo"] = "Plano de teste."
    fake_session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    fake_session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()

    fc._handle_submit("pat_new_999", base_data)

    plans = fake_session_state["extra_treatment_plans"]
    goals = fake_session_state["extra_patient_goals"]
    assert len(plans) == 1
    assert len(goals) == 1
    assert plans[0]["patient_id"] == "pat_new_999"
    assert goals[0]["plan_id"] == plans[0]["plan_id"]
    # Navigation side effect
    assert fake_session_state["page"] == "Ficha do Paciente"
    assert fake_session_state["selected_patient_id"] == "pat_new_999"


def test_handle_ficha_submit_creates_weight_entry_when_peso_atual_positive(
    fake_session_state, base_data
):
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_999", "name": "Maria", "normalized_name": "maria",
         "medical_record": None, "phone": None, "age": 30,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    fake_session_state["cadastro_ficha_age"] = 30
    fake_session_state["cadastro_ficha_objetivo"] = ""
    fake_session_state["cadastro_ficha_peso_inicial"] = 0.0
    fake_session_state["cadastro_ficha_peso_atual"] = 82.5
    fake_session_state["cadastro_ficha_peso_meta"] = 0.0
    fake_session_state["cadastro_ficha_status"] = "Aguardando início"
    fake_session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    fake_session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=30)
    ).date()

    fc._handle_submit("pat_new_999", base_data)

    weights = fake_session_state["extra_weight_entries"]
    assert len(weights) == 1
    assert weights[0]["weight"] == 82.5
    assert weights[0]["patient_id"] == "pat_new_999"


def test_handle_ficha_submit_skips_weight_entry_when_peso_atual_zero(
    fake_session_state, base_data
):
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_999", "name": "Maria", "normalized_name": "maria",
         "medical_record": None, "phone": None, "age": 30,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    fake_session_state["cadastro_ficha_age"] = 30
    fake_session_state["cadastro_ficha_objetivo"] = ""
    fake_session_state["cadastro_ficha_peso_inicial"] = 0.0
    fake_session_state["cadastro_ficha_peso_atual"] = 0.0  # zero → no weight entry
    fake_session_state["cadastro_ficha_peso_meta"] = 0.0
    fake_session_state["cadastro_ficha_status"] = "Aguardando início"
    fake_session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    fake_session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=30)
    ).date()

    fc._handle_submit("pat_new_999", base_data)

    assert fake_session_state["extra_weight_entries"] == []


def test_handle_ficha_submit_skips_items_with_empty_name(fake_session_state, base_data):
    """Items whose name is empty must be filtered out (the data editor
    starts with 3 empty rows by default)."""
    fake_session_state["extra_patients"] = [
        {"patient_id": "pat_new_999", "name": "Maria", "normalized_name": "maria",
         "medical_record": None, "phone": None, "age": 30,
         "created_at": pd.Timestamp.today().normalize()}
    ]
    fake_session_state["cadastro_ficha_age"] = 30
    fake_session_state["cadastro_ficha_objetivo"] = "Emagrecimento"
    fake_session_state["cadastro_ficha_peso_inicial"] = 0.0
    fake_session_state["cadastro_ficha_peso_atual"] = 0.0
    fake_session_state["cadastro_ficha_peso_meta"] = 0.0
    fake_session_state["cadastro_ficha_status"] = "Ativo"
    fake_session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    fake_session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=30)
    ).date()
    # Simulate the user filling two of the three default rows
    fake_session_state["cadastro_ficha_items"] = pd.DataFrame(
        [
            {"nome": "Injetáveis", "categoria": "EV", "sessoes": 8, "frequencia": "Semanal"},
            {"nome": "", "categoria": "", "sessoes": 0, "frequencia": "Quinzenal"},
            {"nome": "Manipulado", "categoria": "Med", "sessoes": 1, "frequencia": "Diário"},
        ]
    )

    fc._handle_submit("pat_new_999", base_data)

    items = fake_session_state["extra_treatment_plan_items"]
    assert len(items) == 2
    assert items[0]["raw_name"] == "Injetáveis"
    assert items[0]["frequency_type"] == "Semanal"
    assert items[0]["frequency_text"] == "8 sessões - semanal"
    assert items[1]["raw_name"] == "Manipulado"
