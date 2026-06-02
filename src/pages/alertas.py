"""Alerts page."""
from __future__ import annotations

import streamlit as st

from src.components.badges import badge
from src.components.patient_actions import render_open_patient_button


def render(data):
    st.title("Alertas")
    patients = data["patients"][["patient_id", "name"]]
    alerts = data["alerts"].merge(patients, on="patient_id", how="left")

    col1, col2, col3, col4 = st.columns(4)
    category = col1.selectbox("Categoria", ["Todos", "Enfermagem", "Médica", "Comercial", "Nutrição"])
    priority = col2.selectbox("Prioridade", ["Todas", "Alta", "Média", "Baixa"])
    status = col3.selectbox("Status", ["Todos"] + sorted(alerts["status"].dropna().unique().tolist()))
    query = col4.text_input("Buscar paciente", "")

    if category != "Todos":
        alerts = alerts[alerts["category"] == category]
    if priority != "Todas":
        alerts = alerts[alerts["priority"] == priority]
    if status != "Todos":
        alerts = alerts[alerts["status"] == status]
    if query:
        alerts = alerts[alerts["name"].str.lower().str.contains(query.lower(), na=False)]

    st.caption("Alertas fictícios para validar fluxo de priorização e abertura da ficha.")

    k1, k2, k3 = st.columns(3)
    k1.metric("Alertas filtrados", len(alerts))
    k2.metric("Prioridade alta", int((alerts["priority"] == "Alta").sum()))
    k3.metric("Abertos", int((alerts["status"] == "Aberto").sum()))

    priority_order = {"Alta": 0, "Média": 1, "Baixa": 2}
    alerts = alerts.assign(_priority_rank=alerts["priority"].map(priority_order).fillna(3))

    for _, row in alerts.sort_values(["_priority_rank", "created_at"], ascending=[True, False]).iterrows():
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            cols[0].markdown(f"**{row['alert_type']}**  \n{row['name']} · {row['description']}")
            cols[0].caption(f"Categoria: {row['category']}")
            with cols[1]:
                badge(row["priority"], row["priority"])
            cols[2].write(row["status"])
            cols[2].caption(str(row["created_at"].date()))
            with cols[3]:
                render_open_patient_button(row["patient_id"], key=f"alert_{row['alert_id']}")
    if alerts.empty:
        st.info("Nenhum alerta para a categoria selecionada.")
