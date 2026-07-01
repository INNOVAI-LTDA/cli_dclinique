"""Catalogo de Servicos page (MVP Jornada Clinica, Fase 1).

Pagina READ-ONLY por design (Q7 da reuniao de 2026-06-30): a entrada
de dados no catalogo acontece via upload de arquivo CSV
(``scripts/import_service_catalog.py --csv ... --source ...``), NAO
via formulario na UI. Isso evita que a equipe altere a nomenclatura
canonica por acidente e mantem a fonte de verdade em formato
versionado (o CSV enviado pela equipe / pela Dane).

Filtros disponiveis:
  - classification: active / rare / obsolete
  - category: injectable / professional / other (None para "(vazio)")
  - source: lista_ativa / dane / manual / excel_import / pdf_import
  - busca textual por nome ou codigo

Tambem mostra a fila de revisao (servicos nao-classificados
encontrados em Excel/PDF — Fase 2/3 enfileiram via
:func:`src.service_catalog.review_queue.enqueue_unknown_service`).
Acoes de classificar/ignorar entram na Fase 6 (junto com o painel
de alertas).
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.service_catalog.types import Category, Classification, SourceTag


CLASSIFICATION_OPTIONS: tuple[str, ...] = ("active", "rare", "obsolete")
CATEGORY_OPTIONS: tuple[str, ...] = ("injectable", "professional", "other")
SOURCE_OPTIONS: tuple[str, ...] = (
    "lista_ativa",
    "dane",
    "manual",
    "excel_import",
    "pdf_import",
)
REVIEW_STATUS_OPTIONS: tuple[str, ...] = ("pending", "classified", "ignored")


def _catalogo_css() -> str:
    return """
        <style>
            .catalogo-page-title {
                color: #111827;
                font-size: 1.15rem;
                font-weight: 750;
                line-height: 1.2;
                margin: 0 0 0.32rem;
            }
            .catalogo-caption {
                color: #64748b;
                font-size: 0.78rem;
                margin: 0 0 0.72rem;
            }
            .catalogo-subtitle {
                color: #0f172a;
                font-size: 0.92rem;
                font-weight: 700;
                margin: 1.0rem 0 0.4rem;
            }
            .catalogo-table-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                overflow: hidden;
                padding: 0.4rem;
            }
            .catalogo-row {
                align-items: center;
                border-bottom: 1px solid #edf2f7;
                color: #1f2937;
                display: flex;
                font-size: 0.74rem;
                gap: 0.6rem;
                padding: 0.5rem 0.7rem;
            }
            .catalogo-row:last-child { border-bottom: none; }
            .catalogo-row:hover { background: #f8fbff; }
            .catalogo-cell-code { flex: 1.4; font-family: monospace; color: #0f172a; }
            .catalogo-cell-name { flex: 3.0; color: #111827; font-weight: 600; }
            .catalogo-cell-class { flex: 0.9; }
            .catalogo-cell-cat { flex: 1.1; color: #475569; }
            .catalogo-cell-per { flex: 1.2; color: #475569; }
            .catalogo-cell-src { flex: 1.4; color: #334155; }
            .catalogo-cell-date { flex: 1.2; color: #475569; }

            .catalogo-badge {
                border-radius: 999px;
                display: inline-flex;
                font-size: 0.68rem;
                font-weight: 700;
                line-height: 1;
                padding: 0.22rem 0.55rem;
            }
            .catalogo-class-active { background: #dcfce7; color: #166534; }
            .catalogo-class-rare { background: #fef3c7; color: #b45309; }
            .catalogo-class-obsolete { background: #fee2e2; color: #b91c1c; }
            .catalogo-cat-injectable { background: #e0e7ff; color: #3730a3; }
            .catalogo-cat-professional { background: #fce7f3; color: #9d174d; }
            .catalogo-cat-other { background: #e5e7eb; color: #374151; }
            .catalogo-cat-empty { color: #94a3b8; font-style: italic; }

            .catalogo-empty {
                color: #64748b;
                font-size: 0.82rem;
                padding: 1.4rem;
                text-align: center;
            }

            .catalogo-upload-hint {
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #334155;
                font-family: monospace;
                font-size: 0.78rem;
                padding: 0.62rem 0.78rem;
                margin: 0.42rem 0 0.72rem;
            }
        </style>
    """


def _ensure_state() -> None:
    st.session_state.setdefault("catalogo_classification", "Todas")
    st.session_state.setdefault("catalogo_category", "Todas")
    st.session_state.setdefault("catalogo_source", "Todas")
    st.session_state.setdefault("catalogo_query", "")
    st.session_state.setdefault("catalogo_review_status", "pending")


def _class_badge(cls: str) -> str:
    if cls == "active":
        return "catalogo-class-active"
    if cls == "rare":
        return "catalogo-class-rare"
    if cls == "obsolete":
        return "catalogo-class-obsolete"
    return ""


def _cat_badge(cat: object) -> str:
    if cat is None or (isinstance(cat, float) and pd.isna(cat)) or cat == "":
        return "catalogo-cat-empty"
    s = str(cat)
    if s == "injectable":
        return "catalogo-cat-injectable"
    if s == "professional":
        return "catalogo-cat-professional"
    if s == "other":
        return "catalogo-cat-other"
    return ""


def _format_date(value: object) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return "--"
    return dt.strftime("%d/%m/%Y")


def _format_periodicity(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "(pontual)"
    return f"{int(value)} dias"


def _render_filters(catalog: pd.DataFrame) -> None:
    cols = st.columns([1, 1, 1, 2])
    class_options = ["Todas"] + list(CLASSIFICATION_OPTIONS)
    cat_options = ["Todas"] + list(CATEGORY_OPTIONS)
    src_options = ["Todas"] + list(SOURCE_OPTIONS)
    cols[0].selectbox(
        "Classificação",
        class_options,
        key="catalogo_classification",
    )
    cols[1].selectbox(
        "Categoria",
        cat_options,
        key="catalogo_category",
    )
    cols[2].selectbox(
        "Origem",
        src_options,
        key="catalogo_source",
    )
    cols[3].text_input(
        "Buscar",
        placeholder="Buscar por nome ou código...",
        key="catalogo_query",
    )


def _apply_filters(catalog: pd.DataFrame) -> pd.DataFrame:
    filtered = catalog.copy()
    classification = st.session_state.get("catalogo_classification", "Todas")
    category = st.session_state.get("catalogo_category", "Todas")
    source = st.session_state.get("catalogo_source", "Todas")
    query = (st.session_state.get("catalogo_query", "") or "").strip().lower()

    if classification != "Todas" and "classification" in filtered.columns:
        filtered = filtered[filtered["classification"].astype(str) == classification]
    if category != "Todas" and "category" in filtered.columns:
        filtered = filtered[filtered["category"].astype(str) == category]
    if source != "Todas" and "source" in filtered.columns:
        filtered = filtered[filtered["source"].astype(str) == source]
    if query:
        mask = pd.Series(False, index=filtered.index)
        if "service_code" in filtered.columns:
            mask = mask | filtered["service_code"].astype(str).str.lower().str.contains(query, na=False)
        if "name" in filtered.columns:
            mask = mask | filtered["name"].astype(str).str.lower().str.contains(query, na=False)
        filtered = filtered[mask]
    return filtered.sort_values(["service_code"], ascending=True) if "service_code" in filtered.columns else filtered


def _render_catalog_table(catalog: pd.DataFrame) -> None:
    if catalog.empty:
        st.markdown(
            '<div class="catalogo-table-shell"><div class="catalogo-empty">Nenhum serviço para os filtros selecionados.</div></div>',
            unsafe_allow_html=True,
        )
        return

    header_html = (
        '<div class="catalogo-table-shell">'
        '<div class="catalogo-row" style="font-weight:700;color:#0f172a;background:#f8fafc;">'
        '<div class="catalogo-cell-code">Código</div>'
        '<div class="catalogo-cell-name">Nome</div>'
        '<div class="catalogo-cell-class">Classificação</div>'
        '<div class="catalogo-cell-cat">Categoria</div>'
        '<div class="catalogo-cell-per">Periodicidade</div>'
        '<div class="catalogo-cell-src">Origem</div>'
        '<div class="catalogo-cell-date">Criado em</div>'
        "</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    for _, row in catalog.iterrows():
        code = str(row.get("service_code", ""))
        name = str(row.get("name", ""))
        cls = str(row.get("classification", ""))
        cat = row.get("category")
        per = row.get("default_periodicity_days")
        src = str(row.get("source", ""))
        created = _format_date(row.get("created_at"))

        cat_text = "(vazio)" if cat is None or (isinstance(cat, float) and pd.isna(cat)) or cat == "" else str(cat)

        row_html = (
            '<div class="catalogo-row">'
            f'<div class="catalogo-cell-code">{html.escape(code)}</div>'
            f'<div class="catalogo-cell-name">{html.escape(name)}</div>'
            f'<div class="catalogo-cell-class"><span class="catalogo-badge {_class_badge(cls)}">{html.escape(cls)}</span></div>'
            f'<div class="catalogo-cell-cat">{html.escape(cat_text)}</div>'
            f'<div class="catalogo-cell-per">{html.escape(_format_periodicity(per))}</div>'
            f'<div class="catalogo-cell-src">{html.escape(src)}</div>'
            f'<div class="catalogo-cell-date">{created}</div>'
            "</div>"
        )
        st.markdown(row_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_review_queue(review_queue: pd.DataFrame) -> None:
    st.markdown(
        '<h2 class="catalogo-subtitle">Fila de revisão (serviços não classificados)</h2>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Serviços encontrados em Excel/PDF que ainda não estão no catálogo. "
        "Ações de classificar/ignorar entram na Fase 6."
    )

    if review_queue.empty:
        st.markdown(
            '<div class="catalogo-table-shell"><div class="catalogo-empty">Fila vazia — nenhum serviço pendente.</div></div>',
            unsafe_allow_html=True,
        )
        return

    status_options = ["Todos"] + list(REVIEW_STATUS_OPTIONS)
    st.selectbox(
        "Status",
        status_options,
        key="catalogo_review_status",
    )
    active_status = st.session_state.get("catalogo_review_status", "pending")
    filtered = review_queue
    if active_status != "Todos" and "status" in filtered.columns:
        filtered = filtered[filtered["status"].astype(str) == active_status]

    if filtered.empty:
        st.markdown(
            '<div class="catalogo-table-shell"><div class="catalogo-empty">Nenhuma entrada com este status.</div></div>',
            unsafe_allow_html=True,
        )
        return

    st.dataframe(
        filtered[["id", "service_name", "source", "occurrences", "first_seen_at", "last_seen_at", "status"]],
        width="stretch",
        hide_index=True,
    )


def render(data):
    _ensure_state()
    st.markdown(_catalogo_css(), unsafe_allow_html=True)

    st.markdown(
        '<h1 class="catalogo-page-title">Catálogo de Serviços</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="catalogo-caption">Lista canônica usada para validar serviços '
        'encontrados em Excel/PDF (matching por nome exato).</p>',
        unsafe_allow_html=True,
    )

    # Hint de upload (Q7: entrada via CSV, nao UI).
    st.markdown(
        '<div class="catalogo-upload-hint">'
        'Para adicionar/atualizar serviços, rode no terminal:<br/>'
        'python scripts/import_service_catalog.py '
        '--csv &lt;arquivo.csv&gt; --source lista_ativa|dane'
        '</div>',
        unsafe_allow_html=True,
    )

    catalog = data.get("service_catalog", pd.DataFrame())
    review_queue = data.get("service_review_queue", pd.DataFrame())

    # KPI rapido: total no catalogo + total na fila.
    col_a, col_b = st.columns(2)
    col_a.metric("Serviços no catálogo", len(catalog))
    pending_count = 0
    if not review_queue.empty and "status" in review_queue.columns:
        pending_count = int((review_queue["status"].astype(str) == "pending").sum())
    col_b.metric("Pendentes na fila de revisão", pending_count)

    _render_filters(catalog)
    filtered = _apply_filters(catalog)
    st.caption(f"{len(filtered)} de {len(catalog)} serviços exibidos.")
    _render_catalog_table(filtered)

    _render_review_queue(review_queue)