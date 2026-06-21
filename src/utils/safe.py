"""NA-safe value coercion utilities.

The data layer (`src/data_layer/`) returns pandas DataFrames whose
nullable columns (``Int64``, ``boolean``, ``string``) use ``pd.NA``
as the missing-value sentinel — different from the legacy ``NaN``
that ``float64`` columns carry. Many downstream call sites were
written assuming ``float64`` and use the legacy NaN-check pattern
(``x == x``) which raises ``TypeError: boolean value of NA is
ambiguous`` on ``pd.NA`` (reproduzido em PRD no Mapa de Decisão em
2026-06-21 quando um paciente sem entrada em ``satisfaction_entries``
deixou ``score = pd.NA``).

These helpers centralize the coercion: a single ``is_missing`` check
covers NaN/NA/NaT/None/empty-string, and the ``safe_*`` helpers
return a typed default for any missing input.

Notas de design
---------------
- NA-safe NAO significa "esconder o erro". Quando o default for
  exibido (ex.: ``safe_int(score) == 0`` num campo de "Satisfação"),
  é um sinal visual de "sem dado", não um bug.
- NUNCA chamar ``pd.isna`` em código de página — usar ``is_missing``
  deste módulo. Centralizar permite um único lugar para evoluir a
  semantica (ex.: se um dia quisermos distinguir "missing" de
  "explicitamente zero").
- ``is_missing`` cobre os sentinels que aparecem em todo o data
  layer: ``None``, ``float('nan')``, ``pd.NA``, ``pd.NaT``, e
  strings vazias / whitespace-only.

Uso típico
----------
>>> from src.utils.safe import safe_int, safe_str, is_missing
>>> safe_int(pd.NA)
0
>>> safe_int(pd.NA, default="-")
'-'
>>> is_missing("")
True
>>> is_missing("  ")
True
>>> is_missing("Maria")
False
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def is_missing(value: Any) -> bool:
    """Return True when ``value`` is None, NaN, pd.NA, pd.NaT, or empty/blank.

    Single source of truth for "is this a missing value?" across the app.
    Catches None, ``float('nan')``, ``pd.NA``, ``pd.NaT``, empty strings,
    and whitespace-only strings. Falls through to False for any object
    that ``pd.isna`` does not understand (e.g. arbitrary user classes) —
    the same defensive behavior the legacy ``_is_missing`` in
    ``src.components.patient_header`` already implements.
    """
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def safe_int(value: Any, default: Any = 0) -> Any:
    """Return ``int(value)`` if ``value`` is a real number; ``default`` otherwise.

    Critical: do NOT use the pattern ``int(value) if value == value else 0``
    to "check for NaN" — that pattern raises ``TypeError: boolean value of
    NA is ambiguous`` on ``pd.NA`` (the sentinel carried by ``Int64``
    nullable columns from the Postgres backend).

    The ``default`` parameter accepts any type so callers can render the
    missing case differently (e.g. ``safe_int(score, default="-")``).
    """
    if is_missing(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: Any = 0.0) -> Any:
    """Return ``float(value)`` if ``value`` is a real number; ``default`` otherwise.

    Same NA-safety contract as :func:`safe_int`.
    """
    if is_missing(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_str(value: Any, default: Any = "") -> Any:
    """Return ``str(value).strip()`` if ``value`` is a real string; ``default`` otherwise.

    Empty / whitespace-only strings are treated as missing — same contract
    as :func:`is_missing`. Use this when rendering values into HTML/text
    so that ``pd.NA`` does not surface as the literal ``"<NA>"``.
    """
    if is_missing(value):
        return default
    try:
        s = str(value).strip()
        return s if s else default
    except Exception:
        return default


def safe_pct(value: Any, default: str = "0%") -> str:
    """Return a percentage-formatted string for ``value``; ``default`` if missing.

    Treats ``value`` as a fraction in [0, 1] and multiplies by 100 before
    formatting with zero decimals. Used for engagement_rate and similar
    fields that arrive as decimals (e.g., 0.85 → "85%").
    """
    if is_missing(value):
        return default
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return default
