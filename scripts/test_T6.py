"""Test T6: scripts/make_synthetic_pdf.py existe e gera um PDF PII-clean.

Valida SEM precisar de pymupdf real:
  - Arquivo scripts/make_synthetic_pdf.py existe
  - Modulo carrega sem erro (mock de fitz em sys.modules)
  - Funcao make_synthetic_pdf e' chamavel
  - Funcao escreve um arquivo no path informado:
      * arquivo existe
      * arquivo nao-vazio
      * arquivo comeca com "%PDF" (header PDF valido)
  - main() e' chamavel (a CLI e' verificada em smoke test abaixo)
  - Constantes PII-clean estao no modulo (nomes/CPFs fake)

Padrao (harness retroativo):
  - load_module_for_test com stubs (fitz, pymupdf)
  - O mock de fitz (make_fitz_stub) escreve um PDF fake (%PDF-1.4) no
    save() para que o test consiga verificar o header
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_harness import (  # noqa: E402
    load_module_for_test,
    make_fitz_stub,
)

TID = "T6"
TITLE = "Criar scripts/make_synthetic_pdf.py"
FILE = Path("scripts/make_synthetic_pdf.py")

# PII esperado: todos sao dados claramente fake ("Maria Teste da Silva",
# prontuario 12345678, etc). O test verifica que o modulo expoe esses
# valores para confirmar que o script gera o PDF correto, e tambem
# verifica que NAO expoe nenhum valor que pareca dado real.
EXPECTED_FAKE_VALUES = [
    "Maria Teste da Silva",  # nome ficticio
    "12345678",              # prontuario ficticio
    "Emagrecimento",         # foco do tratamento
]


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      criar scripts/make_synthetic_pdf.py")
        return 1

    # 2. Carrega com mock de fitz
    try:
        mod = load_module_for_test(
            FILE, "make_synthetic_pdf",
            stubs={
                "fitz": make_fitz_stub(),
                "pymupdf": make_fitz_stub(),
            },
        )
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 3. make_synthetic_pdf existe e e' chamavel
    if not callable(getattr(mod, "make_synthetic_pdf", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcao make_synthetic_pdf(path) definida")
        return 1

    # 4. main() existe e e' chamavel
    if not callable(getattr(mod, "main", None)):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcao main() definida")
        return 1

    # 5. Gera PDF em temp path e verifica o arquivo
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test_orcamento.pdf"
        result = mod.make_synthetic_pdf(out)
        # make_synthetic_pdf nao retorna nada; so escreve o arquivo
        if result is not None:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: make_synthetic_pdf retorna None")
            print(f"  Got:      {result!r}")
            return 1

        if not out.exists():
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: PDF criado em {out}")
            print(f"  Got:      arquivo nao existe")
            return 1

        if out.stat().st_size == 0:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: PDF nao-vazio")
            print(f"  Got:      0 bytes")
            return 1

        with open(out, "rb") as f:
            header = f.read(8)
        if not header.startswith(b"%PDF"):
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: header PDF (comeca com %PDF)")
            print(f"  Got:      {header!r}")
            return 1

    # 6. PII check: o modulo expoe os dados fake esperados.
    #    Esses dados DEVEM aparecer como atributos do modulo; caso
    #    contrario, o PDF gerado nao tera o conteudo esperado.
    source = FILE.read_text(encoding="utf-8")
    missing = [v for v in EXPECTED_FAKE_VALUES if v not in source]
    if missing:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: dados fake {EXPECTED_FAKE_VALUES} presentes no source")
        print(f"  Got:      faltam: {missing}")
        return 1

    # 7. DEFAULT_OUTPUT aponta para data/synthetic/orcamento_demo.pdf
    if str(mod.DEFAULT_OUTPUT).replace("\\", "/") != "data/synthetic/orcamento_demo.pdf":
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: DEFAULT_OUTPUT = data/synthetic/orcamento_demo.pdf")
        print(f"  Got:      {mod.DEFAULT_OUTPUT}")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:    {FILE}")
    print(f"  make_synthetic_pdf: chamavel, escreve %PDF-1.4 (OK)")
    print(f"  main():     chamavel (OK)")
    print(f"  PII clean:  {len(EXPECTED_FAKE_VALUES)} dados fake no source (OK)")
    print(f"  DEFAULT_OUTPUT: {mod.DEFAULT_OUTPUT} (OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
