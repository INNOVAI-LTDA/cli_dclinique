"""Patient-record (ficha) creation helpers and form.

Session-state contract (mirrors ``src.components.add_patient``):
  - ``extra_treatment_plans``  — list[dict] matching ``EXPECTED_SCHEMAS["treatment_plans"]``
  - ``extra_treatment_plan_items`` — list[dict] matching ``EXPECTED_SCHEMAS["treatment_plan_items"]``
  - ``extra_patient_goals``    — list[dict] matching ``EXPECTED_SCHEMAS["patient_goals"]``
  - ``extra_weight_entries``   — list[dict] matching ``EXPECTED_SCHEMAS["weight_entries"]``

A "ficha" is the combination of a treatment plan, its items, and the
patient's goal for that plan. ``merge_extra_fichas`` is the single read
path that pages and metrics use to see those session-added rows.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from src.schemas import EXPECTED_SCHEMAS

_EXTRA_PLANS_KEY = "extra_treatment_plans"
_EXTRA_ITEMS_KEY = "extra_treatment_plan_items"
_EXTRA_GOALS_KEY = "extra_patient_goals"
_EXTRA_WEIGHT_KEY = "extra_weight_entries"
_ITEMS_WIDGET_KEY = "cadastro_ficha_items"
_FORM_KEY = "cadastro_ficha_form"

_STATUS_OPTIONS = [
    "Aguardando início",
    "Ativo",
    "Pausado",
    "Encerrado",
]

_FREQUENCY_OPTIONS = ["Semanal", "Quinzenal", "Diário", "Mensal"]


def _ensure_state() -> None:
    st.session_state.setdefault(_EXTRA_PLANS_KEY, [])
    st.session_state.setdefault(_EXTRA_ITEMS_KEY, [])
    st.session_state.setdefault(_EXTRA_GOALS_KEY, [])
    st.session_state.setdefault(_EXTRA_WEIGHT_KEY, [])
    # NOTE: _ITEMS_WIDGET_KEY is intentionally NOT set via setdefault —
    # Streamlit forbids writing to st.session_state for widget-bound keys
    # like st.data_editor. The data_editor widget initialises the value
    # on first render and the submit handler reads it from session state
    # at submit time.


def _next_indexed_id(used: set[str], prefix: str, width: int = 3) -> str:
    counter = 1
    while True:
        candidate = f"{prefix}_{counter:0{width}d}"
        if candidate not in used:
            return candidate
        counter += 1


def _next_plan_id(data: dict[str, pd.DataFrame]) -> str:
    used: set[str] = set()
    plans = data.get("treatment_plans")
    if plans is not None and not plans.empty and "plan_id" in plans.columns:
        used.update(plans["plan_id"].dropna().astype(str).tolist())
    used.update(str(p.get("plan_id")) for p in st.session_state.get(_EXTRA_PLANS_KEY, []))
    return _next_indexed_id(used, "plan_new")


def _next_goal_id(data: dict[str, pd.DataFrame]) -> str:
    used: set[str] = set()
    goals = data.get("patient_goals")
    if goals is not None and not goals.empty and "goal_id" in goals.columns:
        used.update(goals["goal_id"].dropna().astype(str).tolist())
    used.update(str(g.get("goal_id")) for g in st.session_state.get(_EXTRA_GOALS_KEY, []))
    return _next_indexed_id(used, "goal_new")


def _next_item_id(data: dict[str, pd.DataFrame]) -> str:
    used: set[str] = set()
    items = data.get("treatment_plan_items")
    if items is not None and not items.empty and "plan_item_id" in items.columns:
        used.update(items["plan_item_id"].dropna().astype(str).tolist())
    used.update(str(i.get("plan_item_id")) for i in st.session_state.get(_EXTRA_ITEMS_KEY, []))
    return _next_indexed_id(used, "item_new")


def _next_weight_id(data: dict[str, pd.DataFrame]) -> str:
    used: set[str] = set()
    weights = data.get("weight_entries")
    if weights is not None and not weights.empty and "weight_id" in weights.columns:
        used.update(weights["weight_id"].dropna().astype(str).tolist())
    used.update(str(w.get("weight_id")) for w in st.session_state.get(_EXTRA_WEIGHT_KEY, []))
    return _next_indexed_id(used, "w_new")


def merge_extra_fichas(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Append session-added fichas to the corresponding tables.

    Returns the **same** dict instance when there are no extras, so
    ``@st.cache_data`` consumers keep their cache.
    """
    _ensure_state()
    plans = st.session_state[_EXTRA_PLANS_KEY]
    items = st.session_state[_EXTRA_ITEMS_KEY]
    goals = st.session_state[_EXTRA_GOALS_KEY]
    weights = st.session_state[_EXTRA_WEIGHT_KEY]
    if not plans and not items and not goals and not weights:
        return data
    if data is None:
        return data

    new_data = dict(data)

    if plans and "treatment_plans" in new_data:
        plans_df = pd.DataFrame(plans, columns=EXPECTED_SCHEMAS["treatment_plans"])
        for col in ("issue_date", "start_date", "end_date"):
            plans_df[col] = pd.to_datetime(plans_df[col], errors="coerce")
        plans_df["is_renewal"] = plans_df["is_renewal"].astype(bool)
        new_data["treatment_plans"] = pd.concat(
            [new_data["treatment_plans"], plans_df], ignore_index=True
        )

    if items and "treatment_plan_items" in new_data:
        items_df = pd.DataFrame(items, columns=EXPECTED_SCHEMAS["treatment_plan_items"])
        items_df["needs_manual_review"] = items_df["needs_manual_review"].astype(bool)
        new_data["treatment_plan_items"] = pd.concat(
            [new_data["treatment_plan_items"], items_df], ignore_index=True
        )

    if goals and "patient_goals" in new_data:
        goals_df = pd.DataFrame(goals, columns=EXPECTED_SCHEMAS["patient_goals"])
        for col in ("initial_weight", "target_weight"):
            goals_df[col] = pd.to_numeric(goals_df[col], errors="coerce")
        if "target_date" in goals_df.columns:
            goals_df["target_date"] = pd.to_datetime(goals_df["target_date"], errors="coerce")
        new_data["patient_goals"] = pd.concat(
            [new_data["patient_goals"], goals_df], ignore_index=True
        )

    if weights and "weight_entries" in new_data:
        weights_df = pd.DataFrame(weights, columns=EXPECTED_SCHEMAS["weight_entries"])
        weights_df["measurement_date"] = pd.to_datetime(weights_df["measurement_date"], errors="coerce")
        weights_df["weight"] = pd.to_numeric(weights_df["weight"], errors="coerce")
        new_data["weight_entries"] = pd.concat(
            [new_data["weight_entries"], weights_df], ignore_index=True
        )

    return new_data


def reset_extra_fichas() -> None:
    """Clear session-added fichas. Useful for tests / debug only."""
    st.session_state[_EXTRA_PLANS_KEY] = []
    st.session_state[_EXTRA_ITEMS_KEY] = []
    st.session_state[_EXTRA_GOALS_KEY] = []
    st.session_state[_EXTRA_WEIGHT_KEY] = []


def patient_has_ficha(patient_id: str, data: dict[str, pd.DataFrame]) -> bool:
    """Return True if ``patient_id`` already has at least one treatment plan."""
    plans = data.get("treatment_plans") if data else None
    if plans is None or plans.empty or "patient_id" not in plans.columns:
        return False
    return bool((plans["patient_id"].astype(str) == str(patient_id)).any())


def _default_items_df() -> pd.DataFrame:
    """Initial rows for the items data editor.

    Three empty rows pre-selected with a sensible frequency so the user
    can fill in either the existing patterns (Injetáveis EV,
    Acompanhamento nutricional, Medicamento manipulado) or something
    completely new.
    """
    return pd.DataFrame(
        [
            {"nome": "", "categoria": "", "sessoes": 0, "frequencia": "Semanal"},
            {"nome": "", "categoria": "", "sessoes": 0, "frequencia": "Quinzenal"},
            {"nome": "", "categoria": "", "sessoes": 0, "frequencia": "Diário"},
        ]
    )


def _coerce_date(value: Any) -> pd.Timestamp:
    if isinstance(value, pd.Timestamp):
        return value.normalize()
    if isinstance(value, date):
        return pd.Timestamp(value)
    return pd.to_datetime(value, errors="coerce")


def _handle_submit(patient_id: str, data: dict[str, pd.DataFrame]) -> None:
    """Build and persist the ficha rows, then navigate to the Ficha page."""
    _ensure_state()
    today = pd.Timestamp.today().normalize()

    try:
        age = int(st.session_state.get("cadastro_ficha_age", 0) or 0)
    except (TypeError, ValueError):
        age = 0

    try:
        peso_inicial = float(st.session_state.get("cadastro_ficha_peso_inicial", 0.0) or 0.0)
    except (TypeError, ValueError):
        peso_inicial = 0.0
    try:
        peso_atual = float(st.session_state.get("cadastro_ficha_peso_atual", 0.0) or 0.0)
    except (TypeError, ValueError):
        peso_atual = 0.0
    try:
        peso_meta = float(st.session_state.get("cadastro_ficha_peso_meta", 0.0) or 0.0)
    except (TypeError, ValueError):
        peso_meta = 0.0

    objetivo = str(st.session_state.get("cadastro_ficha_objetivo", "") or "").strip()
    status = str(st.session_state.get("cadastro_ficha_status", "Aguardando início") or "Aguardando início")
    data_inicio = _coerce_date(st.session_state.get("cadastro_ficha_inicio", today))
    data_fim = _coerce_date(st.session_state.get("cadastro_ficha_fim", today + timedelta(days=60)))
    is_renewal = bool(st.session_state.get("cadastro_ficha_renovacao", False))
    budget_code = str(st.session_state.get("cadastro_ficha_orcamento", "") or "").strip()
    notes = str(st.session_state.get("cadastro_ficha_resumo", "") or "").strip()
    goal_type = objetivo if objetivo else "Emagrecimento"

    plan_id = _next_plan_id(data)
    goal_id = _next_goal_id(data)

    plan_row: dict[str, Any] = {
        "plan_id": plan_id,
        "patient_id": patient_id,
        "budget_code": budget_code or f"orc_new_{plan_id.split('_')[-1]}",
        "issue_date": today,
        "start_date": data_inicio if pd.notna(data_inicio) else today,
        "end_date": data_fim if pd.notna(data_fim) else today + timedelta(days=60),
        "status": status,
        "main_goal": goal_type,
        "is_renewal": is_renewal,
        "notes": notes,
    }
    st.session_state[_EXTRA_PLANS_KEY].append(plan_row)

    goal_row: dict[str, Any] = {
        "goal_id": goal_id,
        "patient_id": patient_id,
        "plan_id": plan_id,
        "goal_type": goal_type,
        "initial_weight": peso_inicial,
        "target_weight": peso_meta,
        "target_date": data_fim if pd.notna(data_fim) else today + timedelta(days=60),
        "goal_notes": notes,
    }
    st.session_state[_EXTRA_GOALS_KEY].append(goal_row)

    items_df = st.session_state.get(_ITEMS_WIDGET_KEY)
    if items_df is None or (hasattr(items_df, "empty") and items_df.empty):
        items_df = _default_items_df()
    if hasattr(items_df, "to_dict"):
        items_records = items_df.to_dict(orient="records")
    else:
        items_records = []

    for record in items_records:
        name = str(record.get("nome", "") or "").strip()
        if not name:
            continue
        category = str(record.get("categoria", "") or "").strip() or "Geral"
        try:
            sessions_expected = int(record.get("sessoes", 0) or 0)
        except (TypeError, ValueError):
            sessions_expected = 0
        frequency_type = str(record.get("frequencia", "Semanal") or "Semanal")
        item_id = _next_item_id(data)
        st.session_state[_EXTRA_ITEMS_KEY].append(
            {
                "plan_item_id": item_id,
                "plan_id": plan_id,
                "patient_id": patient_id,
                "budget_code": plan_row["budget_code"],
                "raw_name": name,
                "category": category,
                "sessions_expected": sessions_expected,
                "frequency_text": f"{sessions_expected} sessões - {frequency_type.lower()}",
                "frequency_type": frequency_type,
                "source": "Dados manuais",
                "needs_manual_review": False,
            }
        )

    if peso_atual > 0:
        weight_id = _next_weight_id(data)
        st.session_state[_EXTRA_WEIGHT_KEY].append(
            {
                "weight_id": weight_id,
                "patient_id": patient_id,
                "plan_id": plan_id,
                "measurement_date": today,
                "weight": peso_atual,
                "source": "Dados manuais",
                "notes": "Peso atual no cadastro da ficha.",
            }
        )

    # Update the session-added patient record's age (no-op for fixture rows).
    for extra in st.session_state.get("extra_patients", []):
        if str(extra.get("patient_id", "")) == str(patient_id):
            extra["age"] = age
            break

    st.session_state["selected_patient_id"] = patient_id
    st.session_state["page"] = "Ficha do Paciente"


def _ficha_css() -> str:
    return """
        <style>
            .ficha-form-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 1rem 1.1rem 1.2rem;
                margin-top: 0.6rem;
            }
            .ficha-form-title {
                color: #0f172a;
                font-size: 1.05rem;
                font-weight: 700;
                margin: 0 0 0.25rem;
            }
            .ficha-form-subtitle {
                color: #64748b;
                font-size: 0.78rem;
                margin: 0 0 0.85rem;
            }
            .ficha-form-section {
                color: #0f172a;
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.01em;
                margin: 0.85rem 0 0.45rem;
                text-transform: uppercase;
            }
            .ficha-form-section:first-of-type { margin-top: 0; }

            div[data-testid="stTextInput"] label,
            div[data-testid="stNumberInput"] label,
            div[data-testid="stTextArea"] label,
            div[data-testid="stSelectbox"] label,
            div[data-testid="stDateInput"] label,
            div[data-testid="stCheckbox"] label {
                color: #334155;
                font-size: 0.7rem;
                font-weight: 700;
                margin-bottom: 0.16rem;
            }
            div[data-testid="stTextInput"] input,
            div[data-testid="stNumberInput"] input,
            div[data-testid="stTextArea"] textarea,
            div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
            div[data-testid="stDateInput"] input {
                border-color: #dbe2ea;
                border-radius: 6px;
                font-size: 0.78rem;
                min-height: 2.18rem;
            }
            div[data-testid="stDataEditor"] {
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
            .ficha-form-actions div[data-testid="stButton"] > button {
                border-radius: 6px;
                font-size: 0.78rem;
                font-weight: 700;
                min-height: 2.2rem;
            }
        </style>
    """


def render_cadastro_ficha_form(data: dict[str, pd.DataFrame], patient: dict) -> None:
    """Render the ficha registration form for ``patient``.

    ``data`` must already include the patient (use ``merge_extra_patients``
    before calling). On submit the function writes the new plan/items/goal
    into session state and switches the active page to the Ficha do
    Paciente.
    """
    _ensure_state()
    st.markdown(_ficha_css(), unsafe_allow_html=True)

    patient_id = str(patient.get("patient_id", ""))
    today = pd.Timestamp.today().normalize().date()
    default_end = today + timedelta(days=60)
    try:
        initial_age = int(patient.get("age") or 0)
    except (TypeError, ValueError):
        initial_age = 0

    st.markdown(
        '<div class="ficha-form-shell">'
        '<p class="ficha-form-title">Cadastrar Ficha do Paciente</p>'
        f'<p class="ficha-form-subtitle">Paciente: {str(patient.get("name", "—"))}</p>',
        unsafe_allow_html=True,
    )

    # Items editor lives outside the form because st.data_editor is not
    # allowed inside st.form. The current widget value is captured by
    # _handle_submit via session_state.
    st.markdown(
        '<p class="ficha-form-section">Itens do plano de tratamento</p>',
        unsafe_allow_html=True,
    )
    st.data_editor(
        _default_items_df(),
        num_rows="dynamic",
        column_config={
            "nome": st.column_config.TextColumn("Nome do procedimento", required=False),
            "categoria": st.column_config.TextColumn("Categoria", required=False),
            "sessoes": st.column_config.NumberColumn(
                "Sessões previstas", min_value=0, step=1, format="%d", default=0
            ),
            "frequencia": st.column_config.SelectboxColumn(
                "Frequência", options=_FREQUENCY_OPTIONS, default="Semanal", required=True
            ),
        },
        key=_ITEMS_WIDGET_KEY,
        use_container_width=True,
    )

    with st.form(_FORM_KEY, clear_on_submit=False):
        st.markdown(
            '<p class="ficha-form-section">Dados do plano</p>',
            unsafe_allow_html=True,
        )
        col_a, col_b, col_c = st.columns([1.2, 1, 1])
        with col_a:
            st.selectbox(
                "Status do plano",
                _STATUS_OPTIONS,
                index=_STATUS_OPTIONS.index("Aguardando início"),
                key="cadastro_ficha_status",
            )
        with col_b:
            st.date_input(
                "Data de início",
                value=today,
                key="cadastro_ficha_inicio",
            )
        with col_c:
            st.date_input(
                "Data de fim",
                value=default_end,
                key="cadastro_ficha_fim",
            )

        col_d, col_e = st.columns([1, 1])
        with col_d:
            st.text_input(
                "Código do orçamento",
                key="cadastro_ficha_orcamento",
                placeholder="Ex.: orc_001",
            )
        with col_e:
            st.checkbox(
                "É renovação?",
                value=False,
                key="cadastro_ficha_renovacao",
            )

        st.markdown(
            '<p class="ficha-form-section">Objetivo e pesos</p>',
            unsafe_allow_html=True,
        )
        col_f, col_g = st.columns([1, 1.6])
        with col_f:
            st.number_input(
                "Idade",
                min_value=0,
                max_value=120,
                step=1,
                value=initial_age,
                format="%d",
                key="cadastro_ficha_age",
            )
        with col_g:
            st.text_input(
                "Objetivo principal",
                key="cadastro_ficha_objetivo",
                placeholder="Ex.: Emagrecimento",
            )

        col_h, col_i, col_j = st.columns(3)
        with col_h:
            st.number_input(
                "Peso inicial (kg)",
                min_value=0.0,
                step=0.1,
                value=0.0,
                format="%.1f",
                key="cadastro_ficha_peso_inicial",
            )
        with col_i:
            st.number_input(
                "Peso atual (kg)",
                min_value=0.0,
                step=0.1,
                value=0.0,
                format="%.1f",
                key="cadastro_ficha_peso_atual",
            )
        with col_j:
            st.number_input(
                "Peso meta (kg)",
                min_value=0.0,
                step=0.1,
                value=0.0,
                format="%.1f",
                key="cadastro_ficha_peso_meta",
            )

        st.markdown(
            '<p class="ficha-form-section">Resumo / Observações</p>',
            unsafe_allow_html=True,
        )
        st.text_area(
            "Resumo do plano",
            key="cadastro_ficha_resumo",
            placeholder="Notas sobre o plano, observações clínicas, etc.",
            height=120,
        )

        st.markdown(
            '<div class="ficha-form-actions" style="margin-top:0.6rem;">',
            unsafe_allow_html=True,
        )
        action_cols = st.columns([1, 1, 6])
        with action_cols[0]:
            submitted = st.form_submit_button(
                "Cadastrar ficha", type="primary", use_container_width=True
            )
        with action_cols[1]:
            cancelled = st.form_submit_button("Cancelar", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if submitted:
            _handle_submit(patient_id, data)
        elif cancelled:
            st.session_state["page"] = "Pacientes"
            st.session_state["cadastro_ficha_cancelled"] = True

    st.markdown("</div>", unsafe_allow_html=True)
