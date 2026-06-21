"""Parse a PDF into row dicts by applying regex/normalizers to zone text.

The parser takes the per-zone text from :mod:`src.pdf_importer.extract`
and applies the ``field_mappings`` declared in the zone config
(``data/import_zones/<id>.json``). The output is a candidate dict with
the three top-level entities (``patient``, ``plan``, ``items``) that the
data layer can persist.

Two zone ``mode``s are supported:

- ``"single"`` (default) — the field_mappings apply to the whole zone
  text once (used for ``cabecalho``, ``dados_paciente``, ``rodape``).
- ``"list"`` — the zone text is split by newlines and each non-empty
  line is parsed with the field_mappings to produce one item row (used
  for ``procedimentos``).

All public functions accept an optional ``logger: PdfImportLogger``
keyword-only argument so the wizard can thread a single log through
``parse_pdf_to_rows`` → ``validate_rows`` → ``persist_rows`` and see
each step in one ordered trace. When ``logger`` is None (the default)
the functions behave exactly as before — no side effects, no overhead.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Union

from src.pdf_importer.extract import PdfSource, extract_text_from_zone
from src.pdf_importer.log import PdfImportLogger

# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------
#
# A normalizer is a pure function: str -> value (or None on failure).
# A normalizer that raises is caught by the parser and the field is
# left as None (so the row is marked needs_manual_review=True).


_MONTHS_PT: dict[str, int] = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _norm_date_pt_br_ext(value: str) -> str | None:
    """Parse ``"D de Mês de AAAA"`` (PT-BR month name) to ``"YYYY-MM-DD"``."""
    value = (value or "").strip().lower()
    if not value:
        return None
    m = re.match(r"(\d{1,2})\s+de\s+([a-zçãéíóú]+)\s+de\s+(\d{4})", value)
    if not m:
        return None
    month = _MONTHS_PT.get(m.group(2))
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    except ValueError:
        return None


def _norm_str(value: str) -> str | None:
    value = (value or "").strip()
    return value or None


def _norm_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _norm_date_pt_br(value: str) -> str | None:
    """Parse ``dd/mm/yyyy`` (PT-BR) into an ISO date string ``YYYY-MM-DD``."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _norm_name(value: str) -> str | None:
    """Normalize a person's name: strip, drop a leading label that may
    have been captured with the name (e.g. ``"Paciente: Maria"``)."""
    value = (value or "").strip()
    if not value:
        return None
    value = re.sub(
        r"^(paciente|cliente|senhor\(a\)|sr\.?|sra\.?)\s*[:\-]?\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip() or None


def _norm_phone(value: str) -> str | None:
    """Normalize a Brazilian phone: collapse internal whitespace; trim."""
    value = (value or "").strip()
    if not value:
        return None
    return " ".join(value.split()) or None


_FREQUENCY_TYPE_TOKENS: dict[str, str] = {
    "semanal": "Semanal",
    "por semana": "Semanal",
    "quinzenal": "Quinzenal",
    "diario": "Diário",
    "diário": "Diário",
    "por dia": "Diário",
    "mensal": "Mensal",
    "por mês": "Mensal",
    "por mes": "Mensal",
    "dose única": "Dose única",
    "dose unica": "Dose única",
}


def _norm_frequency_type(value: str) -> str | None:
    """Map a free-text frequency token to the canonical label.

    The PDF text may say ``"2x/semana"`` or ``"semanal"``; the data
    layer expects one of ``Semanal | Quinzenal | Diário | Mensal``.
    """
    value = (value or "").strip().lower()
    if not value:
        return None
    # Try the explicit token table first
    for token, label in _FREQUENCY_TYPE_TOKENS.items():
        if token in value:
            return label
    # Fall back to a regex over the canonical forms
    match = re.search(r"semanal|quinzenal|di[áa]rio|mensal", value)
    if match:
        token = match.group(0)
        return _FREQUENCY_TYPE_TOKENS.get(token, token.capitalize())
    return None


NORMALIZERS: dict[str, Callable[[str], Any]] = {
    "str": _norm_str,
    "int": _norm_int,
    "date_pt_br": _norm_date_pt_br,
    "date_pt_br_ext": _norm_date_pt_br_ext,
    "name": _norm_name,
    "phone": _norm_phone,
    "frequency_type": _norm_frequency_type,
}

# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------
#
# A small lookup table to infer the category of a procedure by its
# raw_name. Items that don't match fall back to category=None and are
# flagged needs_manual_review=True.
CATEGORY_LOOKUP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"drenagem", re.IGNORECASE), "Drenagem"),
    (re.compile(r"massagem", re.IGNORECASE), "Massagem"),
    (re.compile(r"limpeza|profilaxia", re.IGNORECASE), "Limpeza"),
    (re.compile(r"avalia[çc][ãa]o", re.IGNORECASE), "Avaliação"),
    (re.compile(r"injet[áa]vel|\bev\b|\bim\b|intramuscular", re.IGNORECASE), "Injetáveis"),
    (
        re.compile(r"acompanhamento\s+profissional|acompanhamento\s+nutricional|nutri[çc][ãa]o", re.IGNORECASE),
        "Acompanhamento profissional",
    ),
    (
        re.compile(
            r"manipulado|medicamento|implante|testosterona|nadh|enzima|tirzerp|mounj|ghkcu|bcp\s*157",
            re.IGNORECASE,
        ),
        "Medicamento manipulado",
    ),
    (re.compile(r"ultrassom|ultra-som|cavita[çc][ãa]o|regenera|deep\s*regenera", re.IGNORECASE), "Estética"),
    (re.compile(r"radiofrequ[êe]ncia", re.IGNORECASE), "Estética"),
]


def _infer_category(raw_name: str | None) -> str | None:
    if not raw_name:
        return None
    for pattern, category in CATEGORY_LOOKUP:
        if pattern.search(raw_name):
            return category
    return None


# ---------------------------------------------------------------------------
# Field-mapping application
# ---------------------------------------------------------------------------


def _apply_mapping(
    text: str, mapping: dict[str, Any]
) -> tuple[Any, str]:
    """Apply a single field_mapping to ``text``.

    Returns ``(value, status)`` where ``status`` is one of:

    * ``"MATCHED"`` — regex matched and normalizer returned a non-None value
    * ``"MISSING_REQUIRED"`` — pattern didn't match (or normalizer
      returned None) and the field is required
    * ``"MISSING_OPTIONAL"`` — same, but the field is optional
    * ``"NORMALIZER_FAILED"`` — regex matched but the normalizer
      raised. The field is treated as missing (value=None) so the
      existing downstream behaviour is preserved, but the log
      records the difference between "no text" and "text was
      there but couldn't be normalized" — which is exactly the
      signal you need when a regex change accidentally widens the
      captured group.
    """
    pattern = mapping.get("pattern", "")
    normalizer_name = mapping.get("normalizer", "str")
    required = bool(mapping.get("required", False))
    # DOTALL makes ``.`` match newlines, so a pattern like ``(.+)`` on
    # the rodape zone captures the full footer text (not just the
    # first line).
    match = re.search(
        pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    if not match:
        return None, "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
    raw = match.group(1) if match.groups() else match.group(0)
    normalizer = NORMALIZERS.get(normalizer_name)
    if normalizer is None:
        stripped = raw.strip() or None
        if stripped is None:
            return None, "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
        return stripped, "MATCHED"
    try:
        value = normalizer(raw)
    except Exception:
        return None, "NORMALIZER_FAILED"
    if value is None:
        return None, "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
    return value, "MATCHED"


def _parse_single_zone(
    text: str,
    zone: dict[str, Any],
    *,
    zone_id: str | None = None,
    logger: PdfImportLogger | None = None,
) -> tuple[dict[tuple[str, str], Any], list[str]]:
    """Apply a ``"single"`` zone's field_mappings to ``text`` once.

    When ``logger`` is provided, emits one ``field`` event per
    mapping with status (MATCHED / MISSING_* / NORMALIZER_FAILED)
    so the wizard's log can pinpoint which field failed.
    """
    result: dict[tuple[str, str], Any] = {}
    warnings: list[str] = []
    zone_id = zone_id or zone.get("id", "?")
    for mapping in zone.get("field_mappings", []):
        value, status = _apply_mapping(text, mapping)
        column = mapping.get("target_column", "")
        table = mapping.get("target_table", "")
        result[(table, column)] = value
        if logger is not None:
            logger.field(
                zone=zone_id,
                field_name=column,
                status=status,
                value=value if status == "MATCHED" else None,
                pattern=mapping.get("pattern"),
            )
        if status in {"MISSING_REQUIRED", "NORMALIZER_FAILED"}:
            warnings.append(f"{zone_id}.{column} (obrigatório não encontrado)")
    return result, warnings


def _parse_list_zone(
    text: str,
    zone: dict[str, Any],
    *,
    zone_id: str | None = None,
    logger: PdfImportLogger | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply a ``"list"`` zone's field_mappings to each non-empty line.

    Each line becomes a row. Items that don't match a category are
    flagged ``needs_manual_review=True`` so the user can fix them in
    the preview. ``logger`` is forwarded so the per-line trace is
    visible (it gets noisy for 30-item plans — the wizard can flip
    PDF_IMPORT_DEBUG=1 to filter it out).
    """
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    current: dict[str, Any] | None = None
    zone_id = zone_id or zone.get("id", "?")

    _APLICACAO_PREFIXES = ("aplicação:", "aplicacao:")
    _SKIP_PREFIXES = (
        "foco do tratamento:",
        "preparação:",
        "preparacao:",
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()

        if lower.startswith(_APLICACAO_PREFIXES):
            if current is None:
                warnings.append(
                    f"{zone_id}: '{line[:30]}...' sem item anterior"
                )
                continue
            for mapping in zone.get("field_mappings", []):
                column = mapping.get("target_column", "")
                if column == "raw_name":
                    continue
                value, status = _apply_mapping(line, mapping)
                if logger is not None:
                    logger.field(
                        zone=zone_id,
                        field_name=column,
                        status=status,
                        value=value if status == "MATCHED" else None,
                        pattern=mapping.get("pattern"),
                    )
                if value is not None:
                    current[column] = value
            continue

        if lower.startswith(_SKIP_PREFIXES):
            continue

        row: dict[str, Any] = {}
        item_warnings: list[str] = []
        for mapping in zone.get("field_mappings", []):
            value, status = _apply_mapping(line, mapping)
            column = mapping.get("target_column", "")
            row[column] = value
            if logger is not None:
                logger.field(
                    zone=zone_id,
                    field_name=column,
                    status=status,
                    value=value if status == "MATCHED" else None,
                    pattern=mapping.get("pattern"),
                )
            if status in {"MISSING_REQUIRED", "NORMALIZER_FAILED"}:
                item_warnings.append(f"{column} (obrigatório não encontrado)")
        if row.get("category") is None:
            row["category"] = _infer_category(row.get("raw_name"))
        row["needs_manual_review"] = bool(item_warnings) or row.get("category") is None
        if item_warnings or row.get("category") is None:
            warnings.append(
                f"{zone_id}: linha '{line[:30]}...' requer revisão"
            )
        rows.append(row)
        current = row

    return rows, warnings


def _assemble_candidate(
    zone_results: dict[str, dict[tuple[str, str], Any]],
    *,
    logger: PdfImportLogger | None = None,
) -> dict[str, Any]:
    """Group the per-zone results into the three top-level entities.

    When ``logger`` is set, emits a single ``assemble`` event
    listing which keys landed in ``patient`` and ``plan`` — useful
    for spotting silent drops (e.g. a field that the JSON declared
    as target_table=treatment_plans but landed nowhere because the
    parser used the wrong key).
    """
    patient: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    for _zone_id, kv in zone_results.items():
        for (table, column), value in kv.items():
            if table == "patients":
                patient[column] = value
            elif table == "treatment_plans":
                plan[column] = value

    # Defaults for fields that don't come from the PDF. The data layer
    # expects ``normalized_name`` and ``created_at`` to be populated; we
    # derive them from ``name`` and "today" if the parser didn't extract
    # them.
    name = patient.get("name")
    patient.setdefault("normalized_name", (name or "").lower().strip() or None)
    patient.setdefault("created_at", date.today().isoformat())

    plan.setdefault("issue_date", date.today().isoformat())
    plan.setdefault("start_date", plan.get("issue_date") or date.today().isoformat())
    plan.setdefault("status", "Ativo")
    plan.setdefault("is_renewal", False)

    if logger is not None:
        logger.stage(
            "assemble",
            patient_keys=sorted(patient.keys()),
            plan_keys=sorted(plan.keys()),
        )

    return {"patient": patient, "plan": plan}


def _source_filename(source: PdfSource) -> str:
    """Best-effort filename for a PDF source (for log headers)."""
    if isinstance(source, (str, Path)):
        return Path(source).name
    return "<bytes>"


def parse_pdf_to_rows(
    source: PdfSource,
    zones_config: list[dict[str, Any]],
    page: int = 1,
    *,
    logger: PdfImportLogger | None = None,
) -> dict[str, Any]:
    """Parse ``source`` into a candidate dict using ``zones_config``.

    The returned shape is::

        {
            "patient": {name, normalized_name, medical_record, phone,
                        age, created_at},
            "plan":    {budget_code, issue_date, start_date, end_date,
                        status, main_goal, is_renewal, notes},
            "items":   [{raw_name, category, sessions_expected,
                         frequency_text, frequency_type,
                         needs_manual_review}, ...],
            "warnings": [str, ...]
        }

    The caller (the wizard's preview or the dev CLI) is responsible
    for calling :func:`src.pdf_importer.validate.validate_rows`
    before persisting.

    When ``logger`` is provided, the function emits:

    * ``start`` — with filename, total_zones, has_field_mappings (the
      common "0 mappings" mistake lights up here)
    * one ``zone`` event per configured zone with bbox, text length
      and whether the zone actually has field_mappings
    * one ``field`` event per mapping with status
      (MATCHED/MISSING_*/NORMALIZER_FAILED)
    * one ``assemble`` event listing the resulting keys
    * one ``parse_done`` event with the totals (cpf value, items,
      warnings) so the wizard can show a one-line summary
    """
    warnings: list[str] = []
    zone_results: dict[str, dict[tuple[str, str], Any]] = {}
    items: list[dict[str, Any]] = []

    if logger is not None:
        first_zone = zones_config[0] if zones_config else {}
        logger.start(
            _source_filename(source),
            total_zones=len(zones_config),
            has_field_mappings=bool(first_zone.get("field_mappings")),
            page=page,
        )
        logger.stage("parse", total_zones=len(zones_config))

    for zone in zones_config:
        zone_id = zone["id"]
        bbox = zone["bbox"]
        text = extract_text_from_zone(source, page, bbox)
        mode = zone.get("mode", "single")
        if logger is not None:
            logger.stage(
                "zone",
                id=zone_id,
                mode=mode,
                bbox=list(bbox),
                text_len=len(text),
                has_mappings=bool(zone.get("field_mappings")),
            )
        if mode == "list":
            list_rows, list_warnings = _parse_list_zone(
                text, zone, zone_id=zone_id, logger=logger,
            )
            items.extend(list_rows)
            warnings.extend(list_warnings)
        else:
            single_result, single_warnings = _parse_single_zone(
                text, zone, zone_id=zone_id, logger=logger,
            )
            zone_results[zone_id] = single_result
            warnings.extend(single_warnings)

    candidate = _assemble_candidate(zone_results, logger=logger)
    candidate["items"] = items
    candidate["warnings"] = warnings

    if logger is not None:
        logger.stage(
            "parse_done",
            warnings=len(warnings),
            cpf=candidate["patient"].get("cpf"),
            items=len(items),
            patient_keys=sorted(candidate["patient"].keys()),
        )

    return candidate
