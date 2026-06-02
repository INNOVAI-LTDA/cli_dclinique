"""Utilities for session-state based navigation."""

PAGES = [
    "Visão Geral",
    "Mapa de Decisão",
    "Pacientes",
    "Ficha do Paciente",
    "Alertas",
    "Atualização de Dados",
    "Qualidade dos Dados",
]
DEFAULT_PAGE = PAGES[0]


def init_navigation_state() -> None:
    """Ensure Streamlit navigation keys exist."""
    import streamlit as st

    current_page = st.session_state.setdefault("page", DEFAULT_PAGE)
    if current_page not in PAGES:
        st.session_state["page"] = DEFAULT_PAGE
    st.session_state.setdefault("selected_patient_id", None)


def go_to(page: str) -> None:
    """Navigate to a top-level page."""
    import streamlit as st

    st.session_state["page"] = page
    st.rerun()


def open_patient(patient_id: str) -> None:
    """Select a patient and navigate to the patient detail page."""
    import streamlit as st

    st.session_state["selected_patient_id"] = patient_id
    st.session_state["page"] = "Ficha do Paciente"
    st.rerun()
