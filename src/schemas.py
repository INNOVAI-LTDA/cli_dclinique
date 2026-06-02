"""Expected mock table schemas for the MAP shell."""
from __future__ import annotations

import pandas as pd

EXPECTED_SCHEMAS: dict[str, list[str]] = {
    "patients": ["patient_id", "name", "normalized_name", "medical_record", "phone", "age", "created_at"],
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
