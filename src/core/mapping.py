"""v1 row → v2 dataclass mapping helpers (Caminho B, Phase 1).

The v1 schema (11 tables in ``src/schemas.py:EXPECTED_SCHEMAS``) is procedural:
``patients``, ``treatment_plans``, ``treatment_plan_items``, ``appointments``
etc. carry the data needed to build the v2 entity/association model, but the
column names and the lifecycle (no ``deleted_at``, no ``criado_em``) do not
match 1:1. This module is the translation layer:

* **Constants** (e.g., ``PATIENT_TO_CLIENT``) document the column rename in
  one place. Read them before adding a new column.
* **Row-level helpers** (e.g., ``patient_row_to_client``) take a
  ``pd.Series`` and return the v2 dataclass. They NEVER raise on missing
  optional columns -- N7: all errors are caught and translated to
  ``None``/default values; the caller (``repos.py``) is responsible for
  raising if a required field is missing.
* **Synthesis helpers** (e.g., ``synthesize_organization``) build v2
  entities that have no v1 source (organizations, the users catalog, the
  deliverables catalog). These run once per ``load_*`` call.

N7 (exception handling):
  * Every call to a lib that can raise (pd.to_numeric, pd.to_datetime,
    pd.isna) is wrapped in try/except. See ``docs/exception_catalog.md``
    §1 (pandas) and §3 (datetime) for the canonical patterns.
  * The helpers log via ``logging.getLogger(__name__)`` -- never ``print``
    (criterion de aceite global §3 item 4).
  * On any error, the helper returns the dataclass with sensible defaults
    (``None`` for optional, default for required) -- repos.py will see the
    partial record and decide whether to filter or surface.

N8 (experience accumulation): every row-level helper that "soft-handles" a
missing or malformed column must be accompanied by a smoke test in
``tests/test_core_types.py`` -- if the test fails, the helper has a bug.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

from src.core.types import (
    Client,
    ClientDeliverable,
    ClientDeliverableStatus,
    ClientSession,
    Deliverable,
    DeliverableFrequencia,
    DeliverableTipo,
    Organization,
    SessionStatus,
    User,
    UserTipo,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeamentos de coluna (documentam o rename v1 -> v2 num lugar so')
# ---------------------------------------------------------------------------

#: ``patients`` (v1) -> ``Client`` (v2). Colunas ausentes em v1 ficam None.
PATIENT_TO_CLIENT: dict[str, str] = {
    "patient_id": "id",
    "name": "nome",
    "phone": "telefone",
    # 'medical_record' -> 'observacoes' (prefixo "prontuario:") em Phase 1.
    # 'cpf', 'rg', 'data_nascimento' nao existem em v1.
    "created_at": "criado_em",
}

#: ``treatment_plans`` (v1) -> ``ClientDeliverable`` (v2, papel=Plano)
TREATMENT_PLAN_TO_CD: dict[str, str] = {
    "plan_id": "id",
    "patient_id": "client_id",
    "budget_code": "orcamento",
    "start_date": "data_inicio",
    "end_date": "data_fim",
    "is_renewal": "is_renovacao",
}

#: ``treatment_plan_items`` (v1) -> ``ClientDeliverable`` (v2, papel=Item)
TREATMENT_PLAN_ITEM_TO_CD: dict[str, str] = {
    "plan_item_id": "id",
    "patient_id": "client_id",
    "plan_id": "parent_client_deliverable_id",  # resolvido via plan_id_map
    "budget_code": "orcamento",
    "sessions_expected": "sessions_expected",
}

#: ``appointments`` (v1) -> ``ClientSession`` (v2)
APPOINTMENT_TO_CS: dict[str, str] = {
    "appointment_id": "id",
    "patient_id": "client_id",
    "appointment_start": "session_start",
    "appointment_end": "session_end",
    "appointment_code": "codigo_origem",
}

# ---------------------------------------------------------------------------
# Helpers de coerce -- N7: try/except especifico + log
# ---------------------------------------------------------------------------


def _safe_str(value: Any, default: str | None = None) -> str | None:  # noqa: ANN401
    """Coerce to ``str`` returning ``default`` on None/NaN/NA.

    Treats ``None``, ``float('nan')``, and ``pd.NA`` as "no value". Empty
    strings (after ``strip()``) are also returned as ``default`` (None)
    so downstream code can rely on "string = non-empty".
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        # pd.isna raises on some custom types -- treat as "no value"
        return default
    text = str(value).strip()
    return text if text else default


def _safe_int(value: Any, default: int | None = None) -> int | None:  # noqa: ANN401
    """Coerce to ``int`` via ``pd.to_numeric(..., errors="coerce")``.

    Returns ``default`` on NaN/NA. Raises ``ValueError`` ONLY if the input
    is non-numeric and not coercible -- but ``errors="coerce"`` turns
    *all* non-numeric into NaN, so this is defensive.
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        return default
    try:
        coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    except (ValueError, TypeError) as exc:
        logger.warning("Coerce int falhou para %r: %s", value, exc)
        return default
    if pd.isna(coerced):
        return default
    return int(coerced)


def _safe_bool(value: Any, default: bool = False) -> bool:  # noqa: ANN401
    """Coerce to ``bool``.

    Treats the string "true"/"false"/"1"/"0"/"yes"/"no" (case-insensitive)
    as their bool equivalents. Other inputs fall back to ``default``.
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "sim", "y", "s"):
        return True
    if text in ("false", "0", "no", "não", "nao", "n"):
        return False
    return default


def _safe_date(value: Any) -> date | None:  # noqa: ANN401
    """Coerce to ``datetime.date`` via ``pd.to_datetime(..., errors="coerce")``.

    Returns ``None`` on NaT/NaN/missing. Logs a warning if the value is a
    string that doesn't parse (defensive -- shouldn't happen with
    ``errors="coerce"`` but useful for telemetry).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        ts = pd.to_datetime(pd.Series([value]), errors="coerce").iloc[0]
    except (ValueError, TypeError) as exc:
        logger.warning("Coerce date falhou para %r: %s", value, exc)
        return None
    if pd.isna(ts):
        return None
    return ts.date()


def _safe_datetime(value: Any) -> datetime | None:  # noqa: ANN401
    """Coerce to ``datetime.datetime`` via ``pd.to_datetime``.

    Same contract as ``_safe_date`` but preserves the time component.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        ts = pd.to_datetime(pd.Series([value]), errors="coerce").iloc[0]
    except (ValueError, TypeError) as exc:
        logger.warning("Coerce datetime falhou para %r: %s", value, exc)
        return None
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def _safe_id_from_string(value: Any) -> int | None:  # noqa: ANN401
    """Extrai o sufixo numerico de um id v1 no formato ``<prefix>_<int>``.

    v1 usa surrogate keys textuais (ex.: ``pat_001``, ``plan_002``,
    ``item_003``, ``wgt_004``) -- o v2 quer ``int``. Extraimos o ultimo
    segmento apos underscore; se for numerico, retornamos como int. Se o
    valor ja' e' numerico, retornamos direto. Caso contrario, None.

    Exemplos:
      * ``"pat_001"`` -> 1
      * ``"plan_42"`` -> 42
      * ``"pat_new_007"`` -> 7  (multi-segmento, pega o ultimo)
      * ``123`` -> 123
      * ``"abc"`` -> None
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    # Tenta parse direto (caso seja "123" sem prefixo)
    try:
        return int(text)
    except ValueError:
        pass
    # Caso "<prefix>_<int>" -- pega o ultimo segmento
    if "_" in text:
        last = text.rsplit("_", 1)[-1]
        try:
            return int(last)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Helpers de validacao -- runtime checks para Literal
# ---------------------------------------------------------------------------

#: ``deliverables.tipo`` validos. Subset do ``DeliverableTipo`` Literal
#: que aparece no v1 mock (v1 nao tem todos os tipos). Fuzz-match em
#: ``category`` do v1 para atribuir um tipo.
_KNOWN_TIPOS: set[str] = {
    "Plano de Tratamento",
    "Injetável",
    "Medicamento Manipulado",
    "Implante",
    "Consulta",
    "Acompanhamento",
    "Exame",
    "Meta",
}

#: Mapeamento de ``treatment_plan_items.category`` (v1) para
#: ``deliverables.tipo`` (v2). Valores nao mapeados caem em
#: "Acompanhamento" como default.
#:
#: Nota: 'EV' = "Endovenoso" (atalho do v1 para "Injetável EV"). Strings
#: em mojibake (cp1252 lido como utf-8) ainda matcham via fuzzy.
_CATEGORY_TO_TIPO: dict[str, DeliverableTipo] = {
    "Injetáveis": "Injetável",
    "Injetável": "Injetável",
    "Injetavel": "Injetável",
    "EV": "Injetável",
    "Medicamento": "Medicamento Manipulado",
    "Medicamento manipulado": "Medicamento Manipulado",
    "Medicamento Manipulado": "Medicamento Manipulado",
    "Implante": "Implante",
    "Consulta": "Consulta",
    "Acompanhamento": "Acompanhamento",
    "Acompanhamento profissional": "Acompanhamento",
    "Exame": "Exame",
    "Meta": "Meta",
}

#: ``client_deliverables.status`` validos
_KNOWN_CD_STATUSES: set[str] = {
    "Ativo", "Pausado", "Aguardando", "Finalizado", "Cancelado", "Não iniciado",
}

#: ``client_sessions.status`` validos
_KNOWN_SESSION_STATUSES: set[str] = {
    "Agendado", "Confirmado", "Atendido", "Atrasado", "Cancelado", "Reagendado",
}

#: ``frequency_type`` validos do v1 ``treatment_plan_items.frequency_type``
_KNOWN_FREQUENCIA: set[str] = {
    "Diário", "Semanal", "Quinzenal", "Mensal", "Única", "Outro",
}


def _validate_tipo(value: str | None) -> DeliverableTipo:
    """Coerce ``value`` to a known ``DeliverableTipo``; default ``Acompanhamento``.

    Phase 1 only sees v1 ``category`` strings, which may not match a
    v2 tipo exactly. The mapping in ``_CATEGORY_TO_TIPO`` handles
    exact + case/accent-insensitive matches; everything else falls
    back to "Acompanhamento" (the most generic tipo).
    """
    if not value:
        return "Acompanhamento"
    # Match 1: exact (case + accent sensitive)
    mapped = _CATEGORY_TO_TIPO.get(value)
    if mapped is not None:
        return mapped
    # Match 2: case + accent-insensitive equality
    norm_input = _strip_accents(value).lower()
    for key, tipo in _CATEGORY_TO_TIPO.items():
        if _strip_accents(key).lower() == norm_input:
            return tipo
    # Match 3: substring ("Acompanhamento profissional" -> "Acompanhamento")
    for key, tipo in _CATEGORY_TO_TIPO.items():
        n_key = _strip_accents(key).lower()
        if n_key in norm_input:
            return tipo
    logger.warning("Tipo de deliverable nao mapeado: %r -> Acompanhamento", value)
    return "Acompanhamento"


def _validate_cd_status(value: str | None) -> ClientDeliverableStatus:
    """Coerce ``value`` to a known ``ClientDeliverableStatus``; default ``Ativo``."""
    if not value:
        return "Ativo"
    if value in _KNOWN_CD_STATUSES:
        return value  # type: ignore[return-value]
    norm = _strip_accents(value).lower()
    for known in _KNOWN_CD_STATUSES:
        if _strip_accents(known).lower() == norm:
            return known  # type: ignore[return-value]
    logger.warning("Status de client_deliverable nao mapeado: %r -> Ativo", value)
    return "Ativo"


def _validate_session_status(value: str | None) -> SessionStatus:
    """Coerce ``value`` to a known ``SessionStatus``; default ``Agendado``."""
    if not value:
        return "Agendado"
    if value in _KNOWN_SESSION_STATUSES:
        return value  # type: ignore[return-value]
    norm = _strip_accents(value).lower()
    for known in _KNOWN_SESSION_STATUSES:
        if _strip_accents(known).lower() == norm:
            return known  # type: ignore[return-value]
    logger.warning("Status de sessao nao mapeado: %r -> Agendado", value)
    return "Agendado"


def _validate_frequencia(value: str | None) -> DeliverableFrequencia | None:
    """Coerce ``value`` to a known ``DeliverableFrequencia``; default None."""
    if not value:
        return None
    if value in _KNOWN_FREQUENCIA:
        return value  # type: ignore[return-value]
    norm = _strip_accents(value).lower()
    for known in _KNOWN_FREQUENCIA:
        if _strip_accents(known).lower() == norm:
            return known  # type: ignore[return-value]
    logger.warning("Frequencia nao mapeada: %r -> None", value)
    return None


#: Strip diacritics (acentos) -- util para fuzzy match de strings PT-BR
#: que o v1 pode ter com encoding inconsistente.
def _strip_accents(text: str) -> str:
    """Remove acentos via decomposicao Unicode (NFKD)."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


# ---------------------------------------------------------------------------
# Row-level helpers -- uma linha v1 -> uma instancia v2
# ---------------------------------------------------------------------------


def patient_row_to_client(row: pd.Series) -> Client:
    """Mapeia uma linha de ``patients`` (v1) para ``Client`` (v2).

    Lacunas conhecidas do v1 mock (campos opcionais em v2):
      * ``cpf`` = None (coluna nao existe em v1)
      * ``rg`` = None
      * ``data_nascimento`` = None (``age`` -> ``observacoes``)
      * ``endereco`` = None
      * ``email`` = None
      * ``origem`` = None
      * ``consentimento_lgpd`` = False (gate do DEPLOY.md, default seguro)
      * ``consentimento_lgpd_em`` = None
    """
    pid = _safe_id_from_string(row.get("patient_id"))
    nome = _safe_str(row.get("name"), default="") or ""
    phone = _safe_str(row.get("phone"))
    age = _safe_int(row.get("age"))
    medical_record = _safe_str(row.get("medical_record"))
    created = _safe_datetime(row.get("created_at")) or datetime.now()
    obs_parts: list[str] = []
    if medical_record:
        obs_parts.append(f"prontuario: {medical_record}")
    if age is not None:
        obs_parts.append(f"idade: {age}")
    observacoes = "; ".join(obs_parts) if obs_parts else None
    return Client(
        id=pid if pid is not None else 0,
        nome=nome,
        cpf=None,  # v1 mock nao tem CPF
        rg=None,
        data_nascimento=None,  # v1 so' tem age; data virá do PDF na Fase 6
        telefone=phone,
        endereco=None,
        email=None,
        origem=None,  # v1 nao rastreia origem
        consentimento_lgpd=False,  # gate LGPD: default seguro ate' consentimento
        consentimento_lgpd_em=None,
        observacoes=observacoes,
        created_via="manual",  # v1 foi seed manual em mock_data.py
        ativo=True,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


def treatment_plan_row_to_cd(
    row: pd.Series,
    deliverable_id_map: dict[str, int],
    organization_id: int,
    *,
    now: datetime | None = None,
) -> ClientDeliverable | None:
    """Mapeia uma linha de ``treatment_plans`` (v1) para ``ClientDeliverable`` (Plano).

    Returns ``None`` se a linha nao tem ``plan_id`` (linha malformada) ou se
    o ``raw_name`` nao tem um deliverable sintetizado -- o caller (repos.py)
    filtra ``None``.
    """
    plan_id = _safe_str(row.get("plan_id"))
    if not plan_id:
        return None
    plan_id_int = _safe_id_from_string(plan_id) or 0
    patient_id = _safe_id_from_string(row.get("patient_id")) or 0
    raw_name = _safe_str(row.get("main_goal")) or f"Plano {plan_id}"
    deliverable_id = deliverable_id_map.get(raw_name)
    if deliverable_id is None:
        # Sem catalogo -- nao podemos sintetizar ClientDeliverable sem FK valida
        logger.warning("Plano %s sem deliverable sintetizado: main_goal=%r", plan_id, raw_name)
        return None
    status = _validate_cd_status(_safe_str(row.get("status")))
    sessions_expected = _safe_int(row.get("sessions_expected"), default=0) or 0
    is_renovacao = _safe_bool(row.get("is_renewal"), default=False)
    data_inicio = _safe_date(row.get("start_date"))
    data_fim = _safe_date(row.get("end_date"))
    created = _safe_datetime(row.get("issue_date")) or (now or datetime.now())
    return ClientDeliverable(
        id=plan_id_int,
        client_id=patient_id,
        deliverable_id=deliverable_id,
        parent_client_deliverable_id=None,  # Plano nao tem parent
        organization_id=organization_id,
        status=status,
        orcamento=_safe_str(row.get("budget_code")),
        is_renovacao=is_renovacao,
        data_inicio=data_inicio,
        data_fim=data_fim,
        sessions_expected=sessions_expected,
        sessions_completed=0,  # v1 plans nao tem completed (vem de execution_summary)
        sessions_remaining=sessions_expected,
        metadata=None,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


def treatment_plan_item_row_to_cd(
    row: pd.Series,
    deliverable_id_map: dict[str, int],
    plan_id_map: dict[str, int],
    organization_id: int,
    *,
    now: datetime | None = None,
) -> ClientDeliverable | None:
    """Mapeia uma linha de ``treatment_plan_items`` (v1) para ``ClientDeliverable`` (Item).

    O ``parent_client_deliverable_id`` e' resolvido via ``plan_id_map`` (que
    mapeia ``plan_id`` v1 -> id do ClientDeliverable Plano sintetizado).
    Se o plano pai nao foi sintetizado, este item e' orfao e retornamos None.
    """
    item_id = _safe_str(row.get("plan_item_id"))
    if not item_id:
        return None
    item_id_int = _safe_id_from_string(item_id) or 0
    patient_id = _safe_id_from_string(row.get("patient_id")) or 0
    plan_id_v1 = _safe_str(row.get("plan_id"))
    parent_id = plan_id_map.get(plan_id_v1) if plan_id_v1 else None
    if parent_id is None:
        logger.warning(
            "Item %s sem plano pai sintetizado: plan_id=%r",
            item_id, plan_id_v1,
        )
        return None
    raw_name = _safe_str(row.get("raw_name")) or f"Item {item_id}"
    deliverable_id = deliverable_id_map.get(raw_name)
    if deliverable_id is None:
        logger.warning("Item %s sem deliverable sintetizado: raw_name=%r", item_id, raw_name)
        return None
    sessions_expected = _safe_int(row.get("sessions_expected"), default=0) or 0
    sessions_completed = _safe_int(row.get("sessions_completed"), default=0) or 0
    sessions_remaining = max(0, sessions_expected - sessions_completed)
    created = now or datetime.now()
    return ClientDeliverable(
        id=item_id_int,
        client_id=patient_id,
        deliverable_id=deliverable_id,
        parent_client_deliverable_id=parent_id,
        organization_id=organization_id,
        status="Ativo",  # items em v1 nao tem status proprio -- herdam do plano
        orcamento=_safe_str(row.get("budget_code")),
        is_renovacao=False,
        data_inicio=None,
        data_fim=None,
        sessions_expected=sessions_expected,
        sessions_completed=sessions_completed,
        sessions_remaining=sessions_remaining,
        metadata=None,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


def appointment_row_to_client_session(
    row: pd.Series,
    user_id_map: dict[str, int],
    organization_id: int,
    *,
    now: datetime | None = None,
) -> ClientSession | None:
    """Mapeia uma linha de ``appointments`` (v1) para ``ClientSession`` (v2).

    ``professional`` (string) e' resolvido via ``user_id_map`` para ``provider_id``.
    ``scheduled_by`` (string, pode ser vazio) e' resolvido para ``agendado_por_id``
    (None se vazio ou nao mapeado).
    """
    appt_id = _safe_str(row.get("appointment_id"))
    if not appt_id:
        return None
    appt_id_int = _safe_id_from_string(appt_id) or 0
    patient_id = _safe_id_from_string(row.get("patient_id")) or 0
    professional = _safe_str(row.get("professional"))
    if not professional:
        logger.warning("Appointment %s sem professional; pulando", appt_id)
        return None
    provider_id = user_id_map.get(professional)
    if provider_id is None:
        logger.warning(
            "Appointment %s: professional %r nao encontrado em user_id_map",
            appt_id, professional,
        )
        return None
    scheduled_by_name = _safe_str(row.get("scheduled_by"))
    agendado_por_id = (
        user_id_map.get(scheduled_by_name) if scheduled_by_name else None
    )
    status = _validate_session_status(_safe_str(row.get("status")))
    session_start = _safe_datetime(row.get("appointment_start")) or (now or datetime.now())
    session_end = _safe_datetime(row.get("appointment_end")) or session_start
    created = session_start
    return ClientSession(
        id=appt_id_int,
        client_id=patient_id,
        provider_id=provider_id,
        agendado_por_id=agendado_por_id,
        organization_id=organization_id,
        session_start=session_start,
        session_end=session_end,
        status=status,
        session_type=_safe_str(row.get("appointment_raw")),
        codigo_origem=_safe_str(row.get("appointment_code")),
        metadata=None,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


# ---------------------------------------------------------------------------
# Synthesis helpers -- entidades sem fonte v1
# ---------------------------------------------------------------------------


def synthesize_organization(
    *,
    org_id: int = 1,
    nome: str = "DClinique",
    now: datetime | None = None,
) -> Organization:
    """Sintetiza a unica Organization do MAP (data_model.md §3.1).

    Phase 1 retorna um unico registro hard-coded. Phase 8 (migracao v2)
    substituira esta sintese por leitura da tabela ``organizations``.
    """
    created = now or datetime.now()
    return Organization(
        id=org_id,
        nome=nome,
        cnpj=None,  # v1 nao tem CNPJ
        endereco=None,
        telefone=None,
        url=None,
        config={"timezone": "America/Sao_Paulo", "idioma": "pt-BR"},
        ativo=True,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


def synthesize_user(
    *,
    user_id: int,
    nome: str,
    tipo: UserTipo,
    organization_id: int,
    funcao: str | None = None,
    now: datetime | None = None,
) -> User:
    """Sintetiza um User a partir de um nome v1 (sem cpf/registro)."""
    created = now or datetime.now()
    return User(
        id=user_id,
        tipo=tipo,
        nome=nome,
        cpf=None,
        registro_especial=None,
        tipo_registro=None,
        telefone=None,
        email=None,
        funcao=funcao,
        organization_id=organization_id,
        ativo=True,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


def synthesize_deliverable(
    *,
    deliverable_id: int,
    titulo: str,
    tipo: DeliverableTipo,
    organization_id: int,
    descricao: str = "",
    parent_deliverable_id: int | None = None,
    frequencia_tipo: DeliverableFrequencia | None = None,
    frequencia_texto: str | None = None,
    now: datetime | None = None,
) -> Deliverable:
    """Sintetiza um Deliverable (catalogo) a partir de um raw_name v1.

    Phase 1: ``parent_deliverable_id`` fica None (v1 nao tem hierarquia
    explicita). Phase 8: data de migracao podera popular com FK real.
    """
    created = now or datetime.now()
    return Deliverable(
        id=deliverable_id,
        titulo=titulo,
        tipo=tipo,
        descricao=descricao,
        parent_deliverable_id=parent_deliverable_id,
        organization_id=organization_id,
        frequencia_tipo=frequencia_tipo,
        frequencia_texto=frequencia_texto,
        metadata=None,
        ativo=True,
        criado_em=created,
        atualizado_em=created,
        deleted_at=None,
    )


__all__ = [
    # Mappings
    "PATIENT_TO_CLIENT",
    "TREATMENT_PLAN_TO_CD",
    "TREATMENT_PLAN_ITEM_TO_CD",
    "APPOINTMENT_TO_CS",
    # Row-level helpers
    "patient_row_to_client",
    "treatment_plan_row_to_cd",
    "treatment_plan_item_row_to_cd",
    "appointment_row_to_client_session",
    # Synthesis helpers
    "synthesize_organization",
    "synthesize_user",
    "synthesize_deliverable",
]
