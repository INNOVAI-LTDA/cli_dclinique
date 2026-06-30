"""End-to-end tests for src.core.repos (Phase 1).

The plan (``docs/caminho_b_plano.md`` §3 Fase 1) requires that:
  * ``load_clients(load_all())`` returns 8 instances in the mock
  * ``load_clients(load_all())[0].cpf`` is None (mock has no CPF)
  * ``streamlit run app.py`` is unchanged (covered manually post-Phase 1)

This file adds the additional repos coverage: organizations default
(DClinique), users extracted from ``appointments``, deliverables
catalog built from ``treatment_plan_items``, client_deliverables
plans+items joined, client_sessions with FKs resolved, and the
deleted_at filter for all load functions.

N7: every test uses ``load_mock_data()`` or a hand-built DataFrame
dict -- never touches the file system or Streamlit runtime.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.core.repos import (
    load_client_deliverables,
    load_client_sessions,
    load_clients,
    load_deliverables,
    load_organizations,
    load_users,
)

# ---------------------------------------------------------------------------
# Fixture: snapshot of the v1 mock data (load_mock_data is in-memory only)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_data() -> dict[str, pd.DataFrame]:
    """Retorna o seed v1 completo (8 patients, 8 plans, 17 items, 16 appts)."""
    from src.mock_data import load_mock_data
    return load_mock_data()


# ---------------------------------------------------------------------------
# load_organizations
# ---------------------------------------------------------------------------


def test_load_organizations_returns_dclinique(mock_data: dict[str, pd.DataFrame]) -> None:
    """Phase 1 retorna 1 Organization: DClinique."""
    orgs = load_organizations(mock_data)
    assert len(orgs) == 1
    org = orgs[0]
    assert org.id == 1
    assert org.nome == "DClinique"
    assert org.ativo is True
    assert org.deleted_at is None


# ---------------------------------------------------------------------------
# load_users
# ---------------------------------------------------------------------------


def test_load_users_extracts_providers_and_admins(
    mock_data: dict[str, pd.DataFrame],
) -> None:
    """Users vem de ``appointments.professional`` (Provider) e
    ``appointments.scheduled_by`` (Admin).
    """
    users = load_users(mock_data)
    assert len(users) >= 2
    by_tipo: dict[str, list] = {"Provider": [], "Admin": []}
    for u in users:
        by_tipo[u.tipo].append(u)
    assert len(by_tipo["Provider"]) >= 1
    assert len(by_tipo["Admin"]) >= 1
    # Todos pertecem a org 1
    assert all(u.organization_id == 1 for u in users)
    # Nenhum deleted
    assert all(u.deleted_at is None for u in users)
    # Hashable (frozen=True)
    assert len({hash(u) for u in users}) == len(users)  # todos distintos


def test_load_users_empty_dataframe() -> None:
    """``appointments`` ausente -> lista vazia, sem excecao."""
    result = load_users({"appointments": pd.DataFrame()})
    assert result == []


# ---------------------------------------------------------------------------
# load_deliverables
# ---------------------------------------------------------------------------


def test_load_deliverables_catalog_from_items(
    mock_data: dict[str, pd.DataFrame],
) -> None:
    """Deliverables vem dos ``raw_name`` unicos de ``treatment_plan_items``."""
    delivs = load_deliverables(mock_data)
    assert len(delivs) >= 1
    # Cada deliverable tem id unico, titulo nao-vazio, organization_id=1
    ids = [d.id for d in delivs]
    assert len(set(ids)) == len(ids)
    for d in delivs:
        assert d.titulo
        assert d.organization_id == 1
        assert d.ativo is True
        assert d.deleted_at is None


def test_load_deliverables_empty() -> None:
    """Tabelas ausentes -> lista vazia, sem excecao."""
    result = load_deliverables({})
    assert result == []


# ---------------------------------------------------------------------------
# load_clients
# ---------------------------------------------------------------------------


def test_load_clients_returns_eight(mock_data: dict[str, pd.DataFrame]) -> None:
    """Criterio de aceite do plano: 8 instâncias no mock."""
    clients = load_clients(mock_data)
    assert len(clients) == 8


def test_load_clients_first_cpf_is_none(
    mock_data: dict[str, pd.DataFrame],
) -> None:
    """Criterio de aceite do plano: cpf e' None (v1 mock nao tem CPF)."""
    clients = load_clients(mock_data)
    assert clients[0].cpf is None


def test_load_clients_ignores_deleted_at() -> None:
    """Linhas com ``deleted_at`` populado sao filtradas."""
    df = pd.DataFrame({
        "patient_id": ["pat_001", "pat_002", "pat_003"],
        "name": ["Kelly", "Joana", "Maria"],
        "normalized_name": ["kelly", "joana", "maria"],
        "medical_record": ["1", "2", "3"],
        "phone": [None, None, None],
        "age": [38, 25, 30],
        "created_at": ["2026-04-04", "2026-04-05", "2026-04-06"],
        "deleted_at": [None, "2026-12-31 12:00:00", None],
    })
    data = {"patients": df}
    clients = load_clients(data)
    nomes = [c.nome for c in clients]
    assert "Kelly" in nomes
    assert "Maria" in nomes
    assert "Joana" not in nomes  # deletada


def test_load_clients_handles_missing_table() -> None:
    """``patients`` ausente -> lista vazia, sem excecao."""
    result = load_clients({})
    assert result == []


# ---------------------------------------------------------------------------
# load_client_deliverables
# ---------------------------------------------------------------------------


def test_load_client_deliverables_plans_and_items(
    mock_data: dict[str, pd.DataFrame],
) -> None:
    """Phase 1 retorna 8 Planos + 17 Items = 25 ClientDeliverable."""
    cds = load_client_deliverables(mock_data)
    plans = [c for c in cds if c.parent_client_deliverable_id is None]
    items = [c for c in cds if c.parent_client_deliverable_id is not None]
    assert len(plans) == 8
    assert len(items) == 17
    # Todo item tem parent que existe entre os plans
    plan_ids = {p.id for p in plans}
    for item in items:
        assert item.parent_client_deliverable_id in plan_ids


def test_load_client_deliverables_handles_empty() -> None:
    """Tabelas ausentes -> lista vazia, sem excecao."""
    result = load_client_deliverables({})
    assert result == []


# ---------------------------------------------------------------------------
# load_client_sessions
# ---------------------------------------------------------------------------


def test_load_client_sessions_resolves_fks(
    mock_data: dict[str, pd.DataFrame],
) -> None:
    """ClientSession tem provider_id e agendado_por_id resolvidos para users."""
    sessions = load_client_sessions(mock_data)
    assert len(sessions) >= 1
    users = load_users(mock_data)
    user_ids = {u.id for u in users}
    for cs in sessions:
        assert cs.provider_id in user_ids
        # agendado_por_id pode ser None se scheduled_by vazio
        if cs.agendado_por_id is not None:
            assert cs.agendado_por_id in user_ids
        assert cs.organization_id == 1
        # session_start <= session_end
        assert cs.session_start <= cs.session_end


def test_load_client_sessions_empty() -> None:
    """Appointments ausente -> lista vazia, sem excecao."""
    result = load_client_sessions({})
    assert result == []


# ---------------------------------------------------------------------------
# Cross-repos: contagem total do mock coerente
# ---------------------------------------------------------------------------


def test_mock_data_total_counts(mock_data: dict[str, pd.DataFrame]) -> None:
    """Smoke check: 8 clients, 25 client_deliverables, 16 sessions nao batem
    zero e somam algo razoavel.
    """
    assert len(load_clients(mock_data)) == 8
    assert len(load_client_deliverables(mock_data)) == 25
    assert len(load_client_sessions(mock_data)) == 16
    # Organizations e deliverables nao sao contados pelo mock (sintetizados)
    assert len(load_organizations(mock_data)) == 1
    assert len(load_deliverables(mock_data)) >= 1
    assert len(load_users(mock_data)) >= 1
