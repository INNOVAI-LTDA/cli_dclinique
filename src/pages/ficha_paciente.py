"""Patient detail page."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.charts.weight_chart import patient_weight_chart
from src.components.empty_states import render_empty
from src.components.patient_header import render_patient_header
from src.metrics import patient_summary
from src.navigation import go_to


def _page_css() -> str:
    return """
        <style>
            .ficha-back-link {
                color: #2563eb;
                display: inline-flex;
                font-size: 0.78rem;
                font-weight: 600;
                margin: 0.05rem 0 0.6rem;
                text-decoration: none;
            }
            .ficha-back-link:hover {
                text-decoration: underline;
            }
            .ficha-section-title {
                color: #0f172a;
                font-size: 0.92rem;
                font-weight: 700;
                letter-spacing: -0.005em;
                margin: 0 0 0.55rem;
            }
            .ficha-info-row {
                align-items: flex-end;
                display: flex;
                flex-wrap: wrap;
                gap: 1.6rem;
                padding: 0.2rem 0 0.85rem;
            }
            .ficha-info-item {
                display: flex;
                flex-direction: column;
                gap: 0.18rem;
                min-width: 6.4rem;
            }
            .ficha-info-label {
                color: #64748b;
                font-size: 0.72rem;
                font-weight: 600;
                letter-spacing: 0.01em;
                text-transform: uppercase;
            }
            .ficha-info-value {
                color: #0f172a;
                font-size: 0.96rem;
                font-weight: 700;
                line-height: 1.1;
            }
            .ficha-card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 0.85rem 0.95rem 0.95rem;
            }
            .ficha-card .ficha-section-title {
                margin-top: 0;
            }
            .ficha-plan-table {
                border-collapse: collapse;
                font-size: 0.78rem;
                width: 100%;
            }
            .ficha-plan-table thead th {
                background: #f8fafc;
                border-bottom: 1px solid #e5e7eb;
                color: #475569;
                font-size: 0.7rem;
                font-weight: 700;
                padding: 0.5rem 0.6rem;
                text-align: left;
                text-transform: uppercase;
            }
            .ficha-plan-table tbody td {
                border-bottom: 1px solid #edf2f7;
                color: #1f2937;
                font-weight: 600;
                padding: 0.55rem 0.6rem;
                vertical-align: middle;
            }
            .ficha-plan-table tbody tr:last-child td {
                border-bottom: none;
            }
            .ficha-plan-table .num {
                color: #0f172a;
                text-align: right;
                width: 4.4rem;
            }
            .ficha-plan-table .item-name {
                color: #0f172a;
                font-weight: 700;
            }
            .ficha-plan-table .item-sub {
                color: #64748b;
                font-size: 0.7rem;
                font-weight: 500;
                margin-left: 0.35rem;
            }
            .ficha-status-pill {
                border-radius: 999px;
                display: inline-block;
                font-size: 0.7rem;
                font-weight: 700;
                padding: 0.18rem 0.55rem;
            }
            .ficha-status-pill.is-active   { background: #dbeafe; color: #1d4ed8; }
            .ficha-status-pill.is-pending  { background: #fef3c7; color: #b45309; }
            .ficha-status-pill.is-done     { background: #dcfce7; color: #15803d; }
            .ficha-status-pill.is-neutral  { background: #e5e7eb; color: #4b5563; }
            .ficha-summary {
                color: #1f2937;
                font-size: 0.85rem;
                line-height: 1.5;
                margin: 0;
            }
            .ficha-switcher {
                color: #64748b;
                font-size: 0.72rem;
                font-weight: 600;
                letter-spacing: 0.01em;
                margin: 0 0 0.25rem;
                text-transform: uppercase;
            }
            div[data-testid="stSelectbox"] label {
                color: #334155;
                font-size: 0.68rem;
                font-weight: 700;
                margin-bottom: 0.16rem;
            }
            div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                border-color: #dbe2ea;
                border-radius: 6px;
                font-size: 0.78rem;
                min-height: 2.18rem;
            }
        </style>
        """


def _status_pill_class(status: str) -> str:
    if not isinstance(status, str):
        return "is-neutral"
    s = status.strip().lower()
    if s in {"em andamento", "em tratamento", "ativo"}:
        return "is-active"
    if s in {"pendente", "aguardando", "pausado"}:
        return "is-pending"
    if s in {"concluído", "concluido", "finalizado"}:
        return "is-done"
    if s in {"não iniciado", "nao iniciado"}:
        return "is-neutral"
    return "is-neutral"


def _format_weight(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        return f"{float(value):.1f} kg"
    except (TypeError, ValueError):
        return str(value)


def _format_age(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value)} anos"


def _render_back_link() -> None:
    if st.button("← Voltar para Pacientes", key="ficha_back_link", type="tertiary"):
        go_to("Pacientes")


def _render_patient_switcher(summary: pd.DataFrame) -> str:
    patient_ids = summary["patient_id"].tolist()
    patient_labels = summary.set_index("patient_id")["name"].to_dict()
    selected = st.session_state.get("selected_patient_id")
    if selected not in patient_ids:
        selected = patient_ids[0]
        st.session_state["selected_patient_id"] = selected

    st.markdown('<p class="ficha-switcher">Trocar paciente</p>', unsafe_allow_html=True)
    chosen = st.selectbox(
        "Selecionar paciente",
        patient_ids,
        index=patient_ids.index(selected),
        format_func=lambda pid: patient_labels.get(pid, pid),
        key="ficha_patient_select",
        label_visibility="collapsed",
    )
    if chosen != st.session_state["selected_patient_id"]:
        st.session_state["selected_patient_id"] = chosen
        st.rerun()
    return chosen


def _render_info_row(patient: dict, goal: pd.Series) -> None:
    items = [
        ("Idade", _format_age(patient.get("age"))),
        ("Objetivo", str(patient.get("main_goal") or "—")),
        ("Peso inicial", _format_weight(goal.get("initial_weight"))),
        ("Peso atual", _format_weight(patient.get("current_weight"))),
        ("Peso meta", _format_weight(goal.get("target_weight"))),
    ]
    html_parts = ['<div class="ficha-info-row">']
    for label, value in items:
        html_parts.append(
            '<div class="ficha-info-item">'
            f'<span class="ficha-info-label">{html.escape(label)}</span>'
            f'<span class="ficha-info-value">{html.escape(value)}</span>'
            "</div>"
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def _render_plan_table(execs: pd.DataFrame) -> None:
    if execs.empty:
        render_empty("Sem execução registrada para este paciente.")
        return

    rows_html = []
    for _, row in execs.iterrows():
        procedure = str(row.get("procedure_raw") or "—")
        category = str(row.get("procedure_category") or "").strip()
        if category and category.lower() != procedure.lower():
            item_html = (
                f'<span class="item-name">{html.escape(procedure)}</span>'
                f'<span class="item-sub">[{html.escape(category)}]</span>'
            )
        else:
            item_html = f'<span class="item-name">{html.escape(procedure)}</span>'
        status = str(row.get("status") or "—")
        pill_class = _status_pill_class(status)
        rows_html.append(
            "<tr>"
            f"<td>{item_html}</td>"
            f'<td class="num">{int(row.get("sessions_expected") or 0)}</td>'
            f'<td class="num">{int(row.get("sessions_completed") or 0)}</td>'
            f'<td class="num">{int(row.get("sessions_remaining") or 0)}</td>'
            f'<td><span class="ficha-status-pill {pill_class}">{html.escape(status)}</span></td>'
            "</tr>"
        )

    table_html = (
        '<table class="ficha-plan-table">'
        "<thead><tr>"
        "<th>Item</th>"
        '<th class="num">Previsto</th>'
        '<th class="num">Realizado</th>'
        '<th class="num">Pendente</th>'
        "<th>Status</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _render_summary(goal: pd.Series) -> None:
    notes = goal.get("goal_notes")
    text = str(notes).strip() if isinstance(notes, str) and notes.strip() else "Resumo ainda não informado."
    st.markdown(
        f'<p class="ficha-summary">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def _render_chart(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame, patient_id: str) -> None:
    fig = patient_weight_chart(weight_entries, patient_goals, patient_id)
    fig.update_layout(
        margin={"l": 12, "r": 8, "t": 6, "b": 4},
        legend={"title": None, "orientation": "h", "x": 0.0, "y": 1.18},
        yaxis_title="Peso (kg)",
        xaxis_title="",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        height=320,
    )
    fig.update_xaxes(showgrid=False, tickformat="%b/%y")
    fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb")
    # Rename legend entries to match the reference wording and tune colors.
    for trace in fig.data:
        if trace.name == "Peso esperado":
            trace.name = "Esperado"
            trace.line = {"color": "#94a3b8", "width": 2, "dash": "dash"}
        elif trace.name == "Peso realizado":
            trace.name = "Realizado"
            trace.line = {"color": "#2563eb", "width": 2.2}
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render(data) -> None:
    st.markdown(_page_css(), unsafe_allow_html=True)

    # The cadastro form's submit handler clears the cached ``get_data``
    # and sets ``_data_dirty``. Re-read the CSVs if the dirty flag is
    # set so a freshly-cadastrada ficha shows up on the same render
    # without an extra rerun.
    if st.session_state.pop("_data_dirty", False):
        from src.data_layer import load_all
        data = load_all()

    summary = patient_summary(data)
    if summary.empty:
        render_empty("Nenhum paciente disponível para exibir a ficha.")
        return

    _render_back_link()

    patient_id = _render_patient_switcher(summary)
    match = summary.loc[summary["patient_id"] == patient_id]
    if match.empty:
        render_empty("Paciente não encontrado.")
        return
    patient = match.iloc[0].to_dict()
    render_patient_header(patient, status_label=patient.get("status") or "—")

    goals = data["patient_goals"][data["patient_goals"]["patient_id"] == patient_id]
    goal = goals.iloc[0] if not goals.empty else pd.Series(dtype=object)

    _render_info_row(patient, goal)

    left, right = st.columns([1.35, 1.0], gap="medium")
    with left:
        st.markdown('<div class="ficha-card">', unsafe_allow_html=True)
        st.markdown('<p class="ficha-section-title">Evolução de peso (kg)</p>', unsafe_allow_html=True)
        _render_chart(data["weight_entries"], data["patient_goals"], patient_id)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="ficha-card">', unsafe_allow_html=True)
        st.markdown('<p class="ficha-section-title">Plano de tratamento</p>', unsafe_allow_html=True)
        execs = data["execution_summary"][data["execution_summary"]["patient_id"] == patient_id].copy()
        _render_plan_table(execs)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="ficha-card" style="margin-top:0.85rem;">', unsafe_allow_html=True)
    st.markdown('<p class="ficha-section-title">Resumo / Observações</p>', unsafe_allow_html=True)
    _render_summary(goal)
    st.markdown("</div>", unsafe_allow_html=True)
