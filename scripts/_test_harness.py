"""Helpers compartilhados pelos scripts de teste do Scrum board (test_TN.py).

Centraliza o pattern de carregar um modulo do projeto com mocks de deps
transitivas em `sys.modules`. Os aprendizados de T2 ("spec_from_file_location
em vez de importlib.import_module") e T3 ("mockar pandas em sys.modules
antes do load") ficam encapsulados aqui para que cada test_TN.py carregue
o harness e re-use a mesma logica.

Uso tipico em scripts/test_TN.py:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))  # para encontrar _test_harness
    from _test_harness import load_module_for_test, make_pandas_stub

    def main() -> int:
        mod = load_module_for_test(
            Path("src/data_layer/schema.py"),
            "src.data_layer.schema",
            stubs={"pandas": make_pandas_stub()},
        )
        # ... assercoes

Nao use `from src.x import y` direto no test — isso resolve via
importlib.import_module, que falha no subprocess do test runner
(sys.path[0] = scripts/, nao raiz do worktree). Use sempre
load_module_for_test, que combina:
  1. aplicacao de stubs em sys.modules
  2. insercao da raiz do worktree em sys.path
  3. spec_from_file_location + module_from_spec + exec_module
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Stubs de pacotes pesados
# ---------------------------------------------------------------------------


def make_pandas_stub() -> types.ModuleType:
    """Cria um stub de pandas com DataFrame exposto.

    Suficiente para `import pandas as pd` em codigo que usa pd apenas em
    type hints (ex.: `pd.DataFrame` em src/schemas.py:105). NAO constroi
    DataFrames reais — se o codigo target chamar `pd.DataFrame(...)` em
    runtime, vai dar TypeError.
    """
    mock = types.ModuleType("pandas")
    mock.DataFrame = type("DataFrame", (), {})
    return mock


def make_psycopg_stub() -> types.ModuleType:
    """Cria um stub de psycopg (psycopg 3) com connect/Connection/Cursor.

    Suficiente para `import psycopg` em codigo que so importa o modulo.
    `psycopg.connect(...)` retorna None — se o codigo target tentar usar
    o retorno como Connection, vai dar AttributeError (use
    make_fake_connection para um conn que registra SQL).
    """
    mock = types.ModuleType("psycopg")
    mock.connect = lambda *a, **kw: None
    mock.Connection = type("Connection", (), {})
    mock.Cursor = type("Cursor", (), {})
    return mock


def make_streamlit_stub() -> types.ModuleType:
    """Cria um stub de streamlit para evitar cold start do framework.

    Expõe o minimo necessario para o codigo target que usa
    `import streamlit as st` e depois acessa `st.secrets`,
    `st.cache_data`, `st.cache_resource`. Nao renderiza UI.
    """
    mock = types.ModuleType("streamlit")
    # `getattr(st, "secrets", None)` precisa retornar algo que suporte
    # o teste de `if secrets and "postgres" in secrets` — um SimpleNamespace
    # vazio falha nesse teste, entao retornamos None. O codigo que usa
    # st.secrets cai no caminho de env var quando secrets e None.
    mock.secrets = None
    # cache_data / cache_resource sao decorators que passam pela funcao.
    # Quando chamados com `(f)`, retornam f. Quando chamados com `()`,
    # retornam um decorator que retorna a funcao passada.
    def _passthrough_decorator(f=None, *a, **kw):
        if f is None:
            return lambda g: g
        return f
    mock.cache_data = _passthrough_decorator
    mock.cache_resource = _passthrough_decorator
    return mock


def make_sqlite_stub() -> types.ModuleType:
    """Stub de sqlite3 (caso o codigo target o use)."""
    mock = types.ModuleType("sqlite3")
    mock.connect = lambda *a, **kw: None
    return mock


def make_fitz_stub() -> types.ModuleType:
    """Stub de PyMuPDF (fitz) para scripts que geram PDF.

    `fitz.open()` retorna um FakeDoc; o FakeDoc.new_page(width, height)
    retorna um FakePage com insert_text(coords, text, **kw) que apenas
    registra os textos. `doc.save(path)` escreve um PDF fake (comeca com
    `%PDF-1.4`) no path informado. Suficiente para o codigo de geracao
    rodar e produzir um arquivo; nao checa layout real.
    """
    class _FakePage:
        def __init__(self):
            self.texts: list = []
        def insert_text(self, coords, text, **kw):
            self.texts.append((coords, text))

    class _FakeDoc:
        def __init__(self):
            self.pages: list = []
        def new_page(self, width, height):
            p = _FakePage()
            self.pages.append(p)
            return p
        def save(self, path):
            with open(path, "wb") as f:
                f.write(b"%PDF-1.4\n%fake synthetic PDF for testing\n")
        def close(self):
            pass

    mock = types.ModuleType("fitz")
    mock.open = lambda: _FakeDoc()
    return mock


def make_pytest_stub() -> types.ModuleType:
    """Stub de pytest suficiente para o conftest carregar e para tests
    verificarem a estrutura das fixtures.

    Expõe:
      - ``pytest.fixture(scope=...)`` -- decorator factory. Suporta tanto
        ``@pytest.fixture`` (default scope='function') quanto
        ``@pytest.fixture(scope='session')``. O wrapper retornado tem:
          * ``_pytestfixturefunction`` (com ``.scope``) -- para tests
            detectarem o scope via ``getattr(fn, '_pytestfixturefunction')``
          * ``__wrapped__`` -- aponta para a funcao original (util para
            ``inspect.getsource()`` ler o corpo do fixture)
          * ``__call__`` -- chamavel (chamar retorna o resultado da funcao)
      - ``pytest.skip(msg)`` -- levanta ``_SkipException``. Suficiente
        para o conftest; tests que tentarem chamar a fixture direto
        recebem a exception (skipped).

    NAO implementa ``pytest.raises``, ``pytest.mark``, ``pytest.main``,
    etc. Se o conftest usar outras APIs, adicionar aqui.
    """
    class _SkipException(Exception):
        pass

    class _FixtureFunction:
        """Wrapper retornado por ``@pytest.fixture(scope=...)``.

        Tem a forma basica do que o pytest real retorna, suficiente para
        que tests detectem que uma funcao e' fixture e leiam o scope.
        """

        def __init__(self, func, scope):
            self.__wrapped__ = func
            self._pytestfixturefunction = types.SimpleNamespace(scope=scope)

        def __call__(self, *args, **kwargs):
            return self.__wrapped__(*args, **kwargs)

    def fixture(*args, **kwargs):
        """Decorator que suporta ambos os call patterns do pytest real:

        * ``@pytest.fixture``              -> ``fixture(func)`` (sugar)
        * ``@pytest.fixture()``            -> ``fixture()(func)``
        * ``@pytest.fixture(scope='s')``   -> ``fixture(scope='s')(func)``
        * ``@pytest.fixture(autouse=True)`` -> ``fixture(autouse=True)(func)``

        Quando o primeiro positional arg e' callable (a funcao sendo
        decorada) e nao ha kwargs, retorna o wrapper direto. Caso
        contrario, retorna um decorator que captura `scope` e ignora
        os outros kwargs (autouse, params, ids, name).
        """
        # Padrao 1: chamado com a funcao direto: pytest.fixture(func)
        if args and callable(args[0]) and not kwargs:
            return _FixtureFunction(args[0], scope="function")
        # Padrao 2: chamado com kwargs (ou sem args): retorna decorator
        scope = kwargs.get("scope", "function")

        def decorator(func):
            return _FixtureFunction(func, scope=scope)

        return decorator

    def skip(msg: str = ""):
        raise _SkipException(msg)

    mock = types.ModuleType("pytest")
    mock.fixture = fixture
    mock.skip = skip
    # pytest.skip tem um attribute .Exception no pytest real; replicamos
    # para que codigo que faca `pytest.skip.Exception` (raro) funcione.
    skip.Exception = _SkipException  # type: ignore[attr-defined]
    return mock


# ---------------------------------------------------------------------------
# Carregamento de modulo com stubs
# ---------------------------------------------------------------------------


def load_module_for_test(
    file_path: Path,
    module_name: str,
    stubs: dict[str, Any] | None = None,
    worktree_root: Path | None = None,
):
    """Carrega `file_path` como `module_name`, aplicando stubs antes do load.

    Args:
        file_path: caminho para o .py do modulo (relativo a worktree_root
            ou absoluto). Se relativo, resolvido contra worktree_root.
        module_name: nome dotted do modulo (ex.: "src.data_layer.schema").
        stubs: dict `{nome_modulo: objeto_stub}` a serem injetados em
            sys.modules ANTES de carregar `file_path`. Use para deps
            que nao estao instaladas (pandas, psycopg, streamlit, etc.).
        worktree_root: raiz do worktree. Se None, usa os.getcwd().

    Returns:
        O modulo carregado (ja executado).

    Raises:
        FileNotFoundError: se file_path nao existir.
        ImportError: se o modulo falhar ao carregar.
    """
    if worktree_root is None:
        worktree_root = Path(os.getcwd())

    file_path = Path(file_path)
    if not file_path.is_absolute():
        file_path = worktree_root / file_path
    if not file_path.exists():
        raise FileNotFoundError(
            f"arquivo nao encontrado: {file_path.resolve()}"
        )

    # 1. Aplica stubs ANTES de qualquer import
    if stubs:
        for mod_name, stub in stubs.items():
            if mod_name not in sys.modules:
                sys.modules[mod_name] = stub

    # 2. Adiciona raiz do worktree ao sys.path (necessario para que
    #    `from src.x import y` resolva o pacote `src` no modulo carregado)
    worktree_root_str = str(worktree_root)
    if worktree_root_str not in sys.path:
        sys.path.insert(0, worktree_root_str)

    # 3. spec_from_file_location em vez de importlib.import_module
    spec = importlib.util.spec_from_file_location(
        module_name, str(file_path)
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"spec_from_file_location retornou None para {file_path}"
        )

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
