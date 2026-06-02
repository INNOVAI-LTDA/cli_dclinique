"""Overview page."""
from __future__ import annotations

import streamlit as st

from src.charts.weight_chart import average_weight_chart
from src.components.kpi_cards import render_kpis
from src.metrics import attention_patients, overview_kpis, patient_summary
from src.navigation import open_patient


def render(data):
    st.title("Visão Geral")
    st.caption("Painel executivo para validar indicadores, alertas e contrato de dados mockado.")
    summary = patient_summary(data)
    render_kpis(overview_kpis(summary), columns=3)
    st.subheader("Peso médio esperado vs realizado")
    st.plotly_chart(average_weight_chart(data["weight_entries"], data["patient_goals"]), width="stretch")
    st.subheader("Pacientes em atenção")
    attention = attention_patients(summary)
    if attention.empty:
        st.success("Nenhum paciente em atenção no mock atual.")
    for _, row in attention.iterrows():
        cols = st.columns([3, 1, 1, 1])
        cols[0].write(f"**{row['name']}**")
        cols[1].write(f"Engajamento: {row['engagement_level']}")
        cols[2].write(f"Alertas: {row['open_alerts']}")
        if cols[3].button("Abrir ficha", key=f"overview_{row['patient_id']}"):
            open_patient(row["patient_id"])
