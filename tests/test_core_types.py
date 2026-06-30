"""Roundtrip + NA-safety tests for src.core.types (Phase 1).

The plan (``docs/caminho_b_plano.md`` §3 Fase 1) lists 9 tests for
``test_core_types.py``. Each one exercises a single dataclass plus a
NA-safety / edge-case to surface the "this column is missing or has
pd.NA" failure mode that production data will hit.

N7: every test uses a v1-style ``pd.Series`` so the row-level helpers
in ``src.core.mapping`` are exercised -- not just the dataclass
constructors. This catches "the dataclass is fine, but mapping forgot
to coerce" bugs.

Why ``load_mock_data()`` and not ``load_all()``:
  * v1 CSVs em ``data/csv/`` estao header-only (Phase 0 / T9 cleanup).
  * ``src.mock_data.load_mock_data()`` retorna o seed completo (8
    patients, 8 plans, 17 items, 16 appointments, ...) -- necessario
    para exercitar os roundtrips.
  * Phase 8 (migracao v2) trocara ``load_mock_data()`` por
    ``load_all()`` quando os CSVs tiverem dados reais.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.core.mapping import (
    appointment_row_to_client_session,
    patient_row_to_client,
    synthesize_deliverable,
    synthesize_organization,
    synthesize_user,
    treatment_plan_item_row_to_cd,
    treatment_plan_row_to_cd,
)
from src.core.types import (
    Client,
    ClientDeliverable,
    Organization,
)

# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------


def _patient_row(**overrides: object) -> pd.Series:
    """Constroi uma pd.Series mimetizando uma linha de ``patients`` (v1).

    Campos opcionais podem ser sobrescritos via ``overrides`` -- ex.:
    ``_patient_row(name=pd.NA)`` para testar NA-safety.
    """
    base = {
        "patient_id": "pat_001",
        "name": "Kelly Cristina Amorim",
        "normalized_name": "kelly cristina amorim",
        "medical_record": "7714697",
        "phone": "(62) 99999-0001",
        "age": 38,
        "created_at": "2026-04-04",
    }
    base.update(overrides)
    return pd.Series(base)


def _plan_row(**overrides: object) -> pd.Series:
    """Constroi uma pd.Series mimetizando ``treatment_plans`` (v1)."""
    base = {
        "plan_id": "plan_001",
        "patient_id": "pat_001",
        "budget_code": "4622306",
        "issue_date": "2026-04-04",
        "start_date": "2026-04-10",
        "end_date": "2026-07-10",
        "status": "Ativo",
        "main_goal": "Emagrecimento",
        "is_renewal": False,
        "notes": None,
    }
    base.update(overrides)
    return pd.Series(base)


def _plan_item_row(**overrides: object) -> pd.Series:
    """Constroi uma pd.Series mimetizando ``treatment_plan_items`` (v1)."""
    base = {
        "plan_item_id": "item_001",
        "plan_id": "plan_001",
        "patient_id": "pat_001",
        "budget_code": "4622306",
        "raw_name": "Injetáveis EV - Plano",
        "category": "EV",
        "sessions_expected": 12,
        "frequency_text": "Semanal",
        "frequency_type": "Semanal",
        "source": "mock",
        "needs_manual_review": False,
    }
    base.update(overrides)
    return pd.Series(base)


def _appointment_row(**overrides: object) -> pd.Series:
    """Constroi uma pd.Series mimetizando ``appointments`` (v1)."""
    base = {
        "appointment_id": "appt_001",
        "appointment_code": "AG0001",
        "patient_id": "pat_001",
        "budget_codes": "4622306",
        "appointment_start": "2026-06-17 08:00:00",
        "appointment_end": "2026-06-17 09:00:00",
        "appointment_raw": "Sessão de acompanhamento",
        "professional": "Dayane Junqueira Vilela",
        "scheduled_by": "Morena Gontijo De Araujo",
        "status": "Atendido",
    }
    base.update(overrides)
    return pd.Series(base)


# ---------------------------------------------------------------------------
# Testes de roundtrip (9 testes do plano §3 Fase 1)
# ---------------------------------------------------------------------------


def test_organization_roundtrip() -> None:
    """synthesize_Organization devolve Organization com defaults saudaveis."""
    org = synthesize_organization()
    assert isinstance(org, Organization)
    assert org.id == 1
    assert org.nome == "DClinique"
    assert org.cnpj is None  # v1 nao tem CNPJ
    assert org.ativo is True
    assert org.deleted_at is None
    assert isinstance(org.criado_em, datetime)
    # Frozen: nao pode mutar
    with pytest.raises((AttributeError, Exception)):
        org.nome = "Outro"  # type: ignore[misc]


def test_user_roundtrip() -> None:
    """synthesize_user aceita Provider e Admin (Literal) sem levant."""
    provider = synthesize_user(
        user_id=1, nome="Dayane Junqueira Vilela",
        tipo="Provider", organization_id=1, funcao="Nutróloga",
    )
    assert provider.tipo == "Provider"
    assert provider.funcao == "Nutróloga"
    assert provider.cpf is None  # v1 nao tem

    admin = synthesize_user(
        user_id=2, nome="Morena Gontijo De Araujo",
        tipo="Admin", organization_id=1, funcao="Recepção",
    )
    assert admin.tipo == "Admin"
    assert admin.funcao == "Recepção"


def test_deliverable_roundtrip() -> None:
    """Deliverable com e sem parent_deliverable_id."""
    root = synthesize_deliverable(
        deliverable_id=1, titulo="Injetáveis EV",
        tipo="Injetável", organization_id=1,
        frequencia_tipo="Semanal", frequencia_texto="1x/semana",
    )
    assert root.parent_deliverable_id is None
    assert root.frequencia_tipo == "Semanal"

    child = synthesize_deliverable(
        deliverable_id=2, titulo="Injetáveis EV - Plano",
        tipo="Injetável", organization_id=1,
        parent_deliverable_id=1,
    )
    assert child.parent_deliverable_id == 1
    assert child.frequencia_tipo is None


def test_client_roundtrip() -> None:
    """Client com e sem cpf/data_nascimento (NA-safety na origem)."""
    # Caminho feliz: dados completos
    c = patient_row_to_client(_patient_row())
    assert isinstance(c, Client)
    assert c.id == 1
    assert c.nome == "Kelly Cristina Amorim"
    assert c.cpf is None  # v1 mock nao tem CPF
    assert c.data_nascimento is None  # v1 so' tem age
    assert c.telefone == "(62) 99999-0001"
    assert c.observacoes == "prontuario: 7714697; idade: 38"
    assert c.created_via == "manual"
    assert c.ativo is True
    assert isinstance(c.criado_em, datetime)

    # Caminho NA: campos opcionais faltando
    c_na = patient_row_to_client(_patient_row(phone=pd.NA, age=pd.NA, medical_record=pd.NA))
    assert c_na.telefone is None
    assert "idade" not in (c_na.observacoes or "")
    assert "prontuario" not in (c_na.observacoes or "")


def test_client_deliverable_roundtrip() -> None:
    """ClientDeliverable para Plano (sem parent) e Item (com parent)."""
    deliv_map = {"Injetáveis EV - Plano": 1, "Emagrecimento": 2}
    # Plano (sem parent)
    plan_cd = treatment_plan_row_to_cd(_plan_row(), deliv_map, organization_id=1)
    assert plan_cd is not None
    assert isinstance(plan_cd, ClientDeliverable)
    assert plan_cd.parent_client_deliverable_id is None  # Plano
    assert plan_cd.client_id == 1
    assert plan_cd.deliverable_id == 2  # "Emagrecimento"
    assert plan_cd.status == "Ativo"
    assert plan_cd.orcamento == "4622306"
    assert plan_cd.is_renovacao is False
    assert plan_cd.sessions_expected == 0  # v1 plans nao tem
    assert plan_cd.sessions_remaining == 0

    # Item (com parent) -- precisa plan_id_map populado
    item_cd = treatment_plan_item_row_to_cd(
        _plan_item_row(), deliv_map, plan_id_map={"plan_001": 1},
        organization_id=1,
    )
    assert item_cd is not None
    assert item_cd.parent_client_deliverable_id == 1
    assert item_cd.deliverable_id == 1  # "Injetáveis EV - Plano"
    assert item_cd.sessions_expected == 12
    assert item_cd.sessions_completed == 0
    assert item_cd.sessions_remaining == 12


def test_client_session_roundtrip() -> None:
    """ClientSession para cada status possivel (todos os 6 do Literal)."""
    user_map = {"Dayane Junqueira Vilela": 1, "Morena Gontijo De Araujo": 2}
    statuses = [
        "Agendado", "Confirmado", "Atendido",
        "Atrasado", "Cancelado", "Reagendado",
    ]
    for s in statuses:
        cs = appointment_row_to_client_session(
            _appointment_row(status=s), user_map, organization_id=1
        )
        assert cs is not None, f"status={s} retornou None"
        assert cs.status == s
        assert cs.client_id == 1
        assert cs.provider_id == 1
        assert cs.agendado_por_id == 2
        assert cs.codigo_origem == "AG0001"
        assert isinstance(cs.session_start, datetime)
        assert cs.session_start <= cs.session_end


# ---------------------------------------------------------------------------
# NA-safety / edge cases
# ---------------------------------------------------------------------------


def test_load_clients_empty() -> None:
    """DataFrame vazio -> lista vazia, sem excecao (N7)."""
    from src.core.repos import load_clients
    empty: dict[str, pd.DataFrame] = {"patients": pd.DataFrame(columns=[
        "patient_id", "name", "normalized_name", "medical_record",
        "phone", "age", "created_at",
    ])}
    result = load_clients(empty)
    assert result == []


def test_load_clients_ignores_deleted() -> None:
    """Linhas com ``deleted_at`` populado sao filtradas."""
    from src.core.repos import load_clients
    df = pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Kelly", "Joana"],
        "normalized_name": ["kelly", "joana"],
        "medical_record": ["1", "2"],
        "phone": [None, None],
        "age": [38, 25],
        "created_at": ["2026-04-04", "2026-04-05"],
        "deleted_at": [None, "2026-12-31 12:00:00"],  # Joana deletada
    })
    data = {"patients": df}
    result = load_clients(data)
    assert len(result) == 1
    assert result[0].nome == "Kelly"


def test_na_safety() -> None:
    """Coluna com pd.NA -> dataclass com None ou default; nunca levanta.

    Cobre: nome vazio, datas malformadas, ints com pd.NA, bools como string
    inesperada, ids em formato invalido.
    """
    # ID completamente invalido -- _safe_id_from_string retorna None -> id=0
    c = patient_row_to_client(_patient_row(patient_id="abc", name=pd.NA))
    assert c.id == 0
    assert c.nome == ""  # None default ""

    # Data malformada -> _safe_datetime retorna None -> criado_em = datetime.now()
    c2 = patient_row_to_client(_patient_row(created_at="not-a-date"))
    assert isinstance(c2.criado_em, datetime)  # now() fallback

    # Bool como string inesperada
    plan = treatment_plan_row_to_cd(
        _plan_row(is_renewal="weird-value"),
        {"Emagrecimento": 1}, organization_id=1,
    )
    assert plan is not None
    assert plan.is_renovacao is False  # default quando string nao e' true/false

    # Frequencia desconhecida -> _validate_frequencia retorna None
    from src.core.mapping import _validate_frequencia
    assert _validate_frequencia("Cada 5 horas") is None
    assert _validate_frequencia("Semanal") == "Semanal"
    assert _validate_frequencia(None) is None

    # Status desconhecido -> _validate_session_status default
    cs = appointment_row_to_client_session(
        _appointment_row(status="StatusInventado"),
        {"Dayane Junqueira Vilela": 1}, organization_id=1,
    )
    assert cs is not None
    assert cs.status == "Agendado"  # default quando invalido
