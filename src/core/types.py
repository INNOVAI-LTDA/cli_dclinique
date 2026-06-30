"""v2 domain dataclasses for the MAP data model (Caminho B, Phase 1).

Each entity / association is a ``@dataclass(frozen=True)`` matching the design
in ``docs/data_model.md``. Field shapes mirror the SQL DDL in §6; values
populated from v1 in Phase 1 (via ``repos.py``) may leave audit-trail
columns (``criado_em``, ``atualizado_em``, ``deleted_at``) as synthetic
defaults because v1 does not track them per row.

Why ``frozen=True``:
  * v2 entities are an identity-by-id model; mutation is expressed by creating
    a new instance. The dataclass is a value object, not a record handle.
  * Makes them hashable + usable in ``set`` / as ``dict`` keys (useful for
    "given id X, fetch the live instance" patterns in Phase 2+).

Why ``from __future__ import annotations``:
  * Type hints reference ``datetime``, ``date``, ``Literal`` and PEP 604
    unions (``int | None``). With the future import these strings are lazy —
    no runtime cost on ``import src.core.types``.

N7 (exception handling): the dataclass constructors themselves do not raise
beyond the standard ``TypeError`` for missing required fields (handled in
``mapping.py``) and ``FrozenInstanceError`` for setattr (see
``docs/exception_catalog.md`` §4.2). Field validation that depends on
runtime values (e.g., "tipo must be one of the Literals") lives in
``mapping.py`` so the dataclasses stay cheap to instantiate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Enums (PEP 675 Literal aliases -- not runtime-validated, but document intent
# and are picked up by static type checkers + IDE autocomplete).
# ---------------------------------------------------------------------------

#: ``users.tipo`` (data_model.md §3.2)
UserTipo = Literal["Provider", "Admin"]

#: ``users.tipo_registro`` (data_model.md §3.2)
UserRegistroTipo = Literal["CRM", "COREN", "CRN", "CRO", "Outro"]

#: ``deliverables.tipo`` (data_model.md §3.3.1)
DeliverableTipo = Literal[
    "Plano de Tratamento",
    "Injetável",
    "Medicamento Manipulado",
    "Implante",
    "Consulta",
    "Acompanhamento",
    "Exame",
    "Meta",
]

#: ``deliverables.frequencia_tipo`` (data_model.md §3.3)
DeliverableFrequencia = Literal[
    "Diário", "Semanal", "Quinzenal", "Mensal", "Única", "Outro"
]

#: ``client_deliverables.status`` (data_model.md §4.2)
ClientDeliverableStatus = Literal[
    "Ativo", "Pausado", "Aguardando", "Finalizado", "Cancelado", "Não iniciado"
]

#: ``client_sessions.status`` (data_model.md §4.3; same enum as
#: ``appointments.status`` in v1)
SessionStatus = Literal[
    "Agendado", "Confirmado", "Atendido", "Atrasado", "Cancelado", "Reagendado"
]

#: ``clients.origem`` (data_model.md §3.4)
ClientOrigem = Literal[
    "Manual", "PDF", "CSV", "SupportHealth", "Indicação", "Instagram", "Outro"
]

#: ``clients.created_via`` (data_model.md §3.4) -- audit-only
ClientCreatedVia = Literal[
    "manual", "pdf_import", "csv_import", "supporthealth_sync"
]


# ---------------------------------------------------------------------------
# Entidades (4 substantivos do data_model.md §2 P1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Organization:
    """A clínica (data_model.md §3.1).

    No MAP, há 1 instância (DClinique). Em SupportHealth, pode haver N.
    Phase 1 retorna uma única org sintetizada de ``load_organizations``,
    porque o v1 não tem tabela de orgs -- a clínica é o contexto implícito.
    """

    id: int
    nome: str
    cnpj: str | None  # v1 não tem CNPJ; default None até Fase 8 (migração v2)
    endereco: str | None
    telefone: str | None
    url: str | None
    config: dict[str, Any] | None  # ex.: {"timezone": "America/Sao_Paulo"}
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class User:
    """Provider ou Admin (data_model.md §3.2).

    Phase 1 sintetiza os 5 profissionais + 1 recepcionista (Morena) a partir
    das colunas ``appointments.professional`` (Provider) e
    ``appointments.scheduled_by`` (Admin) -- v1 não tem tabela de users.
    ``cpf`` e ``registro_especial`` virão na migração v2 (Fase 8).
    """

    id: int
    tipo: UserTipo
    nome: str
    cpf: str | None  # natural-key (validado por DV) -- ausente em v1
    registro_especial: str | None  # CRM/COREN/etc.
    tipo_registro: UserRegistroTipo | None
    telefone: str | None
    email: str | None
    funcao: str | None  # "Nutróloga", "Enfermeira", "Recepção"
    organization_id: int
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class Deliverable:
    """Catálogo de produtos/serviços (data_model.md §3.3).

    Phase 1 extrai o catálogo a partir de ``treatment_plan_items.raw_name`` +
    ``category`` -- o v1 não tem tabela de catálogo; cada plan_item traz o
    seu próprio. A hierarquia Plano → Item será explicitada via
    ``parent_deliverable_id`` quando o v2 tiver dados de produção
    (Fase 8 -- migração).
    """

    id: int
    titulo: str
    tipo: DeliverableTipo
    descricao: str
    parent_deliverable_id: int | None  # self-FK para hierarquia (data_model.md §3.3 P4)
    organization_id: int
    frequencia_tipo: DeliverableFrequencia | None
    frequencia_texto: str | None
    metadata: dict[str, Any] | None  # jsonb com campos específicos por tipo (§3.3.2)
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class Client:
    """Paciente (data_model.md §3.4).

    Phase 1 mapeia diretamente de ``patients`` (v1) com algumas lacunas
    conhecidas: ``cpf``, ``rg``, ``data_nascimento`` são None (v1 não tem
    essas colunas no mock). ``age`` é preservado em ``observacoes`` como
    metadado de migração.
    """

    id: int
    nome: str
    cpf: str | None  # natural-key -- ausente em v1
    rg: str | None
    data_nascimento: date | None  # v1 só tem ``age`` (int); data virá do PDF na Fase 6
    telefone: str | None
    endereco: str | None
    email: str | None
    origem: ClientOrigem | None
    consentimento_lgpd: bool  # LGPD gate do DEPLOY.md
    consentimento_lgpd_em: datetime | None
    observacoes: str | None  # v1 ``age`` preservado aqui ("idade: 38")
    created_via: ClientCreatedVia  # default "manual" em Phase 1
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


# ---------------------------------------------------------------------------
# Associações (data_model.md §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientDeliverable:
    """A tabela central (data_model.md §4.2) -- substitui ``treatment_plans``
    + ``treatment_plan_items`` + ``execution_summary`` por uma única estrutura
    polimórfica.

    Phase 1 sintetiza:
      * Um ClientDeliverable (Plano) por linha de ``treatment_plans``
        (``parent_client_deliverable_id = None``).
      * Um ClientDeliverable (Item) por linha de ``treatment_plan_items``
        (``parent_client_deliverable_id = plan_id``).

    Campos como ``sessions_completed`` vêm de ``execution_summary``;
    ``sessions_remaining`` é derivado = expected - completed.
    """

    id: int
    client_id: int
    deliverable_id: int  # FK ao catálogo (data_model.md §3.3)
    parent_client_deliverable_id: int | None  # None = Plano; setado = Item
    organization_id: int
    status: ClientDeliverableStatus
    orcamento: str | None  # código do orçamento (v1 ``treatment_plans.budget_code``)
    is_renovacao: bool
    data_inicio: date | None  # v1 ``treatment_plans.start_date``
    data_fim: date | None  # v1 ``treatment_plans.end_date``
    sessions_expected: int
    sessions_completed: int
    sessions_remaining: int
    metadata: dict[str, Any] | None
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class ClientSession:
    """Agendamento / consulta (data_model.md §4.3).

    Phase 1 mapeia diretamente de ``appointments`` (v1). As colunas
    ``professional`` e ``scheduled_by`` viram ``provider_id`` e
    ``agendado_por_id`` (resolvidos via ``User`` sintetizado em
    ``load_users``).
    """

    id: int
    client_id: int
    provider_id: int  # FK users(tipo=Provider)
    agendado_por_id: int | None  # FK users(tipo=Admin)
    organization_id: int
    session_start: datetime
    session_end: datetime
    status: SessionStatus
    session_type: str | None  # v1 ``appointment_raw``
    codigo_origem: str | None  # v1 ``appointment_code`` (audit)
    metadata: dict[str, Any] | None
    criado_em: datetime
    atualizado_em: datetime
    deleted_at: datetime | None


__all__ = [
    # Enums
    "UserTipo",
    "UserRegistroTipo",
    "DeliverableTipo",
    "DeliverableFrequencia",
    "ClientDeliverableStatus",
    "SessionStatus",
    "ClientOrigem",
    "ClientCreatedVia",
    # Entities
    "Organization",
    "User",
    "Deliverable",
    "Client",
    # Associations
    "ClientDeliverable",
    "ClientSession",
]
