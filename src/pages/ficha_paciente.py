"""Patient detail page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.charts.execution_chart import execution_bar
from src.charts.weight_chart import patient_weight_chart
from src.components.empty_states import render_empty
from src.components.patient_header import render_patient_header
from src.components.tables import render_table
from src.metrics import patient_summary


def render(data):
    st.title("Ficha do Paciente")
    st.caption("Ficha construída com dados fictícios; campos espelham o contrato planejado para dados reais.")
    summary = patient_summary(data)
    if summary.empty:
        render_empty("Nenhum paciente disponível para exibir a ficha.")
        return

    valid_patient_ids = set(summary["patient_id"].tolist())
    selected_patient_id = st.session_state.get("selected_patient_id")
    if selected_patient_id not in valid_patient_ids:
        selected_patient_id = summary.iloc[0]["patient_id"]
        st.session_state["selected_patient_id"] = selected_patient_id

    patient_ids = summary["patient_id"].tolist()
    patient_labels = summary.set_index("patient_id")["name"].to_dict()
    selected_patient_id = st.selectbox(
        "Trocar paciente",
        patient_ids,
        index=patient_ids.index(selected_patient_id),
        format_func=lambda pid: patient_labels.get(pid, pid),
    )
    if selected_patient_id != st.session_state["selected_patient_id"]:
        st.session_state["selected_patient_id"] = selected_patient_id
        st.rerun()

    patient = summary.loc[summary["patient_id"] == st.session_state["selected_patient_id"]].iloc[0].to_dict()
    render_patient_header(patient)

    goals = data["patient_goals"][data["patient_goals"]["patient_id"] == patient["patient_id"]]
    goal = goals.iloc[0] if not goals.empty else pd.Series(dtype=object)
    cols = st.columns(4)
    cols[0].metric("Objetivo", patient["main_goal"])
    cols[1].metric("Peso inicial", f"{goal.get('initial_weight', 0):.1f} kg")
    cols[2].metric("Peso atual", "—" if pd.isna(patient.get("current_weight")) else f"{patient['current_weight']:.1f} kg")
    cols[3].metric("Peso meta", f"{goal.get('target_weight', 0):.1f} kg")

    st.subheader("Peso esperado vs realizado")
    st.plotly_chart(patient_weight_chart(data["weight_entries"], data["patient_goals"], patient["patient_id"]), use_container_width=True)

    st.subheader("Plano e execução")
    execs = data["execution_summary"][data["execution_summary"]["patient_id"] == patient["patient_id"]].copy()
    if execs.empty:
        render_empty("Sem execução registrada para este paciente.")
    else:
        execs = execs.rename(
            columns={
                "procedure_raw": "Procedimento",
                "sessions_expected": "Previsto",
                "sessions_completed": "Realizado",
                "sessions_remaining": "Restante",
                "status": "Status",
            }
        )
        render_table(execs[["Procedimento", "Previsto", "Realizado", "Restante", "Status"]])
        st.plotly_chart(execution_bar(data["execution_summary"], patient["patient_id"]), use_container_width=True)

    st.subheader("Últimos agendamentos")
    appointments = data["appointments"][data["appointments"]["patient_id"] == patient["patient_id"]].sort_values(
        "appointment_start", ascending=False
    )
    render_table(
        appointments[["appointment_start", "status", "professional", "scheduled_by"]].rename(
            columns={"appointment_start": "Data", "status": "Status", "professional": "Profissional", "scheduled_by": "Agendado por"}
        )
    )

    st.subheader("Alertas do paciente")
    alerts = data["alerts"][data["alerts"]["patient_id"] == patient["patient_id"]]
    if alerts.empty:
        st.success("Sem alertas para este paciente.")
    else:
        render_table(
            alerts[["created_at", "category", "priority", "status", "alert_type", "description", "comment"]].rename(
                columns={
                    "created_at": "Data",
                    "category": "Categoria",
                    "priority": "Prioridade",
                    "status": "Status",
                    "alert_type": "Alerta",
                    "description": "Descrição",
                    "comment": "Comentário",
                }
            )
        )

    st.subheader("Observações / resumo")
    st.write(goal.get("goal_notes", "Resumo ainda não informado."))
