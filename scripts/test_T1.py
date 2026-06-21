"""Test T1: Adicionar psycopg[binary]>=3.2,<4 em requirements.txt.

Validação: o arquivo requirements.txt contém uma linha cujo conteúdo casa
com o pattern `psycopg[binary]>=3.2,<4`. A linha pode estar em qualquer
posição (não importa onde), mas o pattern tem que aparecer literal.

Escopo: 1 arquivo (requirements.txt).
Pré-condição: nenhuma.
Pós-condição: requirements.txt contém a dep. Nada mais.
"""
import re
import sys
from pathlib import Path

TID = "T1"
TITLE = "Adicionar psycopg[binary] em requirements.txt"
EXPECTED_PATTERN = r"psycopg\[binary\]>=3\.2,<4"
REQUIREMENTS_PATH = Path("requirements.txt")


def main() -> int:
    if not REQUIREMENTS_PATH.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {REQUIREMENTS_PATH} existe no cwd")
        print(f"  Got:      arquivo nao encontrado em "
              f"{REQUIREMENTS_PATH.resolve()}")
        print(f"  Fix:      rode o script a partir da raiz do projeto")
        return 1

    content = REQUIREMENTS_PATH.read_text(encoding="utf-8")

    if not re.search(EXPECTED_PATTERN, content):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: linha com pattern `{EXPECTED_PATTERN}`")
        print(f"  Got:      pattern nao encontrado em {REQUIREMENTS_PATH}")
        print(f"  Conteudo atual:")
        for i, line in enumerate(content.splitlines(), 1):
            print(f"    {i:3}: {line}")
        print(f"  Fix:      adicionar a linha "
              f"`psycopg[binary]>=3.2,<4` ao requirements.txt")
        return 1

    matching_line = next(
        i for i, l in enumerate(content.splitlines(), 1)
        if re.search(EXPECTED_PATTERN, l)
    )
    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Pattern encontrado: {EXPECTED_PATTERN}")
    print(f"  Posicao:            linha {matching_line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
