"""Test T12: tests/test_pdf_importer.py — N/A neste worktree.

O plan original referenciava ``tests/test_pdf_importer.py`` (com
assertions de count tipo ``len(patients) == 9`` -> ``== 1``). Porem:

  - O arquivo NAO existe neste worktree (``feature-neon-data-layer``).
  - O fluxo de import de PDF em si nao esta' implementado nesta versao:
    ``src/pages/atualizacao_dados.py:12`` tem apenas um
    ``st.file_uploader(..., help="...os arquivos nao serao lidos.")``
    (placeholder visual, nao parser real).
  - O CLAUDE.md reforça: "Nao implementar parser real de PDF/Excel,
    Supabase, login, deploy, WhatsApp, Google Drive ou outras
    integracoes externas."
  - A cobertura automatizada do wizard de import, quando aplicavel,
    vive em outros worktrees (ex.: ``feature-pdf-ingest``), NAO aqui.

Conclusao: T12 do plan e' N/A. Este test serve como audit trail
documentando que verificamos a ausencia do arquivo e o motivo. NAO
ha codigo de teste para atualizar.

Padrao: check de existencia de arquivo + grep textual em
``atualizacao_dados.py`` para confirmar o placeholder.
"""
import re
import sys
from pathlib import Path

TID = "T12"
TITLE = "Atualizar tests/test_pdf_importer.py (N/A — arquivo nao existe)"
PDF_TEST_FILE = Path("tests/test_pdf_importer.py")
PDF_INT_TEST_FILE = Path("tests/test_pdf_importer_integration.py")
ATUALIZACAO_FILE = Path("src/pages/atualizacao_dados.py")


def main() -> int:
    # 1. test_pdf_importer.py NAO existe (esperado — T12 e' N/A)
    if PDF_TEST_FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {PDF_TEST_FILE} NAO existe (T12 deveria ser N/A)")
        print(f"  Got:      encontrado em {PDF_TEST_FILE.resolve()}")
        print(f"  Fix:      se o arquivo existe, atualizar assertions de count")
        print(f"            (8/9/10 -> 0/1/2) e remover referencias a seed")
        return 1

    # 2. test_pdf_importer_integration.py tambem NAO existe
    if PDF_INT_TEST_FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {PDF_INT_TEST_FILE} NAO existe (T12 deveria ser N/A)")
        print(f"  Got:      encontrado em {PDF_INT_TEST_FILE.resolve()}")
        return 1

    # 3. Verifica que o wizard e' de fato um placeholder (upload simulado)
    if not ATUALIZACAO_FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {ATUALIZACAO_FILE} existe (auditoria do placeholder)")
        print(f"  Got:      nao encontrado em {ATUALIZACAO_FILE.resolve()}")
        return 1

    try:
        text = ATUALIZACAO_FILE.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {ATUALIZACAO_FILE} legivel")
        print(f"  Got:      {type(e).__name__}: {e}")
        return 1

    # Confirma marcador textual "simulado" + "nao serao lidos" (ou similar)
    if not re.search(r"simulad", text, re.IGNORECASE):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: {ATUALIZACAO_FILE} contem marcador de placeholder")
        print(f"            ('simulad' / 'simulado' — indica upload fake)")
        print(f"  Got:      nenhum match")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  {PDF_TEST_FILE}:")
    print(f"    NAO existe (esperado — T12 do plan e' N/A neste worktree)")
    print(f"  {PDF_INT_TEST_FILE}:")
    print(f"    NAO existe (esperado — variante integration tambem ausente)")
    print(f"  {ATUALIZACAO_FILE}:")
    print(f"    Contem placeholder de upload simulado (sem parser real)")
    print(f"  Conclusao: nenhuma assertion de count para atualizar.")
    print(f"  Cobertura automatizada do wizard vive em outros worktrees.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
