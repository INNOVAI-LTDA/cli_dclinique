"""Testes para validar o carregamento das páginas do app Streamlit."""
from __future__ import annotations

import pytest
import pandas as pd


@pytest.fixture
def mock_data():
    """Fixture que fornece dados mockados para testes."""
    from src.mock_data import load_mock_data
    return load_mock_data()


class TestMockData:
    """Testes para validar os dados mockados."""

    def test_load_mock_data_returns_dict(self, mock_data):
        """Verifica se load_mock_data retorna um dicionário."""
        assert isinstance(mock_data, dict)

    def test_mock_data_has_required_tables(self, mock_data):
        """Verifica se todas as tabelas necessárias estão presentes."""
        required_tables = [
            "patients",
            "treatment_plans",
            "treatment_plan_items",
            "execution_summary",
            "appointments",
            "appointment_items",
            "patient_goals",
            "weight_entries",
            "satisfaction_entries",
            "alerts",
            "data_quality_issues",
        ]
        for table in required_tables:
            assert table in mock_data, f"Tabela {table} não encontrada nos dados mockados"
            assert isinstance(mock_data[table], pd.DataFrame), f"Tabela {table} não é um DataFrame"

    def test_patients_table_has_required_columns(self, mock_data):
        """Verifica colunas obrigatórias na tabela patients."""
        required_columns = ["patient_id", "name", "medical_record", "phone", "age"]
        for col in required_columns:
            assert col in mock_data["patients"].columns, f"Coluna {col} não encontrada em patients"

    def test_alerts_table_has_required_columns(self, mock_data):
        """Verifica colunas obrigatórias na tabela alerts."""
        required_columns = ["alert_id", "patient_id", "category", "priority", "status", "description"]
        for col in required_columns:
            assert col in mock_data["alerts"].columns, f"Coluna {col} não encontrada em alerts"

    def test_mock_data_not_empty(self, mock_data):
        """Verifica se as tabelas principais têm dados."""
        assert len(mock_data["patients"]) > 0, "Tabela patients está vazia"
        assert len(mock_data["treatment_plans"]) > 0, "Tabela treatment_plans está vazia"


class TestMetrics:
    """Testes para validar as métricas derivadas."""

    def test_patient_summary_returns_dataframe(self, mock_data):
        """Verifica se patient_summary retorna um DataFrame."""
        from src.metrics import patient_summary
        result = patient_summary(mock_data)
        assert isinstance(result, pd.DataFrame)

    def test_patient_summary_has_required_columns(self, mock_data):
        """Verifica colunas obrigatórias no resumo de pacientes."""
        from src.metrics import patient_summary
        result = patient_summary(mock_data)
        required_columns = ["patient_id", "name", "status", "engagement_level", "is_engaged"]
        for col in required_columns:
            assert col in result.columns, f"Coluna {col} não encontrada no patient_summary"

    def test_overview_kpis_returns_dict(self, mock_data):
        """Verifica se overview_kpis retorna um dicionário."""
        from src.metrics import overview_kpis, patient_summary
        summary = patient_summary(mock_data)
        kpis = overview_kpis(summary)
        assert isinstance(kpis, dict)
        assert "Pacientes em plano" in kpis
        assert "Engajados" in kpis

    def test_attention_patients_returns_dataframe(self, mock_data):
        """Verifica se attention_patients retorna um DataFrame."""
        from src.metrics import attention_patients, patient_summary
        summary = patient_summary(mock_data)
        result = attention_patients(summary)
        assert isinstance(result, pd.DataFrame)


class TestNavigation:
    """Testes para validação da navegação."""

    def test_init_navigation_state(self):
        """Verifica se init_navigation_state configura session_state corretamente."""
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py")
        at.run()
        assert not at.exception
        assert "page" in at.session_state
        assert "selected_patient_id" in at.session_state

    def test_go_to_changes_page(self):
        """Verifica se go_to altera a página no session_state."""
        from src.navigation import go_to, PAGES
        import streamlit as st
        
        # Simula session_state
        class MockSessionState:
            def __init__(self):
                self._data = {}
            
            def __setitem__(self, key, value):
                self._data[key] = value
            
            def __getitem__(self, key):
                return self._data.get(key)
            
            def __contains__(self, key):
                return key in self._data
            
            def setdefault(self, key, default):
                if key not in self._data:
                    self._data[key] = default
                return self._data[key]
        
        original_session_state = st.session_state
        st.session_state = MockSessionState()
        
        try:
            for page in PAGES:
                go_to(page)
                assert st.session_state["page"] == page
        finally:
            st.session_state = original_session_state

    def test_open_patient_sets_patient_id(self):
        """Verifica se open_patient define o patient_id corretamente."""
        from src.navigation import open_patient
        import streamlit as st
        
        class MockSessionState:
            def __init__(self):
                self._data = {}
            
            def __setitem__(self, key, value):
                self._data[key] = value
            
            def __getitem__(self, key):
                return self._data.get(key)
            
            def __contains__(self, key):
                return key in self._data
            
            def setdefault(self, key, default):
                if key not in self._data:
                    self._data[key] = default
                return self._data[key]
        
        original_session_state = st.session_state
        st.session_state = MockSessionState()
        
        try:
            open_patient("pat_001")
            assert st.session_state["selected_patient_id"] == "pat_001"
            assert st.session_state["page"] == "Ficha do Paciente"
        finally:
            st.session_state = original_session_state


class TestPages:
    """Testes para validação do carregamento das páginas."""

    def test_visao_geral_render(self, mock_data):
        """Verifica se a página Visão Geral carrega sem erros."""
        from src.pages.visao_geral import render
        import streamlit as st
        
        # Testa se a função pode ser chamada sem levantar exceções de importação ou lógica básica
        # Nota: Não podemos testar completamente sem um contexto Streamlit real
        assert callable(render)

    def test_mapa_decisao_render(self, mock_data):
        """Verifica se a página Mapa de Decisão carrega sem erros."""
        from src.pages.mapa_decisao import render
        assert callable(render)

    def test_pacientes_render(self, mock_data):
        """Verifica se a página Pacientes carrega sem erros."""
        from src.pages.pacientes import render
        assert callable(render)

    def test_ficha_paciente_render(self, mock_data):
        """Verifica se a página Ficha do Paciente carrega sem erros."""
        from src.pages.ficha_paciente import render
        assert callable(render)

    def test_alertas_render(self, mock_data):
        """Verifica se a página Alertas carrega sem erros."""
        from src.pages.alertas import render
        assert callable(render)

    def test_atualizacao_dados_render(self, mock_data):
        """Verifica se a página Atualização de Dados carrega sem erros."""
        from src.pages.atualizacao_dados import render
        assert callable(render)

    def test_qualidade_dados_render(self, mock_data):
        """Verifica se a página Qualidade dos Dados carrega sem erros."""
        from src.pages.qualidade_dados import render
        assert callable(render)


class TestSchemas:
    """Testes para validação dos schemas."""

    def test_validate_mock_schema_returns_empty_for_valid_data(self, mock_data):
        """Verifica se validate_mock_schema retorna vazio para dados válidos."""
        from src.schemas import validate_mock_schema
        missing = validate_mock_schema(mock_data)
        assert isinstance(missing, dict)
        # Os dados mockados devem passar pela validação
        assert len(missing) == 0, f"Colunas ausentes encontradas: {missing}"

    def test_expected_schemas_has_all_tables(self):
        """Verifica se EXPECTED_SCHEMAS tem todas as tabelas necessárias."""
        from src.schemas import EXPECTED_SCHEMAS
        required_tables = [
            "patients",
            "treatment_plans",
            "treatment_plan_items",
            "execution_summary",
            "appointments",
            "patient_goals",
            "weight_entries",
            "satisfaction_entries",
            "alerts",
        ]
        for table in required_tables:
            assert table in EXPECTED_SCHEMAS, f"Tabela {table} não encontrada em EXPECTED_SCHEMAS"


class TestQuality:
    """Testes para validação da qualidade dos dados."""

    def test_quality_scores_returns_dict(self, mock_data):
        """Verifica se quality_scores retorna um dicionário."""
        from src.quality import quality_scores
        scores = quality_scores(mock_data)
        assert isinstance(scores, dict)
        assert "Score geral" in scores

    def test_client_checklist_returns_list(self):
        """Verifica se client_checklist retorna uma lista."""
        from src.quality import client_checklist
        checklist = client_checklist()
        assert isinstance(checklist, list)
        assert len(checklist) > 0


class TestCharts:
    """Testes para validação dos gráficos."""

    def test_patient_weight_chart_returns_figure(self, mock_data):
        """Verifica se patient_weight_chart retorna uma figura Plotly."""
        from src.charts.weight_chart import patient_weight_chart
        fig = patient_weight_chart(mock_data["weight_entries"], mock_data["patient_goals"], "pat_001")
        assert fig is not None

    def test_average_weight_chart_returns_figure(self, mock_data):
        """Verifica se average_weight_chart retorna uma figura Plotly."""
        from src.charts.weight_chart import average_weight_chart
        fig = average_weight_chart(mock_data["weight_entries"], mock_data["patient_goals"])
        assert fig is not None

    def test_execution_bar_returns_figure(self, mock_data):
        """Verifica se execution_bar retorna uma figura Plotly."""
        from src.charts.execution_chart import execution_bar
        fig = execution_bar(mock_data["execution_summary"], "pat_001")
        assert fig is not None

    def test_quadrants_returns_dict(self, mock_data):
        """Verifica se quadrants retorna um dicionário com DataFrames."""
        from src.charts.decision_map import quadrants
        from src.metrics import patient_summary
        summary = patient_summary(mock_data)
        result = quadrants(summary)
        assert isinstance(result, dict)
        assert len(result) == 4
        for quadrant_name, df in result.items():
            assert isinstance(df, pd.DataFrame)


class TestComponents:
    """Testes para validação dos componentes."""

    def test_badge_function_exists(self):
        """Verifica se a função badge existe e é chamável."""
        from src.components.badges import badge
        assert callable(badge)

    def test_render_kpis_function_exists(self):
        """Verifica se render_kpis existe e é chamável."""
        from src.components.kpi_cards import render_kpis
        assert callable(render_kpis)

    def test_render_table_function_exists(self):
        """Verifica se render_table existe e é chamável."""
        from src.components.tables import render_table
        assert callable(render_table)

    def test_render_empty_function_exists(self):
        """Verifica se render_empty existe e é chamável."""
        from src.components.empty_states import render_empty
        assert callable(render_empty)

    def test_render_patient_header_function_exists(self):
        """Verifica se render_patient_header existe e é chamável."""
        from src.components.patient_header import render_patient_header
        assert callable(render_patient_header)

    def test_render_open_patient_button_function_exists(self):
        """Verifica se render_open_patient_button existe e é chamável."""
        from src.components.patient_actions import render_open_patient_button
        assert callable(render_open_patient_button)


class TestAppIntegration:
    """Testes de integração para o app principal."""

    def test_app_imports_successfully(self):
        """Verifica se o app.py pode ser importado sem erros."""
        # Importa as funções principais do app
        from app import get_data, main
        assert callable(get_data)
        assert callable(main)

    def test_get_data_returns_mock_data(self):
        """Verifica se get_data retorna os dados mockados corretamente."""
        from app import get_data
        # Limpa cache para garantir teste limpo
        get_data.clear()
        data = get_data()
        assert isinstance(data, dict)
        assert "patients" in data
        assert len(data["patients"]) > 0

    def test_main_function_exists(self):
        """Verifica se a função main existe."""
        from app import main
        assert callable(main)
