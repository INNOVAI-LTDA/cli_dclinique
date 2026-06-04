"""Alerts page."""
from __future__ import annotations

import html
from urllib.parse import quote

import pandas as pd
import streamlit as st


CATEGORIES = ["Todos", "Enfermagem", "Médica", "Comercial", "Nutrição"]
PRIORITY_ORDER = {"Alta": 0, "Média": 1, "Baixa": 2}


def _alertas_css() -> str:
    return """
        <style>
            .alertas-page-title {
                color: #111827;
                font-size: 1.15rem;
                font-weight: 750;
                line-height: 1.2;
                margin: 0 0 0.5rem;
            }

            .alertas-caption {
                color: #64748b;
                font-size: 0.78rem;
                margin: 0 0 0.72rem;
            }

            .alertas-tabs {
                display: flex;
                flex-wrap: wrap;
                gap: 0.4rem;
                margin: 0.2rem 0 0.7rem;
            }

            .alertas-tab {
                align-items: center;
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 999px;
                color: #334155;
                display: inline-flex;
                font-size: 0.74rem;
                font-weight: 650;
                gap: 0.4rem;
                padding: 0.32rem 0.78rem;
            }

            .alertas-tab.is-active {
                background: #0f172a;
                border-color: #0f172a;
                color: #ffffff;
            }

            .alertas-tab-count {
                background: #f1f5f9;
                border-radius: 999px;
                color: #475569;
                font-size: 0.68rem;
                font-weight: 700;
                padding: 0.05rem 0.42rem;
            }

            .alertas-tab.is-active .alertas-tab-count {
                background: #1e293b;
                color: #e2e8f0;
            }

            .alertas-tab-button-row > div[data-testid="stButton"] {
                margin-top: -2.4rem;
            }

            div[data-testid="stButton"] > button.alertas-tab-button {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 999px;
                color: transparent;
                cursor: pointer;
                font-size: 0.74rem;
                font-weight: 650;
                min-height: 1.9rem;
                padding: 0.2rem 0.78rem;
            }

            div[data-testid="stButton"] > button.alertas-tab-button:hover {
                background: transparent;
                border-color: transparent;
                color: transparent;
            }

            div[data-testid="stButton"] > button.alertas-tab-button:focus {
                outline: none;
            }

            .alertas-secondary {
                display: flex;
                gap: 0.7rem;
                margin: 0.4rem 0 0.7rem;
            }

            .alertas-table-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                margin-top: 0.32rem;
                overflow: hidden;
                padding: 0.4rem;
            }

            .alertas-table-header {
                background: #f8fafc;
                border-bottom: 1px solid #e5e7eb;
                color: #0f172a;
                display: flex;
                font-size: 0.68rem;
                font-weight: 750;
                gap: 0.6rem;
                line-height: 1.15;
                padding: 0.5rem 0.7rem;
            }

            .alertas-table-header > div {
                white-space: nowrap;
            }

            .alertas-row {
                align-items: center;
                border-bottom: 1px solid #edf2f7;
                color: #1f2937;
                display: flex;
                font-size: 0.74rem;
                gap: 0.6rem;
                line-height: 1.2;
                padding: 0.5rem 0.7rem;
            }

            .alertas-row:last-child {
                border-bottom: none;
            }

            .alertas-row:hover {
                background: #f8fbff;
            }

            .alertas-cell-paciente { flex: 2.2; font-weight: 650; color: #0f172a; }
            .alertas-name-link {
                color: #0f172a;
                display: inline-block;
                font-weight: 700;
                padding: 0.36rem 0.5rem;
                text-decoration: none;
            }

            .alertas-name-link:hover {
                color: #2563eb;
                cursor: pointer;
                text-decoration: underline;
            }

            .alertas-name-link:focus-visible {
                border-radius: 4px;
                outline: 2px solid #2563eb;
                outline-offset: 2px;
            }
            .alertas-cell-tipo { flex: 2.0; color: #1f2937; }
            .alertas-cell-desc { flex: 3.2; color: #475569; }
            .alertas-cell-prio { flex: 1.0; }
            .alertas-cell-data { flex: 1.0; color: #334155; }
            .alertas-cell-status { flex: 1.4; }
            .alertas-cell-action { flex: 0.9; display: flex; justify-content: flex-end; }

            .alertas-badge {
                border-radius: 999px;
                display: inline-flex;
                font-size: 0.68rem;
                font-weight: 750;
                line-height: 1;
                padding: 0.22rem 0.55rem;
            }

            .alertas-prio-alta { background: #fee2e2; color: #b91c1c; }
            .alertas-prio-media { background: #fef3c7; color: #b45309; }
            .alertas-prio-baixa { background: #dcfce7; color: #166534; }

            .alertas-status-aberto { background: #fee2e2; color: #b91c1c; }
            .alertas-status-andamento { background: #dbeafe; color: #1d4ed8; }
            .alertas-status-analise { background: #fef3c7; color: #b45309; }
            .alertas-status-default { background: #e5e7eb; color: #374151; }

            .alertas-empty {
                color: #64748b;
                font-size: 0.82rem;
                padding: 1.4rem;
                text-align: center;
            }

            .alertas-footer {
                align-items: center;
                display: flex;
                justify-content: center;
                margin-top: 0.82rem;
            }

            div[data-testid="stButton"] > button.alertas-footer-button {
                background: transparent;
                border: none;
                color: #2563eb;
                font-size: 0.78rem;
                font-weight: 650;
                min-height: 1.7rem;
                padding: 0.2rem 0.6rem;
            }

            div[data-testid="stButton"] > button.alertas-footer-button:hover {
                color: #1d4ed8;
                text-decoration: underline;
            }
        </style>
        """


def _format_date(value: object) -> str:
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return "--"
    return date.strftime("%d/%m/%Y")


def _priority_class(priority: str) -> str:
    normalized = (priority or "").lower()
    if normalized == "alta":
        return "alertas-prio-alta"
    if normalized in {"média", "media"}:
        return "alertas-prio-media"
    return "alertas-prio-baixa"


def _status_class(status: str) -> str:
    normalized = (status or "").lower()
    if "aberto" in normalized:
        return "alertas-status-aberto"
    if "andamento" in normalized:
        return "alertas-status-andamento"
    if "análise" in normalized or "analise" in normalized:
        return "alertas-status-analise"
    return "alertas-status-default"


def _category_counts(alerts: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {"Todos": int(len(alerts))}
    for category in CATEGORIES[1:]:
        counts[category] = int((alerts["category"] == category).sum())
    return counts


def _ensure_state() -> None:
    st.session_state.setdefault("alertas_category", "Todos")
    st.session_state.setdefault("alertas_priority", "Todas")
    st.session_state.setdefault("alertas_status", "Todos")
    st.session_state.setdefault("alertas_query", "")


def _render_category_tabs(alerts: pd.DataFrame) -> None:
    counts = _category_counts(alerts)
    active = st.session_state.get("alertas_category", "Todos")

    chips = "".join(
        f'<span class="alertas-tab{" is-active" if category == active else ""}">'
        f'<span>{html.escape(category)}</span>'
        f'<span class="alertas-tab-count">{counts.get(category, 0)}</span>'
        "</span>"
        for category in CATEGORIES
    )
    st.markdown(f'<div class="alertas-tabs">{chips}</div>', unsafe_allow_html=True)

    # Overlay real (transparent) buttons on top of the visual chips so the
    # category filter remains clickable without disturbing the styled pills.
    st.markdown('<div class="alertas-tab-button-row">', unsafe_allow_html=True)
    cols = st.columns(len(CATEGORIES))
    for idx, category in enumerate(CATEGORIES):
        with cols[idx]:
            if st.button(
                category,
                key=f"alertas_tab_{category}",
            ):
                st.session_state["alertas_category"] = category
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _apply_filters(alerts: pd.DataFrame) -> pd.DataFrame:
    filtered = alerts.copy()
    category = st.session_state.get("alertas_category", "Todos")
    priority = st.session_state.get("alertas_priority", "Todas")
    status = st.session_state.get("alertas_status", "Todos")
    query = (st.session_state.get("alertas_query", "") or "").strip().lower()

    if category != "Todos":
        filtered = filtered[filtered["category"] == category]
    if priority != "Todas":
        filtered = filtered[filtered["priority"] == priority]
    if status != "Todos":
        filtered = filtered[filtered["status"] == status]
    if query:
        filtered = filtered[filtered["name"].astype(str).str.lower().str.contains(query, na=False)]

    filtered = filtered.assign(
        _priority_rank=filtered["priority"].map(PRIORITY_ORDER).fillna(3),
    )
    return filtered.sort_values(
        ["_priority_rank", "created_at"], ascending=[True, False]
    ).drop(columns=["_priority_rank"])


def _render_table(alerts: pd.DataFrame) -> None:
    if alerts.empty:
        st.markdown(
            '<div class="alertas-table-shell"><div class="alertas-empty">Nenhum alerta para os filtros selecionados.</div></div>',
            unsafe_allow_html=True,
        )
        return

    header_html = (
        '<div class="alertas-table-shell">'
        '<div class="alertas-table-header">'
        '<div style="flex:2.2">Paciente</div>'
        '<div style="flex:2.0">Tipo de alerta</div>'
        '<div style="flex:3.2">Descrição</div>'
        '<div style="flex:1.0">Prioridade</div>'
        '<div style="flex:1.0">Data</div>'
        '<div style="flex:1.4">Status</div>'
        "</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    for _, row in alerts.iterrows():
        patient_id = str(row.get("patient_id", ""))
        name = str(row.get("name", ""))
        alert_type = str(row.get("alert_type", ""))
        description = str(row.get("description", ""))
        priority = str(row.get("priority", ""))
        status = str(row.get("status", ""))
        created_at = _format_date(row.get("created_at"))

        safe_name = html.escape(name) if name else "-"
        safe_pid = quote(patient_id, safe="")
        safe_type = html.escape(alert_type)
        safe_desc = html.escape(description)
        safe_priority = html.escape(priority)
        safe_status = html.escape(status)

        # Patient name is rendered as a navigation link that triggers the same
        # query-param flow used on the Pacientes page, so the click on the
        # name opens the patient record without a separate button.
        paciente_html = (
            f'<a class="alertas-name-link" '
            f'href="?nav=Ficha%20do%20Paciente&patient_id={safe_pid}" '
            f'target="_self" rel="noopener">{safe_name}</a>'
        )

        row_html = (
            '<div class="alertas-row">'
            f'<div class="alertas-cell-paciente">{paciente_html}</div>'
            f'<div class="alertas-cell-tipo">{safe_type}</div>'
            f'<div class="alertas-cell-desc">{safe_desc}</div>'
            f'<div class="alertas-cell-prio"><span class="alertas-badge {_priority_class(priority)}">{safe_priority}</span></div>'
            f'<div class="alertas-cell-data">{created_at}</div>'
            f'<div class="alertas-cell-status"><span class="alertas-badge {_status_class(status)}">{safe_status}</span></div>'
            "</div>"
        )
        st.markdown(row_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_secondary_filters(alerts: pd.DataFrame) -> None:
    priority_options = ["Todas", "Alta", "Média", "Baixa"]
    status_options = ["Todos"] + sorted(alerts["status"].dropna().unique().tolist())
    cols = st.columns([1, 1, 1.4, 1.4])
    cols[0].selectbox("Prioridade", priority_options, key="alertas_priority")
    cols[1].selectbox("Status", status_options, key="alertas_status")
    cols[2].text_input("Buscar paciente", placeholder="Buscar por nome...", key="alertas_query")


def render(data):
    _ensure_state()
    st.markdown(_alertas_css(), unsafe_allow_html=True)

    st.markdown('<h1 class="alertas-page-title">Alertas</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="alertas-caption">Alertas fictícios para validar fluxo de priorização e abertura da ficha.</p>',
        unsafe_allow_html=True,
    )

    patients = data["patients"][["patient_id", "name"]]
    alerts = data["alerts"].merge(patients, on="patient_id", how="left")

    _render_category_tabs(alerts)
    _render_secondary_filters(alerts)
    filtered = _apply_filters(alerts)
    _render_table(filtered)

    # Footer link: resets the secondary filters and category, matching the
    # "Ver todos os alertas →" affordance shown in the layout reference.
    st.markdown('<div class="alertas-footer">', unsafe_allow_html=True)
    if st.button(
        "Ver todos os alertas →",
        key="alertas_view_all",
    ):
        st.session_state["alertas_category"] = "Todos"
        st.session_state["alertas_priority"] = "Todas"
        st.session_state["alertas_status"] = "Todos"
        st.session_state["alertas_query"] = ""
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
