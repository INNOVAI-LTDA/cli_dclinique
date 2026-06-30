"""Frequency-based alert detection (Caminho B, Phase 3).

Motivacao (relatorio cliente 2026-06-23):
  A regra "comparecimento < 70% E >= 2 faltas consecutivas -> alerta
  Alta/Media" vira **funcao deterministica** que respeita
  ``deliverable.frequencia_tipo`` do catalogo. Este modulo expoe
  :func:`detect_frequency_alerts` que percorre os
  :class:`~src.core.types.ClientDeliverable` ativos e emite alertas
  (Alta/Media) baseando-se em
  :func:`~src.core.frequency.attendance_rate` e
  :func:`~src.core.frequency.max_consecutive_missed`.

Forma dos alertas:
  Cada alerta e' um ``dict`` com a shape esperada pela tabela ``alerts``
  v1 (ver ``src/schemas.py:EXPECTED_SCHEMAS['alerts']``). A dataclass
  v2 ``Alert`` ainda NAO existe -- ela vir'a na Fase 8 (cutover) quando
  alerta virar entidade de primeira classe no modelo. Por enquanto,
  dict e' suficiente para persistencia + leitura pela UI.

N7 (exception handling) -- **FUNCAO PURA** (N7 E5):
  :func:`detect_frequency_alerts` NAO captura excecoes internamente;
  erros de tipo (``as_of=None``, ``cd.client_id <= 0``) sao deixados
  subir como ``TypeError`` / ``ValueError`` para o chamador decidir.
  Persistencia (write) e' responsabilidade de
  :mod:`src.core.persistence` (boundary function -- N7 E6).

Idempotencia:
  ``_make_alert`` gera ``alert_id`` deterministico
  (``freq_{client_id}_{cd_id}_{priority.lower()}``) -- o que permite
  :func:`src.core.persistence.save_frequency_alerts` deduplicar antes
  de inserir (roda o mesmo calculo 2x -> nao duplica linhas).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.core.frequency import (
    _to_date,
    attendance_rate,
    expected_sessions,
    max_consecutive_missed,
)
from src.core.mapping import _strip_accents
from src.core.types import ClientDeliverable, ClientSession, Deliverable

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Limiares para geracao de alertas de frequencia.

    Atributos:
      consecutive_missed_alta: minimo de sessões consecutivas NAO atendidas
        para emitir alerta Alta. Default 2 (regra do relatorio cliente 2026-06-23).
      attendance_rate_media: taxa maxima de comparecimento (inclusive) abaixo
        da qual um alerta Media e' emitido. Default 0.70 (70%).
      no_sessions_alta_days: dias (inclusive) desde a ultima sessao atendida
        para emitir alerta Alta. Default 30 (caso "Jaqueline" -- paciente
        sem sessões no ciclo).
      min_expected_for_rate_alert: minimo de sessões esperadas (inclusive)
        para considerar o ratio de comparecimento significativo. Default 3
        (abaixo disso, 1 falta ja' e' > 30% e gera muito ruido).
    """

    consecutive_missed_alta: int = 2
    attendance_rate_media: float = 0.70
    no_sessions_alta_days: int = 30
    min_expected_for_rate_alert: int = 3


#: Singleton usado em runtime -- todos os alertas comparam contra estes
#: valores. ``frozen=True`` impede mutacao acidental.
THRESHOLDS: Thresholds = Thresholds()


# ---------------------------------------------------------------------------
# detect_frequency_alerts -- API publica
# ---------------------------------------------------------------------------


def detect_frequency_alerts(
    client_deliverables: list[ClientDeliverable],
    deliverables: list[Deliverable],
    sessions: list[ClientSession],
    as_of: date,
    *,
    thresholds: Thresholds = THRESHOLDS,
) -> list[dict]:
    """Detecta alertas de frequencia para os ``client_deliverables``.

    Algoritmo (caminho_b_plano.md §3 Fase 3 + relatorio cliente 2026-06-23):
      Para cada ``cd`` que:
        (a) NAO e' plano-pai (``cd.parent_client_deliverable_id is not None``)
            -- apenas ITENS disparam alerta (plano-pai e' agregado, nao
            acionavel diretamente).
        (b) Tem status "Ativo" ou "Aguardando" -- "Pausado", "Cancelado",
            "Finalizado", "Nao iniciado" NAO disparam.
        (c) Tem ``deliverable`` correspondente no catalogo.

      Aplica 3 checks:
        1. ``max_consecutive_missed(cd, sessions) >= consecutive_missed_alta``
           -> alerta Alta ("N sessões consecutivas nao atendidas").
        2. ``expected_sessions(cd, d, as_of) >= min_expected_for_rate_alerta``
           AND ``attendance_rate(cd, d, sessions, as_of) < attendance_rate_media``
           -> alerta Media ("Comparecimento de X% no ciclo").
        3. ``_days_since_last_session(cd, sessions, as_of) >= no_sessions_alta_days``
           -> alerta Alta ("Sem sessões ha' N dias").

    Args:
        client_deliverables: lista de ClientDeliverable (Phase 1 schema).
        deliverables: catalogo de Deliverable (Phase 1 schema).
        sessions: lista de ClientSession (Phase 1 schema).
        as_of: data de referencia para o calculo (parametro para pureza).
        thresholds: override opcional dos THRESHOLDS (uso de teste).

    Returns:
        Lista de dicts com a shape de ``alerts.csv``. Pode ser vazia
        (nenhum alerta detectado). NAO inclui duplicatas -- cada alerta
        e' uma entrada unica por ``(cd, priority)``.

    Raises:
        TypeError: se ``as_of`` nao for ``date`` (via ``_to_date`` /
            comparacao).
        ValueError: se algum ``cd.client_id <= 0`` ou ``cd.id <= 0``
            (id invalido -> alert_id nao deterministico).
    """
    if not isinstance(as_of, date):
        raise TypeError(
            f"as_of deve ser date, recebeu: {type(as_of).__name__}"
        )

    # Indexa deliverables por id (lookup O(1) por cd em vez de O(N))
    deliverables_by_id = {d.id: d for d in deliverables}

    alerts: list[dict] = []
    for cd in client_deliverables:
        # Filtro (a): apenas ITENS, nao plano-pai.
        if cd.parent_client_deliverable_id is None:
            continue
        # Filtro (b): status ativo ou aguardando.
        if cd.status not in ("Ativo", "Aguardando"):
            continue
        # Filtro (c): deliverable existe no catalogo.
        d = deliverables_by_id.get(cd.deliverable_id)
        if d is None:
            continue
        # Sanidade: cd.id e cd.client_id devem ser positivos.
        if cd.id <= 0 or cd.client_id <= 0:
            raise ValueError(
                f"ClientDeliverable sem id valido para gerar alerta: "
                f"client_id={cd.client_id}, cd_id={cd.id}. "
                f"Verifique o mapeamento em repos.py."
            )

        # Check 1: max_consecutive_missed >= threshold.
        consecutive = max_consecutive_missed(cd, sessions)
        if consecutive >= thresholds.consecutive_missed_alta:
            alerts.append(_make_alert(
                cd, "Alta",
                f"{consecutive} sessões consecutivas nao atendidas",
                as_of,
            ))

        # Check 2: attendance_rate < threshold (so' se expected >= min).
        expected = expected_sessions(cd, d, as_of)
        if expected >= thresholds.min_expected_for_rate_alert:
            rate = attendance_rate(cd, d, sessions, as_of)
            if rate < thresholds.attendance_rate_media:
                alerts.append(_make_alert(
                    cd, "Média",
                    f"Comparecimento de {rate:.0%} no ciclo",
                    as_of,
                ))

        # Check 3: days_since_last_session >= threshold.
        days_since = _days_since_last_session(cd, sessions, as_of)
        if days_since is not None and days_since >= thresholds.no_sessions_alta_days:
            alerts.append(_make_alert(
                cd, "Alta",
                f"Sem sessões ha' {days_since} dias",
                as_of,
            ))

    return alerts


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _make_alert(
    cd: ClientDeliverable,
    priority: str,
    description: str,
    as_of: date,
) -> dict:
    """Constroi um dict de alerta com a shape esperada por ``alerts.csv``.

    Args:
        cd: ClientDeliverable que disparou o alerta.
        priority: "Alta" ou "Media".
        description: texto PT-BR legivel ao usuario.
        as_of: data de referencia (vira ``created_at``).

    Returns:
        Dict com chaves: ``alert_id``, ``patient_id``, ``plan_id``,
        ``category``, ``alert_type``, ``description``, ``priority``,
        ``status``, ``created_at``, ``comment``.

    Schema ref: ``src/schemas.py:EXPECTED_SCHEMAS['alerts']``.

    Note:
        ``alert_id`` e' deterministico:
        ``f"freq_{cd.client_id}_{cd.id}_{priority.lower()}"``. Isso
        permite que :func:`src.core.persistence.save_frequency_alerts`
        deduplique antes de inserir (idempotencia).
    """
    return {
        # alert_id e' ASCII-safe (sem acento) para evitar encoding issues
        # no CSV. ``_strip_accents`` converte "Média" -> "Media".
        "alert_id": (
            f"freq_{cd.client_id}_{cd.id}_"
            f"{_strip_accents(priority).lower()}"
        ),
        # v1 naming convention (pat_NNN). Phase 8 (cutover) trocara'
        # para a chave natural do v2.
        "patient_id": f"pat_{cd.client_id:03d}",
        # Para ITENS: o plan_id e' o parent_client_deliverable_id
        # (plano-pai). Para PLANOS: usa o cd.id (so' acontece se a
        # logica evoluir para gerar alertas em planos tambem).
        "plan_id": (
            f"plan_{cd.parent_client_deliverable_id}"
            if cd.parent_client_deliverable_id is not None
            else f"plan_{cd.id}"
        ),
        "category": "Frequência",  # Nova categoria da Fase 5 (alertas.py)
        "alert_type": priority,    # "Alta" ou "Média"
        "description": description,
        "priority": priority,
        "status": "Aberto",        # Default para alertas novos
        "created_at": as_of.isoformat(),
        "comment": "",
    }


def _days_since_last_session(
    cd: ClientDeliverable,
    sessions: list[ClientSession],
    as_of: date,
) -> int | None:
    """Dias desde a ultima sessao do cliente (Atendido ou nao) ate ``as_of``.

    Args:
        cd: ClientDeliverable usado para identificar o cliente
            (``cd.client_id``).
        sessions: lista de ClientSession (filtra internamente).
        as_of: data de referencia.

    Returns:
        Numero inteiro >= 0 se ha' sessões para o cliente;
        ``None`` se nao ha' sessões (caso "sem historico").

    Note:
        Considera TODAS as sessões (nao apenas "Atendido") -- uma sessao
        "Cancelado" conta como "houve interacao com o cliente". Se
        quisessemos apenas Atendido, o filtro seria:
        ``s.status == "Atendido"``. Decisao de design: a regra do
        relatorio e' "30+ dias SEM sessao", o que inclui cancelamentos
        -- se o cliente cancelou, ele NAO compareceu.
    """
    relevant = sorted(
        (s for s in sessions if s.client_id == cd.client_id),
        key=lambda s: _to_date(s.session_start),
    )
    if not relevant:
        return None
    last_date = _to_date(relevant[-1].session_start)
    return (as_of - last_date).days


__all__ = [
    "Thresholds",
    "THRESHOLDS",
    "detect_frequency_alerts",
    # _make_alert e _days_since_last_session sao privados (prefixo _) -- nao exportados.
]
