"""Patient-record (ficha) creation helpers and form.

The MAP shell's source of truth is the CSV layer at ``data/csv/`` (see
:mod:`src.data_layer`). This module writes the new plan, items, goal,
and (optional) weight row directly to the corresponding CSVs and then
clears the Streamlit cache so the next render observes them.

A "ficha" is the combination of a treatment plan, its items, and the
patient's goal for that plan. The cadastro form persists them in one
submission and updates the patient's age on the existing ``patients``
row.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from src.data_layer import append_row, load_table, next_id, update_row

_ITEMS_WIDGET_KEY = "cadastro_ficha_items"
_FORM_KEY = "cadastro_ficha_form"

_STATUS_OPTIONS = [
    "Aguardando início",
    "Ativo",
    "Pausado",
    "Encerrado",
]

_FREQUENCY_OPTIONS = ["Semanal", "Quinzenal", "Diário", "Mensal"]


def patient_has_ficha(patient_id: str, data: dict[str, pd.DataFrame] | None = None) -> bool:
    """Return True if ``patient_id`` already has at least one treatment plan.

    Reads the treatment plans CSV directly (not the cached ``load_all``)
    so the deep-link on the Pacientes page reflects the on-disk state
    right after a hard refresh.
    """
    df = load_table("treatment_plans")
    if df.empty or "patient_id" not in df.columns:
        return False
    return bool((df["patient_id"].astype(str) == str(patient_id)).any())


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


def _handle_submit(patient_id: str) -> None:
    """Build and persist the ficha rows, then navigate to the Ficha page."""
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

    plan_id = next_id("treatment_plans")
    goal_id = next_id("patient_goals")

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
    append_row("treatment_plans", plan_row)

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
    append_row("patient_goals", goal_row)

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
        item_id = next_id("treatment_plan_items")
        append_row(
            "treatment_plan_items",
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
            },
        )

    if peso_atual > 0:
        weight_id = next_id("weight_entries")
        append_row(
            "weight_entries",
            {
                "weight_id": weight_id,
                "patient_id": patient_id,
                "plan_id": plan_id,
                "measurement_date": today,
                "weight": peso_atual,
                "source": "Dados manuais",
                "notes": "Peso atual no cadastro da ficha.",
            },
        )

    # Persist the age entered on the form to the patient's row. The
    # patient is always present (the cadastro page resolves a
    # ``selected_patient_id`` from the Pacientes deep-link), so this is
    # never a no-op — unlike the previous session-state flow.
    update_row("patients", "patient_id", patient_id, {"age": age if age > 0 else None})

    # Drop the cached ``get_data`` so the next render re-reads the CSVs
    # and the new ficha is visible immediately. Pages that care about
    # freshness (e.g. ``pacientes``, ``ficha_paciente``) check the
    # ``_data_dirty`` flag below and re-read on the same render — no
    # ``st.rerun()`` needed (which would interact poorly with the
    # form's ``clear_on_submit=True``).
    st.cache_data.clear()
    st.session_state["_data_dirty"] = True

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


def render_cadastro_ficha_form(data: dict | None, patient: dict) -> None:
    """Render the ficha registration form for ``patient``.

    ``data`` is accepted for backward compatibility with the previous
    merge-based contract; this form reads the CSVs directly via the data
    layer. On submit the function writes the new plan/items/goal to the
    corresponding CSVs and switches the active page to the Ficha do
    Paciente.
    """
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
            _handle_submit(patient_id)
        elif cancelled:
            st.session_state["page"] = "Pacientes"
            st.session_state["cadastro_ficha_cancelled"] = True

    st.markdown("</div>", unsafe_allow_html=True)
