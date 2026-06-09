"""Varredura heurística de PII nos CSVs de `data/csv/` e em nomes de arquivo
em `data/`. **Não** é uma ferramenta de detecção robusta: usa uma lista
pequena de regex para sinalizar candidatos a CPF, e-mail e telefone BR.

O gate de release no `DEPLOY.md` exige rodar este script e *resolver todos
os achados antes de publicar* — o exit code serve apenas para sinalizar
"houve candidato"; a decisão de release é humana.

Exit codes:
    0 — nenhum candidato encontrado
    1 — pelo menos um candidato (ver tabela em stdout)
    2 — erro de I/O ou de configuração
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# CPF com ou sem pontuação: 11 dígitos. Aceita "123.456.789-09" e "12345678909".
# Evita casar com sequências arbitrárias de 11 dígitos exigindo separador
# (ponto, hífen ou espaço) ou boundaries de palavra em volta.
_CPF_RE = re.compile(r"\b\d{3}[\.\s-]?\d{3}[\.\s-]?\d{3}-?\d{2}\b")

# E-mail — pattern RFC-ish, suficiente para sinalizar candidatos.
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Telefone BR: DDD de 2 dígitos + 8 ou 9 dígitos, com separadores opcionais.
# Casa "(11) 91234-5678", "11 91234-5678", "11912345678", "+55 11 91234-5678".
_PHONE_RE = re.compile(r"(?:\+?55[\s-]?)?\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}\b")

# Nomes próprios brasileiros comuns — usados apenas na varredura de NOMES DE
# ARQUIVO em `data/`. Não aplicado ao conteúdo dos CSVs porque ali nomes
# próprios são esperados (coluna `patient_name` do fixture).
_BRAZILIAN_FIRST_NAMES = {
    "adriana", "alessandra", "alexandre", "amanda", "ana", "anderson",
    "andrea", "antonio", "beatriz", "bruno", "camila", "carlos", "claudia",
    "daniel", "daniela", "debora", "diego", "eduardo", "eliane", "elisa",
    "fabiana", "felipe", "fernanda", "flavia", "francisco", "gabriel",
    "gabriela", "gisele", "gustavo", "helena", "henrique", "isabela",
    "ivana", "jaqueline", "jessica", "joao", "jose", "julia", "juliana",
    "karla", "kelly", "larissa", "leandro", "leticia", "lia", "lidia",
    "lorena", "lucas", "luciana", "luis", "luiza", "marcelo", "marcia",
    "maria", "mariana", "marina", "marta", "matheus", "michelle", "natalia",
    "patricia", "paula", "paulo", "pedro", "priscila", "rafael", "renata",
    "ricardo", "roberto", "rodrigo", "sandra", "sergio", "silvia", "simone",
    "sofia", "stephanie", "tatiana", "thiago", "valeria", "vanessa",
    "vinicius", "viviane",
}
# Lista curinga de sobrenomes comuns — menor cobertura, mais sinalização.
_BRAZILIAN_SURNAMES = {
    "almeida", "alves", "andrade", "barbosa", "barros", "batista",
    "borges", "carlos", "carvalho", "castro", "cavalcante", "cerqueira",
    "coelho", "correia", "costa", "cunha", "dias", "duarte", "farias",
    "fernandes", "ferreira", "freitas", "gomes", "goncalves", "lima",
    "lopes", "machado", "marin", "marinho", "martins", "mendes", "moura",
    "nascimento", "nunes", "oliveira", "pereira", "pinto", "pires",
    "ribeiro", "rocha", "rodrigues", "santos", "silva", "souza", "teixeira",
    "viana", "vilela",
}

# CSVs-alvo: o fixture intencional de `data/csv/`. Não varremos o diretório
# recursivamente para não correr contra `data/pacientes_e_planos/` (PDFs
# com nomes reais que **não** devem ir para o repo) — esse controle é
# humano, via `.gitignore` e o gate de release.
_CSV_DIR = Path(__file__).resolve().parents[1] / "data" / "csv"


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------
def _scan_csv(csv_path: Path) -> list[tuple[str, str, str, str]]:
    """Retorna [(fonte, coluna, valor_candidato, contexto)] para um CSV."""
    import csv

    findings: list[tuple[str, str, str, str]] = []
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader, start=2):  # 1 = header
                for col, value in row.items():
                    if not value:
                        continue
                    text = str(value)
                    for pattern, label in (
                        (_CPF_RE, "cpf"),
                        (_EMAIL_RE, "email"),
                        (_PHONE_RE, "phone"),
                    ):
                        for match in pattern.finditer(text):
                            findings.append((
                                str(csv_path.relative_to(csv_path.parents[2])),
                                col,
                                match.group(0),
                                f"row {row_index}",
                            ))
                            break  # one finding per cell is enough
    except (OSError, UnicodeDecodeError) as exc:
        print(f"AVISO: falha ao ler {csv_path}: {exc}", file=sys.stderr)
    return findings


def _scan_filenames(data_dir: Path) -> list[tuple[str, str, str, str]]:
    """Sinaliza nomes de arquivo que parecem conter nome próprio de pessoa.

    Retorna apenas candidatos — a confirmação é humana.
    """
    findings: list[tuple[str, str, str, str]] = []
    if not data_dir.exists():
        return findings
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        # Ignora o fixture CSV (já coberto) e o diretório de PDFs com nomes
        # reais (esse gate é separado e mais estrito).
        if path.suffix.lower() == ".csv":
            continue
        stem_tokens = re.split(r"[^A-Za-zÀ-ÿ]+", path.stem.lower())
        tokens = [t for t in stem_tokens if t]
        hits = [
            t for t in tokens
            if t in _BRAZILIAN_FIRST_NAMES or t in _BRAZILIAN_SURNAMES
        ]
        # Sinaliza apenas se houver 2+ tokens que parecem nome (reduz
        # falso-positivo de "Croquis" ou "SAD").
        if len(hits) >= 2:
            findings.append((
                str(path.relative_to(data_dir)),
                "filename",
                " ".join(hits),
                "possível nome de pessoa",
            ))
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    csv_dir = data_dir / "csv"

    print("=" * 72)
    print("scan_pii — varredura heurística de PII")
    print("=" * 72)
    print(f"Projeto:  {project_root}")
    print(f"CSVs:     {csv_dir}")
    print(f"Arquivos: {data_dir} (recursivo, exceto *.csv)")
    print()

    all_findings: list[tuple[str, str, str, str]] = []

    if csv_dir.exists():
        for csv_path in sorted(csv_dir.glob("*.csv")):
            all_findings.extend(_scan_csv(csv_path))
    else:
        print(f"AVISO: {csv_dir} não existe.", file=sys.stderr)

    all_findings.extend(_scan_filenames(data_dir))

    if not all_findings:
        print("Nenhum candidato encontrado. (Não é garantia — a decisão de")
        print("release continua humana, ver gate em DEPLOY.md.)")
        return 0

    print(f"Encontrados {len(all_findings)} candidato(s):")
    print()
    header = f"{'Fonte':<30}  {'Coluna/Campo':<22}  {'Valor':<24}  Contexto"
    print(header)
    print("-" * len(header))
    for source, field, value, context in all_findings:
        source_disp = source[:28] + ".." if len(source) > 30 else source
        field_disp = field[:20] + ".." if len(field) > 22 else field
        value_disp = value[:22] + ".." if len(value) > 24 else value
        print(f"{source_disp:<30}  {field_disp:<22}  {value_disp:<24}  {context}")
    print()
    print("AÇÃO: revisar cada candidato antes de qualquer deploy.")
    print("      Exit 1 é só um sinalizador; o gate de release é humano.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
