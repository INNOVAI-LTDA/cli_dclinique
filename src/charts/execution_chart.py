"""Execution chart helpers."""
from __future__ import annotations

import pandas as pd
import plotly.express as px


def execution_bar(execution_summary: pd.DataFrame, patient_id: str):
    df = execution_summary[execution_summary["patient_id"] == patient_id]
    long = df.melt(id_vars="procedure_raw", value_vars=["sessions_completed", "sessions_remaining"], var_name="Tipo", value_name="Sessões")
    long["Tipo"] = long["Tipo"].map({"sessions_completed": "Realizado", "sessions_remaining": "Restante"})
    return px.bar(long, x="procedure_raw", y="Sessões", color="Tipo", barmode="stack")
