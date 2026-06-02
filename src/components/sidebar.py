"""Sidebar navigation component."""
from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from pathlib import Path
import re
from urllib.parse import quote

import streamlit as st

from src.navigation import SIDEBAR_PAGES


ICON_DIR = Path(__file__).resolve().parents[2] / "data" / "images" / "icones_Croquis_SVG"
PAGE_ICONS = {
    "Visão Geral": "01_visao_geral.svg",
    "Mapa de Decisão": "02_mapa_de_decisao.svg",
    "Pacientes": "03_pacientes.svg",
    "Alertas": "04_alertas.svg",
    "Atualização de Dados": "05_atualizacao_dados.svg",
    "Qualidade dos Dados": "06_qualidade_dados.svg",
}


def _read_svg(icon_file: str) -> str:
    svg = (ICON_DIR / icon_file).read_text(encoding="utf-8")
    return svg


def _svg_data_uri(icon_file: str, color: str) -> str:
    svg = _read_svg(icon_file)
    svg = re.sub(r'stroke="[^"]*"', f'stroke="{color}"', svg)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _apply_sidebar_actions() -> None:
    params = st.query_params

    target_page = params.get("nav")
    if target_page in SIDEBAR_PAGES:
        if target_page != st.session_state.get("page"):
            st.session_state["page"] = target_page
        del params["nav"]
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
        icon_color = "#2b63d9" if page == current_page else "#4b5563"
        icon_uri = _svg_data_uri(PAGE_ICONS[page], icon_color)
        row = (
            f'<a class="map-nav-item{active_class}" href="?nav={quote(page)}">'
            f'<span class="map-nav-icon" aria-hidden="true"><img src="{icon_uri}" alt="" /></span>'
            f'<span class="map-nav-label">{escape(page)}</span>'
            "</a>"
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
        f'<a class="map-refresh-link" href="?refresh=1"><span aria-hidden="true"><img src="{icon_refresh_uri}" alt="" /></span>Atualizar agora</a>'
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

            .map-nav-item {
                display: flex;
                align-items: center;
                gap: 0.56rem;
                min-height: 2rem;
                padding: 0.36rem 0.62rem;
                border-radius: 0.5rem;
                text-decoration: none !important;
                color: #374151;
                font-size: 0.95rem;
                font-weight: 600;
                transition: background-color 120ms ease, color 120ms ease;
            }

            .map-nav-item:hover {
                background: #edf3ff;
                color: #1e40af;
            }

            .map-nav-item.is-active {
                background: #dee8f8;
                color: #2857b8;
            }

            .map-nav-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                line-height: 0;
                flex-shrink: 0;
            }

            .map-nav-icon img,
            .map-refresh-link img {
                width: 17px;
                height: 17px;
                display: block;
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
                display: inline-flex;
                align-items: center;
                gap: 0.34rem;
                color: #2d66d2;
                text-decoration: none !important;
                font-size: 0.88rem;
                font-weight: 600;
            }

            .map-refresh-link:hover {
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
