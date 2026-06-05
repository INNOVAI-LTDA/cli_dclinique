"""Patient-record (ficha) registration page.

Renders the cadastro form for a patient who doesn't yet have a
treatment plan. The patient is taken from ``st.session_state["selected_patient_id"]``,
which is set by the deep-link on the Pacientes page when the patient
has no ficha.

If the patient already has a ficha (e.g. they reached the page from a
stale link), the page silently redirects to the Ficha do Paciente
view.
"""
from __future__ import annotations

import streamlit as st

from src.components.add_patient import merge_extra_patients
from src.components.empty_states import render_empty
from src.components.ficha import (
    merge_extra_fichas,
    patient_has_ficha,
    render_cadastro_ficha_form,
)
from src.components.patient_header import render_patient_header
from src.navigation import go_to


def _page_css() -> str:
    return """
        <style>
            .ficha-cadastro-back-link {
                color: #2563eb;
                display: inline-flex;
                font-size: 0.78rem;
                font-weight: 600;
                margin: 0.05rem 0 0.6rem;
                text-decoration: none;
            }
            .ficha-cadastro-back-link:hover {
                text-decoration: underline;
            }
            .ficha-cadastro-empty {
                color: #475569;
                font-size: 0.88rem;
                margin-top: 0.6rem;
            }
        </style>
    """


def _render_back_link() -> None:
    if st.button("← Voltar para Pacientes", key="ficha_cadastro_back_link", type="secondary"):
        go_to("Pacientes")


def render(data) -> None:
    st.markdown(_page_css(), unsafe_allow_html=True)

    data = merge_extra_patients(data)
    data = merge_extra_fichas(data)

    patient_id = st.session_state.get("selected_patient_id")
    if not patient_id:
        _render_back_link()
        render_empty("Nenhum paciente selecionado para cadastro de ficha.")
        return

    # If the patient picked up a ficha between the link click and the
    # page render (or a stale link landed here), bounce to the ficha
    # view instead of showing the cadastro form.
    if patient_has_ficha(str(patient_id), data):
        st.session_state["selected_patient_id"] = str(patient_id)
        st.session_state["page"] = "Ficha do Paciente"
        st.rerun()
        return

    patients = data.get("patients")
    if patients is None or patients.empty or "patient_id" not in patients.columns:
        _render_back_link()
        render_empty("Tabela de pacientes indisponível.")
        return

    matches = patients[patients["patient_id"].astype(str) == str(patient_id)]
    if matches.empty:
        _render_back_link()
        render_empty("Paciente não encontrado.")
        return

    patient = matches.iloc[0].to_dict()

    _render_back_link()
    render_patient_header(patient, status_label="Sem ficha")
    render_cadastro_ficha_form(data, patient)
