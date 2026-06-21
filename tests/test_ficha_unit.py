"""Unit tests for ``src.components.ficha`` helpers.

Mirrors the add-patient unit test suite: covers id generation, the
``patient_has_ficha`` helper, and the ``_handle_submit`` handler. Uses
``FakeSessionState`` from ``conftest.py`` so no Streamlit runtime is
required. Each test runs against a per-test copy of the (header-only)
CSVs (the ``csv_dir`` fixture), so appends never leak between tests
or into the developer's local checkout.

Base zerada (T9): os CSVs vem sem dados. Tests que precisavam do
paciente ``pat_001`` do seed agora chamam ``_register_patient()`` no
setup para construir a pre-existencia.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.components import ficha as fc
from src.components.ficha import (
    _handle_submit,
    patient_has_ficha,
)
from src.data_layer import append_row, load_table, next_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_patient(name: str = "Paciente Teste", age: int = 30) -> str:
    """Registra paciente na base zerada e retorna o ``patient_id``.

    Substitui a dependencia do seed ``pat_001`` (removido em T9).
    Cada test que precisa de um paciente existente chama este
    helper no setup.
    """
    pid = next_id("patients")
    append_row(
        "patients",
        {
            "patient_id": pid,
            "name": name,
            "normalized_name": name.lower(),
            "medical_record": None,
            "phone": None,
            "age": age,
            "created_at": pd.Timestamp.today().normalize(),
        },
    )
    return pid


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
    """Base zerada: simular item pre-existente e verificar que
    ``next_id`` pula o numero ja' usado.

    Antes do T9, o test confiava que o seed tinha ``item_001..item_NN``
    e que ``next_id`` retornava ``item_new_001``. Agora a pre-existencia
    e' construida no proprio teste.
    """
    append_row(
        "treatment_plan_items",
        {
            "plan_item_id": "item_new_001",
            "plan_id": "plan_new_test",
            "raw_name": "Pre-existente",
            "category": "EV",
            "sessions": 1,
            "frequency_type": "Semanal",
            "frequency_text": "1 sessao - semanal",
            "created_at": pd.Timestamp.today().normalize(),
        },
    )
    assert next_id("treatment_plan_items") == "item_new_002"  # pula o 001


# ---------------------------------------------------------------------------
# patient_has_ficha
# ---------------------------------------------------------------------------


def test_patient_has_ficha_true_for_existing_plan(csv_dir):
    """Base zerada: registrar paciente + criar plan, depois verificar."""
    pid = _register_patient(name="Com Plan", age=30)
    plan_id = next_id("treatment_plans")
    append_row(
        "treatment_plans",
        {
            "plan_id": plan_id,
            "patient_id": pid,
            "budget_code": "orc_test",
            "issue_date": pd.Timestamp.today().normalize(),
            "start_date": pd.Timestamp.today().normalize(),
            "end_date": pd.Timestamp.today().normalize(),
            "status": "Ativo",
            "main_goal": "g",
            "is_renewal": False,
            "notes": "",
        },
    )
    assert patient_has_ficha(pid) is True


def test_patient_has_ficha_false_for_missing_patient(csv_dir):
    assert patient_has_ficha("pat_does_not_exist") is False


def test_patient_has_ficha_false_when_no_plan_in_seed(csv_dir):
    """Base zerada: plans CSV so' tem header; helper retorna False
    para qualquer pid.
    """
    assert patient_has_ficha("any_pid") is False


def test_patient_has_ficha_reflects_recent_appends(csv_dir):
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
    pid = _register_patient(name="Vai pra Ficha", age=30)
    _cadastro_form_state(fake_session_state)

    _handle_submit(pid)

    plans = load_table("treatment_plans")
    goals = load_table("patient_goals")
    # 0 seed + 1 new = 1
    assert len(plans) == 1
    assert len(goals) == 1
    new_plan = plans.iloc[-1]
    new_goal = goals.iloc[-1]
    assert new_plan["patient_id"] == pid
    assert new_goal["plan_id"] == new_plan["plan_id"]
    # Navigation side effect
    assert fake_session_state["page"] == "Ficha do Paciente"
    assert fake_session_state["selected_patient_id"] == pid


def test_handle_ficha_submit_creates_weight_entry_when_peso_atual_positive(
    fake_session_state, csv_dir
):
    pid = _register_patient(name="Com Peso Atual", age=30)
    _cadastro_form_state(
        fake_session_state,
        objetivo="",
        peso_inicial=0.0,
        peso_atual=82.5,
        peso_meta=0.0,
        status="Aguardando início",
    )

    _handle_submit(pid)

    weights = load_table("weight_entries")
    assert len(weights) == 1  # 0 seed + 1 new
    new_weight = weights.iloc[-1]
    assert float(new_weight["weight"]) == 82.5
    assert new_weight["patient_id"] == pid


def test_handle_ficha_submit_skips_weight_entry_when_peso_atual_zero(
    fake_session_state, csv_dir
):
    pid = _register_patient(name="Sem Peso Atual", age=30)
    _cadastro_form_state(
        fake_session_state,
        objetivo="",
        peso_inicial=0.0,
        peso_atual=0.0,  # zero → no weight entry
        peso_meta=0.0,
        status="Aguardando início",
    )

    _handle_submit(pid)

    weights = load_table("weight_entries")
    assert len(weights) == 0  # base zerada, peso_atual=0 nao cria entry


def test_handle_ficha_submit_skips_items_with_empty_name(fake_session_state, csv_dir):
    """Items whose name is empty must be filtered out (the data editor
    starts with 3 empty rows by default)."""
    pid = _register_patient(name="Com Items", age=30)
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

    _handle_submit(pid)

    items = load_table("treatment_plan_items")
    assert len(items) == 2  # 0 seed + 2 (Injetaveis + Manipulado)
    assert items.iloc[-2]["raw_name"] == "Injetáveis"
    assert items.iloc[-2]["frequency_type"] == "Semanal"
    assert items.iloc[-2]["frequency_text"] == "8 sessões - semanal"
    assert items.iloc[-1]["raw_name"] == "Manipulado"


def test_handle_ficha_submit_updates_patient_age(fake_session_state, csv_dir):
    pid = _register_patient(name="Vai Atualizar Idade", age=30)
    _cadastro_form_state(fake_session_state, age=55)

    _handle_submit(pid)

    patients = load_table("patients")
    row = patients[patients["patient_id"] == pid].iloc[0]
    assert int(row["age"]) == 55
