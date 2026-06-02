"""Demonstrative data update page."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render(data):
    st.title("Atualização de Dados")
    st.warning("Tela demonstrativa: nenhum arquivo é processado e não há parser real de PDF/Excel nesta versão.")
    source_type = st.selectbox("Tipo de fonte", ["PDFs de plano", "Relatório de frequência", "Relatório de agendamentos", "Dados manuais"])
    st.file_uploader("Upload simulado", accept_multiple_files=True, help="Apenas demonstra o fluxo visual; os arquivos não serão lidos.")
    preview = pd.DataFrame(
        [
            {"arquivo": "plano_kelly.pdf", "tipo": "PDFs de plano", "status": "Aguardando processamento", "linhas_previstas": 1},
            {"arquivo": "frequencia_maio.xlsx", "tipo": "Relatório de frequência", "status": "Pronto para validação", "linhas_previstas": 48},
            {"arquivo": "agendamentos.xlsx", "tipo": "Relatório de agendamentos", "status": "Prévia fictícia", "linhas_previstas": 16},
            {"arquivo": "pesos_manuais.xlsx", "tipo": "Dados manuais", "status": "Requer conferência", "linhas_previstas": 8},
        ]
    )
    st.subheader(f"Preview fictício — {source_type}")
    st.dataframe(preview[preview["tipo"] == source_type], hide_index=True, width="stretch")
    if st.button("Processar dados", type="primary"):
        st.toast("Processamento não implementado nesta casca navegável.")
        st.info("Aqui futuramente entrarão validações, parsers e persistência em banco.")
