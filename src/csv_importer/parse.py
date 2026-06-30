"""Helpers compartilhados pelos parsers CSV (Caminho B, Fase 6).

Fornece 4 grupos de helpers puros:

  * ``split_multi(value, sep)``     — divide string multi-valor por sep
                                        (``"A, B, C"`` → ``["A", "B", "C"]``).
  * ``parse_br_date(value)``        — ``"DD/MM/YYYY"`` → ``pd.Timestamp``.
  * ``parse_br_datetime(value)``    — ``"DD/MM/YYYY HH:MM[:SS]"`` → ``pd.Timestamp``.
  * ``parse_br_date_range(value)``  — ``"DD/MM HH:MM - HH:MM"`` → ``(start, end)``.
  * ``normalize_name(value)``       — lowercase + trim + colapsa whitespace
                                        (mantém acentos; Fase 6 dedup é tolerante).

N7 (exception handling): todos os helpers retornam ``pd.NaT`` / ``[]`` / ``""``
em vez de levantar excecao — parser CSVs do mundo real tem dados sujos.
Mensagens de warning em PT-BR via ``logging.getLogger(__name__)``.

Nao importa ``streamlit`` — manter puro para testes hermeticos.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = [
    "split_multi",
    "parse_br_date",
    "parse_br_datetime",
    "parse_br_date_range",
    "normalize_name",
]


# ---------------------------------------------------------------------------
# split_multi
# ---------------------------------------------------------------------------


def split_multi(value: str | None, sep: str = ",") -> list[str]:
    """Divide string multi-valor por ``sep``. Trim + drop vazios.

    Comportamento:
      * ``None`` / nao-string → ``[]``.
      * ``"A, B, C"`` → ``["A", "B", "C"]``.
      * ``"A,, B"`` → ``["A", "B"]`` (vazios colapsados).
      * ``"-"`` → ``["-"]`` (sentinel de "sem valor" e' preservado).
    """
    if value is None:
        return []
    if not isinstance(value, str):
        return []
    parts = [p.strip() for p in value.split(sep)]
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# parse_br_date / parse_br_datetime / parse_br_date_range
# ---------------------------------------------------------------------------


def parse_br_date(value: str | None) -> pd.Timestamp | pd.NaT:
    """Coerce ``"DD/MM/YYYY"`` → ``pd.Timestamp`` normalizado (00:00:00).

    Retorna ``pd.NaT`` (nao levanta) para inputs vazios / invalidos / formato ISO.
    A normalizacao para meia-noite evita que comparacoes entre datas
    gerem falsos negativos (e.g. ``2026-05-25 14:30`` vs ``2026-05-25 00:00``).
    """
    if not value or not isinstance(value, str):
        return pd.NaT
    try:
        ts = pd.to_datetime(value.strip(), format="%d/%m/%Y", errors="coerce")
    except (ValueError, TypeError) as exc:
        logger.warning("parse_br_date falhou para %r: %s", value, exc)
        return pd.NaT
    if pd.isna(ts):
        return pd.NaT
    return ts.normalize()


def parse_br_datetime(value: str | None) -> pd.Timestamp | pd.NaT:
    """Coerce ``"DD/MM/YYYY HH:MM[:SS]"`` → ``pd.Timestamp`` (sem normalizar hora).

    Tenta formatos em ordem; cai para ``pd.to_datetime(dayfirst=True)``
    como fallback (cobre ``"YYYY-MM-DD HH:MM:SS"`` vindo de alguma exportacao
    futura). Retorna ``pd.NaT`` se tudo falhar.
    """
    if not value or not isinstance(value, str):
        return pd.NaT
    value = value.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            ts = pd.to_datetime(value, format=fmt, errors="raise")
        except (ValueError, TypeError):
            continue
        if not pd.isna(ts):
            return ts
    try:
        ts = pd.to_datetime(value, dayfirst=True, errors="coerce")
    except (ValueError, TypeError) as exc:
        logger.warning("parse_br_datetime falhou para %r: %s", value, exc)
        return pd.NaT
    if pd.isna(ts):
        return pd.NaT
    return ts


def parse_br_date_range(
    value: str | None, sep: str = "-"
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT]:
    """Coerce ``"DD/MM HH:MM - HH:MM"`` → ``(start, end)``.

    Variacoes:
      * ``"-"`` / ``""`` / ``None`` → ``(NaT, NaT)``.
      * ``"25/05/2026 12:00 - 14:00"`` → ``(Timestamp 12:00, Timestamp 14:00)``.
        O 2o pedaco (``"14:00"``) e' SÓ HORA — compomos com a data do start
        para evitar que ``pd.to_datetime("14:00")`` infira a data de HOJE
        (bug sutil: "14:00" sem dia e' ambiguo, pandas assume hoje).
      * ``"25/05/2026 12:00 - 25/05/2026 14:00"`` → ``(start, end)`` ambos
        com data e hora.
      * Split por ``sep`` ("-") e' naive — se algum horario tiver "-", quebra.
        Fica como TODO para Fase 6.5 se surgir CSVs com horarios negativos.
    """
    if not value or not isinstance(value, str):
        return pd.NaT, pd.NaT
    stripped = value.strip()
    if not stripped or stripped == sep:
        return pd.NaT, pd.NaT
    parts = [p.strip() for p in stripped.split(sep) if p.strip()]
    if not parts:
        return pd.NaT, pd.NaT
    start = parse_br_datetime(parts[0])
    if len(parts) < 2 or pd.isna(start):
        return start, pd.NaT
    second = parts[1].strip()
    # Heuristica: se o 2o pedaco NAO tem "/" (data), e' so' hora. Compomos
    # com a data do start para nao cair no bug "14:00 → hoje".
    if "/" not in second:
        date_str = start.strftime("%d/%m/%Y")
        composed = f"{date_str} {second}"
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                end = pd.to_datetime(composed, format=fmt, errors="raise")
                return start, end
            except (ValueError, TypeError):
                continue
        return start, pd.NaT
    end = parse_br_datetime(second)
    return start, end


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------

# Pre-compiled: colapsa qualquer whitespace (espaco, tab, NBSP) em 1 espaco.
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(value: str | None) -> str:
    """Lowercase + trim + colapsa whitespace. Mantem acentos (Fase 6 dedup).

    Decisao de design: acentos sao preservados para que o dedup de paciente
    nao confunda "Joao" com "João". O matching tolerante a typo fica para
    ``src.csv_importer.dedup`` via Levenshtein <= 2 sobre o resultado
    desta funcao.

    >>> normalize_name("Kelly Cristina a Silva Amorim")
    'kelly cristina a silva amorim'
    >>> normalize_name("  João  da  Silva  ")
    'joão da silva'
    >>> normalize_name(None)
    ''
    """
    if not value or not isinstance(value, str):
        return ""
    return _WHITESPACE_RE.sub(" ", value.strip()).lower()
