"""Add-patient widget: toggle button, form, and session-state merge helper.

The MAP shell keeps all data in memory; new patients live in
``st.session_state["extra_patients"]`` (a list of dicts that matches the
``EXPECTED_SCHEMAS["patients"]`` contract — see ``src/schemas.py``) for the
lifetime of the session. ``merge_extra_patients`` is the single read path used
by the pages that need to see those rows.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.schemas import EXPECTED_SCHEMAS

_EXTRA_KEY = "extra_patients"
_OPEN_KEY = "add_patient_open"
_FORM_KEY = "add_patient_form"
_NAME_KEY = "add_patient_name"
_RECORD_KEY = "add_patient_record"
_PHONE_KEY = "add_patient_phone"
_AGE_KEY = "add_patient_age"


def _ensure_state() -> None:
    st.session_state.setdefault(_EXTRA_KEY, [])
    st.session_state.setdefault(_OPEN_KEY, False)


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
    st.session_state[_OPEN_KEY] = False
    st.session_state["patients_page"] = 1
    st.success(f"Paciente '{name}' cadastrado.")
    return True


def _open_form() -> None:
    st.session_state[_OPEN_KEY] = True


def _close_form() -> None:
    st.session_state[_OPEN_KEY] = False


def render_add_patient_control(data: dict[str, pd.DataFrame] | None = None) -> None:
    """Render the toggle button and, when open, the add-patient form.

    The caller controls positioning via its own ``st.columns`` / container.
    When the toggle is closed nothing is rendered, so the closed state costs
    effectively zero.
    """
    _ensure_state()
    is_open = bool(st.session_state[_OPEN_KEY])

    if not is_open:
        st.button(
            "+ Adicionar paciente",
            key="add_patient_toggle",
            on_click=_open_form,
            type="primary",
        )
        return

    with st.form(_FORM_KEY, clear_on_submit=True):
        st.markdown(
            '<p style="color:#0f172a;font-size:0.92rem;font-weight:700;'
            'margin:0 0 0.5rem;">Cadastrar novo paciente</p>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            st.text_input("Nome completo", key=_NAME_KEY, placeholder="Ex.: Maria de Souza")
        with c2:
            st.text_input("Prontuário", key=_RECORD_KEY, placeholder="Opcional")
        c3, c4 = st.columns([1, 1])
        with c3:
            st.text_input("Telefone", key=_PHONE_KEY, placeholder="(00) 00000-0000")
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

        submitted = st.form_submit_button("Cadastrar", type="primary")
        if submitted:
            _handle_submit(data)

    st.button("Cancelar", key="add_patient_cancel", on_click=_close_form)
