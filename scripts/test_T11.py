"""Test T11: tests/test_add_patient_unit.py atualizado para base zerada.

Apos T9 (CSV -> header only), os testes que assumiam 8 pacientes
iniciais precisam ser ajustados:

  - test_next_patient_id_starts_at_001:  continua valido (base
    zerada, proximo id == pat_new_001).
  - test_existing_normalized_names_includes_seed_patients:  removido
    (nao ha seed). Substituido por test_existing_normalized_names_starts_empty
    que verifica ``keys == set()``.
  - test_handle_submit_rejects_*:  ``len(...) == 8`` -> ``len(...) == 0``.
  - test_handle_submit_appends_valid_patient:  ``len(df) == 9`` -> ``== 1``.
  - test_handle_submit_keeps_form_open_on_rejection:  ``== 8`` -> ``== 0``.
  - test_handle_submit_uses_next_id_avoiding_existing: ``== 10`` -> ``== 2``.
  - Id semantics preservadas: ``pat_new_001`` (1o insert) e
    ``pat_new_002`` (apos pre-existing) continuam corretos.

Padrao: check estrutural via leitura do arquivo (sem precisar carregar
o test_add_patient_unit.py como modulo). Regex para extrair as
assertions de count, e busca literal para nomes de pacientes seed.
"""
import re
import sys
from pathlib import Path

TID = "T11"
TITLE = "Atualizar tests/test_add_patient_unit.py (assertions de count)"
FILE = Path("tests/test_add_patient_unit.py")

# Counts que DEVEM estar presentes (base zerada: 0 seed)
#   0: 2 reject tests (empty, form open on rejection)
#   1: 2 success-ish (success test + duplicate test que prepende Kelly)
#   2: 1 next_id_avoiding_existing (0 + 1 pre + 1 new)
EXPECTED_COUNTS = {
    0: 2,
    1: 2,
    2: 1,
}

# Counts que NAO devem aparecer mais (eram do seed de 8 pacientes)
FORBIDDEN_COUNTS = [8, 9, 10]

# Nomes de pacientes seed que NAO devem aparecer
FORBIDDEN_NAMES = ["kelly", "ana maria"]


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

    # 3. Extrai todas as assertions do tipo ``len(...) == N``
    #    A regex simples `len\([^)]*\) == N` quebra com parenteses
    #    aninhados como `len(load_table("patients"))` (o `[^)]*` para
    #    no primeiro `)`). Abordagem por linha: para cada linha com
    #    `len(` e `==`, extrai o N depois do `==`.
    found_counts = []
    for line in text.splitlines():
        if "len(" in line and "==" in line:
            m = re.search(r"==\s*(\d+)", line)
            if m:
                found_counts.append(int(m.group(1)))

    # 4. Verifica counts esperados
    for expected_n, min_occurrences in EXPECTED_COUNTS.items():
        actual = found_counts.count(expected_n)
        if actual < min_occurrences:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: count == {expected_n} aparece >= {min_occurrences}x")
            print(f"  Got:      aparece {actual}x. Total: {found_counts}")
            return 1

    # 5. Verifica counts proibidos
    for forbidden_n in FORBIDDEN_COUNTS:
        if forbidden_n in found_counts:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: count == {forbidden_n} NAO aparece (era do seed de 8)")
            print(f"  Got:      aparece em {found_counts.count(forbidden_n)} assertion(s)")
            print(f"            Total: {found_counts}")
            return 1

    # 6. Verifica que nomes de pacientes seed NAO aparecem
    text_lower = text.lower()
    for name in FORBIDDEN_NAMES:
        if name in text_lower:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: '{name}' NAO aparece (paciente seed removido em T9)")
            return 1

    # 7. Verifica que id semantics estao preservadas
    if "pat_new_001" not in text:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: 'pat_new_001' presente (1o insert)")
        return 1
    if "pat_new_002" not in text:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: 'pat_new_002' presente (apos pre-existing)")
        return 1

    # 8. Verifica que o test renomeado existe
    if "test_existing_normalized_names_includes_seed_patients" in text:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: test antigo removido")
        print(f"  Got:      'test_existing_normalized_names_includes_seed_patients' ainda existe")
        return 1
    if "test_existing_normalized_names_starts_empty" not in text:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: novo test 'test_existing_normalized_names_starts_empty' presente")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:            {FILE}")
    print(f"  Counts encontrados: {sorted(found_counts)}")
    print(f"  Counts esperados:   {dict(EXPECTED_COUNTS)} (presentes)")
    print(f"  Counts proibidos:   {FORBIDDEN_COUNTS} (ausentes)")
    print(f"  Id semantics:       pat_new_001 + pat_new_002 preservados (OK)")
    print(f"  Test renomeado:     starts_empty substitui includes_seed_patients (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
