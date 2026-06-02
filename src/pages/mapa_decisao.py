"""Decision map page."""
from __future__ import annotations

import streamlit as st

from src.charts.decision_map import quadrants
from src.components.badges import patient_chip
from src.metrics import patient_summary
from src.navigation import open_patient


def _quadrant(title: str, df) -> None:
    st.markdown(f"### {title}")
    st.caption(f"{len(df)} paciente(s)")
    if df.empty:
        st.info("Sem pacientes neste quadrante.")
    for _, row in df.iterrows():
        patient_chip(row["name"])
        if st.button("Abrir ficha", key=f"map_{title}_{row['patient_id']}"):
            open_patient(row["patient_id"])


def render(data):
    st.title("Mapa de Decisão")
    st.caption("Matriz 2x2 baseada em engajamento mockado e satisfação declarada.")
    groups = quadrants(patient_summary(data))
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
