"""PDF import wizard for the Pacientes page.

Four-step flow:

1. Upload one or more PDFs via ``st.file_uploader`` (outside any
   ``st.form`` because ``file_uploader`` cannot be nested).
2. Click **Ler PDFs** — the wizard parses each PDF using
   :func:`src.pdf_importer.parse_pdf_to_rows` and stores the
   validated candidates in ``session_state``.
3. Fill in any missing CPFs. When the parser did not extract a
   CPF from the PDF, the wizard renders an inline
   ``st.text_input`` per candidate with a clear label ("CPF para
   Maria da Silva — PDF maria.pdf"). The user's input is
   reflected on the candidate and the candidate is re-validated
   so the dedup status (Novo / Substituir paciente / Substituir
   plano / Substituir paciente e plano) updates on the next
   render.
4. Review the editable preview (KPIs + ``st.data_editor``) and
   click **Importar tudo**. If any candidate has a duplicate
   patient or duplicate plan, a single batched confirmation UI
   is shown (per the user's design — listing all duplicates at
   once, with two buttons: "Substituir cadastros/planos
   existentes" or "Cancelar importação"). After the user picks
   "Substituir", each candidate is persisted with the
   appropriate ``dedup_action`` (replacement keeps the existing
   ``patient_id`` / ``plan_id``; see :mod:`src.pdf_importer.dedup`
   and :func:`src.pdf_importer.persist.persist_rows`). The last
   imported patient is opened via :func:`src.navigation.open_patient`.

The wizard deliberately keeps the heavy pymupdf import inside the
``Ler PDFs`` callback so the Streamlit cold start stays flat. If
pymupdf is missing, the wizard surfaces a clear "install pymupdf"
error instead of a stack trace.

Debug log
---------

A :class:`src.pdf_importer.PdfImportLogger` is created when the
user clicks **Ler PDFs** and the same instance is threaded
through :func:`parse_pdf_to_rows` → :func:`validate_rows` →
:func:`persist_rows` so the user can see the full lifecycle in
one trace. The log is rendered in a collapsed ``st.expander`` at
the bottom of the wizard with a "Baixar log" button. The same
text is also flushed to ``data/test_logs/pdf_import_<ts>.log``
following the existing ``neon_validate_*.log`` /
``scrum_*.log`` naming convention so the on-disk file joins the
rest of the operational logs.
"""
from __future__ import annotations

import copy
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.components.empty_states import render_empty
from src.components.kpi_cards import render_kpis
from src.navigation import open_patient

_UPLOADER_KEY = "import_pdf_files"
_READ_BUTTON_KEY = "import_pdf_read"
_EDITOR_KEY = "import_pdf_editor"
_CONFIRM_KEY = "import_pdf_confirm"
_CONFIRM_DEDUP_KEY = "import_pdf_confirm_dedup"
_CANCEL_KEY = "import_pdf_cancel"
_CANDIDATES_KEY = "import_pdf_candidates"
_CPF_INPUT_PREFIX = "import_pdf_cpf_input_"
_LOG_KEY = "import_pdf_logger"


# Opções da coluna suspensa "Frequência" — mapeia direto para
# ``treatment_plan_items.frequency_type``. Mantém a convenção
# lowercase + "a cada N dias" do operador (a coluna "Desc.
# Frequência" continua livre para variações tipo "1x/semana",
# "2x por semana", etc.).
FREQUENCY_OPTIONS: list[str] = [
    "dose única",
    "diario",
    "a cada 5 dias",
    "semanal",
    "a cada 10 dias",
    "quinzenal",
    "mensal",
    "bimestral",
    "trimestral",
]


def _test_logs_dir() -> Path:
    """Return the directory where PDF import logs are flushed.

    The directory mirrors the existing
    ``neon_validate_*.log`` / ``scrum_*.log`` family so anyone
    running ``ls data/test_logs/`` finds the new files alongside
    the rest of the operational logs.
    """
    return Path("data") / "test_logs"


def _new_logger_filename() -> str:
    """Build a unique-ish filename for the per-batch log file.

    The Streamlit ``session_id`` is included when available so two
    concurrent browser tabs land in distinct files; the
    wall-clock timestamp gives uniqueness across reruns in the
    same session. Falling back to a millisecond-resolution
    timestamp is enough for the dev use case (a single user, one
    wizard at a time).
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        sid = getattr(ctx, "session_id", None) or "anon"
    except Exception:
        sid = "anon"
    ts = time.strftime("%Y%m%dT%H%M%S")
    return f"pdf_import_{sid}_{ts}.log"


def _new_logger() -> "PdfImportLogger":
    """Create a fresh :class:`PdfImportLogger` and stash it in session state.

    The wizard passes this same instance through
    :func:`parse_pdf_to_rows`, :func:`validate_rows` and
    :func:`persist_rows` so all three stages land in one ordered
    trace the user can inspect in the expander.
    """
    from src.pdf_importer import PdfImportLogger

    sink_dir = _test_logs_dir()
    sink_dir.mkdir(parents=True, exist_ok=True)
    sink = sink_dir / _new_logger_filename()
    logger = PdfImportLogger(sink_path=sink)
    st.session_state[_LOG_KEY] = logger
    return logger


def _get_logger() -> "PdfImportLogger | None":
    """Return the logger stashed in session state, or ``None`` if absent.

    The wizard creates the logger on the **Ler PDFs** click; if
    the user navigates back to the wizard and clicks **Importar
    tudo** without re-parsing (rare — the candidates would be
    empty), this returns ``None`` and the import runs silently
    as it did before the log feature.
    """
    return st.session_state.get(_LOG_KEY)


def _wizard_css() -> str:
    return """
        <style>
            .import-pdf-shell {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 1rem 1.1rem 1.2rem;
                margin-top: 0.6rem;
            }
            .import-pdf-title {
                color: #0f172a;
                font-size: 1.05rem;
                font-weight: 700;
                margin: 0 0 0.25rem;
            }
            .import-pdf-subtitle {
                color: #64748b;
                font-size: 0.78rem;
                margin: 0 0 0.85rem;
            }
            .import-pdf-section {
                color: #0f172a;
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.01em;
                margin: 0.85rem 0 0.45rem;
                text-transform: uppercase;
            }
            .import-pdf-cpf-row {
                align-items: center;
                background: #fffbeb;
                border: 1px solid #fde68a;
                border-radius: 6px;
                display: flex;
                flex-wrap: wrap;
                gap: 0.55rem;
                margin: 0.35rem 0 0.55rem;
                padding: 0.55rem 0.7rem;
            }
            .import-pdf-cpf-row .import-pdf-cpf-label {
                color: #92400e;
                font-size: 0.78rem;
                font-weight: 600;
                line-height: 1.25;
                min-width: 18rem;
            }
            .import-pdf-cpf-row div[data-testid="stTextInput"] {
                flex: 1 1 12rem;
                min-width: 12rem;
            }
            div[data-testid="stDataEditor"] {
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
            .import-pdf-actions div[data-testid="stButton"] > button {
                border-radius: 6px;
                font-size: 0.78rem;
                font-weight: 700;
                min-height: 2.2rem;
            }
        </style>
    """


def _dedup_status(candidate: dict) -> str:
    """Compute the human-readable dedup status from the candidate's
    ``dup_patient_id`` / ``dup_plan_id`` slots.

    Returns one of: ``"Novo"``, ``"Substituir paciente"``,
    ``"Substituir plano"``, ``"Substituir paciente e plano"``,
    ``"CPF ausente"`` (the last one wins so the user always sees
    the most actionable problem first).
    """
    if not (candidate.get("patient", {}) or {}).get("cpf"):
        return "CPF ausente"
    if candidate.get("dup_patient_id") and candidate.get("dup_plan_id"):
        return "Substituir paciente e plano"
    if candidate.get("dup_patient_id"):
        return "Substituir paciente"
    if candidate.get("dup_plan_id"):
        return "Substituir plano"
    return "Novo"


def _preview_section_title(candidates: list[dict]) -> str:
    """Build the "Pré-visualização Editável: ..." section header.

    Per the June 2026 redesign the patient identity (name / CPF /
    prontuário) moved out of the per-row columns and into the
    section title so the user reads it once instead of N times.
    The format mirrors the ficha header convention (``CPF:`` /
    ``Prontuário:`` labels) so the user sees the same identity
    vocabulary in both surfaces. For multi-PDF batches the title
    carries the first candidate's identity and a ``(+N mais)``
    suffix so the rest are still visible at a glance.

    Empty fields degrade gracefully to ``"—"`` so the title is
    never malformed; the inline CPF inputs and the dedup
    confirmation dialog cover the "missing CPF" case with a more
    actionable message.
    """
    if not candidates:
        return "Pré-visualização Editável: —"
    first = candidates[0]
    patient = first.get("patient", {}) or {}
    name = (patient.get("name") or "").strip() or "—"
    cpf = (patient.get("cpf") or "").strip() or "—"
    prontuario = (patient.get("medical_record") or "").strip() or "—"
    extra = ""
    if len(candidates) > 1:
        extra = f" (+{len(candidates) - 1} mais)"
    return (
        f"Pré-visualização Editável: {name}, "
        f"CPF: {cpf}, Prontuário: {prontuario}{extra}"
    )


def _sync_editor_to_candidates() -> None:
    """Push the data_editor's current value back onto the candidates.

    Wired to ``st.data_editor(on_change=...)`` so every cell edit
    triggers this callback. It re-runs :func:`_from_preview_rows`
    on the editor's session state and writes the result back to
    :data:`st.session_state[_CANDIDATES_KEY]` so the next render
    reflects the user's edits in real time — not just at import
    time.

    The callback is intentionally a no-op when the editor's value
    isn't a DataFrame yet (first render, no edits) or when there
    are no candidates to update. It is also defensive against the
    first render where ``st.session_state[_EDITOR_KEY]`` is the
    DataFrame that was just built: in that case the round-trip is
    a no-op (no user changes) but we still write the same value
    back so subsequent renders don't get confused.
    """
    edited = st.session_state.get(_EDITOR_KEY)
    if not isinstance(edited, pd.DataFrame):
        return
    candidates = st.session_state.get(_CANDIDATES_KEY, [])
    if not candidates:
        return
    new_candidates = _from_preview_rows(edited, candidates)
    st.session_state[_CANDIDATES_KEY] = new_candidates


def _build_preview_rows(candidates: list[dict]) -> pd.DataFrame:
    """Flatten the candidates into one row per item for the data editor.

    Layout (revised June 2026): the per-item table only carries the
    fields the user actually edits or scans at the item level.
    Patient/plan context (name, CPF, prontuário, dedup status,
    orçamento) was demoted out of the columns because it repeated
    on every row of the same candidate and crowded the editor —
    it now lives in the section title (see
    :func:`_preview_section_title`) so the user can see it once,
    not N times.

    ``filename`` stays in the underlying DataFrame as a hidden
    column (it's filtered out via ``column_order`` in the editor)
    so :func:`_from_preview_rows` can group rows back to their
    source candidate without resorting to brittle row-index math.
    The user never sees it.

    The two frequency columns are intentional and complementary:

    * ``frequencia`` (dropdown, listed first because it's the
      canonical value) is bound to :data:`FREQUENCY_OPTIONS` and
      maps to ``treatment_plan_items.frequency_type`` — the
      normalized category used by the ficha's status pills and
      reports.
    * ``desc_frequencia`` (free text, listed right after) carries
      the free-form description the parser extracted (e.g.
      "1x/semana", "2x por semana"); the user can tweak it. It
      maps to ``treatment_plan_items.frequency_text`` and is
      descriptive only — the canonical record lives in the
      dropdown.
    """
    columns = [
        "procedimento",
        "sessoes",
        "frequencia",
        "desc_frequencia",
        "categoria",
        "revisao",
        "filename",
    ]
    rows: list[dict] = []
    for c in candidates:
        for item in c.get("items", []) or []:
            rows.append(
                {
                    "procedimento": item.get("raw_name") or "",
                    "sessoes": int(item.get("sessions_expected") or 0),
                    # Frequência (dropdown) comes first — it's the
                    # canonical DB value — then Desc. Frequência
                    # (free text) immediately to its right.
                    "frequencia": item.get("frequency_type") or "",
                    "desc_frequencia": item.get("frequency_text") or "",
                    "categoria": item.get("category") or "",
                    "revisao": bool(item.get("needs_manual_review", False)),
                    "filename": c.get("filename", ""),
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def _from_preview_rows(
    edited: pd.DataFrame, candidates: list[dict]
) -> list[dict]:
    """Map the edited rows back to a list of candidates, grouped by filename.

    The patient/plan info of each candidate is preserved (it lives
    outside the data editor now, in the section title and dedup
    confirmation); only the item-level fields are taken from the
    edited DataFrame.

    Per the June 2026 layout, the editor carries six visible
    item-level columns plus a hidden ``filename`` column used
    solely for grouping. The visible columns are:

    * ``procedimento`` → ``raw_name``
    * ``sessoes``      → ``sessions_expected`` (int; empty → None)
    * ``frequencia``   → ``frequency_type`` (one of
      :data:`FREQUENCY_OPTIONS`; empty → None so the column
      round-trips through ``append_row`` as NULL). This is the
      canonical value persisted to the DB.
    * ``desc_frequencia`` → ``frequency_text`` (free text;
      descriptive only)
    * ``categoria``    → ``category``
    * ``revisao``      → ``needs_manual_review`` (bool)
    """
    by_filename: dict[str, dict] = {
        c.get("filename", ""): c for c in candidates
    }
    new_candidates: list[dict] = []
    for filename in edited["filename"].unique():
        group = edited[edited["filename"] == filename]
        original = copy.deepcopy(by_filename.get(filename, {}))
        new_items: list[dict] = []
        for _, row in group.iterrows():
            sessoes_raw = row.get("sessoes")
            sessoes_int = (
                int(sessoes_raw) if pd.notna(sessoes_raw) else None
            )
            new_items.append(
                {
                    "raw_name": (row.get("procedimento") or None),
                    "category": (row.get("categoria") or None),
                    "sessions_expected": sessoes_int,
                    "frequency_text": (row.get("desc_frequencia") or None),
                    "frequency_type": (row.get("frequencia") or None),
                    "needs_manual_review": bool(row.get("revisao", False)),
                }
            )
        original["items"] = new_items
        new_candidates.append(original)
    return new_candidates


def _revalidate_candidates(candidates: list[dict]) -> None:
    """Re-run :func:`validate_rows` on each candidate in place.

    Called after the user types a CPF into the inline input or
    edits a CPF in the data editor — the dedup status slots need
    to be recomputed against the on-disk state for the preview /
    confirmation UI to be accurate.
    """
    from src.pdf_importer import validate_rows

    for c in candidates:
        try:
            validate_rows(c)
        except Exception:
            # Validation should never raise for a parsed candidate;
            # the existing try/except was preserved as a defensive
            # guard so a malformed row doesn't break the whole
            # wizard.
            pass


def _apply_inline_cpf_inputs(candidates: list[dict]) -> None:
    """Fold the per-candidate ``st.text_input`` values back onto the candidates.

    Streamlit re-runs the script on every widget interaction;
    the inputs are stable across reruns thanks to their ``key``
    being derived from the filename. We walk the candidates,
    read the matching session-state value (if any) and write it
    back onto ``candidate["patient"]["cpf"]`` so the next
    :func:`_revalidate_candidates` call sees the user input.
    """
    for c in candidates:
        patient = c.setdefault("patient", {})
        if patient.get("cpf"):
            # Already populated by the parser or by a previous
            # inline input; nothing to do.
            continue
        filename = c.get("filename", "")
        if not filename:
            continue
        typed = st.session_state.get(_CPF_INPUT_PREFIX + filename, "")
        if isinstance(typed, str) and typed.strip():
            patient["cpf"] = typed.strip()


def _handle_read_click(uploaded_files) -> None:
    """Parse each uploaded PDF and store the candidates in session state.

    Errors on individual files are surfaced via ``st.error`` and
    the file is skipped; the rest of the batch is still
    imported.
    """
    try:
        from src.pdf_importer import (
            load_zones,
            parse_pdf_to_rows,
            validate_rows,
        )
    except ImportError as exc:
        st.error(
            f"Dependência ausente ({exc.name}). "
            "Instale com: pip install pymupdf"
        )
        return

    # Fresh logger for this batch. The same instance is reused by
    # the import click (validate + persist) so all three stages
    # land in one ordered trace. The previous batch's logger is
    # dropped — the user is starting a new read.
    logger = _new_logger()

    zones = load_zones()
    candidates: list[dict] = []
    for uploaded in uploaded_files:
        try:
            candidate = parse_pdf_to_rows(
                uploaded.read(), zones, logger=logger,
            )
            candidate["filename"] = uploaded.name
            validate_rows(candidate, logger=logger)
            candidates.append(candidate)
        except Exception as exc:  # noqa: BLE001 — surface any parse error
            st.error(f"Erro ao processar {uploaded.name}: {exc}")
            if logger is not None:
                logger.error(
                    f"parse failed: {uploaded.name}",
                    error=str(exc),
                )
    st.session_state[_CANDIDATES_KEY] = candidates
    # Drop any previously-typed CPF inputs and the editor's state
    # so the new candidates start with a clean slate.
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(_CPF_INPUT_PREFIX):
            st.session_state.pop(key, None)
    st.session_state.pop(_EDITOR_KEY, None)
    st.session_state.pop(_CONFIRM_DEDUP_KEY, None)
    # NO st.rerun(): this function is wired to the file_uploader's
    # ``on_change`` callback (see ``render_importar_pdf_wizard``),
    # and Streamlit already reruns the page after an ``on_change``
    # callback completes. Calling ``st.rerun()`` here triggers the
    # warning ``Calling st.rerun() within a callback is a no-op``.


def _handle_confirm_dedup() -> None:
    """Arm the dedup replacement: set a flag the render loop reads."""
    st.session_state[_CONFIRM_DEDUP_KEY] = True


def _handle_import_click(edited: pd.DataFrame) -> dict:
    """Validate and persist the edited candidates.

    Returns a dict with ``imported_pids``, ``imported_filenames``
    and ``errors`` so the caller can decide what to do (rerun
    to the patient ficha, show errors, etc.).
    """
    try:
        from src.pdf_importer import persist_rows, validate_rows
    except ImportError as exc:
        st.error(
            f"Dependência ausente ({exc.name}). "
            "Instale com: pip install pymupdf"
        )
        return {"imported_pids": [], "imported_filenames": [], "errors": [str(exc)]}

    candidates = st.session_state.get(_CANDIDATES_KEY, [])
    new_candidates = _from_preview_rows(edited, candidates)
    # Reuse the logger created in ``_handle_read_click`` so the
    # final validate and the persist events land in the same
    # trace. ``_get_logger`` returns ``None`` if the user landed
    # here without clicking **Ler PDFs** (defensive — the import
    # button is only shown after a read).
    logger = _get_logger()
    imported_pids: list[str] = []
    imported_filenames: list[str] = []
    errors: list[str] = []
    for candidate in new_candidates:
        validate_rows(candidate, logger=logger)
        if candidate.get("status") == "Erro":
            errors.append(
                f"{candidate.get('filename', '?')}: "
                f"{'; '.join(candidate.get('warnings', []))}"
            )
            continue
        # Build the dedup action from the candidate's dup slots —
        # the wizard has already confirmed the user wants to
        # proceed (or there were no duplicates to begin with).
        dedup_action = {
            "replace_patient": bool(candidate.get("dup_patient_id")),
            "replace_plan": bool(candidate.get("dup_plan_id")),
        }
        try:
            result = persist_rows(
                candidate,
                dedup_action=dedup_action,
                logger=logger,
            )
            imported_pids.append(result["patient_id"])
            imported_filenames.append(candidate.get("filename", ""))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate.get('filename', '?')}: {exc}")
            if logger is not None:
                logger.error(
                    f"persist failed: {candidate.get('filename', '?')}",
                    error=str(exc),
                )

    total_items = sum(
        len(c.get("items", []) or [])
        for c in new_candidates
        if c.get("filename") in imported_filenames
    )
    if imported_pids:
        st.toast(
            f"Importação concluída: {len(imported_pids)} paciente(s), "
            f"{total_items} item(ns)."
        )
    # Revisão summary — count how many items the user actually
    # checked off (vs how many the parser had flagged). The
    # ``_from_preview_rows`` step rewrote ``needs_manual_review``
    # on every item from the editor's Revisão column, so a True
    # here means "the user validated this row" and False means
    # "the user left it unchecked (could be intentional or could
    # be missed)".
    items_reviewed = sum(
        1
        for c in new_candidates
        for i in (c.get("items", []) or [])
        if i.get("needs_manual_review")
    )
    items_pending = total_items - items_reviewed
    if logger is not None and total_items > 0:
        logger.stage(
            "review",
            total=total_items,
            reviewed=items_reviewed,
            pending=items_pending,
        )
    # Close the log. ``finish`` is idempotent so it's safe to call
    # even when no rows were imported (the log will record
    # ``success=False`` with an empty ``imported_pids``). The
    # on-disk sink gets flushed here so the user can grab the file
    # from ``data/test_logs/`` even if the import button wasn't
    # the one that completed the batch.
    if logger is not None:
        logger.finish(
            success=bool(imported_pids) and not errors,
            imported_pids=imported_pids,
            imported_filenames=imported_filenames,
            errors=len(errors),
        )
    return {
        "imported_pids": imported_pids,
        "imported_filenames": imported_filenames,
        "errors": errors,
    }


def _handle_cancel_click() -> None:
    """Close the wizard and clear any staged candidates."""
    st.session_state[_CANDIDATES_KEY] = []
    st.session_state.pop(_EDITOR_KEY, None)
    st.session_state.pop(_CONFIRM_DEDUP_KEY, None)
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(_CPF_INPUT_PREFIX):
            st.session_state.pop(key, None)
    st.session_state["import_pdf_open"] = False
    # Drop the logger so a fresh read starts clean. ``finish`` is
    # idempotent so the in-memory log still gets written to disk
    # before we drop the reference — the user might want to
    # inspect it after cancelling (e.g. when the parse failed
    # before they got to the import step).
    logger = st.session_state.get(_LOG_KEY)
    if logger is not None:
        logger.finish(success=False, reason="cancelled")
    st.session_state.pop(_LOG_KEY, None)
    # NO st.rerun(): this function is wired to the Cancel button's
    # ``on_click`` (see ``render_importar_pdf_wizard``). Streamlit
    # already reruns the page after an ``on_click`` callback
    # completes; calling ``st.rerun()`` here is a no-op and emits
    # the warning ``Calling st.rerun() within a callback is a no-op``.


def _render_cpf_inputs(candidates: list[dict]) -> None:
    """Render one inline text_input per candidate with a missing CPF.

    The inputs are stable across reruns (keyed by the PDF
    filename) so the user can fill them in incrementally. When a
    new value is captured, :func:`_apply_inline_cpf_inputs`
    writes it onto the candidate on the next render.
    """
    missing = [c for c in candidates if not (c.get("patient", {}) or {}).get("cpf")]
    if not missing:
        return

    st.markdown(
        '<p class="import-pdf-section">CPF ausente</p>',
        unsafe_allow_html=True,
    )
    for c in missing:
        filename = c.get("filename", "?")
        name = (c.get("patient", {}) or {}).get("name") or "(sem nome)"
        cpf_key = _CPF_INPUT_PREFIX + filename
        cols = st.columns([3, 2])
        with cols[0]:
            st.markdown(
                f'<div class="import-pdf-cpf-label">'
                f"CPF para <b>{name}</b> — PDF <code>{filename}</code>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.text_input(
                "CPF",
                key=cpf_key,
                placeholder="000.000.000-00",
                label_visibility="collapsed",
            )


def _render_log_expander() -> None:
    """Render the collapsed expander that shows the import event log.

    Always visible once the user clicks **Ler PDFs** so they can
    see the parse/validate trace while still filling in CPFs and
    reviewing the preview. The expander is collapsed by default
    — opening it is the explicit "I want to debug" gesture. The
    on-disk sink path is shown as a caption so the user knows
    where the file lives if they want to grab it from
    ``data/test_logs/`` directly.
    """
    logger = _get_logger()
    if logger is None:
        return
    n = len(logger.events())
    label = f"Log de eventos ({n})"
    sink = logger.sink_path
    with st.expander(label, expanded=False):
        st.caption(
            "Cada linha registra uma etapa do parse → validate → persist. "
            "Use o botão abaixo para baixar o arquivo completo."
        )
        st.code(logger.to_text(), language="text")
        if sink is not None:
            try:
                payload = logger.to_text().encode("utf-8")
            except Exception:
                payload = b""
            st.download_button(
                "Baixar log",
                data=payload or logger.to_text(),
                file_name=sink.name,
                mime="text/plain",
                use_container_width=False,
                key="import_pdf_log_download",
            )
            st.caption(f"Salvo em: {sink}")


def _render_dedup_confirmation(candidates: list[dict]) -> None:
    """Render the batched "Substituir cadastros/planos existentes" prompt.

    Shown when at least one candidate has a duplicate patient or
    duplicate plan. The user must explicitly confirm (or cancel
    the whole import) before the wizard proceeds.
    """
    n_dup_patient = sum(1 for c in candidates if c.get("dup_patient_id"))
    n_dup_plan = sum(1 for c in candidates if c.get("dup_plan_id"))

    st.warning(
        f"Encontramos {n_dup_patient} paciente(s) já cadastrado(s) e "
        f"{n_dup_plan} plano(s) já registrado(s) nesta importação. "
        "Substituir os cadastros e planos existentes pelos dados do PDF?"
    )

    rows_html = []
    for c in candidates:
        status = _dedup_status(c)
        if status == "Novo" or status == "CPF ausente":
            continue
        name = (c.get("patient", {}) or {}).get("name") or "(sem nome)"
        filename = c.get("filename", "?")
        import html as _html
        rows_html.append(
            f'<li><b>{_html.escape(name)}</b> — <code>{_html.escape(filename)}</code>: '
            f'{_html.escape(status)}</li>'
        )
    if rows_html:
        st.markdown("<ul>" + "".join(rows_html) + "</ul>", unsafe_allow_html=True)

    st.markdown(
        '<div class="import-pdf-actions" style="margin-top:0.6rem;">',
        unsafe_allow_html=True,
    )
    action_cols = st.columns([1, 1, 6])
    with action_cols[0]:
        st.button(
            "Substituir cadastros/planos existentes",
            key=_CONFIRM_KEY,
            type="primary",
            use_container_width=True,
            on_click=_handle_confirm_dedup,
        )
    with action_cols[1]:
        st.button(
            "Cancelar importação",
            key=_CANCEL_KEY,
            use_container_width=True,
            on_click=_handle_cancel_click,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_importar_pdf_wizard() -> None:
    """Render the multi-PDF import wizard."""
    st.markdown(_wizard_css(), unsafe_allow_html=True)
    st.markdown(
        '<div class="import-pdf-shell">'
        '<p class="import-pdf-title">Importar paciente(s) do PDF</p>'
        '<p class="import-pdf-subtitle">Selecione um ou mais PDFs de orçamento e revise os campos extraídos antes de persistir.</p>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Selecione um ou mais PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key=_UPLOADER_KEY,
    )
    if not uploaded:
        st.markdown("</div>", unsafe_allow_html=True)
        render_empty("Selecione ao menos um PDF para começar.")
        return

    st.button(
        "Ler PDFs",
        key=_READ_BUTTON_KEY,
        type="primary",
        on_click=_handle_read_click,
        args=(uploaded,),
    )

    candidates = st.session_state.get(_CANDIDATES_KEY, [])
    if not candidates:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Fold any typed CPF inputs onto the candidates and re-validate
    # so the dedup slots reflect the user's latest input.
    _apply_inline_cpf_inputs(candidates)
    _revalidate_candidates(candidates)
    st.session_state[_CANDIDATES_KEY] = candidates

    n_pdfs = len(candidates)
    n_items = sum(len(c.get("items", []) or []) for c in candidates)
    n_items_review = sum(
        1
        for c in candidates
        for i in (c.get("items", []) or [])
        if i.get("needs_manual_review")
    )
    n_patients_ok = sum(1 for c in candidates if c.get("status") != "Erro")
    render_kpis(
        {
            "PDFs lidos": n_pdfs,
            "Pacientes OK": n_patients_ok,
            "Itens extraídos": n_items,
            "Itens com alerta": n_items_review,
        },
        columns=4,
    )

    # Inline CPF input for any candidate whose CPF the parser
    # missed — the user fills these in before the import runs.
    _render_cpf_inputs(candidates)

    # Section title now carries the patient identity instead of
    # repeating it on every row of the table (June 2026 redesign).
    st.markdown(
        f'<p class="import-pdf-section">{_preview_section_title(candidates)}</p>',
        unsafe_allow_html=True,
    )

    # Revisão rule: count items the parser flagged as needing
    # manual review and notify the user. The notification is
    # *advisory* — it doesn't block the import. We log it too so
    # the operational trace shows the suggestion landed; on
    # import we record how many of those flags were actually
    # checked off.
    items_to_review = sum(
        1
        for c in candidates
        for i in (c.get("items", []) or [])
        if i.get("needs_manual_review")
    )
    if items_to_review > 0:
        st.info(
            f"🔍 **{items_to_review} item(ns)** foram marcados pelo "
            "parser como precisando de revisão manual. Marque a "
            "checkbox **Revisão** para cada item que você validar "
            "— a regra apenas notifica e registra no log, não "
            "bloqueia a importação."
        )
        logger = _get_logger()
        if logger is not None:
            logger.warn(
                f"{items_to_review} item(ns) pendentes de revisão",
                item_count=items_to_review,
            )

    rows = _build_preview_rows(candidates)
    # ``filename`` lives in the DataFrame for the round-trip but
    # is filtered out of the visible columns via ``column_order``.
    # Frequência (dropdown) and Desc. Frequência (free text) sit
    # side-by-side; the dropdown comes first because it's the
    # canonical value persisted to ``treatment_plan_items.
    # frequency_type`` — the free-text column is descriptive
    # only and feeds ``frequency_text``.
    visible_columns = [
        "procedimento",
        "sessoes",
        "frequencia",
        "desc_frequencia",
        "categoria",
        "revisao",
    ]
    column_config = {
        "procedimento": st.column_config.TextColumn(
            "Procedimento", required=True
        ),
        "sessoes": st.column_config.NumberColumn(
            "Sessões", min_value=0, step=1, format="%d"
        ),
        "frequencia": st.column_config.SelectboxColumn(
            "Frequência",
            options=FREQUENCY_OPTIONS,
            required=False,
            help=(
                "Valor padronizado que vai para o banco de dados "
                "(treatment_plan_items.frequency_type). Use a "
                "coluna ao lado para variações livres como "
                "'1x/semana'."
            ),
        ),
        "desc_frequencia": st.column_config.TextColumn(
            "Desc. Frequência",
            help=(
                "Descrição livre da frequência — não é persistida "
                "como campo canônico. Use Frequência (lista "
                "suspensa) para garantir uniformidade do registro."
            ),
        ),
        "categoria": st.column_config.TextColumn("Categoria"),
        "revisao": st.column_config.CheckboxColumn("Revisão"),
        "filename": st.column_config.TextColumn("filename", disabled=True),
    }
    st.data_editor(
        rows,
        column_config=column_config,
        column_order=visible_columns,
        num_rows="fixed",
        use_container_width=True,
        key=_EDITOR_KEY,
        on_change=_sync_editor_to_candidates,
    )

    # Decide whether the import button can proceed, whether the
    # dedup confirmation is needed, or whether the import is
    # blocked on a missing CPF.
    missing_cpf = [
        c for c in candidates if not (c.get("patient", {}) or {}).get("cpf")
    ]
    has_duplicates = any(
        c.get("dup_patient_id") or c.get("dup_plan_id") for c in candidates
    )
    dedup_confirmed = bool(st.session_state.get(_CONFIRM_DEDUP_KEY))

    if missing_cpf:
        st.error(
            f"CPF ausente para {len(missing_cpf)} paciente(s). "
            "Informe o CPF acima (ou na coluna CPF da pré-visualização) "
            "antes de importar."
        )
        _render_log_expander()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if has_duplicates and not dedup_confirmed:
        _render_dedup_confirmation(candidates)
        _render_log_expander()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.markdown(
        '<div class="import-pdf-actions" style="margin-top:0.6rem;">',
        unsafe_allow_html=True,
    )
    action_cols = st.columns([1, 1, 6])
    with action_cols[0]:
        import_clicked = st.button(
            "Importar tudo",
            key=_CONFIRM_KEY if has_duplicates else "import_pdf_confirm_clean",
            type="primary",
            use_container_width=True,
        )
    with action_cols[1]:
        st.button(
            "Cancelar",
            key="import_pdf_cancel_clean" if not has_duplicates else "import_pdf_cancel_dedup",
            use_container_width=True,
            on_click=_handle_cancel_click,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    _render_log_expander()
    st.markdown("</div>", unsafe_allow_html=True)

    if import_clicked:
        edited_df = st.session_state.get(_EDITOR_KEY, rows)
        # Fallback: when the data_editor was seeded with an empty
        # DataFrame (e.g. all candidates had zero items) the
        # editor can round-trip without the original columns.
        # Re-seed from ``rows`` in that case so the import
        # handler can iterate by filename.
        if not isinstance(edited_df, pd.DataFrame) or "filename" not in edited_df.columns:
            edited_df = rows
        # Wrap the persist step in a spinner so the user sees
        # feedback while the data layer writes the rows. The
        # message uses the operator's wording ("Solicitação em
        # andamento...") per the June 2026 spec. ``st.spinner``
        # renders the spinner inside a ``st.info``-style card
        # and blocks the page until the ``with`` block exits —
        # exactly the "janela" the operator asked for. We add a
        # minimum dwell so the spinner is visible long enough to
        # register even for fast inserts.
        with st.spinner("Solicitação em andamento..."):
            result = _handle_import_click(edited_df)
        for err in result["errors"]:
            st.error(err)
        if result["imported_pids"]:
            st.session_state[_CANDIDATES_KEY] = []
            st.session_state.pop(_EDITOR_KEY, None)
            st.session_state.pop(_CONFIRM_DEDUP_KEY, None)
            for key in list(st.session_state.keys()):
                if isinstance(key, str) and key.startswith(_CPF_INPUT_PREFIX):
                    st.session_state.pop(key, None)
            # The import click already called ``logger.finish``;
            # drop the reference so a fresh read starts with a
            # blank log instead of appending to the imported one.
            st.session_state.pop(_LOG_KEY, None)
            st.session_state["import_pdf_open"] = False
            open_patient(result["imported_pids"][-1])
            st.rerun()
