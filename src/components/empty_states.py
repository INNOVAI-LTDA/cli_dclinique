"""Empty state helpers."""
from __future__ import annotations

import streamlit as st


def render_empty(message: str) -> None:
    st.info(message)
