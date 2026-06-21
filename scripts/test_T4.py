"""Test T4: src/data_layer/postgres_backend.py existe com 6 funções públicas.

Valida SEM precisar de DB real:
  - Arquivo src/data_layer/postgres_backend.py existe
  - Modulo carrega sem erro (com mocks de pandas, psycopg, streamlit)
  - 6 funcoes publicas: load_all, load_table, append_row, update_row,
    next_id, data_dir — todas definidas e chamaveis
  - data_dir() retorna pathlib.Path (sentinel postgres://neon)
  - NEW_ID_PREFIX tem os 5 pares corretos (pat_new, plan_new, ...)
  - _columns_for e _validate_table levantam ValueError para tabela
    desconhecida (defesa contra SQL injection via nome de tabela)
  - Nenhuma funcao de leitura/escrita foi chamada durante o load
    (psycopg.connect nao foi invocado) — confirma imports lazy

Padrao (learning de T2/T3 + harness retroativo):
  - Usa scripts/_test_harness.load_module_for_test que combina:
    1. stubs em sys.modules (pandas, psycopg, streamlit)
    2. sys.path[0] = raiz do worktree
    3. spec_from_file_location + exec_module
  - Verifica comportamento lazy: psycopg.connect nao e' chamado ate
    o primeiro append_row/load_table/next_id. Spy via wrapper no stub.
"""
import sys
from pathlib import Path

# `scripts/` ja esta em sys.path[0] quando o test roda como subprocess
# de run_scrum_tests.py, mas o harness pode estar em outro path se o
# test for rodado diretamente. Forca o caminho para encontrar _test_harness.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_harness import (  # noqa: E402
    load_module_for_test,
    make_pandas_stub,
    make_psycopg_stub,
    make_streamlit_stub,
)
import types  # noqa: E402

TID = "T4"
TITLE = "Criar src/data_layer/postgres_backend.py"
FILE = Path("src/data_layer/postgres_backend.py")
EXPECTED_FUNCTIONS = [
    "load_all",
    "load_table",
    "append_row",
    "update_row",
    "next_id",
    "data_dir",
]
EXPECTED_PREFIXES = {
    "patients": "pat_new",
    "treatment_plans": "plan_new",
    "treatment_plan_items": "item_new",
    "patient_goals": "goal_new",
    "weight_entries": "w_new",
}


def _spy_psycopg_connect() -> tuple[types.ModuleType, list]:
    """Cria stub de psycopg com spy em `connect()`.

    Retorna (stub, call_log). Cada chamada a psycopg.connect() adiciona
    os args em call_log. Usado para verificar que o load do modulo NAO
    dispara uma conexao (imports lazy).
    """
    call_log: list = []
    mock = types.ModuleType("psycopg")

    def _spy_connect(*args, **kwargs):
        call_log.append((args, kwargs))
        return None  # any subsequent op would fail; tests nao chamam funcoes que usam engine
    mock.connect = _spy_connect
    mock.Connection = type("Connection", (), {})
    mock.Cursor = type("Cursor", (), {})
    return mock, call_log


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe na raiz do worktree")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      criar src/data_layer/postgres_backend.py com as 6 funcoes")
        return 1

    # 2. Carrega modulo com mocks. Spy em psycopg.connect para
    #    verificar que o load NAO dispara conexao (imports lazy).
    psycopg_stub, connect_calls = _spy_psycopg_connect()
    try:
        mod = load_module_for_test(
            FILE,
            "src.data_layer.postgres_backend",
            stubs={
                "pandas": make_pandas_stub(),
                "psycopg": psycopg_stub,
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

    # 3. Verifica que o load foi lazy (psycopg.connect nao foi chamado)
    if connect_calls:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: imports lazy -- psycopg.connect NAO e' chamado no load")
        print(f"  Got:      {len(connect_calls)} chamada(s) a connect: {connect_calls}")
        print(f"  Fix:      mover imports de psycopg/connection para dentro das funcoes")
        return 1

    # 4. 6 funcoes publicas presentes
    missing = [
        f for f in EXPECTED_FUNCTIONS
        if not hasattr(mod, f) or not callable(getattr(mod, f))
    ]
    if missing:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcoes {EXPECTED_FUNCTIONS} definidas e chamaveis")
        print(f"  Got:      faltam: {missing}")
        return 1

    # 5. data_dir() retorna pathlib.Path com sentinel platform-safe.
    #    (NUNCA usar 'postgres://neon' ou 'postgres:neon' — Windows
    #    interpreta `//` como UNC e `:` como drive letter, ambos quebram
    #    a semantica. Usar 'postgres-neon' que e' identico em POSIX e Windows.)
    from pathlib import Path as _Path
    dd = mod.data_dir()
    if not isinstance(dd, _Path):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: data_dir() retorna pathlib.Path")
        print(f"  Got:      {type(dd).__name__}: {dd!r}")
        return 1
    if str(dd) != "postgres-neon":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: data_dir() == Path('postgres-neon')")
        print(f"  Got:      {dd!r}")
        print(f"  Hint:     evitar 'postgres://neon' (Windows UNC) e")
        print(f"            'postgres:neon' (Windows drive letter).")
        return 1

    # 6. NEW_ID_PREFIX tem os 5 pares corretos
    if mod.NEW_ID_PREFIX != EXPECTED_PREFIXES:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: NEW_ID_PREFIX = {EXPECTED_PREFIXES}")
        print(f"  Got:      {mod.NEW_ID_PREFIX}")
        return 1

    # 7. _columns_for levanta ValueError para tabela desconhecida
    try:
        mod._columns_for("tabela_inexistente")
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _columns_for('tabela_inexistente') levanta ValueError")
        print(f"  Got:      retornou sem erro")
        return 1
    except ValueError as e:
        if "tabela_inexistente" not in str(e):
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: mensagem do ValueError menciona 'tabela_inexistente'")
            print(f"  Got:      {e}")
            return 1

    # 8. _validate_table levanta ValueError para tabela desconhecida
    try:
        mod._validate_table("DROP TABLE patients")
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _validate_table rejeita nome de tabela nao-catalogo")
        print(f"  Got:      retornou sem erro (SQL injection vulnerability!)")
        return 1
    except ValueError:
        pass  # expected

    # 9. _next_indexed_id (helper privado) funciona
    if mod._next_indexed_id(set(), "pat_new") != "pat_new_001":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _next_indexed_id(set(), 'pat_new') == 'pat_new_001'")
        print(f"  Got:      {mod._next_indexed_id(set(), 'pat_new')!r}")
        return 1
    used = {"plan_new_001", "plan_new_002"}
    if mod._next_indexed_id(used, "plan_new") != "plan_new_003":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _next_indexed_id com 001+002 usados == 'plan_new_003'")
        print(f"  Got:      {mod._next_indexed_id(used, 'plan_new')!r}")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:           {FILE}")
    print(f"  Funcoes:           {', '.join(EXPECTED_FUNCTIONS)}")
    print(f"  data_dir:          {dd} (sentinel)")
    print(f"  NEW_ID_PREFIX:     {len(EXPECTED_PREFIXES)} pares (OK)")
    print(f"  Imports lazy:      psycopg.connect NAO foi chamado no load (OK)")
    print(f"  Validacao tabela:  _validate_table rejeita nomes fora do catalogo (OK)")
    print(f"  next_id helper:    _next_indexed_id gera '001'/'003' corretamente (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
