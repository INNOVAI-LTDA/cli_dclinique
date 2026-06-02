"""Sidebar navigation component."""
from __future__ import annotations

import streamlit as st

from src.navigation import PAGES


def render_sidebar() -> None:
    with st.sidebar:
        st.title("MAP Pacientes")
        st.caption("Casca navegável com dados fictícios")
        current = st.session_state.get("page", PAGES[0])
        choice = st.radio("Navegação", PAGES, index=PAGES.index(current), key="sidebar_page")
        if choice != current:
            st.session_state["page"] = choice
            st.rerun()
        st.divider()
        st.info("Sem parser real, login, Supabase ou integrações nesta versão.")
