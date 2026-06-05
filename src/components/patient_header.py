"""Patient header component."""
from __future__ import annotations

import html

import streamlit as st

from src.components.badges import badge


def _initials(name: str) -> str:
    parts = [part for part in name.strip().split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar_html(initials: str) -> str:
    safe_initials = html.escape(initials)
    return (
        '<div class="patient-avatar" aria-hidden="true">'
        f'<span>{safe_initials}</span>'
        "</div>"
    )


def _header_css() -> str:
    return """
        <style>
            .patient-header {
                align-items: center;
                display: flex;
                gap: 0.85rem;
                padding: 0.15rem 0 0.45rem;
            }
            .patient-avatar {
                align-items: center;
                background: #eef2ff;
                border: 1px solid #c7d2fe;
                border-radius: 999px;
                color: #3730a3;
                display: inline-flex;
                flex: 0 0 auto;
                font-size: 0.95rem;
                font-weight: 700;
                height: 2.4rem;
                justify-content: center;
                letter-spacing: 0.02em;
                width: 2.4rem;
            }
            .patient-avatar span {
                line-height: 1;
            }
            .patient-name {
                color: #0f172a;
                font-size: 1.2rem;
                font-weight: 700;
                letter-spacing: -0.005em;
                line-height: 1.15;
                margin: 0;
            }
            .patient-header-meta {
                color: #64748b;
                font-size: 0.78rem;
                margin: 0;
            }
            .patient-status-badge {
                align-items: center;
                background: #dcfce7;
                border-radius: 999px;
                color: #15803d;
                display: inline-flex;
                font-size: 0.72rem;
                font-weight: 700;
                gap: 0.32rem;
                padding: 0.18rem 0.55rem;
            }
            .patient-status-badge::before {
                background: #22c55e;
                border-radius: 999px;
                content: "";
                display: inline-block;
                height: 0.42rem;
                width: 0.42rem;
            }
            .patient-header-actions div[data-testid="stPopover"] > button,
            .patient-header-actions div[data-testid="stButton"] > button {
                background: #ffffff;
                border: 1px solid #dbe2ea;
                border-radius: 8px;
                color: #0f172a;
                font-size: 0.78rem;
                font-weight: 600;
                min-height: 2.05rem;
                padding: 0 0.78rem;
            }
            .patient-header-actions div[data-testid="stPopover"] > button:hover,
            .patient-header-actions div[data-testid="stButton"] > button:hover {
                border-color: #93b4f4;
                color: #1d4ed8;
            }
        </style>
        """


def render_patient_header(patient: dict, status_label: str | None = None) -> None:
    """Render the patient hero header (avatar, name, status, actions)."""
    name = str(patient.get("name", ""))
    initials = _initials(name)
    status = status_label or patient.get("status") or "—"

    st.markdown(_header_css(), unsafe_allow_html=True)

    cols = st.columns([6.4, 1.2, 1.0])
    with cols[0]:
        st.markdown(
            '<div class="patient-header">'
            f"{_avatar_html(initials)}"
            '<div style="display:flex;flex-direction:column;gap:0.18rem;">'
            f'<p class="patient-name">{html.escape(name)}</p>'
            f'<span class="patient-status-badge">{html.escape(str(status))}</span>'
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p class="patient-header-meta">Prontuário {html.escape(str(patient.get("medical_record", "—")))} · {html.escape(str(patient.get("age", "—")))} anos</p>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown('<div class="patient-header-actions">', unsafe_allow_html=True)
        _render_actions()
        st.markdown("</div>", unsafe_allow_html=True)


def _render_actions() -> None:
    """Render the Ações control (popover when available, button fallback)."""
    popover = getattr(st, "popover", None)
    if callable(popover):
        with popover("Ações ▾", use_container_width=True):
            st.button("Editar cadastro", key="patient_action_edit", use_container_width=True)
            st.button("Agendar sessão", key="patient_action_schedule", use_container_width=True)
            st.button("Ver histórico", key="patient_action_history", use_container_width=True)
            st.button("Exportar ficha", key="patient_action_export", use_container_width=True)
        return

    if st.button("Ações ▾", key="patient_actions_button", use_container_width=True):
        st.session_state["patient_actions_open"] = not st.session_state.get("patient_actions_open", False)
    if st.session_state.get("patient_actions_open"):
        st.button("Editar cadastro", key="patient_action_edit", use_container_width=True)
        st.button("Agendar sessão", key="patient_action_schedule", use_container_width=True)
        st.button("Ver histórico", key="patient_action_history", use_container_width=True)
        st.button("Exportar ficha", key="patient_action_export", use_container_width=True)

    # Keep the old badge helper import path happy if someone reuses this module elsewhere.
    _ = badge
