"""Overview page."""
from __future__ import annotations

import streamlit as st

from src.charts.weight_chart import average_weight_chart
from src.components.kpi_cards import render_kpis
from src.components.patient_actions import render_open_patient_button
from src.metrics import attention_patients, overview_kpis, patient_summary


def render(data):
    st.title("Visão Geral")
    st.caption("Painel executivo para validar indicadores, alertas e contrato de dados mockado.")

    summary = patient_summary(data)
    st.markdown("### Indicadores principais")
    render_kpis(overview_kpis(summary), columns=3)

    col_chart, col_context = st.columns([2, 1])
    with col_chart:
        st.subheader("Peso médio esperado vs realizado")
        st.plotly_chart(average_weight_chart(data["weight_entries"], data["patient_goals"]), width="stretch")
    with col_context:
        total = len(summary)
        engaged = int(summary["is_engaged"].sum())
        with st.container(border=True):
            st.markdown("#### Leitura rápida")
            st.write(f"Pacientes em plano: **{total}**")
            st.write(f"Engajados: **{engaged}**")
            st.write(f"Taxa de engajamento: **{(engaged / total * 100) if total else 0:.0f}%**")
            st.write("Acompanhe abaixo os pacientes com maior necessidade de atenção.")

    st.subheader("Pacientes em atenção")
    attention = attention_patients(summary)
    if attention.empty:
        st.success("Nenhum paciente em atenção no mock atual.")
        return

    attention = attention.sort_values(["open_alerts", "days_to_renewal", "name"], ascending=[False, True, True])
    for _, row in attention.iterrows():
        with st.container(border=True):
            cols = st.columns([3, 1.2, 1.2, 1.2, 1])
            cols[0].write(f"**{row['name']}**")
            cols[0].caption(f"Objetivo: {row['main_goal']}")
            cols[1].metric("Engajamento", row["engagement_level"])
            cols[2].metric("Alertas abertos", int(row["open_alerts"]))
            days = int(row["days_to_renewal"]) if row["days_to_renewal"] == row["days_to_renewal"] else -1
            cols[3].metric("Dias para fim", "--" if days < 0 else days)
            with cols[4]:
                render_open_patient_button(row["patient_id"], key=f"overview_{row['patient_id']}")
