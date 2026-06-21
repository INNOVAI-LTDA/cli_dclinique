"""Decision map page."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from src.charts.decision_map import quadrants
from src.metrics import patient_summary
from src.utils.safe import safe_int, safe_pct


def _decision_map_css() -> str:
    return """
        <style>
            .dm-section-gap {
                height: 0.45rem;
            }

            .dm-map-shell {
                align-items: start;
                display: grid;
                gap: 0;
                grid-template-columns: 0 minmax(0, 1fr);
                transition: grid-template-columns 180ms ease, gap 180ms ease;
            }

            .dm-patient-toggle {
                opacity: 0;
                pointer-events: none;
                position: absolute;
            }

            .dm-side-panel {
                min-width: 0;
                opacity: 0;
                overflow: hidden;
                pointer-events: none;
                transform: translateX(-0.75rem);
                transition: opacity 180ms ease, transform 180ms ease;
            }

            .dm-panel-frame {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-left: 3px solid #4f46e5;
                border-radius: 9px;
                box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
                max-width: 100%;
                padding: 0.78rem;
                width: 280px;
            }

            .dm-panel-header {
                align-items: start;
                display: grid;
                gap: 0.5rem;
                grid-template-columns: 1fr auto;
                margin-bottom: 0.72rem;
            }

            .dm-panel-eyebrow {
                color: #6b7280;
                font-size: 0.68rem;
                font-weight: 700;
                letter-spacing: 0.02em;
                line-height: 1;
                margin-bottom: 0.28rem;
                text-transform: uppercase;
            }

            .dm-panel-name {
                color: #111827;
                font-size: 0.92rem;
                font-weight: 750;
                line-height: 1.2;
            }

            .dm-panel-close {
                align-items: center;
                border: 1px solid #e5e7eb;
                border-radius: 999px;
                color: #6b7280;
                cursor: pointer;
                display: inline-flex;
                font-size: 1rem;
                font-weight: 600;
                height: 1.65rem;
                justify-content: center;
                line-height: 1;
                width: 1.65rem;
            }

            .dm-panel-close:hover {
                background: #f9fafb;
                color: #111827;
            }

            .dm-panel-row {
                border-top: 1px solid #f3f4f6;
                padding: 0.48rem 0;
            }

            .dm-panel-row:first-of-type {
                border-top: none;
            }

            .dm-panel-label {
                color: #6b7280;
                font-size: 0.68rem;
                font-weight: 600;
                line-height: 1.1;
                margin-bottom: 0.16rem;
            }

            .dm-panel-value {
                color: #111827;
                font-size: 0.78rem;
                font-weight: 600;
                line-height: 1.2;
            }

            .dm-patient-panel {
                display: none;
            }

            .dm-grid-container {
                display: grid;
                gap: 0.55rem;
                grid-template-columns: 1fr 1fr;
            }

            .dm-quadrant-card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 9px;
                box-shadow: 0 1px 1px rgba(15, 23, 42, 0.03);
                min-height: 132px;
                padding: 0.62rem 0.78rem;
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

            .dm-patient-dot-list {
                align-content: flex-start;
                display: flex;
                flex-wrap: wrap;
                gap: 0.38rem;
            }

            .dm-patient-dot {
                align-items: center;
                border: 1px solid #d1d5db;
                border-radius: 999px;
                cursor: pointer;
                display: flex;
                font-size: 0.72rem;
                font-weight: 800;
                height: 2.25rem;
                justify-content: center;
                line-height: 1;
                transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
                width: 2.25rem;
            }

            .dm-patient-dot:hover {
                box-shadow: 0 4px 10px rgba(15, 23, 42, 0.12);
                transform: translateY(-1px);
            }

            .dm-empty-state {
                color: #9ca3af;
                font-size: 0.75rem;
                font-style: italic;
                padding: 0.5rem 0;
                text-align: center;
            }

            .dm-quadrant-engaged-satisfied {
                border-left: 3px solid #16a34a;
            }

            .dm-quadrant-engaged-satisfied .dm-patient-dot {
                background: #dcfce7;
                border-color: #86efac;
                color: #166534;
            }

            .dm-quadrant-engaged-not-satisfied {
                border-left: 3px solid #f59e0b;
            }

            .dm-quadrant-engaged-not-satisfied .dm-patient-dot {
                background: #fef3c7;
                border-color: #fcd34d;
                color: #92400e;
            }

            .dm-quadrant-not-engaged-satisfied {
                border-left: 3px solid #3b82f6;
            }

            .dm-quadrant-not-engaged-satisfied .dm-patient-dot {
                background: #dbeafe;
                border-color: #93c5fd;
                color: #1d4ed8;
            }

            .dm-quadrant-not-engaged-not-satisfied {
                border-left: 3px solid #ef4444;
            }

            .dm-quadrant-not-engaged-not-satisfied .dm-patient-dot {
                background: #fee2e2;
                border-color: #fca5a5;
                color: #991b1b;
            }
        </style>
        """


def _patient_stats(row: pd.Series) -> dict[str, str]:
    """Generate display stats for a patient row.

    NA-safe coercion (2026-06-21): the previous implementation used
    the pattern ``int(score) if score == score else 0`` (a legacy
    NaN check) and called ``int(row.get("open_alerts", 0))`` without
    a guard. Both blow up with ``TypeError: boolean value of NA is
    ambiguous`` whenever the underlying ``Int64`` column carries
    ``pd.NA`` as the missing sentinel (which happens for patients
    with no entry in ``satisfaction_entries``). Reproduced in PRD
    with ``Claudia Helena.pdf`` import → Mapa de Decisão.

    The replacement routes every cast through ``src.utils.safe``,
    which uses ``pd.isna`` and falls back to a default for any
    missing/empty/uncastable value.
    """
    score_display = f"{safe_int(row.get('score'))}"
    alerts_display = str(safe_int(row.get("open_alerts")))
    engagement_display = safe_pct(row.get("engagement_rate"))

    return {
        "Engajamento": engagement_display,
        "Satisfação": f"{score_display}/10",
        "Alertas": alerts_display,
    }


def _patient_initials(name: str) -> str:
    """Return two display initials for a patient name."""
    parts = [part for part in str(name).strip().split() if part]
    if not parts:
        return "--"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def _patient_dot_html(row: pd.Series, target_id: str) -> str:
    """Generate HTML for a clickable patient dot."""
    initials = html.escape(_patient_initials(str(row["name"])))

    return (
        f'<label class="dm-patient-dot" for="{target_id}" title="Selecionar paciente">'
        f"{initials}"
        "</label>"
    )


def _patient_panel_html(row: pd.Series, target_id: str, quadrant_name: str) -> str:
    """Generate HTML for the selected patient side panel."""
    patient_name = html.escape(str(row["name"]))
    patient_id = html.escape(str(row["patient_id"]))
    quadrant = html.escape(quadrant_name)
    stats = _patient_stats(row)

    stats_html = "".join(
        '<div class="dm-panel-row">'
        f'<div class="dm-panel-label">{html.escape(label)}</div>'
        f'<div class="dm-panel-value">{html.escape(value)}</div>'
        "</div>"
        for label, value in stats.items()
    )

    return (
        f'<div class="dm-patient-panel dm-panel-{target_id}">'
        '<div class="dm-panel-header">'
        "<div>"
        '<div class="dm-panel-eyebrow">Paciente</div>'
        f'<div class="dm-panel-name">{patient_name}</div>'
        "</div>"
        '<label class="dm-panel-close" for="dm-patient-none" title="Fechar">×</label>'
        "</div>"
        '<div class="dm-panel-row">'
        '<div class="dm-panel-label">ID</div>'
        f'<div class="dm-panel-value">{patient_id}</div>'
        "</div>"
        '<div class="dm-panel-row">'
        '<div class="dm-panel-label">Quadrante</div>'
        f'<div class="dm-panel-value">{quadrant}</div>'
        "</div>"
        f"{stats_html}"
        "</div>"
    )


def _quadrant_card(title: str, count: int, dots_html: str, style_class: str) -> str:
    """Generate HTML for a quadrant card."""
    if not dots_html:
        content_html = '<div class="dm-empty-state">Sem pacientes neste quadrante</div>'
    else:
        content_html = f'<div class="dm-patient-dot-list">{dots_html}</div>'

    return (
        f'<div class="dm-quadrant-card {style_class}">'
        f'<div class="dm-quadrant-title">{html.escape(title)}</div>'
        f'<div class="dm-quadrant-count">{count} paciente(s)</div>'
        f"{content_html}"
        "</div>"
    )


def _selected_patient_css(target_ids: list[str]) -> str:
    """Generate CSS selectors for selected patient state."""
    if not target_ids:
        return ""

    shell_selectors = ",\n".join(f"#{target_id}:checked ~ .dm-map-shell" for target_id in target_ids)
    panel_selectors = ",\n".join(f"#{target_id}:checked ~ .dm-map-shell .dm-side-panel" for target_id in target_ids)
    patient_panel_selectors = "\n".join(
        f"#{target_id}:checked ~ .dm-map-shell .dm-panel-{target_id} {{ display: block; }}"
        for target_id in target_ids
    )
    dot_selectors = "\n".join(
        (
            f"#{target_id}:checked ~ .dm-map-shell label[for='{target_id}'] "
            "{ border-color: #4f46e5; box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.18); transform: translateY(-1px); }"
        )
        for target_id in target_ids
    )

    return (
        "<style>"
        f"{shell_selectors} {{ grid-template-columns: minmax(230px, 280px) minmax(0, 1fr); gap: 0.7rem; }}"
        f"{panel_selectors} {{ opacity: 1; pointer-events: auto; transform: translateX(0); }}"
        f"{patient_panel_selectors}"
        f"{dot_selectors}"
        "@media (max-width: 760px) {"
        f"{shell_selectors} {{ grid-template-columns: 1fr; gap: 0.55rem; }}"
        ".dm-grid-container { grid-template-columns: 1fr; }"
        "}"
        "</style>"
    )


def _decision_map_html(groups: dict[str, pd.DataFrame]) -> str:
    """Generate the complete interactive decision map HTML."""
    quadrants_config = [
        ("Engajado + Satisfeito", "dm-quadrant-engaged-satisfied"),
        ("Engajado + Não satisfeito", "dm-quadrant-engaged-not-satisfied"),
        ("Não engajado + Satisfeito", "dm-quadrant-not-engaged-satisfied"),
        ("Não engajado + Não satisfeito", "dm-quadrant-not-engaged-not-satisfied"),
    ]

    target_ids: list[str] = []
    inputs_html = [
        '<input class="dm-patient-toggle" type="radio" name="dm-selected-patient" id="dm-patient-none" checked>'
    ]
    panels_html: list[str] = []
    cards_html: list[str] = []
    patient_index = 0

    for title, style_class in quadrants_config:
        df = groups[title]
        dots: list[str] = []

        for _, row in df.iterrows():
            target_id = f"dm-patient-{patient_index}"
            patient_index += 1
            target_ids.append(target_id)
            inputs_html.append(
                f'<input class="dm-patient-toggle" type="radio" name="dm-selected-patient" id="{target_id}">'
            )
            dots.append(_patient_dot_html(row, target_id))
            panels_html.append(_patient_panel_html(row, target_id, title))

        cards_html.append(_quadrant_card(title, len(df), "".join(dots), style_class))

    return (
        _selected_patient_css(target_ids)
        + "".join(inputs_html)
        + '<div class="dm-map-shell">'
        + '<aside class="dm-side-panel"><div class="dm-panel-frame">'
        + "".join(panels_html)
        + "</div></aside>"
        + '<div class="dm-grid-container">'
        + "".join(cards_html)
        + "</div>"
        + "</div>"
    )


def render(data):
    st.markdown(_decision_map_css(), unsafe_allow_html=True)
    st.title("Mapa de Decisão")
    st.caption("Matriz 2x2 baseada em engajamento mockado e satisfação declarada.")

    summary = patient_summary(data)
    sat = summary["is_satisfied"].fillna(False)
    eng = summary["is_engaged"]
    # Single vectorised write replaces 4 sequential boolean `.loc` scans.
    summary["quadrante"] = np.select(
        [eng & sat, eng & ~sat, ~eng & sat],
        ["Engajado + Satisfeito", "Engajado + Não satisfeito", "Não engajado + Satisfeito"],
        default="Não engajado + Não satisfeito",
    )

    groups = quadrants(summary)

    st.markdown('<div class="dm-section-gap"></div>', unsafe_allow_html=True)
    st.markdown(_decision_map_html(groups), unsafe_allow_html=True)
