"""Data quality page."""
from __future__ import annotations

import streamlit as st

from src.components.kpi_cards import render_kpis
from src.quality import client_checklist, quality_scores
from src.schemas import validate_mock_schema


def render(data):
    st.title("Qualidade dos Dados")
    st.caption("Indicadores mockados para discutir lacunas antes da integração real.")
    render_kpis(quality_scores(data), columns=5)

    missing = validate_mock_schema(data)
    if missing:
        st.error(f"Contrato mockado incompleto: {missing}")
    else:
        st.success("Contrato mockado completo para as tabelas esperadas.")

    st.subheader("Problemas identificados")
    st.dataframe(data["data_quality_issues"], width="stretch", hide_index=True)
    st.subheader("Checklist do que falta pedir ao cliente")
    for item in client_checklist():
        st.checkbox(item, value=False)
