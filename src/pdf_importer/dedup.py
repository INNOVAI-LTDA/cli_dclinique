"""Natural-key deduplication helpers for the PDF import flow.

The MAP shell models the patient and the plan as separate entities,
each with its own surrogate primary key (``patient_id`` /
``plan_id``) and its own natural key:

* **Patient natural key = CPF** (Brazilian individual taxpayer
  registry). Two patients are the same person if their CPFs match
  after digit-only normalisation.
* **Plan natural key = (patient_id, issue_date)** — the date the
  orçamento was emitted, in the rodapé of the PDF. A new PDF for the
  same patient with the same ``issue_date`` is a re-import of the
  same plan (replace it); a different ``issue_date`` is a new plan
  (append it). This is the same key the user described as
  "hash from the issue date" — we keep the raw tuple for
  transparency and to avoid a schema change.

The helpers in this module are pure functions of the on-disk CSVs
(no Streamlit), so they can be exercised from unit tests, the dev
CLI ``scripts/pdf_lab.py``, and the wizard itself.
"""
from __future__ import annotations

import hashlib
import re

from src.data_layer import (
    find_plan_by_issue_date as _data_layer_find_plan,
    load_table,
    replace_plan as _data_layer_replace_plan,
    update_row,
)

# Anything that isn't a digit is dropped from a CPF for comparison
# purposes: dots, hyphens, spaces, even a stray slash from a copy-paste.
_NON_DIGIT_RE = re.compile(r"\D+")


def normalize_cpf(value: object) -> str:
    """Return the digit-only representation of ``value``.

    ``None``, ``pd.NA``, and any non-string-ish value come back as
    the empty string. Strings are stripped and have every non-digit
    removed — ``"626.219.801-63"`` becomes ``"62621980163"``,
    ``" 626 219 801 63 "`` becomes the same.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return _NON_DIGIT_RE.sub("", text)


def find_patient_by_cpf(cpf: object) -> dict | None:
    """Return the first patient row whose ``cpf`` matches ``cpf``.

    The comparison is done on the digit-only forms so cosmetic
    differences (``"626.219.801-63"`` vs ``"62621980163"``) do not
    produce false negatives. Returns ``None`` when the table is
    empty, the column is missing, or no row matches.
    """
    target = normalize_cpf(cpf)
    if not target:
        return None
    df = load_table("patients")
    if df.empty or "cpf" not in df.columns:
        return None
    normalized = df["cpf"].apply(normalize_cpf)
    matches = df[normalized == target]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def plan_key(issue_date: str) -> str:
    """Return a short, stable hash for ``issue_date``.

    The hash is informational only — the natural key the rest of the
    app uses is the ``(patient_id, issue_date)`` tuple. The hash is
    exposed so the wizard / reports can show a compact "plan key"
    in tooltips without leaking the full date when the user copies
    the value to a support ticket.
    """
    text = str(issue_date or "").strip()
    if not text:
        return ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def find_plan_by_issue_date(patient_id: str, issue_date: str) -> dict | None:
    """Thin re-export of :func:`src.data_layer.find_plan_by_issue_date`.

    Lives here so the import wizard can depend on a single module
    (``src.pdf_importer.dedup``) without reaching into the data
    layer's internal namespace.
    """
    return _data_layer_find_plan(patient_id, issue_date)


# Fields the patient row carries that may be safely updated by a
# replace. ``patient_id`` and ``created_at`` are intentionally NOT in
# this set — the surrogate key is the link to every clinical
# history, and ``created_at`` is a permanent audit field.
_REPLACEABLE_PATIENT_FIELDS: tuple[str, ...] = (
    "name",
    "normalized_name",
    "medical_record",
    "phone",
    "age",
    "cpf",
    "rg",
    "address",
)


def replace_patient(patient_id: str, new_patient_row: dict) -> None:
    """Update an existing patient row in place.

    The semantics are non-destructive: the ``patient_id`` is kept
    (so every plan, item, weight entry, alert, and appointment
    that was attached to the patient stays attached), and only the
    mutable fields in :data:`_REPLACEABLE_PATIENT_FIELDS` are
    patched. Empty / NaN values in the new row leave the existing
    value alone — the user might be filling in the missing CPF /
    phone that the original import skipped, but they are not
    erasing a value that was already there.
    """
    from src.schemas import EXPECTED_SCHEMAS

    columns = EXPECTED_SCHEMAS["patients"]
    updates: dict = {}
    for col in _REPLACEABLE_PATIENT_FIELDS:
        if col not in columns:
            continue
        if col not in new_patient_row:
            continue
        value = new_patient_row[col]
        # Treat empty / NaN as "no change" — the original value wins.
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        updates[col] = value
    if not updates:
        return
    update_row("patients", "patient_id", patient_id, updates)


def replace_plan(
    patient_id: str,
    issue_date: str,
    new_plan_row: dict,
    new_items: list[dict],
) -> str | None:
    """Thin wrapper around :func:`src.data_layer.replace_plan`.

    Re-exported here so the wizard can call all dedup primitives
    from one module. Returns the existing ``plan_id`` on success
    (so the caller can navigate to the ficha), ``None`` when no
    plan matches the natural key.
    """
    return _data_layer_replace_plan(patient_id, issue_date, new_plan_row, new_items)
