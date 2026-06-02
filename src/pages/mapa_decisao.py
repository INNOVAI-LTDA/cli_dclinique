"""Decision map page."""
from __future__ import annotations

import html
import math

import pandas as pd
import streamlit as st

from src.charts.decision_map import quadrants
from src.components.badges import patient_chip
from src.components.patient_actions import render_open_patient_button
from src.metrics import patient_summary


def _decision_map_css() -> str:
    return """
        <style>
            .dm-section-gap {
                height: 0.45rem;
            }

            .dm-quadrant-card {
                border: 1px solid #e5e7eb;
                border-radius: 9px;
                padding: 0.62rem 0.78rem;
                background: #ffffff;
                min-height: 140px;
                box-shadow: 0 1px 1px rgba(15, 23, 42, 0.03);
            }

            .dm-quadrant-title {
                color: #374151;
                font-size: 0.85rem;
                font-weight: 700;
                line-height: 1.2;
                margin-bottom: 0.35rem;
            }

            .dm-quadrant-count {
                color: #6b7280;
                font-size: 0.72rem;
                font-weight: 500;
                line-height: 1;
                margin-bottom: 0.45rem;
            }

            .dm-patient-list {
                display: flex;
                flex-direction: column;
                gap: 0.28rem;
            }

            .dm-patient-row {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 0.44rem;
                align-items: center;
                padding: 0.22rem 0;
                border-bottom: 1px solid #f3f4f6;
            }

            .dm-patient-row:last-child {
                border-bottom: none;
            }

            .dm-patient-info {
                display: flex;
                flex-direction: column;
                gap: 0.08rem;
            }

            .dm-patient-name {
                color: #111827;
                font-size: 0.78rem;
                font-weight: 600;
                line-height: 1.1;
            }

            .dm-patient-stats {
                color: #6b7280;
                font-size: 0.68rem;
                line-height: 1.1;
            }

            .dm-action-btn {
                background: #4f46e5;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 0.25rem 0.55rem;
                font-size: 0.68rem;
                font-weight: 600;
                cursor: pointer;
                white-space: nowrap;
            }

            .dm-action-btn:hover {
                background: #4338ca;
            }

            .dm-empty-state {
                color: #9ca3af;
                font-size: 0.75rem;
                font-style: italic;
                text-align: center;
                padding: 0.5rem 0;
            }

            .dm-grid-container {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 0.55rem;
            }

            .dm-quadrant-engaged-satisfied {
                border-left: 3px solid #16a34a;
            }

            .dm-quadrant-engaged-not-satisfied {
                border-left: 3px solid #f59e0b;
            }

            .dm-quadrant-not-engaged-satisfied {
                border-left: 3px solid #3b82f6;
            }

            .dm-quadrant-not-engaged-not-satisfied {
                border-left: 3px solid #ef4444;
            }
        </style>
        """


def _patient_stats_html(row: pd.Series) -> str:
    """Generate stats HTML for a patient row."""
    engagement = row.get("engagement_rate", 0) * 100
    score = row.get("score", 0)
    alerts = int(row.get("open_alerts", 0))

    score_display = f"{int(score) if score == score else 0}"
    return f"Engajamento: {engagement:.0f}% | Satisfação: {score_display}/10 | Alertas: {alerts}"


def _patient_row_html(row: pd.Series, quadrant_name: str) -> str:
    """Generate HTML for a single patient row."""
    patient_name = html.escape(str(row["name"]))
    patient_id = str(row["patient_id"])
    stats = _patient_stats_html(row)

    return (
        '<div class="dm-patient-row">'
        '<div class="dm-patient-info">'
        f'<div class="dm-patient-name">{patient_name}</div>'
        f'<div class="dm-patient-stats">{stats}</div>'
        "</div>"
        f'<button class="dm-action-btn" onclick="window.location.href=\'?nav=Ficha_paciente&patient_id={patient_id}\'">Abrir ficha</button>'
        "</div>"
    )


def _quadrant_card(title: str, df: pd.DataFrame, style_class: str) -> str:
    """Generate HTML for a quadrant card."""
    count = len(df)

    if df.empty:
        content_html = '<div class="dm-empty-state">Sem pacientes neste quadrante</div>'
    else:
        rows_html = "".join(_patient_row_html(row, title) for _, row in df.iterrows())
        content_html = f'<div class="dm-patient-list">{rows_html}</div>'

    return (
        f'<div class="dm-quadrant-card {style_class}">'
        f'<div class="dm-quadrant-title">{html.escape(title)}</div>'
        f'<div class="dm-quadrant-count">{count} paciente(s)</div>'
        f"{content_html}"
        "</div>"
    )


def render(data):
    st.markdown(_decision_map_css(), unsafe_allow_html=True)
    st.title("Mapa de Decisão")
    st.caption("Matriz 2x2 baseada em engajamento mockado e satisfação declarada.")

    summary = patient_summary(data).copy()
    summary["quadrante"] = "Não engajado + Não satisfeito"
    summary.loc[summary["is_engaged"] & summary["is_satisfied"].fillna(False), "quadrante"] = "Engajado + Satisfeito"
    summary.loc[summary["is_engaged"] & ~summary["is_satisfied"].fillna(False), "quadrante"] = "Engajado + Não satisfeito"
    summary.loc[~summary["is_engaged"] & summary["is_satisfied"].fillna(False), "quadrante"] = "Não engajado + Satisfeito"

    groups = quadrants(summary)

    st.markdown('<div class="dm-section-gap"></div>', unsafe_allow_html=True)

    grid_html = (
        '<div class="dm-grid-container">'
        + _quadrant_card("Engajado + Satisfeito", groups["Engajado + Satisfeito"], "dm-quadrant-engaged-satisfied")
        + _quadrant_card("Engajado + Não satisfeito", groups["Engajado + Não satisfeito"], "dm-quadrant-engaged-not-satisfied")
        + _quadrant_card("Não engajado + Satisfeito", groups["Não engajado + Satisfeito"], "dm-quadrant-not-engaged-satisfied")
        + _quadrant_card("Não engajado + Não satisfeito", groups["Não engajado + Não satisfeito"], "dm-quadrant-not-engaged-not-satisfied")
        + '</div>'
    )

    st.markdown(grid_html, unsafe_allow_html=True)
