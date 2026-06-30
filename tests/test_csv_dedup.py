"""Tests for ``src/csv_importer/dedup.py`` (Caminho B, Phase 6).

Cobre 5 fluxos:

  1. **test_find_patient_by_name_existing** (plano) — Kelly existe → patient_id.
  2. **test_find_patient_by_name_missing** (plano) — "Fantasma" → None.
  3. **test_find_patient_by_name_case_insensitive** (extra) — "KELLY" == "kelly".
  4. **test_find_plan_by_budget_existing** (plano) — (Kelly, 4622306) → plan_id.
  5. **test_find_plan_by_budget_missing** (extra) — (Kelly, 9999999) → None.
  6. **test_resolve_patient_raises** (plano) — nome inexistente levanta
     :class:`PatientNotFoundError` com ``name``, ``orcamento``, ``normalized``.
  7. **test_resolve_plan_key_raises_on_duplicate** (extra) — duplicate detection.
  8. **test_resolve_plan_key_allows_duplicate** (extra) — flag bypassa erro.

N7: boundary functions (resolve_*) capturam internals e re-emitem como
excecoes de dominio com contexto PT-BR.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.csv_importer.dedup import (
    DuplicatePlanError,
    PatientNotFoundError,
    find_patient_by_name,
    find_plan_by_budget,
    resolve_patient,
    resolve_plan_key,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def data_with_2_patients() -> dict:
    """DataDict com 2 pacientes (Kelly + Erick) e 3 plans (Kelly 1 plan, Erick 2 plans)."""
    return {
        "patients": pd.DataFrame(
            {
                "patient_id": ["pat_seed_001", "pat_seed_002"],
                "name": ["Kelly Cristina a Silva Amorim", "ERICK DE SOUSA KUBIJAN"],
                "normalized_name": [
                    "kelly cristina a silva amorim",
                    "erick de sousa kubijan",
                ],
            }
        ),
        "treatment_plans": pd.DataFrame(
            {
                "plan_id": ["plan_seed_001", "plan_seed_002", "plan_seed_003"],
                "patient_id": ["pat_seed_001", "pat_seed_002", "pat_seed_002"],
                "budget_code": ["4622306", "4671175", "4671251"],
            }
        ),
    }


# ---------------------------------------------------------------------------
# 1-3. find_patient_by_name (plano + extras)
# ---------------------------------------------------------------------------


def test_find_patient_by_name_existing(data_with_2_patients: dict) -> None:
    """Kelly existe → retorna patient_id."""
    pid = find_patient_by_name(data_with_2_patients, "Kelly Cristina a Silva Amorim")
    assert pid == "pat_seed_001"


def test_find_patient_by_name_missing(data_with_2_patients: dict) -> None:
    """Nome inexistente → None (sem excecao)."""
    pid = find_patient_by_name(data_with_2_patients, "Fantasma da Silva")
    assert pid is None


def test_find_patient_by_name_case_insensitive(data_with_2_patients: dict) -> None:
    """Case nao importa (normalize_name faz lowercase)."""
    pid = find_patient_by_name(data_with_2_patients, "KELLY CRISTINA A SILVA AMORIM")
    assert pid == "pat_seed_001"
    pid = find_patient_by_name(data_with_2_patients, "kelly cristina a silva amorim")
    assert pid == "pat_seed_001"
    pid = find_patient_by_name(data_with_2_patients, "ErIcK dE sOuSa KuBiJaN")
    assert pid == "pat_seed_002"


# ---------------------------------------------------------------------------
# 4-5. find_plan_by_budget (plano + extras)
# ---------------------------------------------------------------------------


def test_find_plan_by_budget_existing(data_with_2_patients: dict) -> None:
    """(Kelly, 4622306) → plan_id plan_seed_001."""
    pid = find_plan_by_budget(data_with_2_patients, "pat_seed_001", "4622306")
    assert pid == "plan_seed_001"


def test_find_plan_by_budget_missing(data_with_2_patients: dict) -> None:
    """Orcamento inexistente para o paciente → None."""
    assert find_plan_by_budget(data_with_2_patients, "pat_seed_001", "9999999") is None
    # Outro paciente, mesmo orcamento: nao e' match (composicao)
    assert find_plan_by_budget(data_with_2_patients, "pat_seed_002", "4622306") is None


def test_find_plan_by_budget_empty(data_with_2_patients: dict) -> None:
    """Orcamento vazio → None (plan sem budget e' anonimo)."""
    assert find_plan_by_budget(data_with_2_patients, "pat_seed_001", "") is None


# ---------------------------------------------------------------------------
# 6. resolve_patient (plano)
# ---------------------------------------------------------------------------


def test_resolve_patient_raises(data_with_2_patients: dict) -> None:
    """``resolve_patient`` levanta ``PatientNotFoundError`` com contexto."""
    with pytest.raises(PatientNotFoundError) as excinfo:
        resolve_patient(data_with_2_patients, "Fantasma da Silva", "9999999")
    err = excinfo.value
    assert err.name == "Fantasma da Silva"
    assert err.orcamento == "9999999"
    assert err.normalized == "fantasma da silva"
    # Mensagem PT-BR
    assert "nao encontrado" in str(err).lower()
    assert "Fantasma da Silva" in str(err)


def test_resolve_patient_returns_id(data_with_2_patients: dict) -> None:
    """``resolve_patient`` retorna patient_id quando encontra."""
    pid = resolve_patient(data_with_2_patients, "Kelly Cristina a Silva Amorim", "4622306")
    assert pid == "pat_seed_001"


# ---------------------------------------------------------------------------
# 7-8. resolve_plan_key (extras)
# ---------------------------------------------------------------------------


def test_resolve_plan_key_raises_on_duplicate(data_with_2_patients: dict) -> None:
    """Duplicate detection: (Kelly, 4622306) ja' existe → levanta."""
    with pytest.raises(DuplicatePlanError) as excinfo:
        resolve_plan_key(data_with_2_patients, "pat_seed_001", "4622306")
    err = excinfo.value
    assert err.patient_id == "pat_seed_001"
    assert err.orcamento == "4622306"
    assert err.existing_plan_id == "plan_seed_001"
    assert "duplicado" in str(err).lower() or "insert-only" in str(err).lower()


def test_resolve_plan_key_allows_duplicate(data_with_2_patients: dict) -> None:
    """``allow_duplicate=True`` retorna o plan_id existente sem erro."""
    pid = resolve_plan_key(
        data_with_2_patients, "pat_seed_001", "4622306", allow_duplicate=True
    )
    assert pid == "plan_seed_001"


def test_resolve_plan_key_returns_none_when_missing(data_with_2_patients: dict) -> None:
    """Plan novo → None (sinal para o caller inserir)."""
    pid = resolve_plan_key(data_with_2_patients, "pat_seed_001", "9999999")
    assert pid is None


# ---------------------------------------------------------------------------
# Edge cases de schema drift
# ---------------------------------------------------------------------------


def test_find_patient_handles_missing_table() -> None:
    """data sem tabela 'patients' → None (boundary defensiva)."""
    assert find_patient_by_name({}, "Kelly") is None
    assert find_patient_by_name({"patients": pd.DataFrame()}, "Kelly") is None


def test_find_plan_handles_missing_table() -> None:
    """data sem tabela 'treatment_plans' → None."""
    assert find_plan_by_budget({}, "pat_001", "1234") is None
    assert find_plan_by_budget(
        {"treatment_plans": pd.DataFrame()}, "pat_001", "1234"
    ) is None
