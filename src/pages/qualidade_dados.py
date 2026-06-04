"""Data quality page."""
from __future__ import annotations

import streamlit as st

from src.components.kpi_cards import render_kpis
from src.quality import client_checklist, quality_scores
from src.schemas import validate_mock_schema


def render(data):
    # Plotly is heavy; imported only when this page is actually rendered.
    import plotly.express as px

    st.title("Qualidade dos Dados")
    st.caption("Indicadores mockados para discutir lacunas antes da integração real.")
    render_kpis(quality_scores(data), columns=5)

    missing = validate_mock_schema(data)
    if missing:
        st.error(f"Contrato mockado incompleto: {missing}")
    else:
        st.success("Contrato mockado completo para as tabelas esperadas.")

    issues = data["data_quality_issues"].copy()
    col_a, col_b = st.columns(2)
    with col_a:
        severity = issues.groupby("severity", as_index=False).size().rename(columns={"size": "quantidade"})
        if not severity.empty:
            fig_severity = px.bar(severity, x="severity", y="quantidade", color="severity", title="Problemas por severidade")
            fig_severity.update_layout(margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
            st.plotly_chart(fig_severity, width="stretch")
    with col_b:
        source = issues.groupby("source", as_index=False).size().rename(columns={"size": "quantidade"})
        if not source.empty:
            fig_source = px.bar(source, x="quantidade", y="source", orientation="h", title="Problemas por fonte")
            fig_source.update_layout(margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_source, width="stretch")

    st.subheader("Lacunas relevantes")
    if missing:
        for table, columns in missing.items():
            st.warning(f"{table}: colunas ausentes -> {', '.join(columns)}")
    else:
        st.info("Sem lacunas de schema no mock atual.")

    unresolved = issues[issues["severity"].isin(["Alta", "Média"])].copy()
    if unresolved.empty:
        st.success("Sem lacunas de severidade alta ou média no conjunto atual.")
    else:
        st.dataframe(
            unresolved[["severity", "source", "issue_type", "description", "patient_id", "field_name"]],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Problemas identificados")
    st.dataframe(issues, width="stretch", hide_index=True)
    st.subheader("Checklist do que falta pedir ao cliente")
    for item in client_checklist():
        st.checkbox(item, value=False)
