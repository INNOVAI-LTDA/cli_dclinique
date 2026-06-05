"""Unit tests for ``src.components.ficha`` helpers.

Mirrors the add-patient unit test suite: covers id generation, the
``patient_has_ficha`` helper, and the ``_handle_submit`` handler. Uses
``FakeSessionState`` from ``conftest.py`` so no Streamlit runtime is
required. Each test runs against a per-test copy of the seed CSVs (the
``csv_dir`` fixture), so appends never leak between tests or into the
developer's local checkout.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.components import ficha as fc
from src.components.ficha import (
    _handle_submit,
    patient_has_ficha,
)
from src.data_layer import load_table, next_id


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


def test_next_plan_id_starts_at_001(csv_dir):
    assert next_id("treatment_plans") == "plan_new_001"


def test_next_goal_id_starts_at_001(csv_dir):
    assert next_id("patient_goals") == "goal_new_001"


def test_next_item_id_starts_at_001(csv_dir):
    assert next_id("treatment_plan_items") == "item_new_001"


def test_next_weight_id_starts_at_001(csv_dir):
    assert next_id("weight_entries") == "w_new_001"


def test_next_item_id_avoids_existing_seed_ids(csv_dir):
    # seed has item_001..item_NN; ensure the helper skips them
    new_id = next_id("treatment_plan_items")
    df = load_table("treatment_plan_items")
    assert not df["plan_item_id"].astype(str).eq(new_id).any()


# ---------------------------------------------------------------------------
# patient_has_ficha
# ---------------------------------------------------------------------------


def test_patient_has_ficha_true_for_existing_plan(csv_dir):
    # pat_001 has a plan in the seed fixture
    assert patient_has_ficha("pat_001") is True


def test_patient_has_ficha_false_for_missing_patient(csv_dir):
    assert patient_has_ficha("pat_does_not_exist") is False


def test_patient_has_ficha_false_when_no_plan_in_seed(csv_dir):
    """pat_001 has a plan in the seed, but if we wipe the plan table, the helper says False."""
    from src.data_layer import csv_dir as data_csv_dir

    plans_path = data_csv_dir() / "treatment_plans.csv"
    plans_path.write_text("plan_id,patient_id,budget_code,issue_date,start_date,end_date,status,main_goal,is_renewal,notes\n", encoding="utf-8")
    assert patient_has_ficha("pat_001") is False


def test_patient_has_ficha_reflects_recent_appends(csv_dir):
    from src.data_layer import append_row

    append_row(
        "treatment_plans",
        {
            "plan_id": "plan_new_001",
            "patient_id": "pat_new_999",
            "budget_code": "orc_x",
            "issue_date": pd.Timestamp.today().normalize(),
            "start_date": pd.Timestamp.today().normalize(),
            "end_date": pd.Timestamp.today().normalize(),
            "status": "Ativo",
            "main_goal": "g",
            "is_renewal": False,
            "notes": "",
        },
    )
    assert patient_has_ficha("pat_new_999") is True


# ---------------------------------------------------------------------------
# _handle_submit
# ---------------------------------------------------------------------------


def _cadastro_form_state(
    fake_session_state,
    *,
    age: int = 30,
    objetivo: str = "Emagrecimento",
    peso_inicial: float = 80.0,
    peso_atual: float = 79.5,
    peso_meta: float = 70.0,
    status: str = "Ativo",
    orcamento: str = "orc_test_001",
    renovacao: bool = False,
    resumo: str = "Plano de teste.",
    items: pd.DataFrame | None = None,
):
    fake_session_state["cadastro_ficha_age"] = age
    fake_session_state["cadastro_ficha_objetivo"] = objetivo
    fake_session_state["cadastro_ficha_peso_inicial"] = peso_inicial
    fake_session_state["cadastro_ficha_peso_atual"] = peso_atual
    fake_session_state["cadastro_ficha_peso_meta"] = peso_meta
    fake_session_state["cadastro_ficha_status"] = status
    fake_session_state["cadastro_ficha_orcamento"] = orcamento
    fake_session_state["cadastro_ficha_renovacao"] = renovacao
    fake_session_state["cadastro_ficha_resumo"] = resumo
    fake_session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    fake_session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()
    if items is not None:
        fake_session_state["cadastro_ficha_items"] = items


def test_handle_ficha_submit_writes_plan_and_goal(fake_session_state, csv_dir):
    _cadastro_form_state(fake_session_state)

    _handle_submit("pat_001")

    plans = load_table("treatment_plans")
    goals = load_table("patient_goals")
    # 1 new plan, 1 new goal
    assert len(plans) == 9  # 8 seed + 1
    assert len(goals) == 9  # 8 seed + 1
    new_plan = plans.iloc[-1]
    new_goal = goals.iloc[-1]
    assert new_plan["patient_id"] == "pat_001"
    assert new_goal["plan_id"] == new_plan["plan_id"]
    # Navigation side effect
    assert fake_session_state["page"] == "Ficha do Paciente"
    assert fake_session_state["selected_patient_id"] == "pat_001"


def test_handle_ficha_submit_creates_weight_entry_when_peso_atual_positive(
    fake_session_state, csv_dir
):
    _cadastro_form_state(
        fake_session_state,
        objetivo="",
        peso_inicial=0.0,
        peso_atual=82.5,
        peso_meta=0.0,
        status="Aguardando início",
    )

    _handle_submit("pat_001")

    weights = load_table("weight_entries")
    assert len(weights) == 16  # 15 seed + 1
    new_weight = weights.iloc[-1]
    assert float(new_weight["weight"]) == 82.5
    assert new_weight["patient_id"] == "pat_001"


def test_handle_ficha_submit_skips_weight_entry_when_peso_atual_zero(
    fake_session_state, csv_dir
):
    _cadastro_form_state(
        fake_session_state,
        objetivo="",
        peso_inicial=0.0,
        peso_atual=0.0,  # zero → no weight entry
        peso_meta=0.0,
        status="Aguardando início",
    )

    _handle_submit("pat_001")

    weights = load_table("weight_entries")
    assert len(weights) == 15  # seed only


def test_handle_ficha_submit_skips_items_with_empty_name(fake_session_state, csv_dir):
    """Items whose name is empty must be filtered out (the data editor
    starts with 3 empty rows by default)."""
    _cadastro_form_state(
        fake_session_state,
        peso_inicial=0.0,
        peso_atual=0.0,
        peso_meta=0.0,
        status="Ativo",
        items=pd.DataFrame(
            [
                {"nome": "Injetáveis", "categoria": "EV", "sessoes": 8, "frequencia": "Semanal"},
                {"nome": "", "categoria": "", "sessoes": 0, "frequencia": "Quinzenal"},
                {"nome": "Manipulado", "categoria": "Med", "sessoes": 1, "frequencia": "Diário"},
            ]
        ),
    )

    _handle_submit("pat_001")

    items = load_table("treatment_plan_items")
    assert len(items) == 19  # 17 seed + 2
    assert items.iloc[-2]["raw_name"] == "Injetáveis"
    assert items.iloc[-2]["frequency_type"] == "Semanal"
    assert items.iloc[-2]["frequency_text"] == "8 sessões - semanal"
    assert items.iloc[-1]["raw_name"] == "Manipulado"


def test_handle_ficha_submit_updates_patient_age(fake_session_state, csv_dir):
    _cadastro_form_state(fake_session_state, age=55)

    _handle_submit("pat_001")

    patients = load_table("patients")
    row = patients[patients["patient_id"] == "pat_001"].iloc[0]
    assert int(row["age"]) == 55
