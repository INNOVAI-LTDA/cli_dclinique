"""MAP Streamlit navigable shell."""
from __future__ import annotations

import importlib
from typing import Callable

import streamlit as st

from src.components.sidebar import render_sidebar
from src.navigation import init_navigation_state

# Page module is resolved lazily via `_route` so a cold start does not pay
# the import cost of plotly / pandas for every page (most users only ever
# land on a handful of them).
_PAGE_MODULES: dict[str, str] = {
    "Visão Geral": "src.pages.visao_geral",
    "Mapa de Decisão": "src.pages.mapa_decisao",
    "Pacientes": "src.pages.pacientes",
    "Ficha do Paciente": "src.pages.ficha_paciente",
    "Alertas": "src.pages.alertas",
    "Atualização de Dados": "src.pages.atualizacao_dados",
    "Qualidade dos Dados": "src.pages.qualidade_dados",
}

_route_cache: dict[str, Callable] = {}


def _route(page: str) -> Callable:
    """Resolve and memoise a page's `render` function on first use."""
    if page not in _route_cache:
        module = importlib.import_module(_PAGE_MODULES[page])
        _route_cache[page] = module.render
    return _route_cache[page]


@st.cache_data(show_spinner=False)
def get_data():
    # Deferred import keeps pandas out of the cold-start path of app.py
    # (Streamlit only imports the module body on the first call, after the
    # server is already serving the health endpoint).
    from src.mock_data import load_mock_data
    return load_mock_data()


def main() -> None:
    st.set_page_config(page_title="MAP Pacientes", page_icon="🩺", layout="wide")
    init_navigation_state()
    render_sidebar()
    data = get_data()
    page = st.session_state.get("page", "Visão Geral")
    _route(page)(data)


if __name__ == "__main__":
    main()
