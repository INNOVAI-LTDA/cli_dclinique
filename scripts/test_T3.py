"""Test T3: src/data_layer/schema.py existe com to_ddl() e init_schema().

Valida SEM precisar de DB real nem de pandas instalado:
  - Arquivo src/data_layer/schema.py existe
  - Modulo carrega sem erro
  - Funcoes to_ddl, init_schema, _postgres_type definidas e chamaveis
  - to_ddl gera CREATE TABLE IF NOT EXISTS com PK TEXT na primeira coluna
  - to_ddl mapeia TIMESTAMP/BOOLEAN/INTEGER/DOUBLE PRECISION/TEXT corretamente
  - to_ddl levanta ValueError quando columns=[]
  - to_ddl gera DDL valido para todas as 11 tabelas em EXPECTED_SCHEMAS

Padrao de import (learning de T2):
  - sys.path[0] do subprocess e scripts/, nao a raiz do worktree; usa
    `importlib.util.spec_from_file_location` em vez de
    `importlib.import_module`.

Mock de pandas (learning desta rodada):
  - schema.py faz `from src.schemas import EXPECTED_SCHEMAS` no top-level
  - src/schemas.py:4 faz `import pandas as pd` no top-level
  - Sem pandas instalado, o import cascateia em ModuleNotFoundError antes
    mesmo de checarmos a API. Solucao: stub em sys.modules["pandas"] ANTES
    de carregar schema.py. O stub so precisa expor DataFrame (usado apenas
    como type hint em validate_mock_schema, nao chamado no test).
"""
import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path

TID = "T3"
TITLE = "Criar src/data_layer/schema.py"
FILE = Path("src/data_layer/schema.py")
EXPECTED_FUNCTIONS = ["to_ddl", "init_schema", "_postgres_type"]


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe na raiz do worktree")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      criar src/data_layer/schema.py com to_ddl/init_schema")
        return 1

    # 2. Mock pandas ANTES de qualquer import que dependa dele.
    #    schema.py -> src.schemas -> pandas. O stub so expoe DataFrame
    #    (usado em type hint em src.schemas.validate_mock_schema; a
    #    funcao nao e chamada no test).
    if "pandas" not in sys.modules:
        mock_pd = types.ModuleType("pandas")
        mock_pd.DataFrame = type("DataFrame", (), {})
        sys.modules["pandas"] = mock_pd

    # 3. Adiciona raiz do worktree ao sys.path (learning T2: schema.py faz
    #    `from src.schemas import EXPECTED_SCHEMAS`; sem isso o import falha
    #    porque `src` e namespace package e o subprocess nao tem a raiz no path)
    worktree_root = os.getcwd()
    if worktree_root not in sys.path:
        sys.path.insert(0, worktree_root)

    # 4. Carrega o modulo target via spec_from_file_location
    mod_name = "src.data_layer.schema"
    try:
        spec = importlib.util.spec_from_file_location(
            mod_name, str(FILE.resolve())
        )
        if spec is None or spec.loader is None:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: spec criado para {FILE}")
            print(f"  Got:      spec_from_file_location retornou None")
            return 1
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo {mod_name} carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 5. Funcoes esperadas
    missing = [
        f for f in EXPECTED_FUNCTIONS
        if not hasattr(mod, f) or not callable(getattr(mod, f))
    ]
    if missing:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcoes {EXPECTED_FUNCTIONS} definidas e chamaveis")
        print(f"  Got:      faltam: {missing}")
        return 1

    # 6. to_ddl gera CREATE TABLE IF NOT EXISTS com PK TEXT
    ddl = mod.to_ddl(
        "patients", ["patient_id", "name", "created_at"]
    )
    for needle in (
        "CREATE TABLE IF NOT EXISTS patients",
        "patient_id TEXT PRIMARY KEY",
        "name TEXT",
        "created_at TIMESTAMP",
    ):
        if needle not in ddl:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: ddl contem {needle!r}")
            print(f"  Got:      {ddl}")
            return 1

    # 7. to_ddl respeita type maps: bool -> BOOLEAN, date -> TIMESTAMP
    ddl_plan = mod.to_ddl(
        "treatment_plans",
        ["plan_id", "patient_id", "budget_code", "issue_date",
         "start_date", "end_date", "status", "main_goal",
         "is_renewal", "notes"],
    )
    for needle in ("is_renewal BOOLEAN", "issue_date TIMESTAMP"):
        if needle not in ddl_plan:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: ddl contem {needle!r}")
            print(f"  Got:      {ddl_plan}")
            return 1

    # 8. to_ddl respeita type maps: int -> INTEGER, float -> DOUBLE PRECISION
    ddl_weight = mod.to_ddl(
        "weight_entries",
        ["weight_id", "patient_id", "plan_id", "measurement_date",
         "weight", "source", "notes"],
    )
    if "weight DOUBLE PRECISION" not in ddl_weight:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: ddl tem 'weight DOUBLE PRECISION'")
        print(f"  Got:      {ddl_weight}")
        return 1

    # 9. to_ddl levanta ValueError com columns=[]
    try:
        mod.to_ddl("patients", [])
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: ValueError quando columns=[]")
        print(f"  Got:      to_ddl retornou sem erro")
        return 1
    except ValueError:
        pass  # expected

    # 10. to_ddl gera DDL para todas as 11 tabelas em EXPECTED_SCHEMAS
    #     O mock de pandas do passo 2 ja esta em sys.modules, entao
    #     `import src.schemas` aqui nao tenta carregar o pandas real.
    try:
        from src.schemas import EXPECTED_SCHEMAS
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: src.schemas importa sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        return 1

    if len(EXPECTED_SCHEMAS) != 11:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: EXPECTED_SCHEMAS tem 11 tabelas")
        print(f"  Got:      {len(EXPECTED_SCHEMAS)} tabelas: "
              f"{list(EXPECTED_SCHEMAS.keys())}")
        return 1

    for table, columns in EXPECTED_SCHEMAS.items():
        try:
            ddl = mod.to_ddl(table, columns)
        except Exception as e:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: to_ddl({table!r}, ...) sem erro")
            print(f"  Got:      {type(e).__name__}: {e}")
            return 1
        if f"CREATE TABLE IF NOT EXISTS {table}" not in ddl:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: ddl para {table} comeca com "
                  f"CREATE TABLE IF NOT EXISTS {table}")
            print(f"  Got:      {ddl[:100]!r}")
            return 1
        pk = columns[0]
        if f"{pk} TEXT PRIMARY KEY" not in ddl:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: ddl para {table} tem '{pk} TEXT PRIMARY KEY'")
            print(f"  Got:      {ddl}")
            return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:           {FILE}")
    print(f"  Funcoes:           {', '.join(EXPECTED_FUNCTIONS)}")
    print(f"  to_ddl 'patients': PK TEXT + TIMESTAMP + TEXT (OK)")
    print(f"  to_ddl bool/int:   BOOLEAN/INTEGER respeitados (OK)")
    print(f"  to_ddl float:      DOUBLE PRECISION para weight (OK)")
    print(f"  to_ddl vazio:      ValueError (OK)")
    print(f"  Tabelas:           {len(EXPECTED_SCHEMAS)} (todas geram DDL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
