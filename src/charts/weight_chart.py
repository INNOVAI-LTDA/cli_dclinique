"""Weight evolution charts."""
from __future__ import annotations

import pandas as pd
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


def average_weight_chart(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame, height: int | None = None) -> go.Figure:
    df = _weight_with_expected(weight_entries, patient_goals)

    # Defensive: if measurement_date is missing or all-null, return empty figure
    if "measurement_date" not in df.columns or df["measurement_date"].dropna().empty:
        fig = go.Figure()
        fig.update_layout(title="Sem dados de peso", height=height)
        return fig

    # Ensure measurement_date is datetime and use resample on the index for robust monthly averages
    df = df.copy()
    df["measurement_date"] = pd.to_datetime(df["measurement_date"])
    df = df.set_index("measurement_date")
    avg = df[["expected_weight", "weight"]].resample("MS").mean().reset_index()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=avg["measurement_date"],
            y=avg["expected_weight"],
            name="Esperado",
            mode="lines",
            line={"color": "#3B82F6", "width": 2, "dash": "dash"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=avg["measurement_date"],
            y=avg["weight"],
            name="Realizado",
            mode="lines",
            line={"color": "#2563EB", "width": 2.2},
        )
    )

    fig.update_layout(
        margin={"l": 12, "r": 8, "t": 8, "b": 8},
        legend={"title": None, "orientation": "h", "x": 0.0, "y": 1.15},
        yaxis_title="Peso (kg)",
        xaxis_title="",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        height=height,
    )
    fig.update_xaxes(showgrid=False, tickformat="%b/%y")
    fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb")
    return fig
