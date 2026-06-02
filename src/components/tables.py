"""Reusable table formatting helpers."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_table(df: pd.DataFrame, columns: list[str] | None = None) -> None:
    view = df[columns].copy() if columns else df.copy()
    st.dataframe(view, width="stretch", hide_index=True)
