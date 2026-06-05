"""Add-patient widget: toggle button, form, and session-state merge helper.

The MAP shell keeps fictional data locally; new patients live in
``st.session_state["extra_patients"]`` (a list of dicts that matches the
``EXPECTED_SCHEMAS["patients"]`` contract — see ``src/schemas.py``) and are
mirrored to ``data/extra_data.json`` (see ``src/persistence.py``) so they
survive hard refreshes, tab close/reopen, and Streamlit server restarts.

``merge_extra_patients`` is the single read path used by the pages that need
to see those rows. Within a single Streamlit session, it reads from
``st.session_state`` (warm path). When the session state key is missing —
which happens after a full page reload — ``_ensure_state`` reloads the list
from the on-disk file.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.persistence import load_extras, reset_extras, save_key
from src.schemas import EXPECTED_SCHEMAS

_EXTRA_KEY = "extra_patients"
_OPEN_KEY = "add_patient_open"
_FORM_KEY = "add_patient_form"
_NAME_KEY = "add_patient_name"
_RECORD_KEY = "add_patient_record"
_PHONE_KEY = "add_patient_phone"
_AGE_KEY = "add_patient_age"


def _ensure_state() -> None:
    # `setdefault` would clobber a list loaded from disk, so check first.
    if _EXTRA_KEY not in st.session_state:
        st.session_state[_EXTRA_KEY] = load_extras().get(_EXTRA_KEY, [])
    st.session_state.setdefault(_OPEN_KEY, False)


def _persist_extra_patients() -> None:
    """Mirror the current ``st.session_state[_EXTRA_KEY]`` to the JSON file."""
    save_key(_EXTRA_KEY, st.session_state[_EXTRA_KEY])


def _existing_name_keys(data: dict[str, pd.DataFrame] | None) -> set[str]:
    keys: set[str] = set()
    if data is not None and "patients" in data and not data["patients"].empty:
        keys.update(
            data["patients"]["normalized_name"].dropna().astype(str).str.lower().tolist()
        )
    for row in st.session_state.get(_EXTRA_KEY, []):
        name = row.get("name")
        if name:
            keys.add(str(name).strip().lower())
    return keys


def _next_patient_id(data: dict[str, pd.DataFrame]) -> str:
    used: set[str] = set()
    if data is not None and "patients" in data and not data["patients"].empty:
        used.update(data["patients"]["patient_id"].dropna().astype(str).tolist())
    for row in st.session_state.get(_EXTRA_KEY, []):
        pid = row.get("patient_id")
        if pid:
            used.add(str(pid))
    counter = 1
    while f"pat_new_{counter:03d}" in used:
        counter += 1
    return f"pat_new_{counter:03d}"


def merge_extra_patients(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Return ``data`` with any session-added patients appended to ``patients``.

    Returns the **same** dict instance when there are no extra patients, so
    ``@st.cache_data`` consumers (e.g. ``patient_summary``) keep their cache.
    """
    _ensure_state()
    extras = st.session_state[_EXTRA_KEY]
    if not extras:
        return data
    if data is None or "patients" not in data:
        return data

    columns = EXPECTED_SCHEMAS["patients"]
    extras_df = pd.DataFrame(extras, columns=columns)
    extras_df["created_at"] = pd.to_datetime(extras_df["created_at"], errors="coerce")
    merged_patients = pd.concat([data["patients"], extras_df], ignore_index=True)

    new_data = dict(data)
    new_data["patients"] = merged_patients
    return new_data


def reset_extra_patients() -> None:
    """Clear all session-added patients. Useful for tests / debug only."""
    st.session_state[_EXTRA_KEY] = []
    st.session_state[_OPEN_KEY] = False
    reset_extras()


def _handle_submit(data: dict[str, pd.DataFrame]) -> bool:
    name = str(st.session_state.get(_NAME_KEY, "")).strip()
    record = str(st.session_state.get(_RECORD_KEY, "")).strip()
    phone = str(st.session_state.get(_PHONE_KEY, "")).strip()
    age_raw = st.session_state.get(_AGE_KEY, 0)

    if not name:
        st.error("Nome é obrigatório.")
        return False

    normalized = name.lower()
    if normalized in _existing_name_keys(data):
        st.error("Já existe paciente com esse nome.")
        return False

    try:
        age_value: int | None = int(age_raw)
    except (TypeError, ValueError):
        age_value = None
    if age_value is not None and age_value <= 0:
        age_value = None

    patient_id = _next_patient_id(data)
    new_row: dict[str, Any] = {
        "patient_id": patient_id,
        "name": name,
        "normalized_name": normalized,
        "medical_record": record or None,
        "phone": phone or None,
        "age": age_value,
        "created_at": pd.Timestamp.today().normalize(),
    }
    st.session_state[_EXTRA_KEY].append(new_row)
    _persist_extra_patients()
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
    _ensure_state()
    if st.session_state[_OPEN_KEY]:
        return
    st.button(
        "+ Adicionar paciente",
        key="add_patient_toggle",
        on_click=_open_form,
        type="primary",
    )


def render_add_patient_form(data: dict[str, pd.DataFrame] | None = None) -> None:
    """Render the add-patient form full-width below the toggle row.

    No-op when the form is closed. Caller is expected to gate on
    ``st.session_state["add_patient_open"]`` or simply call this and let
    the helper self-gate.
    """
    _ensure_state()
    if not st.session_state[_OPEN_KEY]:
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
                _handle_submit(data)
            elif cancelled:
                _close_form()
                st.rerun()
