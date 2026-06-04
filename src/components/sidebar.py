"""Sidebar navigation component."""
from __future__ import annotations

import base64
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path
import re

import streamlit as st

from src.navigation import SIDEBAR_PAGES, PAGES


ICON_DIR = Path(__file__).resolve().parents[2] / "data" / "images" / "icones_Croquis_SVG"
PAGE_ICONS = {
    "Visão Geral": "01_visao_geral.svg",
    "Mapa de Decisão": "02_mapa_de_decisao.svg",
    "Pacientes": "03_pacientes.svg",
    "Alertas": "04_alertas.svg",
    "Atualização de Dados": "05_atualizacao_dados.svg",
    "Qualidade dos Dados": "06_qualidade_dados.svg",
}

# Precompiled once at import time – the regex is pure and reusable across calls.
_STROKE_RE = re.compile(r'stroke="[^"]*"')


@lru_cache(maxsize=None)
def _read_svg(icon_file: str) -> str:
    return (ICON_DIR / icon_file).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _svg_data_uri(icon_file: str, color: str) -> str:
    svg = _STROKE_RE.sub(f'stroke="{color}"', _read_svg(icon_file))
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _apply_sidebar_actions() -> None:
    params = st.query_params

    target_page = params.get("nav")
    # normalize if query param is a list
    if isinstance(target_page, (list, tuple)) and target_page:
        target_page = target_page[0]

    if target_page in PAGES:
        if target_page != st.session_state.get("page"):
            st.session_state["page"] = target_page
        # If a patient_id param is supplied, set it in session state so internal pages can use it
        patient_param = params.get("patient_id")
        if isinstance(patient_param, (list, tuple)) and patient_param:
            patient_param = patient_param[0]
        if patient_param:
            st.session_state["selected_patient_id"] = patient_param
        try:
            del params["nav"]
            if "patient_id" in params:
                del params["patient_id"]
        except Exception:
            pass
        st.rerun()

    refresh = params.get("refresh")
    if refresh == "1":
        st.cache_data.clear()
        st.session_state["last_update_at"] = datetime.now()
        del params["refresh"]
        st.rerun()


def _render_nav_html(current_page: str) -> str:
    rows = []
    for page in SIDEBAR_PAGES:
        active_class = " is-active" if page == current_page else ""
        disabled_attr = " disabled" if page == current_page else ""
        icon_color = "#2b63d9" if page == current_page else "#4b5563"
        icon_uri = _svg_data_uri(PAGE_ICONS[page], icon_color)
        row = (
            '<form class="map-nav-form" method="get" target="_self">'
            f'<input type="hidden" name="nav" value="{escape(page, quote=True)}" />'
            f'<button class="map-nav-item{active_class}" type="submit"{disabled_attr}>'
            f'<span class="map-nav-icon" aria-hidden="true"><img src="{icon_uri}" alt="" /></span>'
            f'<span class="map-nav-label">{escape(page)}</span>'
            "</button>"
            "</form>"
        )
        rows.append(row)
    return "".join(rows)


def _render_footer_html() -> str:
    icon_refresh_uri = _svg_data_uri("17_atualizar_agora.svg", "#2563eb")
    last_update = st.session_state.get("last_update_at")
    if not isinstance(last_update, datetime):
        last_update = datetime.now()
        st.session_state["last_update_at"] = last_update
    formatted = last_update.strftime("%d/%m/%Y %H:%M")
    return (
        '<div class="map-sidebar-footer">'
        '<p class="map-footer-title">Última atualização</p>'
        f'<p class="map-footer-value">{formatted}</p>'
        '<form class="map-refresh-form" method="get" target="_self">'
        '<input type="hidden" name="refresh" value="1" />'
        f'<button class="map-refresh-link" type="submit"><span aria-hidden="true"><img src="{icon_refresh_uri}" alt="" /></span>Atualizar agora</button>'
        "</form>"
        "</div>"
    )


def _sidebar_css() -> str:
    return """
        <style>
            section[data-testid="stSidebar"] {
                background: #f2f4f7;
            }

            section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {
                padding-top: 0.85rem;
                padding-left: 0.28rem;
                padding-right: 0.28rem;
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }

            .map-sidebar-title {
                margin: 0 0 0.95rem;
                font-size: 1.18rem;
                font-weight: 700;
                line-height: 1.24;
                letter-spacing: -0.01em;
                color: #1f2937;
            }

            .map-nav-list {
                display: flex;
                flex-direction: column;
                gap: 0.2rem;
            }

            .map-nav-form,
            .map-refresh-form {
                margin: 0;
            }

            .map-nav-item {
                align-items: center;
                background: transparent;
                border: none;
                border-radius: 0.5rem;
                color: #374151;
                display: flex;
                font-size: 0.95rem;
                font-weight: 600;
                gap: 0.56rem;
                justify-content: flex-start;
                min-height: 2rem;
                padding: 0.36rem 0.62rem;
                text-align: left;
                text-decoration: none !important;
                transition: background-color 120ms ease, color 120ms ease;
                width: 100%;
            }

            .map-nav-item:hover {
                background: #edf3ff;
                color: #1e40af;
                cursor: pointer;
            }

            .map-nav-item.is-active {
                background: #dee8f8;
                color: #2857b8;
                cursor: default;
                opacity: 1;
            }

            .map-nav-icon {
                align-items: center;
                display: inline-flex;
                flex-shrink: 0;
                justify-content: center;
                line-height: 0;
            }

            .map-nav-icon img,
            .map-refresh-link img {
                display: block;
                height: 17px;
                width: 17px;
            }

            .map-sidebar-footer {
                margin-top: auto;
                position: sticky;
                bottom: 0;
                padding: 1.15rem 0.08rem 0.3rem;
                background: linear-gradient(180deg, rgba(242,244,247,0) 0%, rgba(242,244,247,1) 22%);
            }

            .map-footer-title {
                margin: 0;
                color: #6b7280;
                font-size: 0.78rem;
                font-weight: 500;
            }

            .map-footer-value {
                margin: 0.15rem 0 0.55rem;
                color: #475569;
                font-size: 0.78rem;
            }

            .map-refresh-link {
                align-items: center;
                background: transparent;
                border: none;
                color: #2d66d2;
                display: inline-flex;
                font-size: 0.88rem;
                font-weight: 600;
                gap: 0.34rem;
                padding: 0;
                text-decoration: none !important;
            }

            .map-refresh-link:hover {
                cursor: pointer;
                text-decoration: underline;
            }
        </style>
        """


def render_sidebar() -> None:
    _apply_sidebar_actions()

    with st.sidebar:
        current = st.session_state.get("page", SIDEBAR_PAGES[0])
        selected = current if current in SIDEBAR_PAGES else SIDEBAR_PAGES[0]

        st.markdown(_sidebar_css(), unsafe_allow_html=True)
        st.markdown('<h2 class="map-sidebar-title">Acompanhamento de Pacientes</h2>', unsafe_allow_html=True)
        st.markdown(f'<nav class="map-nav-list">{_render_nav_html(selected)}</nav>', unsafe_allow_html=True)
        st.markdown(_render_footer_html(), unsafe_allow_html=True)
