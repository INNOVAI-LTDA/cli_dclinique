"""KPI rendering components."""
from __future__ import annotations

import streamlit as st


def render_kpis(kpis: dict[str, int | float], columns: int = 3) -> None:
    cols = st.columns(columns)
    for idx, (label, value) in enumerate(kpis.items()):
        cols[idx % columns].metric(label, value)
