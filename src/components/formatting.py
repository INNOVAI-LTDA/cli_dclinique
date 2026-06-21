"""Display-side formatting helpers.

The MAP shell renders a lot of optional columns (CPF, RG, telefone,
peso inicial, data de início, etc.) where the underlying value is
frequently ``None``, ``pd.NA``, ``NaN``, or an empty string. Before
this module existed the codebase used a mix of ``"—"`` (em-dash) and
``"--"`` (double hyphen) as placeholders, and ``st.dataframe`` would
leak ``NaN`` into the rendered cell. To unify the look across the app,
call-sites use :func:`display_dash` for inline text and
:func:`df_for_display` for DataFrames passed to ``st.dataframe`` /
``st.data_editor``.

The helpers are deliberately pure (no Streamlit import) so they can be
unit-tested without a runtime.
"""
from __future__ import annotations

import math

import pandas as pd

# Single character used everywhere a value is missing. The choice is a
# plain hyphen-minus so it is safe to embed in HTML tables without
# HTML-entity escaping and renders consistently across browsers and
# fonts (the em-dash ``—`` was inconsistent with the user's request).
PLACEHOLDER = "-"


def _is_empty(value: object) -> bool:
    """Return True when ``value`` should be treated as 'no value'."""
    if value is None:
        return True
    if value is pd.NA:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def display_dash(value: object, fallback: str = PLACEHOLDER) -> str:
    """Return ``str(value)`` or ``fallback`` when the value is empty.

    Empty means ``None``, ``pd.NA``, ``NaN``, or a string that is
    empty / whitespace-only. Anything else is returned as its
    ``str(...)`` (so ``123`` becomes ``"123"``, ``1.5`` becomes
    ``"1.5"``, etc.).

    Examples
    --------
    >>> display_dash(None)
    '-'
    >>> display_dash("")
    '-'
    >>> display_dash("  ")
    '-'
    >>> display_dash("Maria")
    'Maria'
    >>> display_dash(0)
    '0'
    """
    if _is_empty(value):
        return fallback
    return str(value)


def df_for_display(df: pd.DataFrame, placeholder: str = PLACEHOLDER) -> pd.DataFrame:
    """Return a copy of ``df`` with NaN/NA cells replaced by ``placeholder``.

    The replacement uses ``object`` dtype so numeric and timestamp
    columns still display as ``"-"`` (the alternative — calling
    ``fillna`` on a mixed DataFrame — coerces ints to floats and
    changes the rendered column type).

    The input DataFrame is not mutated.
    """
    if df.empty:
        return df.copy()
    as_object = df.astype(object)
    masked = as_object.where(as_object.notna(), placeholder)
    return masked
