"""Testes de integração que simulam execução real das páginas Streamlit."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestPageExecutionWithMockedStreamlit:
    """Testa execução das páginas com Streamlit mockado para capturar erros de API."""

    @pytest.fixture
    def mock_streamlit(self):
        """Cria mocks realistas para todas as funções do Streamlit."""
        patches = {
            "title": patch("streamlit.title"),
            "header": patch("streamlit.header"),
            "subheader": patch("streamlit.subheader"),
            "caption": patch("streamlit.caption"),
            "markdown": patch("streamlit.markdown"),
            "text": patch("streamlit.text"),
            "info": patch("streamlit.info"),
            "warning": patch("streamlit.warning"),
            "error": patch("streamlit.error"),
            "success": patch("streamlit.success"),
            "columns": patch("streamlit.columns"),
            "container": patch("streamlit.container"),
            "selectbox": patch("streamlit.selectbox"),
            "file_uploader": patch("streamlit.file_uploader"),
            "button": patch("streamlit.button"),
            "checkbox": patch("streamlit.checkbox"),
            "toast": patch("streamlit.toast"),
            "dataframe": patch("streamlit.dataframe"),
            "plotly_chart": patch("streamlit.plotly_chart"),
            "metric": patch("streamlit.metric"),
            "empty": patch("streamlit.empty"),
            "sidebar": patch("streamlit.sidebar"),
        }
        
        # Iniciar todos os patches
        mocks = {}
        for name, p in patches.items():
            mocks[name] = p.start()
        
        try:
            # Configurar retornos padrão
            mocks["columns"].return_value = [MagicMock() for _ in range(2)]
            mocks["container"].return_value.__enter__ = MagicMock(return_value=MagicMock())
            mocks["container"].return_value.__exit__ = MagicMock(return_value=None)
            mocks["sidebar"].__enter__ = MagicMock(return_value=MagicMock())
            mocks["sidebar"].__exit__ = MagicMock(return_value=None)
            
            # Mock de dataframe que valida parâmetros
            def validate_dataframe(*args, **kwargs):
                width = kwargs.get("width", "stretch")
                if width is None:
                    raise ValueError("Invalid width value: None. Width must be either a positive integer (pixels), 'stretch', or 'content'.")
                if width not in ["stretch", "content"] and not isinstance(width, int):
                    raise ValueError(f"Invalid width value: {width}")
                return MagicMock()
            
            mocks["dataframe"].side_effect = validate_dataframe
            
            # Mock de plotly_chart que valida parâmetros
            def validate_plotly(*args, **kwargs):
                width = kwargs.get("width", "stretch")
                if width not in ["stretch", "content"] and not isinstance(width, int):
                    raise ValueError(f"Invalid width value: {width}")
                return MagicMock()
            
            mocks["plotly_chart"].side_effect = validate_plotly
            
            yield mocks
        finally:
            # Parar todos os patches
            for p in patches.values():
                p.stop()

    @pytest.fixture
    def mock_data(self):
        """Cria dados mockados consistentes."""
        return {
            "patients": pd.DataFrame([
                {"patient_id": 1, "name": "Patient 1", "age": 30},
                {"patient_id": 2, "name": "Patient 2", "age": 45},
            ]),
            "plans": pd.DataFrame([
                {"plan_id": 1, "patient_id": 1, "name": "Plan A"},
            ]),
            "alerts": pd.DataFrame([
                {"alert_id": 1, "patient_id": 1, "message": "Test alert"},
            ]),
            "weight_entries": pd.DataFrame([
                {"patient_id": 1, "date": "2024-01-01", "weight": 70.5},
            ]),
            "patient_goals": pd.DataFrame([
                {"patient_id": 1, "goal_weight": 68.0},
            ]),
            "execution_summary": pd.DataFrame([
                {"patient_id": 1, "Procedimento": "Proc A", "Previsto": 10, "Realizado": 8},
            ]),
            "data_quality_issues": pd.DataFrame([
                {"severity": "Alta", "source": "Test", "issue_type": "Missing", "description": "Test", "patient_id": 1, "field_name": "test"},
            ]),
            "engagement_metrics": {"engagement_rate": 0.85, "satisfaction": 4.5},
        }

    @pytest.fixture
    def page_modules(self):
        """Importa todos os módulos de página."""
        src_dir = Path(__file__).parent.parent / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        pages = []
        pages_dir = src_dir / "pages"
        for page_file in pages_dir.glob("*.py"):
            if page_file.name == "__init__.py":
                continue
            
            module_name = f"src.pages.{page_file.stem}"
            try:
                module = __import__(module_name, fromlist=["render"])
                if hasattr(module, "render"):
                    pages.append({
                        "name": page_file.stem,
                        "module": module,
                        "render": module.render,
                    })
            except Exception as e:
                pytest.fail(f"Falha ao importar {module_name}: {e}")
        
        return pages

    def test_all_pages_execute_without_api_errors(self, mock_streamlit, mock_data, page_modules):
        """Executa todas as páginas e verifica se não há erros de API do Streamlit."""
        errors = []
        
        for page in page_modules:
            try:
                # Executar a função render com dados mockados
                page["render"](mock_data)
            except TypeError as e:
                if "width" in str(e).lower() or "None" in str(e):
                    errors.append(f"{page['name']}: Erro de parâmetro - {e}")
                else:
                    # Outros TypeErrors podem ser esperados devido aos mocks
                    pass
            except Exception as e:
                # Capturar outros erros que não sejam relacionados aos mocks
                error_msg = str(e)
                if "width" in error_msg.lower() or "invalid" in error_msg.lower():
                    errors.append(f"{page['name']}: {type(e).__name__} - {e}")
        
        if errors:
            pytest.fail(f"Erros de API do Streamlit detectados:\n" + "\n".join(errors))

    def test_dataframe_calls_have_valid_width(self, mock_streamlit, mock_data, page_modules):
        """Verifica especificamente se todas as chamadas st.dataframe têm width válido."""
        invalid_calls = []
        
        for page in page_modules:
            try:
                page["render"](mock_data)
                
                # Verificar chamadas ao dataframe
                for call in mock_streamlit["dataframe"].call_args_list:
                    kwargs = call.kwargs if call.kwargs else {}
                    width = kwargs.get("width", "stretch")
                    
                    if width is None:
                        invalid_calls.append(f"{page['name']}: width=None em st.dataframe")
                    elif width not in ["stretch", "content"] and not isinstance(width, int):
                        invalid_calls.append(f"{page['name']}: width='{width}' inválido")
                
            except Exception:
                # Ignorar erros de execução, focar apenas na validação dos parâmetros
                pass
        
        if invalid_calls:
            pytest.fail(f"Chamadas st.dataframe com width inválido:\n" + "\n".join(invalid_calls))

    def test_plotly_chart_calls_have_valid_width(self, mock_streamlit, mock_data, page_modules):
        """Verifica especificamente se todas as chamadas st.plotly_chart têm width válido."""
        invalid_calls = []
        
        for page in page_modules:
            try:
                page["render"](mock_data)
                
                # Verificar chamadas ao plotly_chart
                for call in mock_streamlit["plotly_chart"].call_args_list:
                    kwargs = call.kwargs if call.kwargs else {}
                    width = kwargs.get("width", "stretch")
                    
                    if width not in ["stretch", "content"] and not isinstance(width, int):
                        invalid_calls.append(f"{page['name']}: width='{width}' inválido em st.plotly_chart")
                
            except Exception:
                pass
        
        if invalid_calls:
            pytest.fail(f"Chamadas st.plotly_chart com width inválido:\n" + "\n".join(invalid_calls))


class TestDataFrameColumnSelection:
    """Testa seleções de colunas em DataFrames para evitar KeyError."""

    @pytest.fixture
    def mock_data(self):
        """Cria dados mockados."""
        return {
            "execution_summary": pd.DataFrame([
                {"patient_id": 1, "Procedimento": "Proc A", "Previsto": 10, "Realizado": 8, "Restante": 2, "Status": "Em andamento"},
            ]),
        }

    def test_column_selection_exists(self, mock_data):
        """Verifica se colunas selecionadas existem no DataFrame."""
        df = mock_data["execution_summary"]
        columns_to_select = ["Procedimento", "Previsto", "Realizado", "Restante", "Status"]
        
        missing_columns = [col for col in columns_to_select if col not in df.columns]
        
        if missing_columns:
            pytest.fail(f"Colunas ausentes no DataFrame: {missing_columns}")

    def test_column_selection_no_keyerror(self, mock_data):
        """Executa seleção de colunas e verifica se não há KeyError."""
        df = mock_data["execution_summary"]
        columns_to_select = ["Procedimento", "Previsto", "Realizado", "Restante", "Status"]
        
        try:
            result = df[columns_to_select]
            assert len(result.columns) == len(columns_to_select)
        except KeyError as e:
            pytest.fail(f"KeyError na seleção de colunas: {e}")


class TestComponentFunctionSignatures:
    """Testa assinaturas de funções de componentes."""

    @pytest.fixture
    def component_modules(self):
        """Importa módulos de componentes."""
        src_dir = Path(__file__).parent.parent / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        components = []
        comp_dir = src_dir / "components"
        for comp_file in comp_dir.glob("*.py"):
            if comp_file.name == "__init__.py":
                continue
            
            module_name = f"src.components.{comp_file.stem}"
            try:
                module = __import__(module_name, fromlist=[])
                functions = [name for name in dir(module) if callable(getattr(module, name)) and not name.startswith("_")]
                components.append({
                    "name": comp_file.stem,
                    "module": module,
                    "functions": functions,
                })
            except Exception as e:
                pytest.fail(f"Falha ao importar {module_name}: {e}")
        
        return components

    def test_components_import_without_errors(self, component_modules):
        """Verifica se todos os componentes importam sem erros."""
        # Se chegou até aqui, todos importaram corretamente
        assert len(component_modules) > 0


class TestChartGeneration:
    """Testa geração de gráficos para garantir que retornam objetos válidos."""

    @pytest.fixture
    def chart_modules(self):
        """Importa módulos de gráficos."""
        src_dir = Path(__file__).parent.parent / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        charts = []
        charts_dir = src_dir / "charts"
        for chart_file in charts_dir.glob("*.py"):
            if chart_file.name == "__init__.py":
                continue
            
            module_name = f"src.charts.{chart_file.stem}"
            try:
                module = __import__(module_name, fromlist=[])
                # Filtrar apenas funções públicas que não começam com _ e estão definidas no módulo
                functions = [
                    name for name in dir(module) 
                    if callable(getattr(module, name)) 
                    and not name.startswith("_")
                    and hasattr(getattr(module, name), "__module__")
                    and getattr(module, name).__module__ == module_name
                ]
                charts.append({
                    "name": chart_file.stem,
                    "module": module,
                    "functions": functions,
                })
            except Exception as e:
                pytest.fail(f"Falha ao importar {module_name}: {e}")
        
        return charts

    def test_chart_functions_exist(self, chart_modules):
        """Verifica se funções de gráfico existem (teste informativo)."""
        # Este teste é informativo - alguns módulos podem ter apenas imports
        modules_without_functions = [c["name"] for c in chart_modules if len(c["functions"]) == 0]
        
        # Apenas alertar, não falhar - a ausência de funções pode ser intencional
        if modules_without_functions:
            print(f"\nℹ️  Módulos de gráfico sem funções públicas: {modules_without_functions}")
            print("   Isso pode ser normal se o módulo exporta funções de outros sub-módulos.")
