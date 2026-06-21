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
            .ficha-info-value--empty:empty {
                display: block;
                height: 1.1em;
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
            /* The chart + plan table card is 50/50 in the row;
               we trim the bottom padding so the card hugs the
               content (the operator reported blank rectangles
               below the section title when the chart was the
               only thing inside the card). */
            .ficha-card--chart {
                display: flex;
                flex-direction: column;
                padding-bottom: 0.6rem;
            }
            .ficha-card--chart > .ficha-section-title {
                margin-bottom: 0.5rem;
            }
            .ficha-chart-empty {
                align-items: center;
                color: #94a3b8;
                display: flex;
                flex-direction: column;
                gap: 0.45rem;
                justify-content: center;
                min-height: 320px;
            }
            .ficha-chart-empty-caption {
                color: #475569;
                font-size: 0.85rem;
                font-weight: 600;
                margin: 0;
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


def _is_missing(value: object) -> bool:
    """Return True when ``value`` is None, NaN, or empty/blank.

    Mirrors the patient_header helper. Used everywhere the ficha
    renders a value the user can edit: weights, ages, status
    labels, plan items, etc. Without this guard a missing cell
    used to render literally as ``"None"`` or ``"nan"`` (the
    June 2026 regression).
    """
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _or_dash(value: object) -> str:
    """Render ``value`` as a stripped string, or ``"-"`` when missing.

    The ficha convention (June 2026): empty cells display ``"-"``
    — never ``"None"``, ``"nan"``, or a stray whitespace cell.
    """
    if _is_missing(value):
        return "-"
    s = str(value).strip()
    return s if s else "-"


def _format_weight(value: object) -> str:
    if _is_missing(value):
        return "-"
    try:
        return f"{float(value):.1f} kg"
    except (TypeError, ValueError):
        return _or_dash(value)


def _format_age(value: object) -> str:
    """Render an age, or empty string when no real value exists.

    Per the June 2026 spec the ficha hides the ``" anos"`` suffix
    entirely (and does NOT show ``"-"``) when the patient's age
    is missing — the placeholder is intentionally absent so the
    info row keeps its rhythm. A real age renders as ``"42 anos"``.
    """
    if _is_missing(value):
        return ""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    return f"{n} anos"


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
    # The age value is intentionally left empty (not "-") when
    # missing — see ``_format_age``. The info item is still
    # rendered so the layout doesn't reflow when the user fills
    # the value in later; we just suppress the value span.
    age_text = _format_age(patient.get("age"))
    items = [
        ("Idade", age_text),
        ("Objetivo", _or_dash(patient.get("main_goal"))),
        ("Peso inicial", _format_weight(goal.get("initial_weight"))),
        ("Peso atual", _format_weight(patient.get("current_weight"))),
        ("Peso meta", _format_weight(goal.get("target_weight"))),
    ]
    html_parts = ['<div class="ficha-info-row">']
    for label, value in items:
        # Hide the value span entirely when empty (the age case)
        # so the user doesn't see a stray "-" placeholder.
        value_html = (
            f'<span class="ficha-info-value">{html.escape(value)}</span>'
            if value
            else '<span class="ficha-info-value ficha-info-value--empty"></span>'
        )
        html_parts.append(
            '<div class="ficha-info-item">'
            f'<span class="ficha-info-label">{html.escape(label)}</span>'
            f"{value_html}"
            "</div>"
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def _format_frequencia_aplicacao(row: pd.Series) -> str:
    """Build the "Frequência de Aplicação" cell text.

    Per the June 2026 spec the cell shows the join of the item's
    ``sessions_expected`` and ``frequency_type`` (the dropdown
    value persisted by the wizard — the canonical source of
    truth). The format is exactly:

        "{N} sessões, {frequency_type}"

    When the item has no ``frequency_type`` set (e.g. a plan
    imported before the column existed), the cell collapses to
    ``"-"`` instead of showing a stray empty comma — that
    matches the rest of the ficha's missing-value convention.
    """
    sessions = row.get("sessions_expected")
    frequency_type = row.get("frequency_type")

    if _is_missing(frequency_type):
        return "-"
    if _is_missing(sessions):
        # Drop the "{N} sessões, " prefix but keep the
        # frequency_type — the operator still gets the
        # normalized cadence even when session count is unknown.
        return _or_dash(frequency_type)
    try:
        n = int(sessions)
    except (TypeError, ValueError):
        return _or_dash(frequency_type)
    return f"{n} sessões, {_or_dash(frequency_type)}"


def _render_plan_table(execs: pd.DataFrame) -> None:
    if execs.empty:
        render_empty("Sem execução registrada para este paciente.")
        return

    rows_html = []
    for _, row in execs.iterrows():
        procedure = _or_dash(row.get("procedure_raw"))
        category = str(row.get("procedure_category") or "").strip()
        if category and category.lower() != procedure.lower():
            item_html = (
                f'<span class="item-name">{html.escape(procedure)}</span>'
                f'<span class="item-sub">[{html.escape(category)}]</span>'
            )
        else:
            item_html = f'<span class="item-name">{html.escape(procedure)}</span>'
        status = _or_dash(row.get("status"))
        pill_class = _status_pill_class(status)
        # Numeric columns render ``-`` for missing values rather
        # than ``0`` (the previous behaviour hid missing data).
        sessions_expected = _format_int(row.get("sessions_expected"))
        sessions_completed = _format_int(row.get("sessions_completed"))
        sessions_remaining = _format_int(row.get("sessions_remaining"))
        freq_aplicacao = _format_frequencia_aplicacao(row)
        rows_html.append(
            "<tr>"
            f"<td>{item_html}</td>"
            f"<td>{html.escape(freq_aplicacao)}</td>"
            f'<td class="num">{sessions_expected}</td>'
            f'<td class="num">{sessions_completed}</td>'
            f'<td class="num">{sessions_remaining}</td>'
            f'<td><span class="ficha-status-pill {pill_class}">{html.escape(status)}</span></td>'
            "</tr>"
        )

    table_html = (
        '<table class="ficha-plan-table">'
        "<thead><tr>"
        "<th>Item</th>"
        "<th>Frequência de Aplicação</th>"
        '<th class="num">Previsto</th>'
        '<th class="num">Realizado</th>'
        '<th class="num">Pendente</th>'
        "<th>Status</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _format_int(value: object) -> str:
    """Render an integer or ``"-"`` when missing.

    The plan table cells show ``"-"`` for missing session counts
    instead of ``"0"`` — a missing session count is information
    the operator needs to see, not the same as "zero completed".
    """
    if _is_missing(value):
        return "-"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return _or_dash(value)


def _render_summary(goal: pd.Series) -> None:
    notes = goal.get("goal_notes")
    if _is_missing(notes):
        text = "Resumo ainda não informado."
    else:
        text = str(notes).strip() or "Resumo ainda não informado."
    st.markdown(
        f'<p class="ficha-summary">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def _chart_empty_state_html() -> str:
    """SVG + caption rendered in place of the chart when there's
    no weight data yet.

    Per the June 2026 spec the empty state keeps the same display
    area as the populated chart (so the layout doesn't reflow
    when the first measurement lands) but replaces the grid with
    a soft-tone chart icon and the literal phrase ``"Não há
    dados para exibição."``. The SVG is inline (no extra HTTP
    request, no broken-link risk if ``data/images/`` is empty in
    a deploy) and uses ``currentColor`` so the surrounding
    stylesheet controls the tint.
    """
    # Hand-tuned chart icon: a frame with a flat baseline and a
    # ghost polyline that doesn't reach the baseline (visually
    # "no data yet"). Width/height sized to fit the 320px card
    # comfortably without crowding the caption.
    return (
        '<div class="ficha-chart-empty">'
        '<svg viewBox="0 0 120 80" width="120" height="80" '
        'aria-hidden="true" focusable="false">'
        '<rect x="6" y="6" width="108" height="68" rx="4" '
        'fill="none" stroke="currentColor" stroke-width="1.2" '
        'opacity="0.35" />'
        '<line x1="14" y1="62" x2="106" y2="62" '
        'stroke="currentColor" stroke-width="1" opacity="0.45" />'
        '<polyline points="20,52 40,46 60,48 80,40 100,42" '
        'fill="none" stroke="currentColor" stroke-width="1.5" '
        'opacity="0.55" stroke-linejoin="round" stroke-linecap="round" />'
        "</svg>"
        '<p class="ficha-chart-empty-caption">Não há dados para exibição.</p>'
        "</div>"
    )


def _has_weight_data(weight_entries: pd.DataFrame, patient_id: str) -> bool:
    """True when the patient has at least one weight entry.

    The empty-state guard uses this so the chart knows whether
    to render the Plotly figure (which draws an empty grid for
    an empty dataframe — the regression the operator reported)
    or the inline SVG + caption. Empty string / NaN dates are
    filtered out so a malformed row doesn't fool the check.
    """
    if weight_entries is None or weight_entries.empty:
        return False
    sub = weight_entries.loc[weight_entries["patient_id"] == patient_id]
    if sub.empty:
        return False
    # Treat rows with no measurement_date as "no data" — the
    # chart can't plot them anyway.
    if "measurement_date" not in sub.columns:
        return False
    dates = sub["measurement_date"]
    # ``.notna().any()`` returns ``numpy.bool_`` on pandas' side;
    # wrap in ``bool()`` so callers get a plain ``True``/``False``
    # (matters for ``is True`` checks in tests and for pickling
    # into st.cache_data).
    return bool(dates.notna().any())


def _render_chart(weight_entries: pd.DataFrame, patient_goals: pd.DataFrame, patient_id: str) -> None:
    if not _has_weight_data(weight_entries, patient_id):
        # Render the inline SVG + caption instead of the Plotly
        # figure so the user doesn't see an empty grid (which
        # was the regression — Plotly draws an empty plot area
        # with axes but no trace, and the auto-titled figure
        # clipped its title because the caller sets
        # ``margin.t=6``).
        st.markdown(_chart_empty_state_html(), unsafe_allow_html=True)
        return

    fig = patient_weight_chart(weight_entries, patient_goals, patient_id)
    # ``margin.t`` was 6 before the June 2026 fix — too small for
    # the horizontal legend pinned at ``y=1.18``. Bumping to
    # 36 leaves room for the legend without bleeding into the
    # card above. ``margin.b`` stays at 4 because the X axis
    # tick labels are short (``%b/%y``) and Plotly's default
    # bottom margin already covers them.
    fig.update_layout(
        margin={"l": 12, "r": 8, "t": 36, "b": 4},
        legend={"title": None, "orientation": "h", "x": 0.0, "y": 1.14},
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

    # 50/50 layout per the June 2026 spec: chart and plan table
    # each take half the row. ``gap="medium"`` keeps the cards
    # visually separated. The previous ``[1.35, 1.0]`` ratio
    # crowded the table and left a noticeable imbalance.
    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.markdown('<div class="ficha-card ficha-card--chart">', unsafe_allow_html=True)
        st.markdown('<p class="ficha-section-title">Evolução de peso (kg)</p>', unsafe_allow_html=True)
        _render_chart(data["weight_entries"], data["patient_goals"], patient_id)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="ficha-card ficha-card--chart">', unsafe_allow_html=True)
        st.markdown('<p class="ficha-section-title">Plano de tratamento</p>', unsafe_allow_html=True)
        execs = data["execution_summary"][data["execution_summary"]["patient_id"] == patient_id].copy()
        _render_plan_table(execs)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="ficha-card" style="margin-top:0.85rem;">', unsafe_allow_html=True)
    st.markdown('<p class="ficha-section-title">Resumo / Observações</p>', unsafe_allow_html=True)
    _render_summary(goal)
    st.markdown("</div>", unsafe_allow_html=True)
