"""Reusable filters for patient lists."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def patient_filters(summary: pd.DataFrame) -> pd.DataFrame:
    col1, col2, col3, col4 = st.columns(4)
    query = col1.text_input("Buscar por nome", "")
    statuses = col2.multiselect("Status", sorted(summary["status"].dropna().unique()))
    engagement = col3.multiselect("Engajamento", ["Alto", "Médio", "Baixo"])
    flags = col4.multiselect("Filtros rápidos", ["Renovação próxima", "Com alerta", "Sem peso atualizado"])
    filtered = summary.copy()
    if query:
        filtered = filtered[filtered["normalized_name"].str.contains(query.lower(), na=False)]
    if statuses:
        filtered = filtered[filtered["status"].isin(statuses)]
    if engagement:
        filtered = filtered[filtered["engagement_level"].isin(engagement)]
    if "Renovação próxima" in flags:
        filtered = filtered[filtered["renewal_soon"]]
    if "Com alerta" in flags:
        filtered = filtered[filtered["has_alert"]]
    if "Sem peso atualizado" in flags:
        filtered = filtered[filtered["without_recent_weight"]]
    return filtered
