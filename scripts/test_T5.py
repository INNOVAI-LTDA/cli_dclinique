"""Test T5: scripts/init_neon_schema.py existe e funciona.

Valida SEM precisar de DB real:
  - Arquivo scripts/init_neon_schema.py existe
  - Modulo carrega sem erro (mocks: pandas, psycopg, streamlit)
  - Funcao main() e' chamavel
  - Caminho de sucesso: main() retorna 0 e dispara 11 CREATE TABLE
    IF NOT EXISTS (um por tabela em EXPECTED_SCHEMAS)
  - Caminho de erro (DSN ausente): get_engine levanta RuntimeError →
    main() retorna 1
  - Caminho de erro (DB inacessivel): get_engine retorna engine cujo
    cursor() levanta Exception → init_schema propaga → main() retorna 2

Padrao (harness retroativo):
  - load_module_for_test com stubs em sys.modules ANTES do load
  - patch.object(mod, "get_engine", ...) substitui o get_engine
    importado pelo script por um fake (retorna FakeEngine) ou por uma
    funcao que levanta RuntimeError
  - FakeEngine/FakeCursor gravam o SQL executado para inspecionar
"""
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

TID = "T5"
TITLE = "Criar scripts/init_neon_schema.py"
FILE = Path("scripts/init_neon_schema.py")


class FakeCursor:
    def __init__(self):
        self.executed: list[str] = []

    def execute(self, sql):
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class FakeEngine:
    """Engine fake que aceita `with engine: with engine.cursor() as cur: cur.execute(...)`."""

    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class FailingCursorEngine:
    """Engine fake cujo cursor() levanta Exception (simula DB down)."""

    def cursor(self):
        raise Exception("simulated DB connection error")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      criar scripts/init_neon_schema.py com main()")
        return 1

    # 2. Carrega modulo com mocks (pandas via src.schemas lazy; psycopg/
    #    streamlit por defesa contra imports eager futuros)
    try:
        mod = load_module_for_test(
            FILE, "init_neon_schema",
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

    # 3. main() existe e e' chamavel
    if not callable(getattr(mod, "main", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcao main() definida e chamavel")
        print(f"  Got:      main = {getattr(mod, 'main', '<ausente>')!r}")
        return 1

    # 4. Caminho de SUCESSO: FakeEngine com 11 CREATE TABLE
    fake_engine = FakeEngine()
    with patch.object(mod, "get_engine", return_value=fake_engine):
        rc = mod.main()

    if rc != 0:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: main() retorna 0 em sucesso")
        print(f"  Got:      {rc}")
        return 1

    executed = fake_engine.cursor_obj.executed
    if len(executed) != 11:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: 11 CREATE TABLE executados (um por tabela)")
        print(f"  Got:      {len(executed)} SQLs executados")
        return 1

    for sql in executed:
        if not sql.startswith("CREATE TABLE IF NOT EXISTS "):
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: SQL comeca com 'CREATE TABLE IF NOT EXISTS '")
            print(f"  Got:      {sql[:80]!r}")
            return 1

    # 5. Caminho de ERRO: DSN ausente → RuntimeError → rc=1
    def raise_runtime_error():
        raise RuntimeError("DSN nao configurado (simulado pelo test)")

    with patch.object(mod, "get_engine", side_effect=raise_runtime_error):
        rc = mod.main()

    if rc != 1:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: main() retorna 1 quando DSN nao configurado")
        print(f"  Got:      {rc}")
        return 1

    # 6. Caminho de ERRO: DB inacessivel → cursor() levanta → init_schema
    #    propaga → main() retorna 2
    with patch.object(mod, "get_engine", return_value=FailingCursorEngine()):
        rc = mod.main()

    if rc != 2:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: main() retorna 2 quando init_schema falha")
        print(f"  Got:      {rc}")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:    {FILE}")
    print(f"  main():     chamavel (OK)")
    print(f"  Sucesso:    rc=0, 11 CREATE TABLE IF NOT EXISTS (OK)")
    print(f"  DSN error:  rc=1 quando get_engine levanta RuntimeError (OK)")
    print(f"  DB error:   rc=2 quando init_schema falha (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
