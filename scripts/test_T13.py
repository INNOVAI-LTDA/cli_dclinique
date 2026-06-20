"""Test T13: tests/test_integration.py atualizado para base zerada.

Tres tests reescritos (1 file modified) para nao dependerem mais do seed
de 8 pacientes + pat_001 com plan pre-existente:

  1. test_link_targets_ficha_when_patient_already_has_ficha
     - Antes: assumia 'todos os pacientes base tem plan no seed'
     - Depois: registra paciente + cria ficha via cadastro form, depois
       volta para Pacientes e verifica que o link aponta para Ficha

  2. test_cadastro_redirects_to_ficha_if_patient_already_has_one
     - Antes: usava ``pat_001`` (paciente do seed com plan)
     - Depois: registra paciente + cria plan via ``append_row`` (simula
       pre-existencia), depois deep-link no cadastro redireciona para Ficha

  3. test_add_patient_form_rejects_duplicate_name
     - Antes: usava 'Kelly Cristina Amorim' como nome duplicado
     - Depois: registra Maria Duplicada via form, depois tenta adicionar
       de novo (rejeitado, form continua aberto)

Padrao: check estrutural via leitura do arquivo (sem precisar carregar
o test_integration.py como modulo). Busca por substrings problematicos
e por marcadores da reescrita.
"""
import sys
from pathlib import Path

TID = "T13"
TITLE = "Atualizar tests/test_integration.py (substituir pat_001/seed por setup)"
FILE = Path("tests/test_integration.py")

# Strings que NAO devem aparecer no arquivo (eram do seed removido em T9)
FORBIDDEN_STRINGS = [
    '"pat_001"',  # hardcoded patient_id (string literal)
    'query_params["patient_id"] = "pat_001"',  # deep-link literal
    "pat_001 already has a plan in the seed",  # comentario do seed
    "All base patients have a plan in the seed",  # comentario do seed
    "kelly",  # paciente seed (case-insensitive)
    "ana maria",  # paciente seed
]

# Test functions que DEVEM existir apos a reescrita
REQUIRED_TESTS = [
    "test_link_targets_ficha_when_patient_already_has_ficha",
    "test_cadastro_redirects_to_ficha_if_patient_already_has_one",
    "test_add_patient_form_rejects_duplicate_name",
]


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

    # 3. Verifica que strings proibidas NAO aparecem
    text_lower = text.lower()
    for forbidden in FORBIDDEN_STRINGS:
        if forbidden.lower() in text_lower:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: '{forbidden}' NAO aparece (referencia a seed removido)")
            return 1

    # 4. Verifica que os 3 tests modificados estao presentes
    for test_name in REQUIRED_TESTS:
        if f"def {test_name}" not in text:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: def {test_name} presente")
            return 1

    # 5. Verifica que o helper _register_patient_via_form e' usado
    #    nos tests reescritos (prova de que a pre-existencia e' construida
    #    via setup, nao via seed)
    for test_name in REQUIRED_TESTS:
        # Extrai o corpo da funcao e checa se usa _register_patient_via_form
        marker = f"def {test_name}("
        start = text.find(marker)
        if start == -1:
            continue
        # Acha o proximo 'def ' no nivel de modulo (heuristica simples:
        # proxima linha que comeca com 'def ' no inicio da linha)
        rest = text[start:]
        # Procura o proximo def no inicio de uma linha (com indentacao zero)
        lines = rest.split("\n")
        body_lines = []
        for line in lines[1:]:
            if line.startswith("def "):
                break
            body_lines.append(line)
        body = "\n".join(body_lines)
        if "_register_patient_via_form" not in body:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: {test_name} usa _register_patient_via_form")
            print(f"  Got:      helper nao encontrado no corpo do test")
            return 1

    # 6. Verifica que o test de redirect usa append_row/next_id
    #    (prova de que a pre-existencia do plan e' construida)
    redirect_marker = "def test_cadastro_redirects_to_ficha_if_patient_already_has_one("
    start = text.find(redirect_marker)
    if start != -1:
        rest = text[start:]
        lines = rest.split("\n")
        body_lines = []
        for line in lines[1:]:
            if line.startswith("def "):
                break
            body_lines.append(line)
        body = "\n".join(body_lines)
        if "append_row" not in body or 'next_id("treatment_plans")' not in body:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: redirect test usa append_row + next_id('treatment_plans')")
            print(f"  Got:      sem um ou ambos")
            return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:            {FILE}")
    print(f"  Strings proibidas:  {len(FORBIDDEN_STRINGS)} (todas ausentes)")
    print(f"  Tests reescritos:   {len(REQUIRED_TESTS)}/3 presentes")
    print(f"  Helper usado:       _register_patient_via_form em todos os 3 tests")
    print(f"  Plan pre-existente: append_row + next_id('treatment_plans') no redirect test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
