"""Patients page."""
from __future__ import annotations

import html
import math
from urllib.parse import quote

import pandas as pd
import streamlit as st

from src.components.add_patient import (
    merge_extra_patients,
    render_add_patient_form,
    render_add_patient_toggle,
)
from src.components.ficha import merge_extra_fichas, patient_has_ficha
from src.metrics import patient_summary


# CSS for the per-row layout (matches the historical st.columns visuals).
_ROW_CSS = """
<style>
    .patients-row {
        align-items: center;
        border-bottom: 1px solid #edf2f7;
        display: flex;
        font-size: 0.76rem;
        gap: 0.6rem;
        padding: 0.5rem 0.7rem;
    }
    .patients-row:last-child { border-bottom: none; }
    .patients-row:hover { background: #f8fbff; }
    .patients-row .c-name  { flex: 3; font-weight: 700; }
    .patients-row .c-cell  { flex: 1; }
</style>
"""


DEFAULT_PAGE_SIZE = 10


def _patients_css() -> str:
    return """
        <style>
            .patients-page-title {
                color: #111827;
                font-size: 1.15rem;
                font-weight: 750;
                line-height: 1.2;
                margin: 0 0 0.72rem;
            }

            .patients-table-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                margin-top: 0.42rem;
                overflow: hidden;
            }

            .patients-table {
                border-collapse: collapse;
                color: #111827;
                font-size: 0.76rem;
                width: 100%;
            }

            .patients-table th {
                background: #f8fafc;
                border-bottom: 1px solid #e5e7eb;
                color: #0f172a;
                font-size: 0.68rem;
                font-weight: 750;
                line-height: 1.15;
                padding: 0.58rem 0.7rem;
                text-align: left;
                white-space: nowrap;
            }

            .patients-table td {
                border-bottom: 1px solid #edf2f7;
                color: #1f2937;
                line-height: 1.18;
                padding: 0.52rem 0.7rem;
                vertical-align: middle;
                white-space: nowrap;
            }

            .patients-table tr:last-child td {
                border-bottom: none;
            }

            .patients-table tbody tr:hover td {
                background: #f8fbff;
            }

            .patients-name-cell {
                font-weight: 650;
            }

            .patients-badge {
                border-radius: 999px;
                display: inline-flex;
                font-size: 0.66rem;
                font-weight: 750;
                line-height: 1;
                padding: 0.22rem 0.48rem;
            }

            .patients-badge-active,
            .patients-badge-high {
                background: #dcfce7;
                color: #15803d;
            }

            .patients-badge-paused,
            .patients-badge-medium {
                background: #fef3c7;
                color: #b45309;
            }

            .patients-badge-ended {
                background: #e5e7eb;
                color: #4b5563;
            }

            .patients-badge-low {
                background: #fed7aa;
                color: #c2410c;
            }

            .patients-empty {
                color: #64748b;
                font-size: 0.82rem;
                padding: 1.4rem;
                text-align: center;
            }

            .patients-table-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                margin-top: 0.32rem;
                overflow: hidden;
                padding: 0.4rem;
            }

            .patients-table-body {
                max-height: 220px;
                overflow: auto;
            }

            .patients-row-sep {
                height: 1px;
                background: #edf2f7;
                margin: 0.18rem 0;
            }

            /* name rendered as a navigation link */
            .patients-name-link {
                color: #0f172a;
                display: inline-block;
                font-weight: 700;
                padding: 0.36rem 0.5rem;
                text-decoration: none;
            }

            .patients-name-link:hover {
                color: #2563eb;
                cursor: pointer;
                text-decoration: underline;
            }

            .patients-name-link:focus-visible {
                outline: 2px solid #2563eb;
                outline-offset: 2px;
                border-radius: 4px;
            }

            .patients-footer {
                align-items: center;
                color: #334155;
                display: flex;
                font-size: 0.74rem;
                justify-content: space-between;
                margin-top: 0.78rem;
            }

            .patients-page-controls {
                align-items: center;
                display: flex;
                gap: 0.34rem;
            }

            .patients-page-pill {
                align-items: center;
                border-radius: 6px;
                color: #334155;
                display: inline-flex;
                font-weight: 650;
                height: 1.7rem;
                justify-content: center;
                min-width: 1.7rem;
            }

            .patients-page-pill.is-active {
                background: #dbeafe;
                color: #2563eb;
            }

            .patients-page-muted {
                color: #94a3b8;
            }

            .patients-page-size {
                align-items: center;
                display: flex;
                gap: 0.42rem;
            }

            .patients-page-size-select {
                align-items: center;
                border: 1px solid #dbe2ea;
                border-radius: 6px;
                display: inline-flex;
                font-weight: 650;
                gap: 0.58rem;
                height: 2rem;
                padding: 0 0.68rem;
            }

            /* opener icon removed per UX request */

            div[data-testid="stTextInput"] label,
            div[data-testid="stSelectbox"] label {
                color: #334155;
                font-size: 0.68rem;
                font-weight: 700;
                margin-bottom: 0.16rem;
            }

            div[data-testid="stTextInput"] input,
            div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                border-color: #dbe2ea;
                border-radius: 6px;
                font-size: 0.76rem;
                min-height: 2.18rem;
            }

            div[data-testid="stButton"] > button {
                border-radius: 6px;
                font-size: 0.74rem;
                font-weight: 700;
                min-height: 2.1rem;
            }

            .patients-clear-button div[data-testid="stButton"] > button {
                background: transparent;
                border: none;
                color: #2563eb;
                justify-content: flex-start;
                padding-left: 0;
            }
        </style>
        """


def _reset_filters() -> None:
    st.session_state["patients_query"] = ""
    st.session_state["patients_status"] = "Todos"
    st.session_state["patients_period"] = "Todos"
    st.session_state["patients_engagement"] = "Todos"
    st.session_state["patients_page"] = 1


def _format_date(value: object) -> str:
    date = pd.to_datetime(value, errors="coerce")
    if pd.isna(date):
        return "--"
    return date.strftime("%d/%m/%Y")


def _status_class(status: str) -> str:
    normalized = status.lower()
    if normalized == "ativo":
        return "patients-badge-active"
    if normalized == "pausado":
        return "patients-badge-paused"
    return "patients-badge-ended"


def _engagement_class(engagement: str) -> str:
    normalized = engagement.lower()
    if normalized == "alto":
        return "patients-badge-high"
    if normalized == "médio":
        return "patients-badge-medium"
    return "patients-badge-low"


def _frequency_by_patient(data: dict[str, pd.DataFrame]) -> pd.Series:
    items = data["treatment_plan_items"]
    if items.empty:
        return pd.Series(dtype=object)
    primary_items = items.sort_values(["patient_id", "sessions_expected"], ascending=[True, False])
    return primary_items.groupby("patient_id")["frequency_type"].first()


# Cached for the lifetime of the Streamlit cache; safe because the input is
# a hashable view onto the already-cached `get_data()` dict.
_frequency_by_patient_cached = st.cache_data(show_spinner=False)(_frequency_by_patient)


def _prepare_patient_rows(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    summary = patient_summary(data)
    summary["frequency_expected"] = summary["patient_id"].map(_frequency_by_patient_cached(data)).fillna("--")
    return summary.sort_values("name", kind="stable").reset_index(drop=True)


def _apply_filters(summary: pd.DataFrame) -> pd.DataFrame:
    filtered = summary.copy()
    query = st.session_state.get("patients_query", "").strip().lower()
    status = st.session_state.get("patients_status", "Todos")
    period = st.session_state.get("patients_period", "Todos")
    engagement = st.session_state.get("patients_engagement", "Todos")

    if query:
        filtered = filtered[
            filtered["normalized_name"].str.contains(query, na=False)
            | filtered["medical_record"].astype(str).str.lower().str.contains(query, na=False)
        ]
    if status != "Todos":
        filtered = filtered[filtered["status"] == status]
    if period == "Renovação próxima":
        filtered = filtered[filtered["renewal_soon"]]
    elif period == "Em andamento":
        filtered = filtered[filtered["status"].isin(["Ativo", "Pausado", "Aguardando início"])]
    elif period == "Encerrado":
        filtered = filtered[~filtered["status"].isin(["Ativo", "Pausado", "Aguardando início"])]
    if engagement != "Todos":
        filtered = filtered[filtered["engagement_level"] == engagement]

    return filtered.reset_index(drop=True)


def _render_filters(summary: pd.DataFrame) -> None:
    st.session_state.setdefault("patients_query", "")
    st.session_state.setdefault("patients_status", "Todos")
    st.session_state.setdefault("patients_period", "Todos")
    st.session_state.setdefault("patients_engagement", "Todos")
    st.session_state.setdefault("patients_page", 1)
    st.session_state.setdefault("patients_page_size", DEFAULT_PAGE_SIZE)

    status_options = ["Todos"] + sorted(summary["status"].dropna().unique().tolist())
    filter_cols = st.columns([1.55, 1.1, 1.1, 1.1, 0.7])
    filter_cols[0].text_input("Buscar", placeholder="Buscar por nome ou e-mail...", key="patients_query")
    filter_cols[1].selectbox("Status do plano", status_options, key="patients_status")
    filter_cols[2].selectbox("Período", ["Todos", "Em andamento", "Renovação próxima", "Encerrado"], key="patients_period")
    filter_cols[3].selectbox("Engajamento", ["Todos", "Alto", "Médio", "Baixo"], key="patients_engagement")
    with filter_cols[4]:
        st.markdown('<div class="patients-clear-button">', unsafe_allow_html=True)
        st.write("")
        st.button("Limpar filtros", key="patients_clear_filters", on_click=_reset_filters)
        st.markdown("</div>", unsafe_allow_html=True)
    # filters rendered above; table is rendered by `_render_table`


def _render_add_patient_row(data: dict[str, pd.DataFrame]) -> None:
    """Render the add-patient toggle (right-aligned) and, if open, the form.

    The toggle button is right-aligned to mirror the "Limpar filtros"
    column. When the form is open, it renders full-width on its own row
    below the toggle — that way the form fields are not squashed into a
    narrow side column.
    """
    _button_cols = st.columns([5.4, 0.9])
    with _button_cols[1]:
        render_add_patient_toggle()
    if st.session_state.get("add_patient_open", False):
        render_add_patient_form(data)


def _render_table(df: pd.DataFrame, data: dict[str, pd.DataFrame]) -> None:
    if df.empty:
        st.markdown(
            '<div class="patients-table-shell"><div class="patients-empty">Nenhum paciente encontrado com os filtros atuais.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Build the full table as a single HTML string. Previously this page
    # called `st.columns([3,1,1,1,1,1,1])` once per row, which dominated
    # the render time. A single `st.markdown` is ~3x faster and produces
    # the same visual layout.
    parts = [_ROW_CSS, '<div class="patients-table-shell">']
    parts.append(
        '<div class="patients-row" style="background:#f8fafc;font-weight:750;color:#0f172a;'
        'font-size:0.68rem;padding:0.5rem 0.7rem;border-bottom:1px solid #e5e7eb;">'
        '<div class="c-name">Nome</div>'
        '<div class="c-cell">Status do plano</div>'
        '<div class="c-cell">Data início</div>'
        '<div class="c-cell">Data fim</div>'
        '<div class="c-cell">Frequência esperada</div>'
        '<div class="c-cell">Engajamento</div>'
        '<div class="c-cell">Renovação</div>'
        "</div>"
    )

    for _, row in df.iterrows():
        patient_id = str(row.get("patient_id", ""))
        name = str(row.get("name", ""))
        status = str(row.get("status", ""))
        engagement = str(row.get("engagement_level", ""))

        safe_name = html.escape(name) if name else "-"
        safe_pid = quote(patient_id, safe="")
        # The deep-link target depends on whether the patient already has
        # a ficha: existing patients go to the Ficha do Paciente view,
        # newly added (no-plan) patients go to the Cadastro de Ficha.
        target_page = (
            "Cadastro de Ficha do Paciente"
            if not patient_has_ficha(patient_id, data)
            else "Ficha do Paciente"
        )
        safe_nav = quote(target_page, safe="")
        parts.append(
            '<div class="patients-row">'
            f'<div class="c-name"><a class="patients-name-link" '
            f'href="?nav={safe_nav}&patient_id={safe_pid}" '
            f'target="_self" rel="noopener">{safe_name}</a></div>'
            f'<div class="c-cell"><span class="patients-badge {_status_class(status)}">{html.escape(status)}</span></div>'
            f'<div class="c-cell">{_format_date(row.get("start_date"))}</div>'
            f'<div class="c-cell">{_format_date(row.get("end_date"))}</div>'
            f'<div class="c-cell">{html.escape(str(row.get("frequency_expected", "--")))}</div>'
            f'<div class="c-cell"><span class="patients-badge {_engagement_class(engagement)}">{html.escape(engagement)}</span></div>'
            f'<div class="c-cell">{_format_date(row.get("end_date")) if bool(row.get("is_renewal", False)) else "--"}</div>'
            "</div>"
        )

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _page_numbers(page: int, page_count: int) -> list[int | str]:
    if page_count <= 7:
        return list(range(1, page_count + 1))
    if page <= 4:
        return [1, 2, 3, 4, 5, "...", page_count]
    if page >= page_count - 3:
        return [1, "...", page_count - 4, page_count - 3, page_count - 2, page_count - 1, page_count]
    return [1, "...", page - 1, page, page + 1, "...", page_count]


def _pagination_bounds(total_rows: int) -> tuple[int, int]:
    page_size = int(st.session_state.get("patients_page_size", DEFAULT_PAGE_SIZE))
    page_count = max(math.ceil(total_rows / page_size), 1)
    current_page = min(max(int(st.session_state.get("patients_page", 1)), 1), page_count)
    st.session_state["patients_page"] = current_page
    return (current_page - 1) * page_size, current_page * page_size


def _render_pagination(total_rows: int) -> None:
    page_size = int(st.session_state.get("patients_page_size", DEFAULT_PAGE_SIZE))
    page_count = max(math.ceil(total_rows / page_size), 1)
    current_page = min(max(int(st.session_state.get("patients_page", 1)), 1), page_count)
    start = 0 if total_rows == 0 else (current_page - 1) * page_size + 1
    end = min(current_page * page_size, total_rows)

    page_html = "".join(
        f'<span class="patients-page-pill{" is-active" if item == current_page else ""}">{item}</span>'
        if isinstance(item, int)
        else '<span class="patients-page-muted">...</span>'
        for item in _page_numbers(current_page, page_count)
    )

    st.markdown(
        '<div class="patients-footer">'
        f"<div>{start}-{end} de {total_rows}</div>"
        f'<div class="patients-page-controls"><span class="patients-page-muted">‹</span>{page_html}<span class="patients-page-muted">›</span></div>'
        '<div class="patients-page-size">'
        "<span>Por página:</span>"
        f'<span class="patients-page-size-select">{page_size}⌄</span>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render(data):
    st.markdown(_patients_css(), unsafe_allow_html=True)
    st.markdown('<h1 class="patients-page-title">Pacientes</h1>', unsafe_allow_html=True)

    # Merge session-added patients (registered via the add-patient widget)
    # before any cached metric runs — `merge_extra_patients` returns the
    # same dict instance when there are no extras, keeping the
    # `@st.cache_data` consumers warm. `merge_extra_fichas` is then
    # applied for the same reason so the table's per-row link target
    # sees freshly-cadastradas fichas when computing `patient_has_ficha`.
    data = merge_extra_patients(data)
    data = merge_extra_fichas(data)

    summary = _prepare_patient_rows(data)
    _render_filters(summary)
    _render_add_patient_row(data)
    filtered = _apply_filters(summary)

    start, end = _pagination_bounds(len(filtered))
    _render_table(filtered.iloc[start:end], data)
    _render_pagination(len(filtered))
