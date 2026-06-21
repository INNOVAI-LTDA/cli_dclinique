"""Persist a validated PDF candidate to the data layer.

Three flows share the same persist step:

1. **Insert a new patient + new plan + new items** — the default
   path when the PDF introduces a brand-new patient (no CPF
   collision) and a brand-new plan (no ``(patient_id, issue_date)``
   collision for that patient).

2. **Replace an existing patient's cadastro** — when the CPF
   matches a row in ``patients.csv``. The patient row is patched
   in place via :func:`src.pdf_importer.dedup.replace_patient`
   (preserves ``patient_id`` and ``created_at``; only the mutable
   fields are updated). The plan and items then fall through to
   either the insert or replace-plan path depending on the
   ``issue_date`` collision.

3. **Replace an existing plan** — when
   ``(patient_id, issue_date)`` matches a row in
   ``treatment_plans.csv``. The plan's items and goal are deleted
   via :func:`src.data_layer.replace_plan`, the plan row is
   patched in place (preserves ``plan_id``), and the new items
   are inserted under the same ``plan_id`` so any
   ``appointment_items`` FK references stay valid.

The decision between (1)/(2)/(3) is driven by a small
``dedup_action`` dict the caller passes in — see :func:`persist_rows`
for the contract. The wizard derives it from
``candidate["dup_patient_id"]`` and ``candidate["dup_plan_id"]``
which :func:`src.pdf_importer.validate.validate_rows` populates.

Beyond the three core tables (patients, treatment_plans,
treatment_plan_items) this module also projects the plan into
the two satellite tables that the ficha page reads from:

* ``patient_goals`` — one row per plan, so the ficha's info row
  ("Objetivo", "Peso meta") and summary ("Observações") render.
* ``execution_summary`` — one row per plan item, so the ficha's
  "Plano de tratamento" table renders. The wizard can't observe
  sessions completed (no appointments yet), so it writes
  ``sessions_completed=0`` and ``status="Aguardando início"`` for
  every newly-imported item.

This projection is the read-model contract the ficha was built
against. Skipping it leaves the imported patient invisible in the
ficha even though the patient + plan + items are correctly
written — which is the bug that surfaced in June 2026 when the
ficha started showing empty tables for PDF-imported patients.

This is the only module in ``src/pdf_importer/`` that touches
Streamlit session state — all other modules are pure functions of
the PDF and the on-disk CSVs.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.data_layer import (
    append_row,
    delete_rows,
    next_id,
    next_id_with_prefix,
    replace_plan as _data_layer_replace_plan,
)
from src.pdf_importer.dedup import replace_patient as _dedup_replace_patient
from src.pdf_importer.log import PdfImportLogger


# Status sentinela para ``execution_summary.status`` quando o item é
# recém-importado (zero sessões realizadas). É o mesmo default que o
# cadastro manual da ficha usa em ``src.components.ficha._handle_submit``
# — manter um valor só evita que a UI renderize "—" em vez de um pill
# com cor consistente.
_DEFAULT_EXEC_STATUS = "Aguardando início"


def _build_goal_row(goal_id: str, patient_id: str, plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Assemble the row dict for an insert into ``patient_goals``.

    The PDF rarely carries weight data (``initial_weight`` /
    ``target_weight``), so the columns default to ``None`` and the
    ficha's "Peso inicial / Peso meta" cells render as "—". The
    ``goal_type`` and ``goal_notes`` come from the plan's
    ``main_goal`` / ``notes`` fields the parser extracted, with a
    neutral fallback when the PDF was sparse.
    """
    return {
        "goal_id": goal_id,
        "patient_id": patient_id,
        "plan_id": plan_id,
        "goal_type": (plan.get("main_goal") or "").strip() or "Não informado",
        "initial_weight": None,
        "target_weight": None,
        "target_date": _to_date_or_nat(plan.get("end_date")),
        "goal_notes": plan.get("notes") or None,
    }


def _build_execution_row(
    execution_id: str,
    patient_id: str,
    plan_id: str,
    budget_code: str,
    item: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the row dict for an insert into ``execution_summary``.

    Mirrors the projection the ficha page expects: a row per plan
    item with ``sessions_expected``, ``sessions_completed`` and
    ``sessions_remaining`` populated. The wizard can't observe
    sessions completed (no appointment data has been registered
    yet), so ``sessions_completed`` defaults to 0 and
    ``sessions_remaining`` equals ``sessions_expected``.

    ``frequency_type`` is projected from the item's
    ``frequency_type`` slot (the normalized dropdown value) so the
    ficha's "Frequência de Aplicação" column can read it directly
    from the satellite view. NULL is fine — the ficha renders "-"
    when the column is empty (e.g. for plans imported before the
    column existed).
    """
    sessions_expected = _coerce_int_or_none(item.get("sessions_expected"))
    return {
        "execution_id": execution_id,
        "patient_id": patient_id,
        "plan_id": plan_id,
        "budget_code": budget_code,
        "procedure_raw": item.get("raw_name"),
        "procedure_category": item.get("category") or None,
        "status": _DEFAULT_EXEC_STATUS,
        "sessions_expected": sessions_expected,
        "sessions_completed": 0,
        "sessions_remaining": sessions_expected,
        "plan_created_at": _to_date_or_today(plan.get("issue_date")),
        "frequency_type": item.get("frequency_type") or None,
    }


def _to_date_or_today(value: Any) -> pd.Timestamp:
    """Coerce a date string to ``pd.Timestamp``, falling back to today."""
    if not value:
        return pd.Timestamp.today().normalize()
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.Timestamp.today().normalize()
    return parsed.normalize()


def _to_date_or_nat(value: Any) -> pd.Timestamp | pd.NaT:
    """Coerce a date string to ``pd.Timestamp``, falling back to NaT."""
    if not value:
        return pd.NaT
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed.normalize()


def _coerce_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_patient_row(patient_id: str, patient: dict[str, Any]) -> dict[str, Any]:
    """Assemble the row dict for an insert into ``patients``."""
    return {
        "patient_id": patient_id,
        "name": patient.get("name"),
        "normalized_name": patient.get("normalized_name"),
        "medical_record": patient.get("medical_record") or None,
        "phone": patient.get("phone") or None,
        "age": _coerce_int_or_none(patient.get("age")),
        "cpf": patient.get("cpf") or None,
        "rg": patient.get("rg") or None,
        "address": patient.get("address") or None,
        "created_at": _to_date_or_today(patient.get("created_at")),
    }


def _build_plan_row(plan_id: str, patient_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Assemble the row dict for an insert into ``treatment_plans``."""
    # ``budget_code`` is minted from the data layer if the parse did
    # not surface one — the source PDFs do not carry a budget
    # number, so we always end up with a fresh ``orc_new_NNN``.
    budget_code = (plan.get("budget_code") or "").strip() or next_id_with_prefix("orc_new")
    return {
        "plan_id": plan_id,
        "patient_id": patient_id,
        "budget_code": budget_code,
        "issue_date": _to_date_or_today(plan.get("issue_date")),
        "start_date": _to_date_or_today(plan.get("start_date")),
        "end_date": _to_date_or_nat(plan.get("end_date")),
        "status": plan.get("status") or "Ativo",
        "main_goal": plan.get("main_goal") or None,
        "is_renewal": bool(plan.get("is_renewal", False)),
        "notes": plan.get("notes") or None,
    }


def _build_item_row(item_id: str, plan_id: str, patient_id: str, budget_code: str, item: dict[str, Any]) -> dict[str, Any]:
    """Assemble the row dict for an insert into ``treatment_plan_items``."""
    return {
        "plan_item_id": item_id,
        "plan_id": plan_id,
        "patient_id": patient_id,
        "budget_code": budget_code,
        "raw_name": item.get("raw_name"),
        "category": item.get("category") or None,
        "sessions_expected": _coerce_int_or_none(item.get("sessions_expected")),
        "frequency_text": item.get("frequency_text") or None,
        "frequency_type": item.get("frequency_type") or None,
        "source": "PDF",
        "needs_manual_review": bool(item.get("needs_manual_review", False)),
    }


def _write_goal_and_execution(
    *,
    patient_id: str,
    plan_id: str,
    plan: dict[str, Any],
    items: list[dict[str, Any]],
    budget_code: str,
    clear_existing_executions: bool,
    logger: PdfImportLogger | None,
) -> int:
    """Project the plan into ``patient_goals`` + ``execution_summary``.

    This is the read-model contract the ficha page was built against.
    The wizard has been writing only to ``patients`` /
    ``treatment_plans`` / ``treatment_plan_items`` since 2025, which
    leaves the ficha's "Plano de tratamento" table and goal info row
    empty even when the import succeeded — the bug surfaced in
    June 2026 when a Clinica operator noticed the imported patient
    had no plan items in the ficha.

    Parameters
    ----------
    patient_id, plan_id:
        The (existing or freshly-minted) ids to project the goal /
        execution rows under. The caller is responsible for having
        already inserted the plan row in ``treatment_plans`` and
        the items in ``treatment_plan_items``.
    plan, items:
        The plan/item dicts from the validated candidate. Used to
        build the goal row's ``goal_type`` / ``goal_notes`` and
        the execution row's ``procedure_raw`` /
        ``procedure_category`` / ``sessions_expected`` etc.
    budget_code:
        The plan's budget code; carried into the execution rows
        so they match the plan row.
    clear_existing_executions:
        When True (the replace path), delete the old
        ``execution_summary`` rows for this plan first so we don't
        leave orphans pointing at the previous item list. The
        data-layer ``replace_plan`` already clears
        ``treatment_plan_items`` and ``patient_goals`` but not
        the satellite execution view, so the wizard does it here.
    logger:
        Optional event sink. Records one ``goal`` and one
        ``execution`` stage event with the row counts.

    Returns
    -------
    int
        The number of ``execution_summary`` rows written (used by
        the caller for the final ``commit`` log event).
    """
    if clear_existing_executions:
        # Plan-id is the natural key here: every execution row
        # written by a previous import of this plan points at the
        # same ``plan_id``. Wiping by ``plan_id`` also handles the
        # rare case where the new plan has fewer items than the
        # old one.
        delete_rows("execution_summary", "plan_id", plan_id)

    # patient_goals — one row per plan
    goal_id = next_id("patient_goals")
    append_row(
        "patient_goals",
        _build_goal_row(goal_id, patient_id, plan_id, plan),
    )
    if logger is not None:
        logger.stage(
            "goal",
            op="insert",
            plan_id=plan_id,
            goal_id=goal_id,
        )

    # execution_summary — one row per plan item
    for item in items:
        # ``next_id("execution_summary")`` walks the table's primary
        # key column and returns the next free ``exec_new_NNN``. We
        # use it (rather than ``next_id_with_prefix("exec_new")``)
        # because the prefix-aware helper is hardcoded to scan
        # ``treatment_plans.budget_code`` for collisions, which is
        # the wrong column for execution rows. ``execution_summary``
        # is in ``NEW_ID_PREFIX`` so the table-aware path Just Works.
        execution_id = next_id("execution_summary")
        append_row(
            "execution_summary",
            _build_execution_row(
                execution_id,
                patient_id,
                plan_id,
                budget_code,
                item,
                plan,
            ),
        )
    if logger is not None and items:
        logger.stage(
            "execution",
            op="insert",
            plan_id=plan_id,
            item_count=len(items),
        )

    return len(items)


def persist_rows(
    candidate: dict[str, Any],
    dedup_action: dict[str, bool] | None = None,
    *,
    logger: PdfImportLogger | None = None,
) -> dict[str, Any]:
    """Persist a validated candidate to the data layer.

    Parameters
    ----------
    candidate:
        The validated candidate dict. Must have ``status != "Erro"``;
        the wizard never calls this on error candidates, but the dev
        CLI does, to surface the failure loud and clear.
    dedup_action:
        Optional flags describing how to handle duplicates that
        :func:`src.pdf_importer.validate.validate_rows` flagged:

        - ``replace_patient`` (bool) — when True, update the patient
          row in place using ``candidate["dup_patient_id"]`` as the
          target. When False (or the key is missing), insert a new
          patient.
        - ``replace_plan`` (bool) — when True, replace the plan row
          in place (delete items + goal, patch the plan row,
          re-insert items) using ``candidate["dup_plan_id"]`` as the
          target. When False, insert a new plan.

        When neither flag is True the function takes the default
        path (insert everything).

    logger:
        Optional :class:`PdfImportLogger` from the same batch as
        the one passed to ``parse_pdf_to_rows`` /
        ``validate_rows``. Records one event per
        insert/replace/commit so the wizard's log shows the full
        lifecycle. The function does **not** call ``finish()`` —
        that is the wizard's responsibility, since the wizard
        knows when the whole batch (one or more PDFs) is done.

    Returns
    -------
    dict
        ``{"patient_id", "plan_id", "item_ids"}`` for the caller's
        navigation. ``patient_id`` is the existing id on replace and
        a fresh ``pat_new_NNN`` on insert; ``plan_id`` mirrors the
        same rule.

    Raises
    ------
    ValueError
        On a candidate with status ``"Erro"``.
    """
    if candidate.get("status") == "Erro":
        raise ValueError(
            f"Candidato com erros: {candidate.get('warnings', [])}"
        )

    dedup_action = dedup_action or {}
    replace_patient_flag = bool(dedup_action.get("replace_patient", False))
    replace_plan_flag = bool(dedup_action.get("replace_plan", False))

    patient = candidate.get("patient", {}) or {}
    plan = candidate.get("plan", {}) or {}
    items = candidate.get("items", []) or []

    item_ids: list[str] = []

    if logger is not None:
        logger.stage(
            "persist",
            replace_patient=replace_patient_flag,
            replace_plan=replace_plan_flag,
            items=len(items),
        )

    # ---------------------------------------------------------------
    # Patient
    # ---------------------------------------------------------------
    if replace_patient_flag and candidate.get("dup_patient_id"):
        patient_id = str(candidate["dup_patient_id"])
        # Update in place — the helper preserves ``created_at`` and
        # only patches the mutable fields. The full row is passed
        # in so the helper can also see the missing-CPF case (the
        # wizard may have just collected it from the user).
        _dedup_replace_patient(patient_id, _build_patient_row(patient_id, patient))
        if logger is not None:
            logger.stage(
                "patient",
                op="replace",
                patient_id=patient_id,
            )
    elif replace_plan_flag and candidate.get("dup_patient_id"):
        # Plan-only replacement: the existing plan belongs to the
        # existing patient, so we keep the existing ``patient_id``
        # and skip the patient-row append. The new items are
        # linked to the existing patient; the new plan_id is
        # minted below.
        patient_id = str(candidate["dup_patient_id"])
        if logger is not None:
            logger.stage(
                "patient",
                op="reuse",
                patient_id=patient_id,
            )
    else:
        patient_id = next_id("patients")
        append_row("patients", _build_patient_row(patient_id, patient))
        if logger is not None:
            logger.stage(
                "patient",
                op="insert",
                patient_id=patient_id,
            )

    # ---------------------------------------------------------------
    # Plan
    # ---------------------------------------------------------------
    if replace_plan_flag and candidate.get("dup_plan_id"):
        # The data layer's ``replace_plan`` reuses the existing
        # ``plan_id`` and clears the old items + goal before
        # re-inserting the new ones under the same id. The helper
        # also mints a fresh ``plan_item_id`` for each item at
        # append time, so we just pass the items with the bare
        # fields and the right budget_code.
        existing_plan_id = str(candidate["dup_plan_id"])
        # The existing plan belongs to the existing patient — the
        # ``replace_plan`` lookup is keyed on
        # ``(patient_id, issue_date)`` and the existing plan's
        # ``patient_id`` is the one from the previous import, not
        # the one we just (re)created. Always use the existing
        # patient_id when a patient collision is on file: even if
        # ``replace_patient`` is False (e.g. the user accepted a
        # plan-only replacement), the plan we're replacing still
        # lives under the existing patient. Falling back to the
        # freshly-minted ``patient_id`` would make the lookup miss
        # the existing plan and the ``replace_plan`` would be a
        # no-op.
        plan_owner_pid = (
            str(candidate["dup_patient_id"])
            if candidate.get("dup_patient_id")
            else patient_id
        )
        plan_row = _build_plan_row(existing_plan_id, plan_owner_pid, plan)
        new_items = []
        for item in items:
            new_items.append(
                {
                    "plan_id": existing_plan_id,
                    "patient_id": plan_owner_pid,
                    "budget_code": plan_row["budget_code"],
                    "raw_name": item.get("raw_name"),
                    "category": item.get("category") or None,
                    "sessions_expected": _coerce_int_or_none(item.get("sessions_expected")),
                    "frequency_text": item.get("frequency_text") or None,
                    "frequency_type": item.get("frequency_type") or None,
                    "source": "PDF",
                    "needs_manual_review": bool(item.get("needs_manual_review", False)),
                }
            )
        result_plan_id = _data_layer_replace_plan(
            plan_owner_pid,
            plan.get("issue_date"),
            plan_row,
            new_items,
        )
        plan_id = result_plan_id or existing_plan_id
        # The data-layer helper minted the fresh ``plan_item_id``s
        # during ``append_row``; we don't re-read the CSV here to
        # gather them — the wizard only needs ``patient_id`` and
        # ``plan_id`` for navigation, and the CSV already carries
        # the truth. ``item_ids`` stays empty in the replace path.
        item_ids = []
        if logger is not None:
            logger.stage(
                "plan",
                op="replace",
                plan_id=plan_id,
                item_count=len(new_items),
            )
        # Project the plan into ``patient_goals`` + ``execution_summary``
        # so the ficha can show the imported plan. The data layer's
        # ``replace_plan`` cleared the old ``patient_goals`` row but
        # not the satellite execution view, so we ask the helper to
        # clear it first.
        _write_goal_and_execution(
            patient_id=plan_owner_pid,
            plan_id=plan_id,
            plan=plan,
            items=items,
            budget_code=plan_row["budget_code"],
            clear_existing_executions=True,
            logger=logger,
        )
    else:
        plan_id = next_id("treatment_plans")
        plan_row = _build_plan_row(plan_id, patient_id, plan)
        append_row("treatment_plans", plan_row)
        if logger is not None:
            logger.stage(
                "plan",
                op="insert",
                plan_id=plan_id,
                budget_code=plan_row["budget_code"],
            )
        for item in items:
            item_id = next_id("treatment_plan_items")
            item_ids.append(item_id)
            append_row(
                "treatment_plan_items",
                _build_item_row(item_id, plan_id, patient_id, plan_row["budget_code"], item),
            )
        if logger is not None:
            logger.stage(
                "items",
                op="insert",
                count=len(item_ids),
            )
        # Project the plan into ``patient_goals`` + ``execution_summary``
        # so the ficha can show the imported plan. Nothing to clear —
        # the plan is new so there are no orphan rows.
        _write_goal_and_execution(
            patient_id=patient_id,
            plan_id=plan_id,
            plan=plan,
            items=items,
            budget_code=plan_row["budget_code"],
            clear_existing_executions=False,
            logger=logger,
        )

    # If we extracted a positive age from the PDF, patch it on the
    # patient row. The replace path already went through
    # ``dedup.replace_patient`` which honors the same "age > 0"
    # guard; the insert path needs the explicit patch.
    age_int = _coerce_int_or_none(patient.get("age"))
    if not replace_patient_flag and age_int is not None and age_int > 0:
        from src.data_layer import update_row

        update_row("patients", "patient_id", patient_id, {"age": age_int})
        if logger is not None:
            logger.stage(
                "age_patch",
                patient_id=patient_id,
                age=age_int,
            )

    # Invalidate the Streamlit cache so the next render re-reads
    # the CSVs. Pages that care about freshness (e.g.
    # ``pacientes``) check the ``_data_dirty`` flag and re-read
    # on the same render — no ``st.rerun()`` needed (which would
    # interact poorly with the form's ``clear_on_submit=True``).
    st.cache_data.clear()
    st.session_state["_data_dirty"] = True

    if logger is not None:
        logger.stage(
            "commit",
            patient_id=patient_id,
            plan_id=plan_id,
            item_count=len(item_ids),
        )

    return {"patient_id": patient_id, "plan_id": plan_id, "item_ids": item_ids}
