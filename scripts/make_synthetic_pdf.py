"""One-shot: gera um PDF sintetico PII-clean para o cliente testar o import.

Uso:
    python scripts/make_synthetic_pdf.py
    python scripts/make_synthetic_pdf.py --output /path/to/out.pdf

Por padrao escreve em ``data/synthetic/orcamento_demo.pdf``. O PDF
gerado espelha a estrutura dos orcamentos reais (3 zonas: dados do
paciente, procedimentos, rodape) com coordenadas do template DClinique.
Todos os dados sao ficticios e claramente sinteticos — o cliente pode
importar este PDF no wizard sem preocupacao de LGPD.

Dados hardcoded (todos fake):
  - Nome:    "Maria Teste da Silva"
  - CPF:     "111.222.333-44"
  - Pront.:  "12345678"
  - Tel.:    "(11) 99999-8888"
  - Idade:   35
  - Foco:    "Emagrecimento"
  - 3 procedimentos: Drenagem 8 sessoes, Massagem 4 sessoes, Limpeza 1 sessao
  - Clinica: "Clinica DClinique"
  - Data:    "15 de marco de 2026"

Transitive imports:
  - pymupdf (fitz) e' lazy dentro de :func:`make_synthetic_pdf`. Carregar
    este script NAO importa pymupdf; o import acontece na primeira
    chamada a funcao de geracao.

Exit codes:
  0 — PDF gerado
  1 — pymupdf nao instalado
  2 — falha na geracao (permissao, path invalido, etc.)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Dados PII-clean (todos ficticios, podem ser commitados sem risco LGPD)
PATIENT_NAME = "Maria Teste da Silva"
PATIENT_RECORD = "12345678"
PATIENT_PHONE = "(11) 99999-8888"
PATIENT_AGE = "35"
TREATMENT_FOCUS = "Emagrecimento"
CLINIC_NAME = "Clinica DClinique"
ISSUE_DATE = "15 de marco de 2026"

DEFAULT_OUTPUT = Path("data/synthetic/orcamento_demo.pdf")


def make_synthetic_pdf(path: Path) -> None:
    """Escreve um PDF de uma pagina com texto dentro das zonas default.

    Espelha a estrutura dos 15 PDFs reais em ``data/pacientes_e_planos/``:
      - dados_paciente zone (30, 115, 565, 230)
      - procedimentos zone  (30, 240, 565, 640)
      - rodape zone         (30, 650, 565, 820)

    Cria o diretorio-pai se nao existir. Levanta ImportError se
    pymupdf nao estiver instalado; outras excecoes propagam.
    """
    import fitz  # PyMuPDF, lazy

    path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 em pontos

    # dados_paciente zone (30, 115, 565, 230)
    page.insert_text((50, 140), f"Paciente: {PATIENT_NAME}", fontsize=11)
    page.insert_text((50, 160), f"Prontuario: {PATIENT_RECORD}", fontsize=11)
    page.insert_text((50, 180), f"Telefone: {PATIENT_PHONE}", fontsize=11)
    page.insert_text((50, 200), f"Idade: {PATIENT_AGE}", fontsize=11)

    # procedimentos zone (30, 240, 565, 640)
    page.insert_text((50, 260), f"Foco do tratamento: {TREATMENT_FOCUS}",
                      fontsize=11)
    page.insert_text((50, 290), "1. Drenagem - 8 sessoes 2x/semana",
                      fontsize=11)
    page.insert_text((50, 315), "2. Massagem - 4 sessoes quinzenal",
                      fontsize=11)
    page.insert_text((50, 340), "3. Limpeza - 1 sessoes mensal", fontsize=11)

    # rodape zone (30, 650, 565, 820)
    page.insert_text((50, 670), CLINIC_NAME, fontsize=11)
    page.insert_text((50, 690), f"Data de emissao: {ISSUE_DATE}", fontsize=11)

    doc.save(str(path))
    doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera um PDF sintetico PII-clean para o cliente.",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=DEFAULT_OUTPUT,
        help=f"Output PDF path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    try:
        make_synthetic_pdf(args.output)
    except ImportError as e:
        print(f"[ERROR] pymupdf nao instalado: {e}", file=sys.stderr)
        print("Instale com: pip install pymupdf", file=sys.stderr)
        return 1
    except Exception as e:
        print(
            f"[ERROR] Falha ao gerar PDF: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    print(f"[OK] PDF sintetico gerado em {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
