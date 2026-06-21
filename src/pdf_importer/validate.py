"""Validation for parsed PDF candidates.

Runs the checks the wizard needs to decide whether a candidate is
ready to persist, what to do with duplicates, and what to surface
in the preview:

- required patient / plan fields are present (CPF is **not**
  required at this step — the wizard offers an inline input when
  the PDF omits it, so the candidate can be "Revisar" instead of
  "Erro" and the user has a chance to fix it).
- the patient's **CPF** does not collide with an existing patient
  in ``patients.csv`` — if it does, the candidate is flagged for
  replacement and the wizard shows the batched confirmation.
- the plan's **issue_date** does not collide with an existing
  plan for the same patient (after the patient-level dedup has
  resolved which ``patient_id`` to use) — if it does, the
  candidate is flagged for plan replacement.
- items with missing required fields are flagged for manual review.

The check reads the CSV directly (not the cached ``load_all``) so
it reflects on-disk state at the moment of validation — even if a
previous render left a stale entry in the Streamlit cache.

The result is written back onto the candidate in two new fields
the wizard relies on:

- ``candidate["dup_patient_id"]`` — set to the existing
  ``patient_id`` when a CPF match is found, else ``None``.
- ``candidate["dup_plan_id"]`` — set to the existing
  ``plan_id`` when a ``(patient_id, issue_date)`` match is found,
  else ``None``.

These keys are stable across renders, so the wizard can use them
to drive the inline confirmation UI.
"""
from __future__ import annotations

from typing import Any

from src.pdf_importer.dedup import find_patient_by_cpf, find_plan_by_issue_date
from src.pdf_importer.log import PdfImportLogger

REQUIRED_PATIENT_FIELDS: tuple[str, ...] = ("name", "medical_record")
# ``budget_code`` is no longer required at the validation step — it
# is minted by :mod:`src.pdf_importer.persist` from
# ``next_id("treatment_plans")`` because the source PDFs do not
# carry a budget number.
REQUIRED_PLAN_FIELDS: tuple[str, ...] = ()


def _format_issue_date(issue_date: str | None) -> str:
    """Format an ISO ``YYYY-MM-DD`` as ``DD/MM/YYYY`` for user-facing warnings.

    The CSV stores ``issue_date`` as ISO; the wizard's preview already
    shows it in the same format, but the validation warnings are
    surfaced via ``st.warning`` and read better in PT-BR format.
    """
    if not issue_date or not isinstance(issue_date, str):
        return str(issue_date or "")
    parts = issue_date.split("-")
    if len(parts) != 3:
        return issue_date
    return f"{parts[2]}/{parts[1]}/{parts[0]}"


def validate_rows(
    candidate: dict[str, Any],
    *,
    logger: PdfImportLogger | None = None,
) -> dict[str, Any]:
    """Validate a candidate and return it with ``status`` and ``warnings`` filled.

    The returned ``status`` is one of:

    - ``"OK"`` — all required fields present, no duplicates.
    - ``"Revisar"`` — duplicates or missing optional fields (the
      candidate can still be persisted; the wizard offers the
      confirmation dialog with the warnings surfaced).
    - ``"Erro"`` — a required field is missing (the wizard will
      skip the row on import).

    Mutates the candidate in place and also returns it for chaining.

    When ``logger`` is provided, emits a ``validate`` event on
    entry, a ``warn`` event per dedup / missing-CPF signal (so
    the user can correlate the log with the warnings list), and a
    ``validate_done`` event with the final status.
    """
    warnings: list[str] = list(candidate.get("warnings", []))
    patient = candidate.get("patient", {}) or {}
    plan = candidate.get("plan", {}) or {}
    items = candidate.get("items", []) or []
    cpf = patient.get("cpf")

    if logger is not None:
        logger.stage(
            "validate",
            cpf_present=bool(cpf) and not (isinstance(cpf, str) and not cpf.strip()),
            items=len(items),
        )

    # Default the dedup slots — the wizard reads them to decide
    # whether to show the "substituir" prompt for this candidate.
    candidate.setdefault("dup_patient_id", None)
    candidate.setdefault("dup_plan_id", None)

    # Required patient fields
    for field in REQUIRED_PATIENT_FIELDS:
        if not patient.get(field):
            warnings.append(f"patient.{field} (obrigatório vazio)")
            if logger is not None:
                logger.warn(
                    f"required patient field missing: {field}",
                    field=field,
                )

    # CPF handling — natural key for the patient. We never reject the
    # candidate here: an empty CPF is recoverable (the wizard offers
    # an inline input) and a duplicate CPF is recoverable (the
    # wizard offers replacement). Both show up as "Revisar".
    if not cpf or (isinstance(cpf, str) and not cpf.strip()):
        warnings.append("CPF ausente — informe manualmente antes de importar.")
        if logger is not None:
            logger.warn("CPF ausente — informe manualmente antes de importar.")
    else:
        existing = find_patient_by_cpf(cpf)
        if existing is not None:
            existing_pid = str(existing.get("patient_id", ""))
            existing_name = str(existing.get("name", ""))
            candidate["dup_patient_id"] = existing_pid
            msg = (
                f"Paciente '{existing_name}' já cadastrado com este CPF — "
                "o cadastro será substituído se você confirmar."
            )
            warnings.append(msg)
            if logger is not None:
                logger.warn(
                    msg,
                    dup_patient_id=existing_pid,
                    cpf=cpf,
                )
            # Plan dedup only makes sense against the existing patient
            # — a brand-new patient_id can never collide.
            issue_date = plan.get("issue_date")
            if issue_date:
                dup_plan = find_plan_by_issue_date(existing_pid, issue_date)
                if dup_plan is not None:
                    candidate["dup_plan_id"] = str(dup_plan.get("plan_id", ""))
                    plan_msg = (
                        f"Plano emitido em {_format_issue_date(issue_date)} "
                        "já registrado para este paciente — o plano será "
                        "substituído se você confirmar."
                    )
                    warnings.append(plan_msg)
                    if logger is not None:
                        logger.warn(
                            plan_msg,
                            dup_plan_id=candidate["dup_plan_id"],
                            issue_date=issue_date,
                        )

    # Required plan fields
    for field in REQUIRED_PLAN_FIELDS:
        if not plan.get(field):
            warnings.append(f"plan.{field} (obrigatório vazio)")

    # Note: budget_code uniqueness is enforced implicitly by
    # :func:`src.data_layer.next_id`, which mints a fresh
    # ``orc_new_NNN`` on every persist call — the source PDF does
    # not carry a budget number, so we no longer check for
    # duplicates here.

    # Items: flag any with missing required fields for manual review
    for idx, item in enumerate(items):
        if not item.get("raw_name"):
            item["needs_manual_review"] = True
            warnings.append("Item sem nome de procedimento.")
            if logger is not None:
                logger.warn(
                    "Item sem nome de procedimento.",
                    item_index=idx,
                )

    # Determine overall status
    critical_missing = any(
        "(obrigatório vazio)" in w for w in warnings
    )
    if critical_missing or not items:
        status = "Erro"
    elif warnings:
        status = "Revisar"
    else:
        status = "OK"

    candidate["warnings"] = warnings
    candidate["status"] = status

    if logger is not None:
        logger.stage(
            "validate_done",
            status=status,
            warnings=len(warnings),
        )

    return candidate
