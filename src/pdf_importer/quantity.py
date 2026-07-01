"""Pure-quantity parser: extract a session / application count from free text.

MVP Jornada Clinica, Fase 2 (ver ``docs/mvp_plano.md`` §Fase 2).

Este modulo e' propositalmente isolado do data layer -- e' uma funcao
pura ``str | None -> int | None`` que pode ser exercitada em testes
sem backend, sem fixture de CSV, sem chamada ao parser de PDF.

Exemplos cobertos (ver ``tests/test_pdf_quantity.py``):

  * ``"10 sessões"``             -> 10
  * ``"1 sessão"``               -> 1
  * ``"6 aplicações"``           -> 6
  * ``"1 aplicação"``            -> 1
  * ``"10 sessões, 1x/semana"``  -> 10   (primeira ocorrencia)
  * ``""``  /  ``None``          -> ``None``
  * ``"sem numero"``             -> ``None``

Acentos preservados (decisao Caminho B Fase 6 -- ver
``docs/experience_log.md``): nao normalizamos ``sessão`` -> ``sessao``.

N7 (exception handling): funcao nunca levanta. Texto vazio, None ou
sem match retornam ``None`` silenciosamente. O caller decide se
marca ``needs_manual_review=True``.
"""
from __future__ import annotations

import re

# Captura "N sessões" / "N aplicações" (singular e plural, com/sem acento).
# Estrutura:
#   - \d+                                  : numero a capturar
#   - \s*                                  : whitespace opcional
#   - (?:sess(?:...)|aplica(?:...))        : "sessão/ões" OU "aplicação/ções"
#     - sess(?:[ãáa]o|[õoó]es)             : sessão/sessões/sessao/sessoes
#     - aplica(?:[çc][ãáa]o|[çc][õoó]es)   : aplicação/aplicações/etc.
_PATTERN = re.compile(
    r"(\d+)\s*"
    r"(?:"
    r"sess(?:[ãáa]o|[õoó]es)"
    r"|aplica(?:[çc][ãáa]o|[çc][õoó]es)"
    r")",
    re.IGNORECASE,
)


def parse_quantity(text: str | None) -> int | None:
    """Extrai a contagem numerica de ``"X sessões"`` / ``"X aplicações"``.

    Parameters
    ----------
    text:
        Texto livre (linha crua do PDF, valor ja extraido pelo regex
        de ``default.json``, etc.). Vazio / None retornam ``None``.

    Returns
    -------
    int | None
        Inteiro positivo se a regex casar com a primeira ocorrencia,
        ``None`` caso contrario.

    Notes
    -----
    - Sempre a *primeira* ocorrencia (compostos como
      ``"10 sessões, 1x/semana"`` retornam ``10``).
    - Nao normaliza acentos (preserva ``sessão`` / ``aplicação``).
    - Nao levanta nunca (N7). Texto mal-formado -> ``None``.
    """
    if not text:
        return None
    match = _PATTERN.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


__all__ = ["parse_quantity"]
