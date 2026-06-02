"""Patient header component."""
from __future__ import annotations

import streamlit as st

from src.components.badges import badge


def render_patient_header(patient: dict) -> None:
    st.subheader(patient["name"])
    cols = st.columns([2, 1, 1, 1])
    cols[0].caption(f"Prontuário {patient['medical_record']} · {patient['age']} anos")
    cols[1].metric("Status", patient["status"])
    cols[2].metric("Engajamento", patient["engagement_level"])
    cols[3].metric("Satisfação", patient.get("satisfaction_status") or "Não informado")
    badge(patient["engagement_level"], patient["engagement_level"])
