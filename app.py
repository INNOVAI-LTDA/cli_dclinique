"""MAP Streamlit navigable shell."""
from __future__ import annotations

import streamlit as st

from src.components.sidebar import render_sidebar
from src.mock_data import load_mock_data
from src.navigation import init_navigation_state
from src.pages import alertas, atualizacao_dados, ficha_paciente, mapa_decisao, pacientes, qualidade_dados, visao_geral


@st.cache_data(show_spinner=False)
def get_data():
    return load_mock_data()


def main() -> None:
    st.set_page_config(page_title="MAP Pacientes", page_icon="🩺", layout="wide")
    init_navigation_state()
    render_sidebar()
    data = get_data()
    page = st.session_state["page"]
    routes = {
        "Visão Geral": visao_geral.render,
        "Mapa de Decisão": mapa_decisao.render,
        "Pacientes": pacientes.render,
        "Ficha do Paciente": ficha_paciente.render,
        "Alertas": alertas.render,
        "Atualização de Dados": atualizacao_dados.render,
        "Qualidade dos Dados": qualidade_dados.render,
    }
    routes.get(page, visao_geral.render)(data)


if __name__ == "__main__":
    main()
