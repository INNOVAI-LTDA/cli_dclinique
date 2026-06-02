"""Derived metrics used across pages."""
from __future__ import annotations

import pandas as pd

SATISFIED_STATUSES = {"Satisfeito"}


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
    summary["engagement_rate"] = summary.apply(
        lambda row: 0 if row["sessions_expected"] == 0 else row["sessions_completed"] / row["sessions_expected"], axis=1
    )
    summary["engagement_level"] = summary["engagement_rate"].apply(classify_engagement)
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
    summary["days_to_renewal"] = (pd.to_datetime(summary["end_date"]) - today).dt.days
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
        (today - pd.to_datetime(summary["last_weight_date"])).dt.days > 30
    )
    return summary


def classify_engagement(rate: float) -> str:
    if rate >= 0.7:
        return "Alto"
    if rate >= 0.3:
        return "Médio"
    return "Baixo"


def overview_kpis(summary: pd.DataFrame) -> dict[str, int]:
    return {
        "Pacientes em plano": int(summary["status"].isin(["Ativo", "Pausado", "Aguardando início"]).sum()),
        "Engajados": int(summary["is_engaged"].sum()),
        "Com alerta": int(summary["has_alert"].sum()),
        "Renovação próxima": int(summary["renewal_soon"].sum()),
        "Não engajados": int((summary["engagement_level"] == "Baixo").sum()),
        "Sem peso atualizado": int(summary["without_recent_weight"].sum()),
    }


def attention_patients(summary: pd.DataFrame) -> pd.DataFrame:
    return summary[summary["has_alert"] | summary["renewal_soon"] | summary["without_recent_weight"]].copy()
