"""Ações popover for the Pacientes page.

Replaces the direct ``+ Adicionar paciente`` toggle with a popover that
exposes two flows:

- ``Adicionar paciente`` — the existing form (unchanged).
- ``Importar paciente(s) do PDF`` — the PDF import wizard.

The popover body renders inline (Streamlit's standard behaviour); the
chosen action's flag is set in the ``on_click`` callback and observed on
the next render. Both flags (``add_patient_open`` and
``import_pdf_open``) are mutually exclusive — opening one closes the
other — so the two flows never overlap in the UI.

The popover is meant to be placed in a narrow right-aligned column by
the caller; the form / wizard it triggers renders full-width below
that column so its fields aren't squashed.
"""
from __future__ import annotations

import streamlit as st


def _open_add() -> None:
    st.session_state["add_patient_open"] = True
    st.session_state["import_pdf_open"] = False


def _open_import() -> None:
    st.session_state["import_pdf_open"] = True
    st.session_state["add_patient_open"] = False


def render_acoes_popover() -> None:
    """Render just the Ações popover (no form/wizard).

    The caller (``src/pages/pacientes.py``) renders the form or wizard
    below the popover, full-width, based on the
    ``add_patient_open`` / ``import_pdf_open`` session-state flags.
    """
    if hasattr(st, "popover"):
        with st.popover("Ações", use_container_width=True):
            st.button(
                "Adicionar paciente",
                key="acoes_add_patient",
                on_click=_open_add,
                use_container_width=True,
            )
            st.button(
                "Importar paciente(s) do PDF",
                key="acoes_import_pdf",
                on_click=_open_import,
                use_container_width=True,
            )
    else:
        # Fallback for older Streamlit versions: two buttons side by side.
        col_a, col_b = st.columns(2)
        with col_a:
            st.button(
                "Adicionar paciente",
                key="acoes_add_patient",
                on_click=_open_add,
            )
        with col_b:
            st.button(
                "Importar paciente(s) do PDF",
                key="acoes_import_pdf",
                on_click=_open_import,
            )
