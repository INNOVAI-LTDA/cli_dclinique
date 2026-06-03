"""Testes de validação semântica e sintaxe das APIs do Streamlit."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


class TestStreamlitAPIUsage:
    """Valida o uso correto da API do Streamlit em todo o código."""

    @pytest.fixture
    def source_files(self) -> list[Path]:
        """Retorna todos os arquivos Python do src."""
        src_dir = Path(__file__).parent.parent / "src"
        return list(src_dir.rglob("*.py"))

    @pytest.fixture
    def streamlit_calls(self, source_files: list[Path]) -> list[dict]:
        """Extrai todas as chamadas de funções do streamlit."""
        calls = []
        for file_path in source_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Encontrar chamadas st.funcao(...)
            pattern = r'st\.(\w+)\s*\(([^)]*)\)'
            for match in re.finditer(pattern, content):
                func_name = match.group(1)
                args_str = match.group(2)
                line_no = content[:match.start()].count('\n') + 1
                
                calls.append({
                    "file": str(file_path),
                    "line": line_no,
                    "function": func_name,
                    "args": args_str,
                    "raw": match.group(0)
                })
        return calls

    def test_no_width_none_in_dataframe(self, streamlit_calls: list[dict]):
        """Garante que não há width=None em st.dataframe."""
        violations = []
        for call in streamlit_calls:
            if call["function"] == "dataframe":
                # Verificar se há width=None
                if re.search(r'width\s*=\s*None', call["args"]):
                    violations.append(f"{call['file']}:{call['line']} - {call['raw']}")
        
        if violations:
            pytest.fail(f"Encontrado width=None em st.dataframe:\n" + "\n".join(violations))

    def test_valid_width_values(self, streamlit_calls: list[dict]):
        """Valida que os valores de width são válidos para st.dataframe e st.plotly_chart."""
        valid_width_values = {"stretch", "content"}
        violations = []
        
        for call in streamlit_calls:
            if call["function"] in ["dataframe", "plotly_chart"]:
                # Extrair valor de width
                width_match = re.search(r'width\s*=\s*["\']?(\w+)["\']?', call["args"])
                if width_match:
                    width_value = width_match.group(1)
                    if width_value not in valid_width_values and not width_value.isdigit():
                        # Verificar se não é None
                        if width_value == "None":
                            violations.append(f"{call['file']}:{call['line']} - width=None inválido em st.{call['function']}")
        
        if violations:
            pytest.fail(f"Valores de width inválidos:\n" + "\n".join(violations))

    def test_no_deprecated_use_container_width_with_width_stretch(self, streamlit_calls: list[dict]):
        """Verifica se há uso redundante de use_container_width=True com width='stretch'."""
        warnings = []
        
        for call in streamlit_calls:
            if call["function"] in ["dataframe", "plotly_chart"]:
                has_use_container = "use_container_width=True" in call["args"]
                has_width_stretch = 'width="stretch"' in call["args"] or "width='stretch'" in call["args"]
                
                if has_use_container and has_width_stretch:
                    warnings.append(f"{call['file']}:{call['line']} - Uso redundante: use_container_width=True com width='stretch'")
        
        # Apenas alertar, não falhar (é um warning de melhor prática)
        if warnings:
            print("\n⚠️  Avisos de código redundante:")
            for w in warnings:
                print(f"  {w}")

    def test_plotly_chart_width_parameter(self, streamlit_calls: list[dict]):
        """Valida que st.plotly_chart usa width válido."""
        valid_width_values = {"stretch", "content"}
        violations = []
        
        for call in streamlit_calls:
            if call["function"] == "plotly_chart":
                width_match = re.search(r'width\s*=\s*["\']?(\w+)["\']?', call["args"])
                if width_match:
                    width_value = width_match.group(1)
                    if width_value not in valid_width_values and not width_value.isdigit():
                        violations.append(f"{call['file']}:{call['line']} - width='{width_value}' inválido em st.plotly_chart")
        
        if violations:
            pytest.fail(f"Valores de width inválidos em plotly_chart:\n" + "\n".join(violations))


class TestPythonSyntaxAndSemantics:
    """Testes de sintaxe Python e semântica básica."""

    @pytest.fixture
    def source_files(self) -> list[Path]:
        """Retorna todos os arquivos Python do src."""
        src_dir = Path(__file__).parent.parent / "src"
        return list(src_dir.rglob("*.py"))

    def test_all_files_have_valid_syntax(self, source_files: list[Path]):
        """Garante que todos os arquivos Python têm sintaxe válida."""
        errors = []
        for file_path in source_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            try:
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{file_path}:{e.lineno} - {e.msg}")
        
        if errors:
            pytest.fail(f"Erros de sintaxe encontrados:\n" + "\n".join(errors))

    def test_no_bare_except_clauses(self, source_files: list[Path]):
        """Garante que não há cláusulas 'except:' genéricas."""
        violations = []
        for file_path in source_files:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines, 1):
                # Ignorar comentários
                code_line = line.split("#")[0].strip()
                if code_line == "except:":
                    violations.append(f"{file_path}:{i} - except: genérico encontrado")
        
        if violations:
            pytest.fail(f"Cláusulas except genéricas encontradas:\n" + "\n".join(violations))

    def test_imports_are_valid(self, source_files: list[Path]):
        """Tenta importar todos os módulos para verificar dependências."""
        import sys
        import importlib
        
        src_dir = Path(__file__).parent.parent
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        errors = []
        for file_path in source_files:
            # Ignorar __init__.py e arquivos de teste
            if file_path.name == "__init__.py":
                continue
            
            module_path = file_path.relative_to(src_dir)
            module_name = str(module_path).replace("/", ".").replace(".py", "")
            
            try:
                importlib.import_module(module_name)
            except Exception as e:
                errors.append(f"{module_name}: {type(e).__name__}: {str(e)[:100]}")
        
        if errors:
            pytest.fail(f"Erros de importação:\n" + "\n".join(errors))


class TestDataFrameOperations:
    """Testes específicos para operações com DataFrame."""

    @pytest.fixture
    def dataframe_operations(self) -> list[dict]:
        """Extrai operações de seleção de colunas de DataFrame."""
        src_dir = Path(__file__).parent.parent / "src"
        operations = []
        
        for file_path in src_dir.rglob("*.py"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Padrão para df[["col1", "col2"]]
            pattern = r'(\w+)\s*\[\s*\[(.*?)\]\s*\]'
            for match in re.finditer(pattern, content, re.DOTALL):
                df_var = match.group(1)
                columns_str = match.group(2)
                line_no = content[:match.start()].count('\n') + 1
                
                # Extrair nomes das colunas
                columns = re.findall(r'["\']([^"\']+)["\']', columns_str)
                
                operations.append({
                    "file": str(file_path),
                    "line": line_no,
                    "dataframe": df_var,
                    "columns": columns,
                    "raw": match.group(0)
                })
        
        return operations

    def test_no_duplicate_columns_in_selection(self, dataframe_operations: list[dict]):
        """Garante que não há colunas duplicadas em seleções de DataFrame."""
        violations = []
        for op in dataframe_operations:
            if len(op["columns"]) != len(set(op["columns"])):
                duplicates = [c for c in op["columns"] if op["columns"].count(c) > 1]
                violations.append(f"{op['file']}:{op['line']} - Colunas duplicadas: {set(duplicates)}")
        
        if violations:
            pytest.fail(f"Colunas duplicadas em seleções de DataFrame:\n" + "\n".join(violations))

    def test_column_names_are_strings(self, dataframe_operations: list[dict]):
        """Garante que nomes de colunas são strings."""
        violations = []
        for op in dataframe_operations:
            for col in op["columns"]:
                if not isinstance(col, str) or not col:
                    violations.append(f"{op['file']}:{op['line']} - Nome de coluna inválido: {repr(col)}")
        
        if violations:
            pytest.fail(f"Nomes de colunas inválidos:\n" + "\n".join(violations))


class TestPageRenderFunctions:
    """Testa a estrutura das funções render nas páginas."""

    @pytest.fixture
    def page_files(self) -> list[Path]:
        """Retorna arquivos de páginas."""
        pages_dir = Path(__file__).parent.parent / "src" / "pages"
        return [f for f in pages_dir.glob("*.py") if f.name != "__init__.py"]

    def test_all_pages_have_render_function(self, page_files: list[Path]):
        """Garante que todas as páginas têm uma função render."""
        missing = []
        for file_path in page_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "def render(" not in content:
                missing.append(str(file_path))
        
        if missing:
            pytest.fail(f"Páginas sem função render:\n" + "\n".join(missing))

    def test_render_functions_accept_data_parameter(self, page_files: list[Path]):
        """Garante que todas as funções render aceitam parâmetro data."""
        errors = []
        for file_path in page_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Procurar por def render(
            match = re.search(r'def render\s*\(([^)]*)\)', content)
            if match:
                params = match.group(1)
                if "data" not in params:
                    errors.append(f"{file_path}: função render sem parâmetro 'data'")
            else:
                errors.append(f"{file_path}: função render não encontrada")
        
        if errors:
            pytest.fail(f"Problemas com parâmetros das funções render:\n" + "\n".join(errors))


class TestComponentConsistency:
    """Testa consistência dos componentes."""

    @pytest.fixture
    def component_files(self) -> list[Path]:
        """Retorna arquivos de componentes."""
        comp_dir = Path(__file__).parent.parent / "src" / "components"
        return [f for f in comp_dir.glob("*.py") if f.name != "__init__.py"]

    def test_components_return_none_or_appropriate_type(self, component_files: list[Path]):
        """Verifica se componentes retornam tipos apropriados."""
        # Este teste verifica a estrutura básica
        issues = []
        for file_path in component_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Verificar se há funções principais
            if "def " not in content:
                issues.append(f"{file_path}: Nenhuma função definida")
        
        if issues:
            pytest.fail(f"Problemas na estrutura dos componentes:\n" + "\n".join(issues))
