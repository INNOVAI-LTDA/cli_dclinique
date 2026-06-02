"""Overview page."""
from __future__ import annotations

import html
import math

import pandas as pd
import streamlit as st

from src.charts.weight_chart import average_weight_chart
from src.metrics import attention_patients, overview_kpis, patient_summary


def _overview_css() -> str:
    return """
        <style>
            .ov-section-gap {
                height: 0.45rem;
            }

            .ov-card {
                border: 1px solid #e5e7eb;
                border-radius: 9px;
                padding: 0.62rem 0.78rem;
                background: #ffffff;
                min-height: 94px;
                box-shadow: 0 1px 1px rgba(15, 23, 42, 0.03);
            }

            .ov-card-title {
                color: #374151;
                font-size: 0.82rem;
                font-weight: 600;
                line-height: 1.2;
            }

            .ov-card-value {
                margin-top: 0.1rem;
                color: #111827;
                font-size: 1.95rem;
                font-weight: 700;
                line-height: 1;
            }

            .ov-card-delta {
                margin-top: 0.33rem;
                font-size: 0.8rem;
                font-weight: 600;
            }

            .ov-delta-positive { color: #16a34a; }
            .ov-delta-warning { color: #f59e0b; }
            .ov-delta-critical { color: #ef4444; }

            .ov-panel-title {
                margin: 0 0 0.48rem;
                color: #111827;
                font-size: 0.92rem;
                font-weight: 700;
            }

            .ov-attention-list {
                display: flex;
                flex-direction: column;
                gap: 0.24rem;
            }

            .ov-attention-shell {
                min-height: 305px;
                height: 305px;
                display: flex;
                flex-direction: column;
            }

            .ov-attention-content {
                flex: 1;
            }

            .ov-attention-row {
                display: grid;
                grid-template-columns: 2rem 1fr auto;
                gap: 0.44rem;
                align-items: center;
                padding: 0.18rem 0;
            }

            .ov-avatar {
                width: 1.58rem;
                height: 1.58rem;
                border-radius: 999px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.68rem;
                font-weight: 700;
                color: #4f46e5;
                background: #ede9fe;
            }

            .ov-attention-name {
                color: #111827;
                font-size: 0.8rem;
                font-weight: 600;
                line-height: 1.1;
            }

            .ov-attention-reason {
                color: #4b5563;
                font-size: 0.73rem;
                line-height: 1.1;
            }

            .ov-priority {
                border-radius: 999px;
                font-size: 0.68rem;
                font-weight: 700;
                padding: 0.13rem 0.47rem;
            }

            .ov-priority-alta { background: #fee2e2; color: #b91c1c; }
            .ov-priority-media { background: #fef3c7; color: #b45309; }
            .ov-priority-baixa { background: #dcfce7; color: #166534; }

            .ov-alert-link-wrap {
                margin-top: 0.46rem;
                padding-top: 0.38rem;
                border-top: 1px solid #f1f5f9;
                text-align: center;
            }

            .ov-alert-link {
                color: #2563eb;
                font-size: 0.76rem;
                font-weight: 600;
                text-decoration: none;
            }

            .ov-alert-link:hover {
                text-decoration: underline;
            }
        </style>
        """


def _kpi_card(title: str, value: int, delta_text: str, tone: str) -> str:
    return (
        '<div class="ov-card">'
        f'<div class="ov-card-title">{html.escape(title)}</div>'
        f'<div class="ov-card-value">{value}</div>'
        f'<div class="ov-card-delta {tone}">{html.escape(delta_text)}</div>'
        "</div>"
    )


def _patient_initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "--"


def _priority(row: pd.Series) -> str:
    days = row.get("days_to_renewal")
    has_days = isinstance(days, (int, float)) and not math.isnan(days)
    if int(row.get("open_alerts", 0)) >= 2 or (has_days and days <= 15):
        return "Alta"
    if int(row.get("open_alerts", 0)) >= 1 or (has_days and days <= 30):
        return "Média"
    return "Baixa"


def _reason(row: pd.Series) -> str:
    alerts = int(row.get("open_alerts", 0))
    if alerts > 0:
        return f"{alerts} alerta(s) aberto(s)"
    days = row.get("days_to_renewal")
    if isinstance(days, (int, float)) and not math.isnan(days):
        return "Plano próximo do fim" if days <= 30 else f"{int(days)} dias para fim"
    if bool(row.get("without_recent_weight", False)):
        return "Sem atualização recente de peso"
    return str(row.get("main_goal", "Acompanhamento"))


def _avatar_style(priority: str) -> tuple[str, str]:
    palette = {
        "Alta": ("#fee2e2", "#b91c1c"),
        "Média": ("#fef3c7", "#b45309"),
        "Baixa": ("#dcfce7", "#166534"),
    }
    return palette.get(priority, ("#ede9fe", "#4f46e5"))


def _attention_row_html(row: pd.Series) -> str:
    priority = _priority(row)
    priority_class = {"Alta": "ov-priority-alta", "Média": "ov-priority-media", "Baixa": "ov-priority-baixa"}[priority]
    avatar_bg, avatar_fg = _avatar_style(priority)
    patient_name = html.escape(str(row["name"]))
    reason = html.escape(_reason(row))
    initials = html.escape(_patient_initials(str(row["name"])))
    return (
        '<div class="ov-attention-row">'
        f'<span class="ov-avatar" style="background:{avatar_bg};color:{avatar_fg};">{initials}</span>'
        '<div>'
        f'<div class="ov-attention-name">{patient_name}</div>'
        f'<div class="ov-attention-reason">{reason}</div>'
        "</div>"
        f'<span class="ov-priority {priority_class}">{priority}</span>'
        "</div>"
    )


def render(data):
    st.markdown(_overview_css(), unsafe_allow_html=True)
    st.title("Visão Geral")
    st.caption("Acompanhamento consolidado de performance clínica e operacional.")

    summary = patient_summary(data)
    kpis = overview_kpis(summary)

    patients_in_plan = max(kpis["Pacientes em plano"], 1)
    today = pd.Timestamp.today().normalize()
    starts = pd.to_datetime(summary["start_date"], errors="coerce")
    started_this_month = int((starts.dt.to_period("M") == today.to_period("M")).sum())

    engaged = kpis["Engajados"]
    alert_count = kpis["Com alerta"]
    renewal_soon = kpis["Renovação próxima"]

    cards = [
        _kpi_card("Pacientes em plano ›", kpis["Pacientes em plano"], f"+{started_this_month} este mês", "ov-delta-positive"),
        _kpi_card("Engajados", engaged, f"{(engaged / patients_in_plan) * 100:.1f}%", "ov-delta-positive"),
        _kpi_card("Com alerta", alert_count, f"{(alert_count / patients_in_plan) * 100:.1f}%", "ov-delta-critical"),
        _kpi_card("Renovação próxima ›", renewal_soon, f"{(renewal_soon / patients_in_plan) * 100:.1f}%", "ov-delta-warning"),
    ]

    cols = st.columns(4)
    for idx, card in enumerate(cards):
        cols[idx].markdown(card, unsafe_allow_html=True)

    st.markdown('<div class="ov-section-gap"></div>', unsafe_allow_html=True)

    col_chart, col_context = st.columns([1.7, 1])
    with col_chart:
        with st.container(border=True):
            st.markdown('<p class="ov-panel-title">Evolução do tratamento (peso médio)</p>', unsafe_allow_html=True)
            st.plotly_chart(
                average_weight_chart(data["weight_entries"], data["patient_goals"], height=305),
                width="stretch",
                config={"displayModeBar": False},
            )

    with col_context:
        with st.container(border=True):
            st.markdown('<p class="ov-panel-title">Pacientes que precisam de atenção</p>', unsafe_allow_html=True)
            attention = attention_patients(summary)
            if attention.empty:
                content_html = '<div class="ov-attention-empty">Nenhum paciente em atenção no mock atual.</div>'
            else:
                attention = attention.sort_values(["open_alerts", "days_to_renewal", "name"], ascending=[False, True, True]).head(5)
                rows_html = "".join(_attention_row_html(row) for _, row in attention.iterrows())
                content_html = f'<div class="ov-attention-list">{rows_html}</div>'

            panel_html = (
                '<div class="ov-attention-shell">'
                f'<div class="ov-attention-content">{content_html}</div>'
                '<div class="ov-alert-link-wrap"><a class="ov-alert-link" href="?nav=Alertas">Ver detalhes →</a></div>'
                '</div>'
            )
            st.markdown(panel_html, unsafe_allow_html=True)
