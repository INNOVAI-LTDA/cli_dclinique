"""Derived metrics used across pages."""
from __future__ import annotations

import pandas as pd
import streamlit as st

SATISFIED_STATUSES = {"Satisfeito"}


@st.cache_data(show_spinner=False)
def patient_summary(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    patients = data["patients"].copy()
    plans = data["treatment_plans"]
    execs = data["execution_summary"]
    satisfaction = data["satisfaction_entries"]
    alerts = data["alerts"]
    weights = data["weight_entries"]

    agg = execs.groupby("patient_id", as_index=False).agg(
        sessions_expected=("sessions_expected", "sum"),
        sessions_completed=("sessions_completed", "sum"),
        sessions_remaining=("sessions_remaining", "sum"),
    )
    summary = patients.merge(agg, on="patient_id", how="left").merge(
        plans[["patient_id", "plan_id", "budget_code", "status", "main_goal", "start_date", "end_date", "is_renewal"]],
        on="patient_id",
        how="left",
    )
    summary[["sessions_expected", "sessions_completed", "sessions_remaining"]] = summary[
        ["sessions_expected", "sessions_completed", "sessions_remaining"]
    ].fillna(0)
    # Vectorised engagement rate (replaces an `apply(axis=1)` Python loop).
    # `np.errstate(divide="ignore")` NAO silencia `ZeroDivisionError` --
    # a Series.__truediv__ do pandas dispatcha pro `/` nativo do Python
    # quando ha 0 no denominador, e Python levanta (nao emite warning).
    # Por isso substituimos 0 por NaN antes da divisao: o .fillna(0) na
    # proxima linha cobre o caso "sem expectativa" sem levantar excecao.
    expected = summary["sessions_expected"].replace(0, pd.NA)
    with __import__("numpy").errstate(divide="ignore", invalid="ignore"):
        rate = summary["sessions_completed"] / expected
    summary["engagement_rate"] = rate.fillna(0)
    summary["engagement_level"] = _classify_engagement_vector(summary["engagement_rate"])
    summary["is_engaged"] = summary["engagement_level"].isin(["Alto"])

    latest_sat = satisfaction.sort_values("date").groupby("patient_id").tail(1)
    latest_sat = latest_sat.assign(is_satisfied=latest_sat["satisfaction_status"].isin(SATISFIED_STATUSES))
    summary = summary.merge(
        latest_sat[["patient_id", "score", "satisfaction_status", "is_satisfied"]], on="patient_id", how="left"
    )

    open_alerts = alerts[alerts["status"] != "Resolvido"].groupby("patient_id").size().rename("open_alerts")
    summary = summary.merge(open_alerts, on="patient_id", how="left")
    summary["open_alerts"] = summary["open_alerts"].fillna(0).astype(int)
    summary["has_alert"] = summary["open_alerts"] > 0

    today = pd.Timestamp.today().normalize()
    # `end_date` and `last_weight_date` are already pd.Timestamp; no to_datetime
    # needed, which avoids a full-column parser pass on every call.
    summary["days_to_renewal"] = (summary["end_date"] - today).dt.days
    summary["renewal_soon"] = summary["days_to_renewal"].le(30)

    latest_weight = weights.sort_values("measurement_date").groupby("patient_id").tail(1)
    summary = summary.merge(
        latest_weight[["patient_id", "measurement_date", "weight"]].rename(
            columns={"measurement_date": "last_weight_date", "weight": "current_weight"}
        ),
        on="patient_id",
        how="left",
    )
    summary["without_recent_weight"] = summary["last_weight_date"].isna() | (
        (today - summary["last_weight_date"]).dt.days > 30
    )
    return summary


def _classify_engagement_vector(rates: "pd.Series[float]") -> "pd.Series[str]":
    """Vectorised replacement for the row-by-row `classify_engagement` apply."""
    return pd.cut(
        rates,
        bins=[-0.01, 0.3, 0.7, float("inf")],
        labels=["Baixo", "Médio", "Alto"],
    ).astype(str)


def classify_engagement(rate: float) -> str:
    if rate >= 0.7:
        return "Alto"
    if rate >= 0.3:
        return "Médio"
    return "Baixo"


@st.cache_data(show_spinner=False)
def overview_kpis(summary: pd.DataFrame) -> dict[str, int]:
    return {
        "Pacientes em plano": int(summary["status"].isin(["Ativo", "Pausado", "Aguardando início"]).sum()),
        "Engajados": int(summary["is_engaged"].sum()),
        "Com alerta": int(summary["has_alert"].sum()),
        "Renovação próxima": int(summary["renewal_soon"].sum()),
        "Não engajados": int((summary["engagement_level"] == "Baixo").sum()),
        "Sem peso atualizado": int(summary["without_recent_weight"].sum()),
    }


@st.cache_data(show_spinner=False)
def attention_patients(summary: pd.DataFrame) -> pd.DataFrame:
    return summary[summary["has_alert"] | summary["renewal_soon"] | summary["without_recent_weight"]].copy()
