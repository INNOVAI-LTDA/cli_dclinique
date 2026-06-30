"""Decision map page (Caminho B, Phase 4).

Refactor de ``mapa_decisao.py`` para usar ``src.core.frequency.attendance_rate``
como 3a dimensao (alem de engajamento e satisfacao). Adiciona a 5a classe
"Sem comparecimento" ao quadrante 2x2 quando ``attendance_rate == 0``.

Mudancas (vs v0.3.0):
  * Importa ``load_client_deliverables``, ``load_client_sessions``,
    ``load_deliverables`` de ``src.core.repos`` e ``attendance_rate`` de
    ``src.core.frequency``.
  * Nova funcao privada ``_compute_patient_attendance_rates(data, as_of)``
    que agrega ``attendance_rate`` por ``client_id`` (mean sobre cds ativos).
  * ``render()`` faz merge de ``attendance_rate`` em ``summary`` e adiciona
    override "Sem comparecimento" no quadrante para pacientes com rate == 0.
  * Painel lateral do paciente ganha dimensao "Frequencia" (X% comparecimento).
  * CSS ganha classe ``.dm-quadrant-no-attendance`` (borda cinza neutro) para
    o 5o quadrante.

Boundary (N7 E6) preservado: o try/except defensivo do commit 76d47ab
permanece como o unico ponto de captura. Erros novos viram ``st.error(...)``
em vez de freeze (directriz do Cliente 2026-06-21).
"""
from __future__ import annotations

import html
import logging
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from src.charts.decision_map import quadrants
from src.core.frequency import attendance_rate
from src.core.repos import (
    load_client_deliverables,
    load_client_sessions,
    load_deliverables,
)
from src.metrics import patient_summary
from src.utils.safe import safe_int, safe_pct

_log = logging.getLogger(__name__)


def _compute_patient_attendance_rates(
    data: dict, *, as_of: date | None = None
) -> pd.Series:
    """Agrega ``attendance_rate`` por patient_id a partir de ``core.frequency``.

    Algoritmo:
      1. Carrega cds (Phase 1 schema), catalogo e sessoes via ``src.core.repos``.
      2. Para cada cd com ``parent_client_deliverable_id is not None`` (item,
         NAO plano-pai) E status ``"Ativo"`` ou ``"Aguardando"``: chama
         ``core.frequency.attendance_rate(cd, d, sessions, as_of)``.
      3. Agrupa por ``client_id`` (mean sobre todos os cds do paciente).
      4. Mapeia ``client_id`` (int) para ``patient_id`` (string ``pat_NNN``)
         usando o DataFrame ``patients``.

    Args:
        data: DataDict de ``src.data_layer.load_all()``.
        as_of: data de referencia para o calculo. Default: ``date.today()``.
            Em testes, pinar para uma data fixa (determinismo).

    Returns:
        ``pd.Series`` indexado por ``patient_id`` (string ``pat_NNN``),
        valores ``float`` em ``[0.0, 1.0]``. Pacientes sem cds ativos NAO
        aparecem no indice (caller usa ``fillna``).

    N7:
        Funcao AGGREGADORA -- chama a funcao pura ``core.frequency.attendance_rate``
        (que NAO captura). Erros de tipo do core (TypeError, ValueError) sao
        capturados localmente (caller defensivo) para que 1 paciente com data
        invalida nao quebre o render inteiro. O try/except externo em
        ``render()`` e' a barreira final.
    """
    if as_of is None:
        as_of = date.today()

    cds = load_client_deliverables(data)
    deliverables = load_deliverables(data)
    sessions = load_client_sessions(data)
    deliverable_by_id = {d.id: d for d in deliverables}

    # Build patient_id (str) → client_id (int) map a partir de patients.
    # v1: patients.patient_id == "pat_NNN", onde NNN == client_id.
    patients_df = data.get("patients", pd.DataFrame())
    if isinstance(patients_df, pd.DataFrame) and not patients_df.empty and "patient_id" in patients_df.columns:
        client_by_patient = {
            str(row["patient_id"]): int(row["patient_id"].split("_")[-1])
            for _, row in patients_df.iterrows()
            if str(row["patient_id"]).startswith("pat_")
        }
    else:
        client_by_patient = {}
    patient_by_client = {v: k for k, v in client_by_patient.items()}

    rates: list[tuple[int, float]] = []
    for cd in cds:
        # Apenas ITENS (parent setado) sao acionaveis; plano-pai e' agregado.
        if cd.parent_client_deliverable_id is None:
            continue
        if cd.status not in ("Ativo", "Aguardando"):
            continue
        d = deliverable_by_id.get(cd.deliverable_id)
        if d is None:
            continue
        try:
            rate = attendance_rate(cd, d, sessions, as_of)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            # Caller defensivo: 1 paciente com data invalida nao trava o render.
            _log.warning(
                "attendance_rate falhou para client_id=%s cd_id=%s: %s",
                cd.client_id, cd.id, exc,
            )
            continue
        rates.append((cd.client_id, float(rate)))

    if not rates:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rates, columns=["client_id", "rate"])
    by_client = df.groupby("client_id")["rate"].mean()
    # Renomeia indice: client_id (int) → patient_id (string).
    by_client.index = by_client.index.map(
        lambda cid: patient_by_client.get(int(cid))
    )
    by_client = by_client.dropna()
    return by_client


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

            .dm-quadrant-no-attendance {
                border-left: 3px solid #6b7280;
            }

            .dm-quadrant-no-attendance .dm-patient-dot {
                background: #f3f4f6;
                border-color: #d1d5db;
                color: #374151;
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

    Caminho B / Phase 4 (2026-06-23): added "Frequência" dimension
    sourced from ``row["attendance_rate"]`` (computed in ``render``
    via ``core.frequency.attendance_rate``). NaN → "Sem sessões";
    otherwise ``X% comparecimento`` rounded to 0 decimals.

    Defensive boundary (2026-06-21): any unexpected error here would
    freeze the page for the whole user. We catch broadly, log the
    full traceback via stdlib logging, and return a sentinel dict so
    the quadrant card still renders.
    """
    try:
        score_display = f"{safe_int(row.get('score'))}"
        alerts_display = str(safe_int(row.get("open_alerts")))
        engagement_display = safe_pct(row.get("engagement_rate"))

        attendance_value = row.get("attendance_rate", pd.NA)
        if pd.isna(attendance_value):
            frequency_display = "Sem sessões"
        else:
            try:
                frequency_display = f"{float(attendance_value) * 100:.0f}% comparecimento"
            except (TypeError, ValueError):
                frequency_display = "Sem sessões"

        return {
            "Engajamento": engagement_display,
            "Satisfação": f"{score_display}/10",
            "Alertas": alerts_display,
            "Frequência": frequency_display,
        }
    except Exception:  # noqa: BLE001 — defensive boundary per Cliente directive
        # The log call itself must not raise — a failing ``row.get`` here
        # would defeat the entire defensive boundary.
        try:
            pid = row.get("patient_id")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pid = "<unknown>"
        _log.exception(
            "mapa_decisao._patient_stats failed for row patient_id=%r", pid
        )
        return {
            "Engajamento": "—",
            "Satisfação": "—",
            "Alertas": "—",
            "Frequência": "—",
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
        ("Sem comparecimento", "dm-quadrant-no-attendance"),
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
    """Render the Mapa de Decisão page.

    Defensive boundary (2026-06-21): any exception in the rendering
    pipeline used to freeze the Streamlit page. We now wrap the whole
    body in try/except so the user always sees a friendly error and
    the page never goes blank. The traceback goes to stdlib logging
    so it surfaces in Streamlit Cloud's Logs tab.

    Caminho B / Phase 4 (2026-06-23): add 3a dimensao "Frequencia" via
    ``core.frequency.attendance_rate``. Pacientes com ``attendance_rate``
    conhecido E igual a zero sao movidos para a 5a classe
    "Sem comparecimento" (override sobre as 4 classes normais). Pacientes
    com ``attendance_rate`` NaN (sem cds ativos) permanecem nas 4 classes.
    """
    st.markdown(_decision_map_css(), unsafe_allow_html=True)
    st.title("Mapa de Decisão")
    st.caption("Matriz 2x2 (engajamento x satisfação) + 5ª classe por comparecimento.")

    try:
        summary = patient_summary(data)

        # Phase 4: agrega ``attendance_rate`` por ``patient_id`` (string).
        # ``.reindex`` preserva a ordem de ``summary`` e preenche com NaN
        # pacientes sem cds ativos (nao vao para "Sem comparecimento").
        rates = _compute_patient_attendance_rates(data)
        summary["attendance_rate"] = summary["patient_id"].map(rates)

        # Prevenção inline NA-frágil: ``~eng`` levanta
        # ``TypeError: boolean value of NA is ambiguous`` se
        # ``is_engaged`` carregar ``pd.NA`` (caso real no PRD para
        # pacientes sem entrada em satisfaction_entries / peso).
        sat = summary["is_satisfied"].fillna(False)
        eng = summary["is_engaged"].fillna(False)

        # Single vectorised write replaces 4 sequential boolean `.loc` scans.
        summary["quadrante"] = np.select(
            [eng & sat, eng & ~sat, ~eng & sat],
            ["Engajado + Satisfeito", "Engajado + Não satisfeito", "Não engajado + Satisfeito"],
            default="Não engajado + Não satisfeito",
        )

        groups = quadrants(summary)

        # Phase 4: 5a classe "Sem comparecimento" para pacientes com rate==0.
        # ``==0`` (e nao ``< 0.5``) para alinhar com a spec do plano: rate==0
        # significa nenhuma sessao assistida no periodo. ``NaN != 0`` por
        # semantica pandas -- pacientes sem cds ativos NAO sao movidos.
        if "attendance_rate" in summary.columns:
            no_attendance_ids = set(
                summary.loc[summary["attendance_rate"] == 0, "patient_id"].tolist()
            )
            if no_attendance_ids:
                # Move pacientes das 4 classes originais para a 5a.
                for key in list(groups.keys()):
                    groups[key] = groups[key][
                        ~groups[key]["patient_id"].isin(no_attendance_ids)
                    ].copy()
                groups["Sem comparecimento"] = summary[
                    summary["patient_id"].isin(no_attendance_ids)
                ].copy()
            else:
                # Garante a chave (vazia) para o iterador do ``_decision_map_html``
                groups["Sem comparecimento"] = summary.iloc[0:0].copy()
        else:
            groups["Sem comparecimento"] = summary.iloc[0:0].copy()

        st.markdown('<div class="dm-section-gap"></div>', unsafe_allow_html=True)
        st.markdown(_decision_map_html(groups), unsafe_allow_html=True)
    except Exception:  # noqa: BLE001 — defensive boundary per Cliente directive
        _log.exception("mapa_decisao.render failed")
        st.error(
            "Não foi possível carregar o Mapa de Decisão. "
            "O time já foi notificado — tente recarregar a página."
        )
