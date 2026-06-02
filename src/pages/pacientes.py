"""Patients page."""
from __future__ import annotations

import streamlit as st

from src.components.filters import patient_filters
from src.components.tables import render_table
from src.metrics import patient_summary
from src.navigation import open_patient


def render(data):
    st.title("Pacientes")
    summary = patient_summary(data)
    filtered = patient_filters(summary)
    st.subheader("Tabela de pacientes")
    columns = [
        "name",
        "status",
        "start_date",
        "end_date",
        "budget_code",
        "sessions_expected",
        "sessions_completed",
        "sessions_remaining",
        "engagement_level",
        "open_alerts",
    ]
    render_table(
        filtered[columns].rename(
            columns={
                "name": "Nome",
                "status": "Status",
                "start_date": "Início",
                "end_date": "Fim",
                "budget_code": "Orçamento",
                "sessions_expected": "Sessões previstas",
                "sessions_completed": "Sessões realizadas",
                "sessions_remaining": "Sessões restantes",
                "engagement_level": "Engajamento",
                "open_alerts": "Alertas",
            }
        )
    )
    st.subheader("Selecionar paciente")
    if filtered.empty:
        st.info("Nenhum paciente encontrado com os filtros atuais.")
        return
    options = dict(zip(filtered["name"], filtered["patient_id"]))
    selected_name = st.selectbox("Paciente", list(options))
    if st.button("Abrir Ficha do Paciente", type="primary"):
        open_patient(options[selected_name])
