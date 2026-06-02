"""Small visual badge helpers."""
from __future__ import annotations

import streamlit as st

COLORS = {"Alto": "#d1fae5", "Médio": "#fef3c7", "Baixo": "#fee2e2", "Alta": "#fee2e2", "Média": "#fef3c7", "Baixa": "#dbeafe"}


def badge(label: str, tone: str | None = None) -> None:
    color = COLORS.get(tone or label, "#e5e7eb")
    st.markdown(f"<span style='background:{color};border-radius:999px;padding:0.2rem 0.55rem;margin:0.1rem;display:inline-block'>{label}</span>", unsafe_allow_html=True)


def patient_chip(name: str) -> None:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    st.markdown(f"<span title='{name}' style='background:#eef2ff;border:1px solid #c7d2fe;border-radius:999px;padding:0.35rem 0.55rem;margin:0.15rem;display:inline-block'><b>{initials}</b> {name}</span>", unsafe_allow_html=True)
