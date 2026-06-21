"""End-to-end integration tests for the MAP shell.

These tests drive the real ``app.py`` through ``streamlit.testing.v1.AppTest``
and assert on the rendered markup, session state, and the on-disk CSV
state. They cover the user-reported bug scenarios (patient disappears on
refresh, deep-link 404, link target switching) and the surrounding
flow (navigation, cadastro, form validation).

The ``csv_dir`` fixture (autouse) redirects the data layer to a fresh
copy of the seed CSVs under ``tmp_path`` for every test, so the tests
neither pollute the developer's local checkout nor leak state into one
another.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from streamlit.testing.v1 import AppTest

from src.data_layer import load_table


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_pacientes() -> AppTest:
    at = AppTest.from_file(os.path.abspath("app.py"), default_timeout=30)
    at.session_state["page"] = "Pacientes"
    at.run()
    return at


def _patient_link_markup(at: AppTest) -> str:
    return "".join(
        str(m.value) for m in at.markdown if "patients-name-link" in str(m.value)
    )


def _open_add_form(at: AppTest) -> None:
    """Reopen the add-patient form. The toggle button is only rendered
    when the form is closed, but AppTest's ``at.button`` also contains
    the form's submit/cancel buttons (which never go away), so we set the
    flag directly — this is the same effect as clicking the toggle."""
    at.session_state["add_patient_open"] = True
    at.run()


def _fill_add_form(at: AppTest, *, name: str, age: int, record: str = "", phone: str = "") -> None:
    at.session_state["add_patient_name"] = name
    at.session_state["add_patient_age"] = age
    at.session_state["add_patient_record"] = record
    at.session_state["add_patient_phone"] = phone
    at.run()


def _submit_add_form(at: AppTest) -> None:
    submit = [b for b in at.button if b.label == "Cadastrar"]
    assert submit, "Cadastrar button not found"
    submit[0].click()
    at.run()


def _register_patient_via_form(at: AppTest, *, name: str, age: int) -> str:
    """Open the add-patient form, fill it, submit, and return the new patient_id."""
    _open_add_form(at)
    _fill_add_form(at, name=name, age=age)
    _submit_add_form(at)
    patients = load_table("patients")
    new_rows = patients[patients["patient_id"].str.startswith("pat_new_")]
    assert len(new_rows) == 1, f"Expected 1 new patient, got {len(new_rows)}"
    return str(new_rows.iloc[0]["patient_id"])


# ---------------------------------------------------------------------------
# 1. The reported bug: patient must appear in the table on the same
#    render that the form was submitted (no manual Cancelar required).
# ---------------------------------------------------------------------------


def test_newly_registered_patient_appears_in_table_on_same_render(csv_dir):
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Maria Bug Original", age=33)

    # The rerun triggered by the form submit must already show the patient.
    markup = _patient_link_markup(at)
    assert "Maria Bug Original" in markup, (
        "Bug reproduced: freshly registered patient is not visible in the table "
        "until a manual rerun is forced. The submit handler must rerun so the "
        "cache is repopulated from the CSV."
    )
    # Link target must point to Cadastro de Ficha do Paciente (no ficha yet).
    assert f"patient_id={pid}" in markup
    assert "Cadastro%20de%20Ficha%20do%20Paciente" in markup


def test_cancelar_after_submit_does_not_lose_the_patient(csv_dir):
    """Clicking Cancelar after a successful submit must keep the patient
    in the table (the form just closes)."""
    at = _render_pacientes()
    _open_add_form(at)
    _fill_add_form(at, name="Carlos Mantido", age=40)
    _submit_add_form(at)

    cancel = [b for b in at.button if b.label == "Cancelar"]
    if cancel:
        cancel[0].click()
        at.run()

    markup = _patient_link_markup(at)
    assert "Carlos Mantido" in markup


# ---------------------------------------------------------------------------
# 2. Clicking the patient's name must open the right page.
# ---------------------------------------------------------------------------


def test_link_targets_ficha_when_patient_already_has_ficha(csv_dir):
    """Base zerada (T9): registrar paciente + criar ficha via cadastro form,
    depois voltar para Pacientes e verificar que o link aponta para Ficha.

    Antes do T9, o test assumia 'todos os pacientes base tem plan no seed'
    e o markup ja' vinha com os links de Ficha. Agora a pre-existencia e'
    construida no proprio teste.
    """
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Com Ficha", age=30)

    # Cadastrar ficha
    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()
    at.session_state["cadastro_ficha_objetivo"] = "Emagrecimento"
    at.session_state["cadastro_ficha_peso_inicial"] = 80.0
    at.session_state["cadastro_ficha_peso_atual"] = 79.5
    at.session_state["cadastro_ficha_peso_meta"] = 70.0
    at.session_state["cadastro_ficha_status"] = "Ativo"
    at.session_state["cadastro_ficha_resumo"] = "Teste."
    at.session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    at.session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()
    at.run()
    submit = [b for b in at.button if b.label == "Cadastrar ficha"]
    assert submit, "Cadastrar ficha button not found"
    submit[0].click()
    at.run()

    # Voltar para Pacientes
    at.query_params["nav"] = "Pacientes"
    if "patient_id" in at.query_params:
        del at.query_params["patient_id"]
    at.run()

    # O link do paciente deve apontar para Ficha (nao para Cadastro)
    markup = _patient_link_markup(at)
    for line in markup.split("<a "):
        if "Com Ficha" in line:
            assert "Ficha%20do%20Paciente" in line
            assert "Cadastro%20de%20Ficha%20do%20Paciente" not in line
            break
    else:
        pytest.fail("Link for 'Com Ficha' patient not found in markup")


def test_link_targets_cadastro_for_newly_registered_patient(csv_dir):
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Recém Sem Ficha", age=22)
    markup = _patient_link_markup(at)
    # Find the line for our new patient
    for line in markup.split("<a "):
        if "Recém Sem Ficha" in line:
            assert "Cadastro%20de%20Ficha%20do%20Paciente" in line
            assert f"patient_id={pid}" in line
            break
    else:
        pytest.fail("Link for new patient not found in markup")


def test_deep_link_to_cadastro_finds_session_added_patient(csv_dir):
    """The exact symptom: clicking the new patient's link raised
    'Paciente não encontrado'. The cadastro page reads the CSV directly,
    so the freshly-registered patient is visible without any session
    state dance."""
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Encontrar no Cadastro", age=29)

    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()

    ss = at.session_state
    assert ss["page"] == "Cadastro de Ficha do Paciente"
    assert ss["selected_patient_id"] == pid
    rendered = "".join(str(m.value) for m in at.markdown)
    assert "Paciente não encontrado" not in rendered
    assert "Encontrar no Cadastro" in rendered  # patient name appears in header


# ---------------------------------------------------------------------------
# 3. The patient must persist across navigations (the "sumiu" symptom).
# ---------------------------------------------------------------------------


def test_patient_persists_after_navigating_to_cadastro_and_back(csv_dir):
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Persistente", age=50)

    # Go to cadastro
    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()
    assert at.session_state["page"] == "Cadastro de Ficha do Paciente"

    # Back to Pacientes
    at.query_params["nav"] = "Pacientes"
    if "patient_id" in at.query_params:
        del at.query_params["patient_id"]
    at.run()
    assert "Persistente" in _patient_link_markup(at)
    # Still exactly one extra patient in the CSV
    new_rows = load_table("patients")
    assert len(new_rows[new_rows["patient_id"].str.startswith("pat_new_")]) == 1


def test_patient_persists_after_visiting_other_pages(csv_dir):
    at = _render_pacientes()
    _register_patient_via_form(at, name="Volta e Meia", age=31)

    for nav in ["Visão Geral", "Mapa de Decisão", "Alertas", "Pacientes"]:
        at.query_params["nav"] = nav
        at.run()

    assert "Volta e Meia" in _patient_link_markup(at)


# ---------------------------------------------------------------------------
# 4. Cadastro de Ficha → Ficha navigation & link target switching.
# ---------------------------------------------------------------------------


def test_cadastro_redirects_to_ficha_if_patient_already_has_one(csv_dir):
    """Base zerada (T9): registrar paciente + criar plan via append_row,
    depois abrir o cadastro com deep-link e verificar redirect para Ficha.

    Antes do T9, o test usava 'pat_001' (paciente do seed com plan pre-existente).
    Agora a pre-existencia do plan e' construida no proprio teste.
    """
    from src.data_layer import append_row, next_id

    # Setup: registrar paciente
    at_setup = _render_pacientes()
    pid = _register_patient_via_form(at_setup, name="Com Plan Pre", age=35)

    # Criar plan pre-existente para esse paciente (simula o que o seed fazia)
    plan_id = next_id("treatment_plans")
    append_row(
        "treatment_plans",
        {
            "plan_id": plan_id,
            "patient_id": pid,
            "objective": "Emagrecimento",
            "status": "Ativo",
            "start_date": pd.Timestamp.today().normalize().date(),
            "end_date": (
                pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
            ).date(),
            "initial_weight": 80.0,
            "current_weight": 80.0,
            "target_weight": 70.0,
            "summary": "Pre-existente",
            "created_at": pd.Timestamp.today().normalize(),
        },
    )

    # Deep-link para o cadastro: deve redirecionar para Ficha
    at = _render_pacientes()
    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()
    assert at.session_state["page"] == "Ficha do Paciente"
    assert at.session_state["selected_patient_id"] == pid


def test_cadastro_form_submit_navigates_to_ficha_page(csv_dir):
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Vai pra Ficha", age=27)

    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()

    # Fill the cadastro form and submit.
    at.session_state["cadastro_ficha_objetivo"] = "Emagrecimento"
    at.session_state["cadastro_ficha_peso_inicial"] = 80.0
    at.session_state["cadastro_ficha_peso_atual"] = 79.5
    at.session_state["cadastro_ficha_peso_meta"] = 70.0
    at.session_state["cadastro_ficha_status"] = "Ativo"
    at.session_state["cadastro_ficha_resumo"] = "Teste."
    at.session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    at.session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()
    at.run()

    submit = [b for b in at.button if b.label == "Cadastrar ficha"]
    assert submit, "Cadastrar ficha button not found"
    submit[0].click()
    at.run()

    # The handler must navigate to Ficha do Paciente and select the patient.
    assert at.session_state["page"] == "Ficha do Paciente"
    assert at.session_state["selected_patient_id"] == pid
    # And the plan/goal/weight rows must be in their CSVs
    plans = load_table("treatment_plans")
    goals = load_table("patient_goals")
    assert len(plans[plans["patient_id"] == pid]) == 1
    assert len(goals[goals["patient_id"] == pid]) == 1


def test_link_target_switches_from_cadastro_to_ficha_after_cadastro(csv_dir):
    """After creating a ficha, the link in the Pacientes table must point
    to 'Ficha do Paciente' instead of 'Cadastro de Ficha do Paciente'."""
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Migrou pra Ficha", age=44)

    # Cadastrar ficha
    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()
    at.session_state["cadastro_ficha_objetivo"] = "Controle"
    at.session_state["cadastro_ficha_peso_inicial"] = 90.0
    at.session_state["cadastro_ficha_peso_atual"] = 88.0
    at.session_state["cadastro_ficha_peso_meta"] = 80.0
    at.session_state["cadastro_ficha_status"] = "Ativo"
    at.session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    at.session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()
    at.run()
    submit = [b for b in at.button if b.label == "Cadastrar ficha"][0]
    submit.click()
    at.run()

    # Back to Pacientes
    at.query_params["nav"] = "Pacientes"
    if "patient_id" in at.query_params:
        del at.query_params["patient_id"]
    at.run()

    markup = _patient_link_markup(at)
    for line in markup.split("<a "):
        if "Migrou pra Ficha" in line:
            assert "Ficha%20do%20Paciente" in line
            assert "Cadastro%20de%20Ficha%20do%20Paciente" not in line
            break
    else:
        pytest.fail("Link for migrated patient not found in markup")


# ---------------------------------------------------------------------------
# 5. Form validation behaviour (reject empty / duplicate names).
# ---------------------------------------------------------------------------


def test_add_patient_form_rejects_empty_name(csv_dir):
    at = _render_pacientes()
    _open_add_form(at)
    at.session_state["add_patient_name"] = ""
    at.session_state["add_patient_age"] = 30
    at.run()
    _submit_add_form(at)
    new_rows = load_table("patients")
    assert len(new_rows[new_rows["patient_id"].str.startswith("pat_new_")]) == 0
    # Form should remain open so the user can fix the field
    assert at.session_state["add_patient_open"] is True


def test_add_patient_form_rejects_duplicate_name(csv_dir):
    """Base zerada (T9): registrar Maria Duplicada, depois tentar adicionar
    de novo via form. O form deve rejeitar (form continua aberto, nenhuma
    nova linha pat_new_ criada).

    Antes do T9, o test usava um paciente do seed como nome duplicado.
    Agora a pre-existencia e' construida via form.
    """
    at = _render_pacientes()
    _register_patient_via_form(at, name="Maria Duplicada", age=30)
    _open_add_form(at)
    at.session_state["add_patient_name"] = "Maria Duplicada"
    at.session_state["add_patient_age"] = 30
    at.run()
    _submit_add_form(at)
    new_rows = load_table("patients")
    # 1 pat_new_001 (do setup) + 0 novo (rejeitado) = 1 total
    assert len(new_rows[new_rows["patient_id"].str.startswith("pat_new_")]) == 1
    assert at.session_state["add_patient_open"] is True


# ---------------------------------------------------------------------------
# 6. Cancelar just closes the form (does not save anything).
# ---------------------------------------------------------------------------


def test_cancelar_with_empty_form_closes_without_saving(csv_dir):
    at = _render_pacientes()
    _open_add_form(at)
    assert at.session_state["add_patient_open"] is True
    cancel = [b for b in at.button if b.label == "Cancelar"]
    assert cancel
    cancel[0].click()
    at.run()
    assert at.session_state["add_patient_open"] is False
    new_rows = load_table("patients")
    assert len(new_rows[new_rows["patient_id"].str.startswith("pat_new_")]) == 0


def test_cancelar_does_not_lose_already_registered_patients(csv_dir):
    at = _render_pacientes()
    _register_patient_via_form(at, name="Antes do Cancelar", age=40)
    # Reopen form, fill, then cancel
    _open_add_form(at)
    at.session_state["add_patient_name"] = "Sera Descartado"
    at.session_state["add_patient_age"] = 25
    at.run()
    cancel = [b for b in at.button if b.label == "Cancelar"][0]
    cancel.click()
    at.run()
    # The original patient is still there
    patients = load_table("patients")
    assert "Antes do Cancelar" in patients["name"].values
    assert "Antes do Cancelar" in _patient_link_markup(at)


# ---------------------------------------------------------------------------
# 7. CSV persistence (the F5 scenario).
#
# The data layer's CSVs are the single source of truth: registering a
# patient must persist to ``patients.csv`` so a hard refresh (which wipes
# ``st.session_state`` in a real browser) does not lose the row.
# ---------------------------------------------------------------------------


def test_patient_registration_writes_to_csv(csv_dir):
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Persistido em Disco", age=27)

    # The CSV must contain exactly this one new patient row.
    patients = load_table("patients")
    new_rows = patients[patients["patient_id"] == pid]
    assert len(new_rows) == 1
    row = new_rows.iloc[0]
    assert row["name"] == "Persistido em Disco"
    assert row["patient_id"] == pid


def test_registered_patient_persists_across_simulated_hard_refresh(csv_dir):
    """After a hard refresh, ``st.session_state`` is wiped but the CSV
    remains. The next render must reload the patient from the CSV so
    it keeps appearing in the Pacientes table."""
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Sobrevive ao Refresh", age=41)
    assert len(load_table("patients")[load_table("patients")["patient_id"] == pid]) == 1

    # --- Simulate a hard refresh: wipe the session, keep the CSV. ---
    # In a real browser the WebSocket reconnects and a new session
    # starts; AppTest's session_state survives ``at.run()`` calls, so we
    # explicitly clear the keys we don't want to leak across runs.
    for key in (
        "add_patient_open",
        "patients_page",
        "selected_patient_id",
    ):
        if key in at.session_state:
            del at.session_state[key]
    at.run()

    # After the simulated reload, the patient must be back in the table.
    markup = _patient_link_markup(at)
    assert "Sobrevive ao Refresh" in markup, (
        "Hard refresh lost the patient. The data layer reads from the CSV "
        "on every load_table call, so the row must survive the cache and "
        "session_state wipe."
    )
    assert f"patient_id={pid}" in markup


def test_cadastrada_ficha_persists_across_simulated_hard_refresh(csv_dir):
    """Same property, but for a ficha cadastrada via the Cadastro de
    Ficha form. Plan/goal/items/weight rows must all be reloaded from
    the CSVs after a simulated refresh."""
    at = _render_pacientes()
    pid = _register_patient_via_form(at, name="Ficha Persistente", age=33)

    # Cadastrar a ficha.
    at.query_params["nav"] = "Cadastro de Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()
    at.session_state["cadastro_ficha_objetivo"] = "Emagrecimento"
    at.session_state["cadastro_ficha_peso_inicial"] = 80.0
    at.session_state["cadastro_ficha_peso_atual"] = 79.0
    at.session_state["cadastro_ficha_peso_meta"] = 70.0
    at.session_state["cadastro_ficha_status"] = "Ativo"
    at.session_state["cadastro_ficha_resumo"] = "Plano de teste"
    at.session_state["cadastro_ficha_inicio"] = pd.Timestamp.today().normalize().date()
    at.session_state["cadastro_ficha_fim"] = (
        pd.Timestamp.today().normalize() + pd.Timedelta(days=60)
    ).date()
    at.run()
    submit = [b for b in at.button if b.label == "Cadastrar ficha"][0]
    submit.click()
    at.run()

    # The submit must have written at least one plan, one goal, and one
    # weight entry to the CSVs.
    plans = load_table("treatment_plans")
    goals = load_table("patient_goals")
    weights = load_table("weight_entries")
    assert len(plans[plans["patient_id"] == pid]) == 1
    assert len(goals[goals["patient_id"] == pid]) == 1
    assert len(weights[weights["patient_id"] == pid]) == 1

    # --- Simulate a hard refresh. ---
    for key in (
        "add_patient_open",
        "patients_page",
        "selected_patient_id",
        "page",
    ):
        if key in at.session_state:
            del at.session_state[key]
    at.query_params["nav"] = "Ficha do Paciente"
    at.query_params["patient_id"] = pid
    at.run()

    # The Ficha do Paciente page must find the patient and the plan.
    assert at.session_state["page"] == "Ficha do Paciente"
    assert at.session_state["selected_patient_id"] == pid
    rendered = "".join(str(m.value) for m in at.markdown)
    assert "Ficha Persistente" in rendered
    assert "Plano de teste" in rendered  # resumo from the form
