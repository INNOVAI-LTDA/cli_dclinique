"""Small visual badge helpers."""
from __future__ import annotations

import html
import re

import streamlit as st

COLORS = {
    "Alto": "#d1fae5",
    "Médio": "#fef3c7",
    "Baixo": "#fee2e2",
    "Alta": "#fee2e2",
    "Média": "#fef3c7",
    "Baixa": "#dbeafe",
    "Ativa": "#dcfce7",
    "Ativo": "#dcfce7",
    "Pausado": "#fef3c7",
    "Encerrado": "#e5e7eb",
    "Em andamento": "#dbeafe",
    "Pendente": "#fef3c7",
    "Concluído": "#dcfce7",
    "Concluido": "#dcfce7",
    "Não iniciado": "#e5e7eb",
    "Nao iniciado": "#e5e7eb",
    "Finalizado": "#dcfce7",
    "Aguardando": "#fef3c7",
}
SAFE_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def badge(label: str, tone: str | None = None) -> None:
    color = COLORS.get(tone or label, "#e5e7eb")
    if not SAFE_COLOR_RE.fullmatch(color):
        color = "#e5e7eb"
    safe_label = html.escape(label)
    st.markdown(
        f"<span style='background:{color};border-radius:999px;padding:0.2rem 0.55rem;margin:0.1rem;display:inline-block'>{safe_label}</span>",
        unsafe_allow_html=True,
    )


def patient_chip(name: str) -> None:
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    safe_name = html.escape(name)
    safe_initials = html.escape(initials)
    st.markdown(
        f"<span title='{safe_name}' style='background:#eef2ff;border:1px solid #c7d2fe;border-radius:999px;padding:0.35rem 0.55rem;margin:0.15rem;display:inline-block'><b>{safe_initials}</b> {safe_name}</span>",
        unsafe_allow_html=True,
    )
