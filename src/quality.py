"""Data quality scoring for the mock shell."""
from __future__ import annotations

import pandas as pd


def quality_scores(data: dict[str, pd.DataFrame]) -> dict[str, float]:
    issues = data["data_quality_issues"]
    penalty = min(len(issues) * 4, 25)
    return {
        "Score geral": 100 - penalty,
        "Completude": 88,
        "Consistência": 91,
        "Atualidade": 82,
        "Validade": 90,
    }


def client_checklist() -> list[str]:
    return [
        "PDFs dos planos ativos e renovações recentes.",
        "Relatório de frequência por procedimento e por paciente.",
        "Relatório de agendamentos com status atualizado.",
        "Pesos recentes e metas validadas por paciente.",
        "Regras de negócio finais para alertas clínicos e comerciais.",
    ]
