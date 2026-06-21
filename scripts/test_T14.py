"""Test T14: tests/test_ficha_unit.py atualizado para base zerada.

Apos T9 (CSV -> header only), o test suite inteiro do ficha dependia
do paciente ``pat_001`` do seed (que sumiu). Refactor:

  1. Adicionado helper ``_register_patient(name, age) -> pid`` que cria
     um paciente via ``append_row`` (substitui a dependencia do seed).
  2. Todos os tests que usavam ``pat_001`` agora chamam ``_register_patient``
     no setup e usam o pid retornado.
  3. Counts atualizados: 8/9/15/16/17/19 -> 0/1/2.
  4. ``test_next_item_id_avoids_existing_seed_ids`` reescrito: pre-popula
     com item_new_001 e verifica que ``next_id`` retorna item_new_002
     (prova real de "pula existentes", nao apenas trivial).
  5. ``test_patient_has_ficha_true_for_existing_plan`` reescrito: registra
     paciente + plan via ``append_row`` (simula pre-existencia).
  6. ``test_patient_has_ficha_false_when_no_plan_in_seed`` simplificado:
     base ja' vem zerada, helper retorna False para qualquer pid.

Padrao: check estrutural via leitura do arquivo (sem precisar carregar
o test_ficha_unit.py como modulo).
"""
import sys
from pathlib import Path

TID = "T14"
TITLE = "Atualizar tests/test_ficha_unit.py (seed-dependencia no setup)"
FILE = Path("tests/test_ficha_unit.py")

# Strings que NAO devem aparecer (eram do seed removido em T9)
FORBIDDEN_STRINGS = [
    '"pat_001"',  # hardcoded patient_id (string literal)
    'assert patient_has_ficha("pat_001")',  # uso direto de pat_001
    "_handle_submit(\"pat_001\")",  # submit handler com seed
    'patients[patients["patient_id"] == "pat_001"]',  # filtro por pat_001
    "8 seed + 1",  # comentario sobre seed count
    "15 seed + 1",  # idem
    "17 seed + 2",  # idem
    "pat_001 has a plan in the seed",  # comentario do seed
    "seed has item_001",  # comentario do seed
    "kelly",  # paciente seed
    "ana maria",  # paciente seed
]

# Test functions que DEVEM existir apos a reescrita
REQUIRED_TESTS = [
    "test_next_plan_id_starts_at_001",
    "test_next_goal_id_starts_at_001",
    "test_next_item_id_starts_at_001",
    "test_next_weight_id_starts_at_001",
    "test_next_item_id_avoids_existing_seed_ids",
    "test_patient_has_ficha_true_for_existing_plan",
    "test_patient_has_ficha_false_for_missing_patient",
    "test_patient_has_ficha_false_when_no_plan_in_seed",
    "test_patient_has_ficha_reflects_recent_appends",
    "test_handle_ficha_submit_writes_plan_and_goal",
    "test_handle_ficha_submit_creates_weight_entry_when_peso_atual_positive",
    "test_handle_ficha_submit_skips_weight_entry_when_peso_atual_zero",
    "test_handle_ficha_submit_skips_items_with_empty_name",
    "test_handle_ficha_submit_updates_patient_age",
]

# Counts que devem aparecer (base zerada)
EXPECTED_COUNTS = {0: 1, 1: 3, 2: 1}  # 0:1x, 1:3x, 2:1x
# Counts que NAO devem aparecer (eram do seed)
FORBIDDEN_COUNTS = [8, 9, 15, 16, 17, 19]


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        return 1

    # 2. Le arquivo como texto
    try:
        text = FILE.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo legivel")
        print(f"  Got:      {type(e).__name__}: {e}")
        return 1

    # 3. Verifica strings proibidas
    text_lower = text.lower()
    for forbidden in FORBIDDEN_STRINGS:
        if forbidden.lower() in text_lower:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: '{forbidden}' NAO aparece")
            return 1

    # 4. Verifica tests presentes
    for test_name in REQUIRED_TESTS:
        if f"def {test_name}" not in text:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: def {test_name} presente")
            return 1

    # 5. Verifica helper _register_patient existe e usa append_row/next_id
    if "def _register_patient(" not in text:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: helper '_register_patient()' definido")
        return 1
    # Extrai corpo do helper
    start = text.find("def _register_patient(")
    rest = text[start:]
    lines = rest.split("\n")
    body_lines = []
    for line in lines[1:]:
        if line.startswith("def ") or line.startswith("# ---"):
            break
        body_lines.append(line)
    helper_body = "\n".join(body_lines)
    if "append_row" not in helper_body:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _register_patient usa append_row")
        return 1
    if 'next_id("patients")' not in helper_body:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: _register_patient usa next_id('patients')")
        return 1

    # 6. Extrai assertions de count
    found_counts = []
    for line in text.splitlines():
        if "len(" in line and "==" in line:
            import re
            m = re.search(r"==\s*(\d+)", line)
            if m:
                found_counts.append(int(m.group(1)))

    # 7. Verifica counts esperados
    for expected_n, min_occurrences in EXPECTED_COUNTS.items():
        actual = found_counts.count(expected_n)
        if actual < min_occurrences:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: count == {expected_n} aparece >= {min_occurrences}x")
            print(f"  Got:      aparece {actual}x. Total: {found_counts}")
            return 1

    # 8. Verifica counts proibidos
    for forbidden_n in FORBIDDEN_COUNTS:
        if forbidden_n in found_counts:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: count == {forbidden_n} NAO aparece (era do seed)")
            print(f"  Got:      aparece {found_counts.count(forbidden_n)}x")
            print(f"            Total: {found_counts}")
            return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:           {FILE}")
    print(f"  Strings proibidas: {len(FORBIDDEN_STRINGS)} (todas ausentes)")
    print(f"  Tests presentes:   {len(REQUIRED_TESTS)}/14")
    print(f"  Helper:            _register_patient (append_row + next_id)")
    print(f"  Counts:            {dict(EXPECTED_COUNTS)} (presentes)")
    print(f"  Counts proibidos:  {FORBIDDEN_COUNTS} (ausentes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
