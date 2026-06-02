"""Decision map page."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.charts.decision_map import quadrants
from src.components.badges import patient_chip
from src.components.patient_actions import render_open_patient_button
from src.metrics import patient_summary


def _quadrant(title: str, df) -> None:
    st.markdown(f"### {title}")
    st.caption(f"{len(df)} paciente(s)")
    if df.empty:
        st.info("Sem pacientes neste quadrante.")
    for _, row in df.iterrows():
        with st.container(border=True):
            patient_chip(row["name"])
            st.caption(
                f"Engajamento: {row['engagement_rate'] * 100:.0f}% | Satisfacao: {int(row['score']) if row['score'] == row['score'] else 0}/10 | Alertas: {int(row['open_alerts'])}"
            )
            render_open_patient_button(row["patient_id"], key=f"map_{title}_{row['patient_id']}")


def render(data):
    st.title("Mapa de Decisão")
    st.caption("Matriz 2x2 baseada em engajamento mockado e satisfação declarada.")

    summary = patient_summary(data).copy()
    summary["quadrante"] = "Não engajado + Não satisfeito"
    summary.loc[summary["is_engaged"] & summary["is_satisfied"].fillna(False), "quadrante"] = "Engajado + Satisfeito"
    summary.loc[summary["is_engaged"] & ~summary["is_satisfied"].fillna(False), "quadrante"] = "Engajado + Não satisfeito"
    summary.loc[~summary["is_engaged"] & summary["is_satisfied"].fillna(False), "quadrante"] = "Não engajado + Satisfeito"

    fig = px.scatter(
        summary,
        x=summary["engagement_rate"] * 100,
        y="score",
        color="quadrante",
        hover_name="name",
        hover_data={"engagement_rate": ":.2f", "open_alerts": True, "main_goal": True},
        labels={"x": "Engajamento (%)", "score": "Satisfação (0-10)", "quadrante": "Quadrante"},
        height=420,
    )
    fig.add_vline(x=70, line_dash="dash", line_color="#64748b")
    fig.add_hline(y=7, line_dash="dash", line_color="#64748b")
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")

    groups = quadrants(summary)
    row1 = st.columns(2)
    with row1[0]:
        _quadrant("Engajado + Satisfeito", groups["Engajado + Satisfeito"])
    with row1[1]:
        _quadrant("Engajado + Não satisfeito", groups["Engajado + Não satisfeito"])
    row2 = st.columns(2)
    with row2[0]:
        _quadrant("Não engajado + Satisfeito", groups["Não engajado + Satisfeito"])
    with row2[1]:
        _quadrant("Não engajado + Não satisfeito", groups["Não engajado + Não satisfeito"])
