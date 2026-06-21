"""Test T9: Limpar data/csv/*.csv (11 -> header only, 0 linhas).

Apos T9:
  - Os 11 CSVs em data/csv/ contem APENAS a linha de header
  - Header == EXPECTED_SCHEMAS[table] (ordem das colunas preservada)
  - Zero linhas de dados (LGPD gate trivialmente atendido)

O test e' destrutivo: na primeira execucao, os dados sinteticos sao
removidos. Idempotente: rodar novamente nao causa mudanca (o conteudo
ja e' o esperado). Se o seed for necessario de volta, rodar:
  .venv/Scripts/python.exe scripts/seed_csvs.py

Padrao (harness retroativo):
  - load_module_for_test em src/schemas.py com stub de pandas (defesa)
  - EXPECTED_SCHEMAS e' a fonte de verdade do header
  - Escreve o header com encoding utf-8 e newline \\n (padrao CSV)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_harness import (  # noqa: E402
    load_module_for_test,
    make_pandas_stub,
)

TID = "T9"
TITLE = "Limpar data/csv/*.csv (11 -> header only)"
CSV_DIR = Path("data/csv")
SCHEMAS_FILE = Path("src/schemas.py")


def main() -> int:
    # 1. CSV dir existe
    if not CSV_DIR.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {CSV_DIR} existe")
        print(f"  Got:      nao encontrado em {CSV_DIR.resolve()}")
        return 1

    # 2. Carrega src/schemas.py para EXPECTED_SCHEMAS (com stub pandas)
    try:
        schemas_mod = load_module_for_test(
            SCHEMAS_FILE, "src.schemas",
            stubs={"pandas": make_pandas_stub()},
        )
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: src/schemas.py carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    EXPECTED_SCHEMAS = schemas_mod.EXPECTED_SCHEMAS
    table_names = list(EXPECTED_SCHEMAS.keys())

    # 3. Confirma 11 tabelas
    if len(table_names) != 11:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: 11 tabelas em EXPECTED_SCHEMAS")
        print(f"  Got:      {len(table_names)} tabelas: {table_names}")
        return 1

    # 4. Wipe cada CSV (header only) e verifica
    wiped = 0
    for table in table_names:
        columns = EXPECTED_SCHEMAS[table]
        if not columns:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: EXPECTED_SCHEMAS[{table!r}] tem colunas")
            print(f"  Got:      lista vazia")
            return 1

        csv_path = CSV_DIR / f"{table}.csv"
        if not csv_path.exists():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: {csv_path} existe")
            print(f"  Got:      nao encontrado")
            return 1

        # Header com colunas na ordem do schema
        header_line = ",".join(columns)

        # Conta linhas antes do wipe (para relatar ao usuario)
        try:
            existing = csv_path.read_text(encoding="utf-8")
            existing_lines = len([ln for ln in existing.splitlines() if ln.strip()])
        except Exception:
            existing_lines = -1

        # Wipe: write only header
        csv_path.write_text(header_line + "\n", encoding="utf-8")
        wiped += 1

        # Verifica: arquivo tem 1 linha (header)
        content = csv_path.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if len(lines) != 1:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Arquivo:  {csv_path}")
            print(f"  Expected: 1 linha (header only)")
            print(f"  Got:      {len(lines)} linhas")
            print(f"  Conteudo: {content!r}")
            return 1

        # Verifica: header == columns (ordem-sensitive)
        actual_columns = lines[0].split(",")
        if actual_columns != columns:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Arquivo:  {csv_path}")
            print(f"  Expected: {columns}")
            print(f"  Got:      {actual_columns}")
            return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Diretorio: {CSV_DIR}")
    print(f"  Arquivos:  {wiped}/11 CSVs (header only, 0 linhas)")
    print(f"  Schema:    EXPECTED_SCHEMAS preservado (ordem das colunas)")
    print(f"  ATENCAO:   dados sinteticos removidos. Para repopular, rode:")
    print(f"             .venv/Scripts/python.exe scripts/seed_csvs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
