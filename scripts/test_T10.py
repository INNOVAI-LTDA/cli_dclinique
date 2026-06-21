"""Test T10: tests/conftest.py ganha fixture db_branch (Neon API).

Valida SEM precisar de Neon real nem de pytest:
  - conftest.py carrega sem erro (mocks: pandas, streamlit, psycopg)
  - Helpers privados: _has_neon_creds() e _should_use_csv()
    - _has_neon_creds checa NEON_API_KEY E NEON_PROJECT_ID
    - _should_use_csv retorna True se DCLINIQUE_BACKEND=csv OU sem creds
  - Fixture db_branch existe, e' @pytest.fixture, scope='session'
  - db_branch tem logica de skip (pytest.skip quando _should_use_csv)
  - db_branch usa requests pra criar/ler/deletar branch
  - db_branch exporta DCLINIQUE_DSN no env
  - db_branch tem cleanup (finally) com DELETE request
  - Fallback csv_dir preservado (NAO removido)
  - Fixtures fake_session_state, base_data, app_path, workdir preservados

Padrao (harness retroativo):
  - load_module_for_test em tests/conftest.py com stubs
  - inspect.getsource() na fixture pra verificar o source (yield, skip, etc.)
  - _pytestfixturefunction para detectar @pytest.fixture e scope
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_harness import (  # noqa: E402
    load_module_for_test,
    make_pandas_stub,
    make_psycopg_stub,
    make_pytest_stub,
    make_streamlit_stub,
)

TID = "T10"
TITLE = "Atualizar tests/conftest.py (fixture db_branch Neon API)"
FILE = Path("tests/conftest.py")


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        return 1

    # 2. Carrega com mocks (pandas, psycopg, streamlit, pytest)
    try:
        mod = load_module_for_test(
            FILE, "tests.conftest",
            stubs={
                "pandas": make_pandas_stub(),
                "psycopg": make_psycopg_stub(),
                "streamlit": make_streamlit_stub(),
                "pytest": make_pytest_stub(),
            },
        )
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 3. _has_neon_creds existe e checa NEON_API_KEY + NEON_PROJECT_ID
    if not callable(getattr(mod, "_has_neon_creds", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcao _has_neon_creds()")
        return 1
    # Testa com env vazio
    import os
    saved_neon_key = os.environ.pop("NEON_API_KEY", None)
    saved_neon_pid = os.environ.pop("NEON_PROJECT_ID", None)
    saved_backend = os.environ.get("DCLINIQUE_BACKEND")
    try:
        if mod._has_neon_creds():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: _has_neon_creds() == False sem env setado")
            return 1
        os.environ["NEON_API_KEY"] = "fake-key"
        if mod._has_neon_creds():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: _has_neon_creds() == False com so' NEON_API_KEY")
            return 1
        os.environ["NEON_PROJECT_ID"] = "fake-project"
        if not mod._has_neon_creds():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: _has_neon_creds() == True com ambos setados")
            return 1
    finally:
        # Restaura env
        if saved_neon_key is None:
            os.environ.pop("NEON_API_KEY", None)
        else:
            os.environ["NEON_API_KEY"] = saved_neon_key
        if saved_neon_pid is None:
            os.environ.pop("NEON_PROJECT_ID", None)
        else:
            os.environ["NEON_PROJECT_ID"] = saved_neon_pid

    # 4. _should_use_csv existe e decide certo
    if not callable(getattr(mod, "_should_use_csv", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcao _should_use_csv()")
        return 1
    try:
        os.environ["DCLINIQUE_BACKEND"] = "csv"
        if not mod._should_use_csv():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: _should_use_csv() == True com DCLINIQUE_BACKEND=csv")
            return 1
        os.environ["DCLINIQUE_BACKEND"] = "postgres"
        os.environ.pop("NEON_API_KEY", None)
        os.environ.pop("NEON_PROJECT_ID", None)
        if not mod._should_use_csv():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: _should_use_csv() == True sem creds Neon")
            return 1
    finally:
        if saved_backend is None:
            os.environ.pop("DCLINIQUE_BACKEND", None)
        else:
            os.environ["DCLINIQUE_BACKEND"] = saved_backend

    # 5. db_branch fixture existe
    if not hasattr(mod, "db_branch"):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: fixture db_branch definida")
        return 1

    db_branch = mod.db_branch

    # 6. db_branch e' @pytest.fixture com scope='session'
    #    O decorator @pytest.fixture retorna _pytestfixturefunction que
    #    tem .scope e _pytestfixturefunction attribute.
    pff = getattr(db_branch, "_pytestfixturefunction", None)
    if pff is None:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: db_branch decorado com @pytest.fixture")
        print(f"  Got:      sem _pytestfixturefunction attribute")
        return 1
    scope = getattr(pff, "scope", None)
    if scope != "session":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: db_branch scope = 'session'")
        print(f"  Got:      scope = {scope!r}")
        return 1

    # 7. db_branch source: skip logic + requests + yield + finally + cleanup
    try:
        # _pytestfixturefunction wrapper tem __wrapped__ apontando pra funcao
        underlying = getattr(db_branch, "__wrapped__", db_branch)
        source = inspect.getsource(underlying)
    except (OSError, TypeError) as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: inspect.getsource(db_branch) funciona")
        print(f"  Got:      {e}")
        return 1

    expected_in_source = [
        ("_should_use_csv()", "decisao CSV vs Neon"),
        ("pytest.skip", "logica de skip"),
        ("requests.post", "criar branch via API"),
        ("requests.get", "pegar DSN do branch"),
        ("requests.delete", "deletar branch no teardown"),
        ("DCLINIQUE_DSN", "exporta DSN no env"),
        ("yield", "generator (cleanup no finally)"),
        ("finally", "cleanup guaranteed"),
    ]
    for needle, hint in expected_in_source:
        if needle not in source:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: source do db_branch contem {needle!r} ({hint})")
            print(f"  Got:      nao encontrado")
            return 1

    # 8. Fallback csv_dir preservado
    if not hasattr(mod, "csv_dir"):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: fixture csv_dir preservada (fallback dev sem internet)")
        return 1
    csv_dir = mod.csv_dir
    pff_csv = getattr(csv_dir, "_pytestfixturefunction", None)
    if pff_csv is None:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: csv_dir decorado com @pytest.fixture")
        return 1
    # csv_dir deve ser function-scoped (default), NAO session
    csv_scope = getattr(pff_csv, "scope", "function")
    if csv_scope == "session":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: csv_dir NAO e' session-scoped (e' fallback per-test)")
        print(f"  Got:      csv_dir scope = 'session'")
        return 1

    # 9. Outras fixtures preservadas
    for fixture_name in ("fake_session_state", "base_data", "app_path", "workdir"):
        if not hasattr(mod, fixture_name):
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: fixture {fixture_name} preservada")
            return 1

    # 10. FakeSessionState preservado (a classe, nao fixture)
    if not hasattr(mod, "FakeSessionState"):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: classe FakeSessionState preservada")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:           {FILE}")
    print(f"  _has_neon_creds:   checa NEON_API_KEY + NEON_PROJECT_ID (OK)")
    print(f"  _should_use_csv:   respeita DCLINIQUE_BACKEND=csv e falta de creds (OK)")
    print(f"  db_branch:         @pytest.fixture scope='session' (OK)")
    print(f"  db_branch source:  skip + requests.post/get/delete + yield/finally (OK)")
    print(f"  db_branch env:     exporta DCLINIQUE_DSN (OK)")
    print(f"  Fallback:          csv_dir + fake_session_state + base_data preservados (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
