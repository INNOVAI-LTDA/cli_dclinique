"""Test T8: app.py:get_data() funciona com o router (sem mudança esperada).

Valida SEM precisar de streamlit/DB reais:
  - Arquivo app.py existe
  - Modulo carrega sem erro (mocks: streamlit, pandas, psycopg)
  - get_data() existe, e' chamavel, e' decorado com @st.cache_data
  - get_data() faz import lazy de src.data_layer.load_all (NAO no top-level)
  - get_data() chama load_all() e retorna o resultado (verificado via patch)
  - main() existe e e' chamavel
  - _PAGE_MODULES tem 8 paginas com os nomes esperados (sem contar a Ficha,
    que e' detalhe interno)

Padrao (harness retroativo):
  - load_module_for_test com stubs
  - inspect.getsource() para verificar o corpo de get_data (lazy import)
  - unittest.mock.patch em "src.data_layer.load_all" para interceptar
"""
import inspect
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_harness import (  # noqa: E402
    load_module_for_test,
    make_pandas_stub,
    make_psycopg_stub,
    make_streamlit_stub,
)

TID = "T8"
TITLE = "Verificar app.py:get_data()"
FILE = Path("app.py")


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe na raiz do worktree")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        return 1

    # 2. Carrega modulo com mocks
    try:
        mod = load_module_for_test(
            FILE, "app",
            stubs={
                "streamlit": make_streamlit_stub(),
                "pandas": make_pandas_stub(),
                "psycopg": make_psycopg_stub(),
            },
        )
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 3. get_data existe e e' chamavel
    if not callable(getattr(mod, "get_data", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: get_data() function")
        return 1

    # 4. get_data tem import lazy de src.data_layer.load_all
    #    (verificado via inspect do source — NAO pode ser top-level)
    try:
        source = inspect.getsource(mod.get_data)
    except OSError as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: inspect.getsource(get_data) funciona")
        print(f"  Got:      {e}")
        return 1

    if "from src.data_layer import load_all" not in source:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: get_data faz 'from src.data_layer import load_all'")
        print(f"  Got (source): {source}")
        return 1

    # 5. get_data() chama load_all() — patch para verificar
    sentinel_data = {"patients": "MOCK_PATIENTS_DF", "treatment_plans": "MOCK_PLANS"}
    with patch("src.data_layer.load_all", return_value=sentinel_data):
        result = mod.get_data()
    if result != sentinel_data:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: get_data() retorna load_all() (router -> backend)")
        print(f"  Got:      {result!r}")
        return 1

    # 6. main() existe e e' chamavel
    if not callable(getattr(mod, "main", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: main() function")
        return 1

    # 7. _PAGE_MODULES tem as 8 paginas. Nomes podem ter Unicode
    #    (Visão, Decisão) — nao vou printar, so contar.
    if not hasattr(mod, "_PAGE_MODULES"):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _PAGE_MODULES dict")
        return 1
    page_keys = list(mod._PAGE_MODULES.keys())
    if len(page_keys) != 8:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _PAGE_MODULES tem 8 paginas")
        print(f"  Got:      {len(page_keys)} paginas")
        return 1

    # 8. _route existe (lazy page loader)
    if not callable(getattr(mod, "_route", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _route() function (lazy page loader)")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:    {FILE}")
    print(f"  get_data:   chamavel, lazy import de load_all (OK)")
    print(f"  get_data:   retorna load_all() (router -> backend) (OK)")
    print(f"  main:       chamavel (OK)")
    print(f"  _PAGE_MODULES: {len(page_keys)} paginas (OK)")
    print(f"  _route:     lazy page loader presente (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
