"""Mock data aligned with the future MAP database contract."""
from __future__ import annotations

import pandas as pd


def _d(days: int) -> pd.Timestamp:
    return pd.Timestamp.today().normalize() + pd.Timedelta(days=days)


def _dt(days: int, hour: int = 9) -> pd.Timestamp:
    return _d(days) + pd.Timedelta(hours=hour)


def _assert_referential_integrity(data: dict[str, pd.DataFrame]) -> None:
    """Fail fast if mock relational IDs are inconsistent."""
    patient_ids = set(data["patients"]["patient_id"].dropna().astype(str))
    plan_ids = set(data["treatment_plans"]["plan_id"].dropna().astype(str))

    patient_refs = [
        ("treatment_plans", "patient_id"),
        ("treatment_plan_items", "patient_id"),
        ("execution_summary", "patient_id"),
        ("appointments", "patient_id"),
        ("appointment_items", "patient_id"),
        ("patient_goals", "patient_id"),
        ("weight_entries", "patient_id"),
        ("satisfaction_entries", "patient_id"),
        ("alerts", "patient_id"),
    ]
    plan_refs = [
        ("treatment_plan_items", "plan_id"),
        ("execution_summary", "plan_id"),
        ("patient_goals", "plan_id"),
        ("weight_entries", "plan_id"),
        ("alerts", "plan_id"),
    ]

    errors: list[str] = []
    for table, column in patient_refs:
        unknown = sorted(set(data[table][column].dropna().astype(str)) - patient_ids)
        if unknown:
            errors.append(f"{table}.{column} com patient_id(s) inexistente(s): {', '.join(unknown[:3])}")

    for table, column in plan_refs:
        unknown = sorted(set(data[table][column].dropna().astype(str)) - plan_ids)
        if unknown:
            errors.append(f"{table}.{column} com plan_id(s) inexistente(s): {', '.join(unknown[:3])}")

    if errors:
        raise ValueError("Inconsistencia relacional no mock_data: " + " | ".join(errors))


def load_mock_data() -> dict[str, pd.DataFrame]:
    """Return all mock tables used by the navigable shell."""
    patients = pd.DataFrame(
        [
            ("pat_001", "Kelly Cristina Amorim", "7714697", "(62) 99999-0001", 38, -80),
            ("pat_002", "Jaqueline Aparecida Vilela", "7714698", "(62) 99999-0002", 44, -70),
            ("pat_003", "Ana Maria Souza", "7714699", "(62) 99999-0003", 32, -65),
            ("pat_004", "Ricardo Silva Lima", "7714700", "(62) 99999-0004", 51, -55),
            ("pat_005", "Carla Pereira", "7714701", "(62) 99999-0005", 29, -40),
            ("pat_006", "João Martins", "7714702", "(62) 99999-0006", 47, -30),
            ("pat_007", "Beatriz Gomes", "7714703", "(62) 99999-0007", 35, -20),
            ("pat_008", "Mariana Dias", "7714704", "(62) 99999-0008", 41, -15),
        ],
        columns=["patient_id", "name", "medical_record", "phone", "age", "created_offset"],
    )
    patients["normalized_name"] = patients["name"].str.lower()
    patients["created_at"] = patients["created_offset"].apply(_d)
    patients = patients[["patient_id", "name", "normalized_name", "medical_record", "phone", "age", "created_at"]]

    scenario = {
        "pat_001": {"status": "Ativo", "goal": "Emagrecimento", "end": 45, "expected": 12, "completed": 10, "sat": "Satisfeito", "score": 9, "weight": 77.8, "renewal": False},
        "pat_002": {"status": "Ativo", "goal": "Início de protocolo", "end": 50, "expected": 8, "completed": 0, "sat": "Neutro", "score": 7, "weight": 88.5, "renewal": False},
        "pat_003": {"status": "Ativo", "goal": "Manipulado pendente", "end": 40, "expected": 10, "completed": 5, "sat": "Insatisfeito", "score": 6, "weight": 74.4, "renewal": False},
        "pat_004": {"status": "Pausado", "goal": "Emagrecimento", "end": 35, "expected": 12, "completed": 2, "sat": "Insatisfeito", "score": 4, "weight": 103.1, "renewal": False},
        "pat_005": {"status": "Ativo", "goal": "Controle metabólico", "end": 55, "expected": 10, "completed": 8, "sat": "Insatisfeito", "score": 5, "weight": 65.8, "renewal": False},
        "pat_006": {"status": "Ativo", "goal": "Acompanhamento nutricional", "end": 60, "expected": 10, "completed": 2, "sat": "Satisfeito", "score": 8, "weight": 86.9, "renewal": False},
        "pat_007": {"status": "Ativo", "goal": "Renovação de plano", "end": 9, "expected": 8, "completed": 6, "sat": "Satisfeito", "score": 9, "weight": 70.2, "renewal": True},
        "pat_008": {"status": "Ativo", "goal": "Revisão de peso", "end": 26, "expected": 8, "completed": 3, "sat": "Não informado", "score": 0, "weight": None, "renewal": True},
    }

    plan_rows = []
    for i, patient_id in enumerate(patients["patient_id"], start=1):
        item = scenario[patient_id]
        plan_rows.append(
            {
                "plan_id": f"plan_{i:03d}",
                "patient_id": patient_id,
                "budget_code": f"orc_{i:03d}",
                "issue_date": _d(-45 + i),
                "start_date": _d(-42 + i),
                "end_date": _d(item["end"]),
                "status": item["status"],
                "main_goal": item["goal"],
                "is_renewal": item["renewal"],
                "notes": "Dados fictícios para validar fluxo, contrato e layout.",
            }
        )
    treatment_plans = pd.DataFrame(plan_rows)

    procedures = [
        ("Injetáveis EV - Plano", "EV", "Semanal"),
        ("Acompanhamento nutricional", "Acompanhamento profissional", "Quinzenal"),
        ("Medicamento manipulado", "Medicamento manipulado", "Diário"),
    ]
    treatment_plan_items_rows = []
    execution_rows = []
    item_counter = 1
    exec_counter = 1
    for plan in plan_rows:
        patient_id = plan["patient_id"]
        total_expected = scenario[patient_id]["expected"]
        total_completed = scenario[patient_id]["completed"]
        split_expected = [max(total_expected - 4, 0), 4, 1 if patient_id == "pat_003" else 0]
        split_completed = [min(total_completed, split_expected[0]), max(min(total_completed - split_expected[0], split_expected[1]), 0), 0]
        for idx, (raw_name, category, frequency_type) in enumerate(procedures):
            if split_expected[idx] == 0:
                continue
            completed = split_completed[idx]
            expected = split_expected[idx]
            status = "Finalizado" if completed >= expected else "Em tratamento"
            if completed == 0:
                status = "Não iniciado" if patient_id == "pat_002" else "Aguardando"
            treatment_plan_items_rows.append(
                {
                    "plan_item_id": f"item_{item_counter:03d}",
                    "plan_id": plan["plan_id"],
                    "patient_id": patient_id,
                    "budget_code": plan["budget_code"],
                    "raw_name": raw_name,
                    "category": category,
                    "sessions_expected": expected,
                    "frequency_text": f"{expected} sessões - {frequency_type.lower()}",
                    "frequency_type": frequency_type,
                    "source": "PDF" if idx != 1 else "Dados manuais",
                    "needs_manual_review": patient_id == "pat_003" and idx == 2,
                }
            )
            execution_rows.append(
                {
                    "execution_id": f"exec_{exec_counter:03d}",
                    "patient_id": patient_id,
                    "plan_id": plan["plan_id"],
                    "budget_code": plan["budget_code"],
                    "procedure_raw": raw_name,
                    "procedure_category": category,
                    "status": status,
                    "sessions_expected": expected,
                    "sessions_completed": completed,
                    "sessions_remaining": expected - completed,
                    "plan_created_at": plan["issue_date"],
                }
            )
            item_counter += 1
            exec_counter += 1
    treatment_plan_items = pd.DataFrame(treatment_plan_items_rows)
    execution_summary = pd.DataFrame(execution_rows)

    goal_values = {
        "pat_001": (82.0, 74.0, "Boa adesão e satisfação alta."),
        "pat_002": (91.0, 84.0, "Procedimento ainda não iniciado."),
        "pat_003": (76.0, 71.0, "Manipulado pendente de validação manual."),
        "pat_004": (104.0, 95.0, "Baixo engajamento e insatisfação."),
        "pat_005": (68.0, 64.0, "Alta presença com satisfação baixa."),
        "pat_006": (88.0, 82.0, "Satisfeito, mas com baixa presença."),
        "pat_007": (73.0, 69.0, "Renovação próxima."),
        "pat_008": (80.0, 75.0, "Sem peso atualizado."),
    }
    patient_goals = pd.DataFrame(
        [
            {
                "goal_id": f"goal_{i:03d}",
                "patient_id": plan["patient_id"],
                "plan_id": plan["plan_id"],
                "goal_type": scenario[plan["patient_id"]]["goal"],
                "initial_weight": goal_values[plan["patient_id"]][0],
                "target_weight": goal_values[plan["patient_id"]][1],
                "target_date": plan["end_date"],
                "goal_notes": goal_values[plan["patient_id"]][2],
            }
            for i, plan in enumerate(plan_rows, start=1)
        ]
    )

    weight_rows = []
    for i, plan in enumerate(plan_rows, start=1):
        patient_id = plan["patient_id"]
        initial_weight, _, _ = goal_values[patient_id]
        weight_rows.append(
            {
                "weight_id": f"w_{i:03d}_001",
                "patient_id": patient_id,
                "plan_id": plan["plan_id"],
                "measurement_date": _d(-35),
                "weight": initial_weight,
                "source": "Dados manuais",
                "notes": "Peso inicial fictício",
            }
        )
        if scenario[patient_id]["weight"] is not None:
            weight_rows.append(
                {
                    "weight_id": f"w_{i:03d}_002",
                    "patient_id": patient_id,
                    "plan_id": plan["plan_id"],
                    "measurement_date": _d(-5),
                    "weight": scenario[patient_id]["weight"],
                    "source": "Dados manuais",
                    "notes": "Último peso fictício",
                }
            )
    weight_entries = pd.DataFrame(weight_rows)

    satisfaction_entries = pd.DataFrame(
        [
            {
                "satisfaction_id": f"sat_{i:03d}",
                "patient_id": plan["patient_id"],
                "plan_id": plan["plan_id"],
                "date": _d(-4),
                "satisfaction_status": scenario[plan["patient_id"]]["sat"],
                "score": scenario[plan["patient_id"]]["score"],
                "notes": f"Satisfação fictícia: {scenario[plan['patient_id']]['sat']}.",
            }
            for i, plan in enumerate(plan_rows, start=1)
        ]
    )

    appointment_rows = []
    appointment_item_rows = []
    appt_statuses = ["Atendido", "Agendado", "Confirmado", "Atrasado", "Atendido", "Cancelado", "Confirmado", "Reagendado"]
    for i, plan in enumerate(plan_rows, start=1):
        patient_id = plan["patient_id"]
        for j in range(2):
            appointment_id = f"appt_{i:03d}_{j + 1}"
            start = _dt(-7 + j * 10 + i, 8 + j)
            status = appt_statuses[i - 1]
            appointment_rows.append(
                {
                    "appointment_id": appointment_id,
                    "appointment_code": f"AG{i:03d}{j + 1}",
                    "patient_id": patient_id,
                    "budget_codes": plan["budget_code"],
                    "appointment_start": start,
                    "appointment_end": start + pd.Timedelta(hours=1),
                    "appointment_raw": "Sessão de acompanhamento",
                    "professional": "Equipe MAP",
                    "scheduled_by": "Recepção",
                    "status": status,
                }
            )
            appointment_item_rows.append(
                {
                    "appointment_item_id": f"appt_item_{i:03d}_{j + 1}",
                    "appointment_id": appointment_id,
                    "patient_id": patient_id,
                    "budget_code": plan["budget_code"],
                    "raw_item": "Sessão de acompanhamento",
                    "category": "Acompanhamento profissional",
                    "status": status,
                    "appointment_start": start,
                    "professional": "Equipe MAP",
                }
            )
    appointments = pd.DataFrame(appointment_rows)
    appointment_items = pd.DataFrame(appointment_item_rows)

    alerts = pd.DataFrame(
        [
            ("alert_001", "pat_002", "Enfermagem", "Procedimento não iniciado", "Confirmar primeira sessão do protocolo.", "Alta", "Aberto", -1, "Contato ativo para início."),
            ("alert_002", "pat_003", "Médica", "Manipulado pendente", "Item do plano requer conferência manual.", "Alta", "Aberto", -2, "Validar prescrição e disponibilidade."),
            ("alert_003", "pat_004", "Comercial", "Baixo engajamento e insatisfação", "Risco de abandono do plano.", "Alta", "Aberto", -1, "Contato de resgate."),
            ("alert_004", "pat_005", "Médica", "Engajada e insatisfeita", "Paciente presente, mas insatisfeita com evolução.", "Média", "Em análise", -3, "Revisar expectativa de resultado."),
            ("alert_005", "pat_007", "Comercial", "Renovação próxima", "Plano termina nos próximos 30 dias.", "Média", "Aberto", 0, "Oferecer renovação."),
            ("alert_006", "pat_008", "Nutrição", "Sem peso atualizado", "Não há peso recente registrado para o paciente.", "Média", "Aberto", -2, "Solicitar pesagem atual."),
        ],
        columns=["alert_id", "patient_id", "category", "alert_type", "description", "priority", "status", "offset", "comment"],
    )
    plan_lookup = treatment_plans.set_index("patient_id")["plan_id"]
    alerts["plan_id"] = alerts["patient_id"].map(plan_lookup)
    alerts["created_at"] = alerts["offset"].apply(_d)
    alerts = alerts[["alert_id", "patient_id", "plan_id", "category", "alert_type", "description", "priority", "status", "created_at", "comment"]]

    data_quality_issues = pd.DataFrame(
        [
            ("dq_001", "Dados manuais", "Alta", "Campo ausente", "Paciente sem peso atualizado.", "pat_008", "weight_entries.weight"),
            ("dq_002", "PDFs de plano", "Média", "Revisão manual", "Medicamento manipulado pendente de validação.", "pat_003", "treatment_plan_items.needs_manual_review"),
            ("dq_003", "Relatório de frequência", "Média", "Execução zerada", "Procedimento ainda não iniciado.", "pat_002", "execution_summary.sessions_completed"),
            ("dq_004", "Fonte real", "Baixa", "Integração pendente", "Arquivos reais ainda não integrados.", None, "source_files"),
        ],
        columns=["issue_id", "source", "severity", "issue_type", "description", "patient_id", "field_name"],
    )

    data = {
        "patients": patients,
        "treatment_plans": treatment_plans,
        "treatment_plan_items": treatment_plan_items,
        "execution_summary": execution_summary,
        "appointments": appointments,
        "appointment_items": appointment_items,
        "patient_goals": patient_goals,
        "weight_entries": weight_entries,
        "satisfaction_entries": satisfaction_entries,
        "alerts": alerts,
        "data_quality_issues": data_quality_issues,
    }

    _assert_referential_integrity(data)
    return data
