"""Split composite procedure descriptions into individual items.

MVP Jornada Clinica, Fase 2 -- D5 (ver ``docs/cliente_reuniao_2026-06-30.md``
decisao D5 + ``docs/mvp_plano.md`` §Fase 2).

Exemplos (D5):
    * ``"medicamento X, injetaveis IM, injetaveis EV"`` -- tres itens.
    * ``"Limpeza de Pele e Drenagem Linfatica"``             -- dois itens.
    * ``"Limpeza, Drenagem e Massagem"``                     -- tres itens.
    * ``"1,5 sessões, Drenagem"``                           -- dois itens
      (``","`` antes de "5" e' virgula decimal, NAO separador).
    * ``"Apenas Um"``                                       -- um item.

Algoritmo:
    - Split em ``","`` apenas quando a virgula NAO for precedida de
      digito E NAO for seguida de espaço + digito (= virgula decimal
      tipo ``"1,5"``). Regex: ``(?<!\\d),(?!\\s*\\d)``.
    - Split tambem em ``" e "`` (com whitespace flexivel).
    - Strip + drop empty resultante.

O parser de PDF (``src/pdf_importer/parse.py``::_parse_list_zone)
chama esta funcao *antes* do loop de field_mappings para que cada
substring vire uma row em ``treatment_plan_items`` (em vez de virar
uma row composta -- bug pre-existente).

N7: nunca levanta. Texto vazio / None -> ``[]``.
"""
from __future__ import annotations

import re

# (?<!\\d)               : virgula NAO pode ser precedida de digito
# ,                      : o separador
# (?!\\s*\\d)            : virgula NAO pode ser seguida de whitespace + digito
# |                      : ou
# \\s+e\\s+              : " e " (com whitespace flexivel)
#
# Cobre:
#   - "A, B"          -> split em ","
#   - "A , B"         -> split em "," (whitespace ignorado entre virgula e B)
#   - "A e B"         -> split em " e "
#   - "1,5 sessões"   -> NAO split (decimal)
#   - "1,5 sessões, Drenagem" -> split na 2a virgula ("sessões", "Drenagem")
_SPLIT_RE = re.compile(r"(?<!\d),(?!\s*\d)|\s+e\s+", re.IGNORECASE)


def split_composite_items(line: str | None) -> list[str]:
    """Divide ``"A, B e C"`` em ``["A", "B", "C"]``.

    Parameters
    ----------
    line:
        Linha bruta do PDF (ja stripada ou nao). ``None`` / vazio / so
        whitespace retornam ``[]``.

    Returns
    -------
    list[str]
        Itens individuais, stripados, sem duplicatas vazias. Itens
        preservam virgula decimal (``"1,5 sessões"`` fica inteiro).

    Notes
    -----
    - Nao levanta nunca (N7).
    - Virgula decimal preservada (NAO split dentro de numeros).
    - ``" e "`` (com whitespace) e' separador OR (``"A, B e C"`` -> 3 itens).
    """
    if not line or not line.strip():
        return []
    parts = _SPLIT_RE.split(line)
    return [p.strip() for p in parts if p.strip()]


__all__ = ["split_composite_items"]
