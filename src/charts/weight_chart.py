"""Weight evolution charts."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _weight_with_expected(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame) -> pd.DataFrame:
    df = weight_entries.merge(
        patient_goals[["patient_id", "initial_weight", "target_weight", "target_date"]], on="patient_id", how="left"
    ).copy()
    df["measurement_date"] = pd.to_datetime(df["measurement_date"])
    first_dates = df.groupby("patient_id")["measurement_date"].transform("min")
    target_dates = pd.to_datetime(df["target_date"])
    total_days = (target_dates - first_dates).dt.days.clip(lower=1)
    elapsed_days = (df["measurement_date"] - first_dates).dt.days.clip(lower=0)
    progress = (elapsed_days / total_days).clip(upper=1)
    df["expected_weight"] = df["initial_weight"] + (df["target_weight"] - df["initial_weight"]) * progress
    return df


def patient_weight_chart(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame, patient_id: str) -> go.Figure:
    df = _weight_with_expected(weight_entries, patient_goals)
    df = df[df["patient_id"] == patient_id].sort_values("measurement_date")
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title="Sem dados de peso")
        return fig
    fig.add_trace(go.Scatter(x=df["measurement_date"], y=df["expected_weight"], name="Peso esperado", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=df["measurement_date"], y=df["weight"], name="Peso realizado", mode="lines+markers"))
    fig.update_layout(yaxis_title="Peso (kg)", xaxis_title="Data", legend_title="Série")
    return fig


def average_weight_chart(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame) -> go.Figure:
    df = _weight_with_expected(weight_entries, patient_goals)
    df["measurement_date"] = df["measurement_date"].dt.date
    avg = df.groupby("measurement_date", as_index=False)[["expected_weight", "weight"]].mean()
    long = avg.melt("measurement_date", value_vars=["expected_weight", "weight"], var_name="Série", value_name="Peso médio")
    long["Série"] = long["Série"].map({"expected_weight": "Esperado", "weight": "Realizado"})
    return px.line(long, x="measurement_date", y="Peso médio", color="Série", markers=True)
