"""Reusable patient navigation actions."""
from __future__ import annotations

import streamlit as st

from src.navigation import open_patient


def render_open_patient_button(patient_id: str, key: str, label: str = "Abrir ficha") -> None:
    """Render a button that opens the selected patient record."""
    if st.button(label, key=key):
        open_patient(patient_id)