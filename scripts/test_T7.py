"""Test T7: src/data_layer/__init__.py atualiza o router Postgres/CSV.

Valida SEM precisar de DB real nem de CSV files:
  - Arquivo src/data_layer/__init__.py existe
  - Modulo carrega sem erro (mocks por defesa; router deve ser lazy)
  - RIGOR: apos carregar src.data_layer, nenhum backend deve estar
    em sys.modules (postgres_backend OU csv_backend). Se estiver,
    o router nao e' lazy — falha do design.
  - 7 funcoes publicas: load_all, load_table, append_row, update_row,
    next_id, csv_dir, data_dir — todas chamaveis
  - Roteamento postgres (DCLINIQUE_BACKEND=postgres) → postgres_backend
  - Roteamento csv (DCLINIQUE_BACKEND=csv) → csv_backend
  - Roteamento invalid (DCLINIQUE_BACKEND=invalid) → ValueError
  - restore do env var no finally

Padrao (harness retroativo):
  - load_module_for_test com stubs (pandas, psycopg, streamlit)
  - unittest.mock.patch com string path "src.data_layer.<backend>.load_all"
    importa o backend sob demanda (com mocks ativos) e intercepta a chamada
  - os.environ manipulado direto; restaurado no finally
"""
import os
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

TID = "T7"
TITLE = "Atualizar src/data_layer/__init__.py (router Postgres/CSV)"
FILE = Path("src/data_layer/__init__.py")
EXPECTED_FUNCTIONS = [
    "load_all",
    "load_table",
    "append_row",
    "update_row",
    "next_id",
    "csv_dir",
    "data_dir",
]


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      reescrever src/data_layer/__init__.py com router lazy")
        return 1

    # 2. Carrega modulo com mocks (defesa; router deve ser lazy e nao
    #    precisar deles, mas se algum dia voltar a ser eager, o test
    #    passa com os mocks)
    try:
        mod = load_module_for_test(
            FILE, "src.data_layer",
            stubs={
                "pandas": make_pandas_stub(),
                "psycopg": make_psycopg_stub(),
                "streamlit": make_streamlit_stub(),
            },
        )
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 3. RIGOR: router e' lazy. Apos carregar src.data_layer, nenhum
    #    backend deve estar em sys.modules. Se o router voltar a ter
    #    `from .csv_backend import ...` no top-level, este check falha.
    eagerly_loaded = [
        name for name in (
            "src.data_layer.postgres_backend",
            "src.data_layer.csv_backend",
        ) if name in sys.modules
    ]
    if eagerly_loaded:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: router lazy -- nenhum backend em sys.modules apos load")
        print(f"  Got:      {eagerly_loaded}")
        print(f"  Fix:      importar o backend apenas dentro de _select_backend()")
        return 1

    # 4. Funcoes publicas presentes
    missing = [
        f for f in EXPECTED_FUNCTIONS
        if not callable(getattr(mod, f, None))
    ]
    if missing:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {EXPECTED_FUNCTIONS}")
        print(f"  Got:      faltam: {missing}")
        return 1

    # 5-7. Roteamento. Manipula env var e usa patch para interceptar
    #      a chamada ao backend. Restaura no finally.
    saved_env = os.environ.get("DCLINIQUE_BACKEND")
    try:
        # ---- 5. Postgres mode (default; set explicito) ----
        os.environ["DCLINIQUE_BACKEND"] = "postgres"
        if hasattr(mod, "reset_backend_cache"):
            mod.reset_backend_cache()
        with patch(
            "src.data_layer.postgres_backend.load_all",
            return_value="PG_LOAD_ALL",
        ):
            result = mod.load_all()
        if result != "PG_LOAD_ALL":
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: DCLINIQUE_BACKEND=postgres -> pg_backend.load_all")
            print(f"  Got:      {result!r}")
            return 1

        # ---- 6. CSV mode ----
        os.environ["DCLINIQUE_BACKEND"] = "csv"
        if hasattr(mod, "reset_backend_cache"):
            mod.reset_backend_cache()
        with patch(
            "src.data_layer.csv_backend.load_all",
            return_value="CSV_LOAD_ALL",
        ):
            result = mod.load_all()
        if result != "CSV_LOAD_ALL":
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: DCLINIQUE_BACKEND=csv -> csv_backend.load_all")
            print(f"  Got:      {result!r}")
            return 1

        # ---- 7. Invalid mode → ValueError ----
        os.environ["DCLINIQUE_BACKEND"] = "invalid_mode_xyz"
        if hasattr(mod, "reset_backend_cache"):
            mod.reset_backend_cache()
        try:
            mod.load_all()
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: ValueError quando DCLINIQUE_BACKEND=invalid")
            print(f"  Got:      sem erro")
            return 1
        except ValueError:
            pass  # expected

    finally:
        # Restaurar env var para nao vazar para o resto do test runner
        if saved_env is None:
            os.environ.pop("DCLINIQUE_BACKEND", None)
        else:
            os.environ["DCLINIQUE_BACKEND"] = saved_env
        if hasattr(mod, "reset_backend_cache"):
            mod.reset_backend_cache()

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Funcoes:    {', '.join(EXPECTED_FUNCTIONS)}")
    print(f"  Router:     lazy (nenhum backend em sys.modules apos load) (OK)")
    print(f"  Postgres:   DCLINIQUE_BACKEND=postgres -> pg_backend (OK)")
    print(f"  CSV:        DCLINIQUE_BACKEND=csv -> csv_backend (OK)")
    print(f"  Invalid:    DCLINIQUE_BACKEND=invalid -> ValueError (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
