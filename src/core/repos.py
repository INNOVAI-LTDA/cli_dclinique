"""v2 read-only repositories (Caminho B, Phase 1).

Cada ``load_*``:
  1. Le o DataFrame relevante de ``data: DataDict`` (saida de
     ``src.data_layer.load_all()``).
  2. Para entidades sintetizadas (organizations, users, deliverables
     catalog), constroi o catalogo uma vez e expoe via variavel interna.
  3. Para entidades com fonte v1 (clients, client_deliverables,
     client_sessions), itera as linhas e chama os helpers em
     ``src.core.mapping``.
  4. Filtra ``deleted_at IS NOT NULL`` (Phase 1: sempre ``None`` no v1,
     mas o pattern fica para Fase 8 quando o v2 tiver soft-delete).

N7 (exception handling): cada call externo (``data.get(...)``, ``iterrows``)
e' envolvido em try/except. Logs via ``logging.getLogger(__name__)``. Em
caso de erro de schema (coluna ausente), logamos warning e seguimos --
repos.py NUNCA propaga exception para o caller; o caller (pages Streamlit,
testes) decide o que fazer com uma lista possivelmente vazia.

N8 (experience accumulation): cada novo path code que aparece aqui gera
uma entrada em ``docs/experience_log.md`` quando falha. Phase 1 ainda
nao teve falhas; quando rolar pytest pela primeira vez, qualquer
``Exception`` nao capturada vira entrada ``failed``.

Convencoes:
  * ``organization_id=1`` e' o default -- no MAP ha' uma unica org
    (DClinique). Quando o v2 migrar para multi-tenant (Fase 8), este
    parametro vira obrigatorio.
  * Funcoes retornam ``list[T]`` vazia se a tabela correspondente esta'
    ausente de ``data`` -- nunca levantam KeyError.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

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
    ClientSession,
    Deliverable,
    Organization,
    User,
)

if TYPE_CHECKING:
    from src.core._typing import DataDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Retorna ``datetime.now()`` -- centralizado para monkeypatch em testes."""
    return datetime.now()


def _get_table(data: DataDict, name: str) -> pd.DataFrame:
    """Le uma tabela de ``data`` retornando DataFrame vazio se ausente.

    N7: loga warning (NÃO levanta) se a tabela não existe -- repos.py
    é uma fronteira read-only; schema drift deve ser visível no log
    mas não pode quebrar a página que chamou.
    """
    try:
        df = data.get(name)
    except (KeyError, AttributeError) as exc:
        logger.warning("Tabela %r ausente em data: %s", name, exc)
        return pd.DataFrame()
    if df is None:
        return pd.DataFrame()
    return df


def _filter_active(df: pd.DataFrame, deleted_col: str = "deleted_at") -> pd.DataFrame:
    """Filtra linhas com ``deleted_at`` populado.

    Phase 1: a coluna nunca existe no v1, mas mantemos o pattern para
    Fase 8 (migracao v2 com soft-delete).
    """
    if deleted_col not in df.columns:
        return df
    try:
        return df[df[deleted_col].isna()]
    except (TypeError, ValueError) as exc:
        logger.warning("Filtro deleted_at falhou: %s", exc)
        return df


# ---------------------------------------------------------------------------
# Synthesis -- entidades sem fonte v1 (1 invocacao por repos load)
# ---------------------------------------------------------------------------


def _build_organization(organization_id: int = 1) -> Organization:
    """Sintetiza a unica Organization do MAP (DClinique)."""
    return synthesize_organization(org_id=organization_id, now=_now())


def _build_user_catalog(
    data: DataDict, organization_id: int
) -> tuple[list[User], dict[str, int]]:
    """Extrai Users unicos de ``appointments.professional`` (Provider) e
    ``appointments.scheduled_by`` (Admin).

    Returns:
      * ``users``: lista de User instances (1ª aparição = id 1, depois 2, 3...)
      * ``user_id_map``: ``nome -> id`` para resolver FKs em
        ``appointment_row_to_client_session``

    Regras de tipo:
      * ``professional`` nao-vazio -> Provider
      * ``scheduled_by`` nao-vazio -> Admin
      * Se um nome aparece em ambos os campos (raro), a 1ª classificacao vence
        (Provider vem primeiro porque e' o caso comum).
    """
    appointments = _get_table(data, "appointments")
    # Dicionarios: nome -> (id, tipo, funcao) -- ordem de descoberta vence
    discovered: dict[str, tuple[int, str, str | None]] = {}
    next_id = 1
    # Fase 1: Providers de ``professional``
    for prof_name in appointments.get("professional", pd.Series(dtype=object)).dropna().unique():
        name = str(prof_name).strip()
        if not name or name in discovered:
            continue
        funcao = _guess_funcao_provider(name)
        discovered[name] = (next_id, "Provider", funcao)
        next_id += 1
    # Fase 1: Admins de ``scheduled_by``
    for admin_name in appointments.get("scheduled_by", pd.Series(dtype=object)).dropna().unique():
        name = str(admin_name).strip()
        if not name or name in discovered:
            continue
        discovered[name] = (next_id, "Admin", "Recepção")
        next_id += 1
    users = [
        synthesize_user(
            user_id=uid, nome=name, tipo=tipo, organization_id=organization_id,
            funcao=funcao, now=_now(),
        )
        for name, (uid, tipo, funcao) in discovered.items()
    ]
    user_id_map = {name: uid for name, (uid, _, _) in discovered.items()}
    return users, user_id_map


def _guess_funcao_provider(nome: str) -> str | None:
    """Heuristica: infere funcao a partir do nome do Provider.

    Phase 1: tabela conhecida vem do data_model.md §3.2 (Dayane/Deborah/
    Livia/Madalena/Elika). Para nomes nao conhecidos, retorna None.
    Quando a Fase 8 (migracao) popular o ``users.tipo_registro`` e
    ``funcao`` reais, esta heuristica sai do codigo.
    """
    known: dict[str, str] = {
        "Dayane Junqueira Vilela": "Nutróloga",
        "Deborah Daniele Ribeiro": "Enfermeira",
        "Livia Negreiro Leao": "Enfermeira",
        "Madalena Costa": "Enfermeira",
        "Elika Almeida Cunha": "Enfermeira",
    }
    return known.get(nome)


def _build_deliverable_catalog(
    data: DataDict, organization_id: int
) -> tuple[list[Deliverable], dict[str, int], dict[str, tuple[int, str | None]]]:
    """Constroi o catalogo de Deliverables a partir de:

      * ``treatment_plan_items.raw_name`` + ``category`` + ``frequency_type``
        -- o "item" do v1 vira o titulo do Deliverable.
      * ``treatment_plans.main_goal`` -- o "plano" do v1 vira um Deliverable
        adicional (tipo "Plano de Tratamento").

    Returns:
      * ``deliverables``: lista de Deliverable instances
      * ``deliverable_id_map``: ``titulo -> id`` (lowercase, accent-stripped)
      * ``plan_deliverable_info``: ``main_goal -> (deliverable_id, frequency_type)``
        (informacao adicional para ``treatment_plan_row_to_cd``)

    Dedup: o mesmo titulo (case/accent-insensitive) nao gera duplicatas.
    """
    items_df = _get_table(data, "treatment_plan_items")
    plans_df = _get_table(data, "treatment_plans")
    discovered: dict[str, int] = {}  # normalized titulo -> id
    plan_info: dict[str, tuple[int, str | None]] = {}  # main_goal -> (id, freq)
    next_id = 1

    def _norm(text: str) -> str:
        """Normaliza titulo para dedup: lowercase + sem acentos + trim."""
        import unicodedata
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(
            c for c in nfkd if not unicodedata.combining(c)
        ).lower().strip()

    # Catalogo dos itens
    for _, row in items_df.iterrows():
        raw = row.get("raw_name")
        if pd.isna(raw):
            continue
        titulo = str(raw).strip()
        if not titulo:
            continue
        key = _norm(titulo)
        if key in discovered:
            continue
        cat = row.get("category")
        cat_str = str(cat).strip() if not pd.isna(cat) else None
        freq_raw = row.get("frequency_type")
        freq_str = str(freq_raw).strip() if not pd.isna(freq_raw) else None
        # tipo/freq calculados em type_map abaixo (passo 2); aqui so' precisamos
        # do dedup. As validacoes rodam em loop separado.
        discovered[key] = next_id
        next_id += 1
        # NOTA: a instancia em si nao e' construida aqui -- lista retornada
        # no final. Mantemos so' o id aqui.

    # Catalogo dos planos (main_goal)
    for _, row in plans_df.iterrows():
        goal = row.get("main_goal")
        if pd.isna(goal):
            continue
        titulo = str(goal).strip()
        if not titulo:
            continue
        key = _norm(titulo)
        if key not in discovered:
            discovered[key] = next_id
            next_id += 1
        plan_info[titulo] = (discovered[key], None)

    # Constroi as Deliverable instances
    from src.core.mapping import _validate_frequencia, _validate_tipo
    from src.core.types import DeliverableFrequencia, DeliverableTipo
    deliverables: list[Deliverable] = []
    # Precisa re-iterar para construir os instances (com tipo/freq corretos)
    type_map: dict[str, tuple[DeliverableTipo, DeliverableFrequencia | None]] = {}
    for _, row in items_df.iterrows():
        raw = row.get("raw_name")
        if pd.isna(raw):
            continue
        titulo = str(raw).strip()
        if not titulo:
            continue
        key = _norm(titulo)
        if key in type_map:
            continue
        cat = row.get("category")
        cat_str = str(cat).strip() if not pd.isna(cat) else None
        freq_raw = row.get("frequency_type")
        freq_str = str(freq_raw).strip() if not pd.isna(freq_raw) else None
        type_map[key] = (_validate_tipo(cat_str), _validate_frequencia(freq_str))
    for _, row in plans_df.iterrows():
        goal = row.get("main_goal")
        if pd.isna(goal):
            continue
        titulo = str(goal).strip()
        if not titulo:
            continue
        key = _norm(titulo)
        if key in type_map:
            continue
        type_map[key] = ("Plano de Tratamento", None)

    deliverables = [
        synthesize_deliverable(
            deliverable_id=uid,
            titulo=titulo,
            tipo=type_map[key][0],
            organization_id=organization_id,
            frequencia_tipo=type_map[key][1],
            now=_now(),
        )
        for (titulo, key), uid in [
            ((_denorm_lookup(items_df, plans_df, k), k), v)
            for k, v in discovered.items()
        ]
    ]

    # Re-construct titulo lookup para retornar deliverable_id_map
    deliverable_id_map: dict[str, int] = {}
    for _, row in items_df.iterrows():
        raw = row.get("raw_name")
        if pd.isna(raw):
            continue
        titulo = str(raw).strip()
        if titulo:
            key = _norm(titulo)
            if key in discovered:
                deliverable_id_map[titulo] = discovered[key]
    for _, row in plans_df.iterrows():
        goal = row.get("main_goal")
        if pd.isna(goal):
            continue
        titulo = str(goal).strip()
        if titulo:
            key = _norm(titulo)
            if key in discovered:
                deliverable_id_map[titulo] = discovered[key]

    return deliverables, deliverable_id_map, plan_info


def _denorm_lookup(items_df: pd.DataFrame, plans_df: pd.DataFrame, key: str) -> str:
    """Re-encontra o titulo original (1ª ocorrencia) para a ``key`` normalizada."""
    import unicodedata
    for _, row in items_df.iterrows():
        raw = row.get("raw_name")
        if pd.isna(raw):
            continue
        titulo = str(raw).strip()
        if not titulo:
            continue
        nfkd = unicodedata.normalize("NFKD", titulo)
        n = "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
        if n == key:
            return titulo
    for _, row in plans_df.iterrows():
        goal = row.get("main_goal")
        if pd.isna(goal):
            continue
        titulo = str(goal).strip()
        if not titulo:
            continue
        nfkd = unicodedata.normalize("NFKD", titulo)
        n = "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
        if n == key:
            return titulo
    return key


# ---------------------------------------------------------------------------
# Public API -- 6 load functions
# ---------------------------------------------------------------------------


def load_organizations(data: DataDict) -> list[Organization]:
    """Retorna a unica Organization do MAP (DClinique).

    Phase 1: hard-coded (sintetizado em ``_build_organization``).
    Phase 8: le de ``data["organizations"]`` quando existir.
    """
    try:
        return [_build_organization()]
    except (KeyError, AttributeError, TypeError) as exc:
        logger.error("load_organizations falhou: %s", exc)
        return []


def load_users(data: DataDict, organization_id: int = 1) -> list[User]:
    """Extrai users (Providers + Admins) de ``appointments``.

    Phase 1: usa heuristica (nome em ``professional`` = Provider, em
    ``scheduled_by`` = Admin). Phase 8: le de ``data["users"]``.
    """
    try:
        users, _ = _build_user_catalog(data, organization_id=organization_id)
        return users
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        logger.error("load_users falhou: %s", exc)
        return []


def load_deliverables(data: DataDict, organization_id: int = 1) -> list[Deliverable]:
    """Constroi o catalogo de Deliverables a partir de ``treatment_plan_items``
    e ``treatment_plans`` (v1).

    Phase 8: le de ``data["deliverables"]`` quando existir.
    """
    try:
        deliverables, _, _ = _build_deliverable_catalog(data, organization_id=organization_id)
        return deliverables
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        logger.error("load_deliverables falhou: %s", exc)
        return []


def load_clients(data: DataDict, organization_id: int = 1) -> list[Client]:
    """Mapeia ``data["patients"]`` (v1) -> ``list[Client]`` (v2).

    Criterio de aceite (docs/caminho_b_plano.md §3 Fase 1):
      * retorna 8 instancias no mock (Phase 1 test)
      * ``.cpf`` e' None (v1 nao tem CPF)

    Filtra clientes com ``deleted_at`` populado (Phase 8 -- sempre None hoje).
    """
    df = _get_table(data, "patients")
    df = _filter_active(df, deleted_col="deleted_at")
    clients: list[Client] = []
    for _, row in df.iterrows():
        try:
            client = patient_row_to_client(row)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("patient_row_to_client falhou: %s; linha pulada", exc)
            continue
        clients.append(client)
    return clients


def load_client_deliverables(
    data: DataDict, organization_id: int = 1
) -> list[ClientDeliverable]:
    """Mapeia ``treatment_plans`` + ``treatment_plan_items`` (v1) ->
    ``list[ClientDeliverable]`` (v2).

    Planos vem primeiro (parent_client_deliverable_id=None); itens vem
    depois (parent_client_deliverable_id = id do Plano pai). Items orfaos
    (plano pai nao sintetizado) sao descartados com warning.
    """
    _, deliverable_id_map, plan_info = _build_deliverable_catalog(
        data, organization_id=organization_id
    )
    plans_df = _get_table(data, "treatment_plans")
    plans_df = _filter_active(plans_df, deleted_col="deleted_at")
    items_df = _get_table(data, "treatment_plan_items")
    items_df = _filter_active(items_df, deleted_col="deleted_at")

    # Fase 1: Planos (sintetizados primeiro para popular plan_id_map)
    plan_id_map: dict[str, int] = {}  # plan_id v1 -> ClientDeliverable id (==plan_id_int)
    cds: list[ClientDeliverable] = []
    for _, row in plans_df.iterrows():
        try:
            cd = treatment_plan_row_to_cd(
                row, deliverable_id_map, organization_id, now=_now()
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("treatment_plan_row_to_cd falhou: %s", exc)
            continue
        if cd is None:
            continue
        cds.append(cd)
        # Guarda o mapeamento plan_id v1 -> ClientDeliverable id
        from src.core.mapping import _safe_str
        plan_id_v1 = _safe_str(row.get("plan_id"))
        if plan_id_v1:
            plan_id_map[plan_id_v1] = cd.id

    # Fase 1: Itens
    for _, row in items_df.iterrows():
        try:
            cd = treatment_plan_item_row_to_cd(
                row, deliverable_id_map, plan_id_map, organization_id, now=_now()
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("treatment_plan_item_row_to_cd falhou: %s", exc)
            continue
        if cd is None:
            continue
        cds.append(cd)
    return cds


def load_client_sessions(
    data: DataDict, organization_id: int = 1
) -> list[ClientSession]:
    """Mapeia ``data["appointments"]`` (v1) -> ``list[ClientSession]`` (v2).

    Sessions sem ``professional`` valido sao descartadas (warning).
    """
    _, user_id_map = _build_user_catalog(data, organization_id=organization_id)
    df = _get_table(data, "appointments")
    df = _filter_active(df, deleted_col="deleted_at")
    sessions: list[ClientSession] = []
    for _, row in df.iterrows():
        try:
            cs = appointment_row_to_client_session(
                row, user_id_map, organization_id, now=_now()
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("appointment_row_to_client_session falhou: %s", exc)
            continue
        if cs is None:
            continue
        sessions.append(cs)
    return sessions


__all__ = [
    "load_organizations",
    "load_users",
    "load_deliverables",
    "load_clients",
    "load_client_deliverables",
    "load_client_sessions",
]
