"""Utilities for session-state based navigation."""

SIDEBAR_PAGES = [
    "Visão Geral",
    "Mapa de Decisão",
    "Pacientes",
    "Alertas",
    "Atualização de Dados",
    "Qualidade dos Dados",
]

INTERNAL_PAGES = ["Ficha do Paciente"]
PAGES = SIDEBAR_PAGES + INTERNAL_PAGES
DEFAULT_PAGE = SIDEBAR_PAGES[0]


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
    # When called from a widget callback, Streamlit will rerun after
    # the callback returns. Calling `st.rerun()` inside a callback is
    # effectively a no-op, so we only update session state here and
    # rely on the caller's environment to trigger the run loop.
    st.session_state["selected_patient_id"] = patient_id
    st.session_state["page"] = "Ficha do Paciente"
