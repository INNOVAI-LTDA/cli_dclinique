"""Expected mock table schemas for the MAP shell."""
from __future__ import annotations

import pandas as pd

EXPECTED_SCHEMAS: dict[str, list[str]] = {
    "patients": [
        "patient_id",
        "name",
        "normalized_name",
        "medical_record",
        "phone",
        "age",
        # Campos extraídos do PDF (CPF/RG são natural-key para dedup;
        # ambos nullable porque o PDF pode não trazê-los).
        "cpf",
        "rg",
        "address",
        "created_at",
    ],
    "treatment_plans": [
        "plan_id",
        "patient_id",
        "budget_code",
        "issue_date",
        "start_date",
        "end_date",
        "status",
        "main_goal",
        "is_renewal",
        "notes",
    ],
    "treatment_plan_items": [
        "plan_item_id",
        "plan_id",
        "patient_id",
        "budget_code",
        "raw_name",
        "category",
        "sessions_expected",
        "frequency_text",
        "frequency_type",
        "source",
        "needs_manual_review",
    ],
    "execution_summary": [
        "execution_id",
        "patient_id",
        "plan_id",
        "budget_code",
        "procedure_raw",
        "procedure_category",
        "status",
        "sessions_expected",
        "sessions_completed",
        "sessions_remaining",
        "plan_created_at",
        # ``frequency_type`` was added in June 2026 so the ficha's
        # "Plano de tratamento" table can build the "Frequência de
        # Aplicação" column directly from the satellite view — the
        # projection comes from ``treatment_plan_items.frequency_type``
        # at the wizard's persist step. Stays NULL for plans that
        # were imported before this column existed; the ficha
        # renders "-" for NULL.
        "frequency_type",
    ],
    "appointments": [
        "appointment_id",
        "appointment_code",
        "patient_id",
        "budget_codes",
        "appointment_start",
        "appointment_end",
        "appointment_raw",
        "professional",
        "scheduled_by",
        "status",
    ],
    "appointment_items": [
        "appointment_item_id",
        "appointment_id",
        "patient_id",
        "budget_code",
        "raw_item",
        "category",
        "status",
        "appointment_start",
        "professional",
    ],
    "patient_goals": [
        "goal_id",
        "patient_id",
        "plan_id",
        "goal_type",
        "initial_weight",
        "target_weight",
        "target_date",
        "goal_notes",
    ],
    "weight_entries": ["weight_id", "patient_id", "plan_id", "measurement_date", "weight", "source", "notes"],
    "satisfaction_entries": [
        "satisfaction_id",
        "patient_id",
        "plan_id",
        "date",
        "satisfaction_status",
        "score",
        "notes",
    ],
    "alerts": [
        "alert_id",
        "patient_id",
        "plan_id",
        "category",
        "alert_type",
        "description",
        "priority",
        "status",
        "created_at",
        "comment",
    ],
    "data_quality_issues": ["issue_id", "source", "severity", "issue_type", "description", "patient_id", "field_name"],
    # --- MVP Jornada Clínica (Fase 1 — ver docs/mvp_plano.md) ---
    # service_catalog: whitelist de serviços canônicos. PK = service_code
    # (TEXT, fornecido pelo import — não há next_id porque o código é
    # externo, decidido pela equipe clínica / lista da Dane).
    # classification ∈ {active, rare, obsolete}. category ∈
    # {injectable, professional, other} ou NULL. default_periodicity_days
    # nullable (alguns serviços são pontuais).
    "service_catalog": [
        "service_code",
        "name",
        "classification",
        "category",
        "default_periodicity_days",
        "source",
        "created_at",
    ],
    # service_review_queue: serviços encontrados em Excel/PDF que não
    # constam em service_catalog. PK = id (TEXT, gerado por next_id com
    # prefixo "srv_new"). occurrences = quantas vezes o serviço apareceu
    # (incremental). status ∈ {pending, classified, ignored}.
    "service_review_queue": [
        "id",
        "service_name",
        "source",
        "occurrences",
        "first_seen_at",
        "last_seen_at",
        "status",
    ],
}


def validate_mock_schema(data: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """Return missing required columns by table."""
    missing: dict[str, list[str]] = {}
    for table, columns in EXPECTED_SCHEMAS.items():
        if table not in data:
            missing[table] = columns
            continue
        absent = [column for column in columns if column not in data[table].columns]
        if absent:
            missing[table] = absent
    return missing
