"""Add-patient widget: toggle button, form, and submit handler.

The MAP shell's source of truth is the CSV layer at ``data/csv/``
(see :mod:`src.data_layer`). The widget on this page just writes a new
row to ``patients.csv`` via :func:`src.data_layer.append_row` and then
invalidates the Streamlit cache so the next render reads it.

Persistence across navigations, F5, tab close, and Streamlit server
restart is now provided by the CSVs themselves — no in-memory session
state and no JSON sidecar are needed.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.data_layer import append_row, load_table, next_id

_OPEN_KEY = "add_patient_open"
_FORM_KEY = "add_patient_form"
_NAME_KEY = "add_patient_name"
_RECORD_KEY = "add_patient_record"
_PHONE_KEY = "add_patient_phone"
_AGE_KEY = "add_patient_age"


def _existing_normalized_names() -> set[str]:
    """Return the lower-cased, trimmed names already in ``patients.csv``.

    Reads the CSV directly (not the cached ``load_all``) so the check
    reflects the on-disk state at the moment of submit — even if a
    previous render left a stale entry in the Streamlit cache.
    """
    df = load_table("patients")
    if df.empty or "normalized_name" not in df.columns:
        return set()
    return set(df["normalized_name"].dropna().astype(str).str.strip().str.lower().tolist())


def _handle_submit() -> bool:
    name = str(st.session_state.get(_NAME_KEY, "")).strip()
    record = str(st.session_state.get(_RECORD_KEY, "")).strip()
    phone = str(st.session_state.get(_PHONE_KEY, "")).strip()
    age_raw = st.session_state.get(_AGE_KEY, 0)

    if not name:
        st.error("Nome é obrigatório.")
        return False

    normalized = name.lower()
    if normalized in _existing_normalized_names():
        st.error("Já existe paciente com esse nome.")
        return False

    try:
        age_value: int | None = int(age_raw)
    except (TypeError, ValueError):
        age_value = None
    if age_value is not None and age_value <= 0:
        age_value = None

    patient_id = next_id("patients")
    new_row: dict[str, Any] = {
        "patient_id": patient_id,
        "name": name,
        "normalized_name": normalized,
        "medical_record": record or None,
        "phone": phone or None,
        "age": age_value,
        "created_at": pd.Timestamp.today().normalize(),
    }
    append_row("patients", new_row)
    # Drop the cached ``get_data`` so the next render re-reads the CSV
    # and the new patient is visible in the table immediately. Pages
    # that care about the freshness (e.g. ``pacientes``) check the
    # ``_data_dirty`` flag below and re-read on the same render — no
    # ``st.rerun()`` needed (which would interact poorly with the
    # form's ``clear_on_submit=True``).
    st.cache_data.clear()
    st.session_state["_data_dirty"] = True

    st.session_state[_OPEN_KEY] = False
    st.session_state["patients_page"] = 1
    st.success(f"Paciente '{name}' cadastrado.")
    return True


def _open_form() -> None:
    st.session_state[_OPEN_KEY] = True


def _close_form() -> None:
    st.session_state[_OPEN_KEY] = False


def render_add_patient_toggle() -> None:
    """Render the ``+ Adicionar paciente`` button (closed state only).

    The button is meant to live in a narrow right-aligned column. When the
    form is already open this function renders nothing — the open state
    owns its own row via ``render_add_patient_form``.
    """
    if st.session_state.get(_OPEN_KEY):
        return
    st.button(
        "+ Adicionar paciente",
        key="add_patient_toggle",
        on_click=_open_form,
        type="primary",
    )


def render_add_patient_form(data: dict | None = None) -> None:
    """Render the add-patient form full-width below the toggle row.

    No-op when the form is closed. ``data`` is accepted for backward
    compatibility with the previous merge-based contract but is no longer
    needed — the submit handler reads ``patients.csv`` directly.
    """
    if not st.session_state.get(_OPEN_KEY):
        return

    with st.container(border=True):
        st.markdown(
            '<p style="color:#0f172a;font-size:0.95rem;font-weight:700;'
            'margin:0 0 0.6rem;">Cadastrar novo paciente</p>',
            unsafe_allow_html=True,
        )
        with st.form(_FORM_KEY, clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.text_input(
                    "Nome completo",
                    key=_NAME_KEY,
                    placeholder="Ex.: Maria de Souza",
                )
            with c2:
                st.text_input(
                    "Prontuário",
                    key=_RECORD_KEY,
                    placeholder="Opcional",
                )
            c3, c4 = st.columns([1, 1])
            with c3:
                st.text_input(
                    "Telefone",
                    key=_PHONE_KEY,
                    placeholder="(00) 00000-0000",
                )
            with c4:
                st.number_input(
                    "Idade",
                    min_value=0,
                    max_value=120,
                    step=1,
                    value=0,
                    format="%d",
                    key=_AGE_KEY,
                )

            action_cols = st.columns([1, 1, 6])
            with action_cols[0]:
                submitted = st.form_submit_button(
                    "Cadastrar", type="primary", use_container_width=True
                )
            with action_cols[1]:
                cancelled = st.form_submit_button(
                    "Cancelar", use_container_width=True
                )
            if submitted:
                _handle_submit()
            elif cancelled:
                _close_form()
                st.rerun()
