"""Alerts page."""
from __future__ import annotations

import streamlit as st

from src.components.badges import badge
from src.navigation import open_patient


def render(data):
    st.title("Alertas")
    patients = data["patients"][["patient_id", "name"]]
    alerts = data["alerts"].merge(patients, on="patient_id", how="left")
    category = st.selectbox("Categoria", ["Todos", "Enfermagem", "Médica", "Comercial", "Nutrição"])
    if category != "Todos":
        alerts = alerts[alerts["category"] == category]
    st.caption("Alertas fictícios para validar fluxo de priorização e abertura da ficha.")
    for _, row in alerts.sort_values(["priority", "created_at"], ascending=[True, False]).iterrows():
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            cols[0].markdown(f"**{row['alert_type']}**  \n{row['name']} · {row['description']}")
            with cols[1]:
                badge(row["priority"], row["priority"])
            cols[2].write(row["status"])
            cols[2].caption(str(row["created_at"].date()))
            if cols[3].button("Abrir ficha", key=f"alert_{row['alert_id']}"):
                open_patient(row["patient_id"])
    if alerts.empty:
        st.info("Nenhum alerta para a categoria selecionada.")
