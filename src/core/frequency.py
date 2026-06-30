"""Pure functions for session frequency analysis (Caminho B, Phase 2).

Motivacao (data_model.md §8 + relatorio cliente 2026-06-23):
  A regra "comparecimento < 70% E >= 2 faltas consecutivas -> alerta Alta/Media"
  vira **funcao deterministica** que respeita ``deliverable.frequencia_tipo``
  do catalogo (resolve C3 do relatorio). O ``consecutive_missed`` calcula
  direto de ``client_sessions`` (resolve C4).

N7 (exception handling) — **FUNCOES PURAS** (N7 E5):
  Estas funcoes NAO capturam excecoes internamente. Erros de tipo
  (e.g., ``as_of=None``, ``cd.sessions_expected < 0``) sao deixados subir
  como ``TypeError`` / ``ValueError`` para o chamador decidir. Logging,
  I/O e fallbacks silenciosos NAO acontecem aqui -- isso fica na camada
  de fronteira (``repos.py``, futuras ``persistence.py``, ``pages/*``).

Performance:
  Algoritmos sao O(N) sobre ``sessions`` (uma passada por funcao).
  ``max_consecutive_missed`` ordena uma vez; demais funcoes sao streaming.
  Phase 7 (e2e) mede com 238 sessoes -- bem dentro do SLA de Fase 2
  (medicao alvo: < 5ms para 1 client_deliverable, < 100ms para 100).

Determinismo:
  Nenhuma dependencia de ``datetime.now()`` ou ``date.today()`` -- o
  ``as_of`` e' sempre parametro. Isso torna as funcoes puras e
  testaveis deterministicamente (ver ``test_core_frequency.py``).
"""
from __future__ import annotations

from datetime import date, datetime

from src.core.types import ClientDeliverable, ClientSession, Deliverable

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Periodo em dias para cada ``deliverable.frequencia_tipo`` canonica
#: (data_model.md §3.3 + types.py::DeliverableFrequencia). ``None`` significa
#: "sessao unica" -- esperado = ``cd.sessions_expected`` literal, sem calculo.
#: ``"Outro"`` -> 0 (nao ha regra canonica; cai no fallback do plan).
#:
#: Forma canonica COM acentos. A normalizacao de v1 (mojibake cp1252) para
#: canonico acontece em ``mapping.py::_validate_frequencia`` -- ``frequency.py``
#: opera APENAS na forma canonica.
PERIOD_DAYS: dict[str, int | None] = {
    "Diário": 1,
    "Semanal": 7,
    "Quinzenal": 14,
    "Mensal": 30,
    "Única": None,
    "Outro": 0,
}

#: Status que conta como "sessao atendida" para fins de comparecimento.
#: Demais status (Agendado, Confirmado, Atrasado, Cancelado, Reagendado)
#: NAO contam -- a sessao nao foi de fato realizada.
ATTENDED_STATUS: str = "Atendido"


# ---------------------------------------------------------------------------
# expected_sessions
# ---------------------------------------------------------------------------


def expected_sessions(
    cd: ClientDeliverable,
    d: Deliverable,
    as_of: date,
) -> int:
    """Sessoes que DEVERIAM ter ocorrido entre ``cd.data_inicio`` e ``as_of``.

    Logica (caminho_b_plano.md §3 Fase 2 + data_model.md §8):
      1. Se ``d.frequencia_tipo`` e' ``None`` ou ``"Unica"``, retorna
         ``cd.sessions_expected`` (sem calculo -- plano tem contagem fixa).
      2. Se ``d.frequencia_tipo`` nao esta' em ``PERIOD_DAYS`` (ex.: ``"Outro"``)
         OU ``cd.data_inicio`` e' ``None``, retorna ``cd.sessions_expected``
         (fallback gracioso).
      3. Se ``as_of <= cd.data_inicio``, retorna 0 (ainda nao comecou).
      4. Caso contrario, retorna ``min(cd.sessions_expected, elapsed // period)``
         -- cap garante que nao extrapolamos o plano.

    Args:
        cd: ClientDeliverable (item de plano; tipicamente
            ``cd.parent_client_deliverable_id`` e' setado).
        d: Deliverable (catalogo) -- usado para ler ``frequencia_tipo``.
        as_of: Data de referencia para o calculo. Normalmente ``date.today()``
            na camada de chamada, mas mantida como parametro para pureza.

    Returns:
        Numero inteiro de sessoes devidas ate ``as_of``.

    Raises:
        ValueError: Se ``cd.sessions_expected`` for negativo (estado
            inconsistente -- sessao devida nao pode ser negativa).
        TypeError: Se ``as_of`` nao for ``date`` (Python nativo).
    """
    # Guard de dominio: sessions_expected negativo e' estado inconsistente
    # (CD nao pode "dever" sessoes negativas). Phase 1 nunca produz isso
    # (mapping normaliza para 0), mas a funcao e' defensiva.
    if cd.sessions_expected < 0:
        raise ValueError(
            f"sessions_expected nao pode ser negativo "
            f"(recebido: {cd.sessions_expected}; cd_id={cd.id}). "
            f"Verifique o cadastro do client_deliverable."
        )

    # Caso 1: frequencia nula ou "Unica" -- sessoes sao contagem fixa.
    if d.frequencia_tipo is None or d.frequencia_tipo == "Única":
        return cd.sessions_expected

    # Caso 2: frequencia nao mapeada (ex.: "Outro") ou data_inicio ausente.
    period = PERIOD_DAYS.get(d.frequencia_tipo)
    if period is None or period == 0 or cd.data_inicio is None:
        return cd.sessions_expected

    # Caso 3: as_of antes do inicio do plano.
    elapsed_days = (as_of - cd.data_inicio).days
    if elapsed_days <= 0:
        return 0

    # Caso 4: cap em sessions_expected (plano nao pode dever mais do que o
    # contratado, mesmo que o tempo decorrido sugira mais).
    return min(cd.sessions_expected, elapsed_days // period)


# ---------------------------------------------------------------------------
# actual_sessions
# ---------------------------------------------------------------------------


def actual_sessions(
    cd: ClientDeliverable,
    sessions: list[ClientSession],
    as_of: date,
) -> int:
    """Sessoes com ``status='Atendido'`` para o cliente do ``cd`` ate ``as_of``.

    Phase 2 simplificacao: filtra por ``s.client_id == cd.client_id``. Em
    Phase 6 (csv_importer) e Phase 8 (cutover v2), a associacao N:N entre
    sessao e item sera via ``client_session_items`` -- o filtro passara' a
    usar ``s.id IN (SELECT client_session_id FROM client_session_items
    WHERE client_deliverable_id = cd.id)``. Por enquanto, ``client_id`` e'
    o melhor proxy disponivel sem migracao v1.

    Args:
        cd: ClientDeliverable usado para identificar o cliente alvo
            (``cd.client_id``).
        sessions: Lista completa de ``ClientSession`` (ja' carregada via
            ``load_client_sessions``). Funcao filtra internamente.
        as_of: Data de referencia -- sessoes com ``session_start`` APOS
            essa data nao contam.

    Returns:
        Numero inteiro de sessoes atendidas (status="Atendido") para
        o cliente do cd, ate a data de referencia.

    Raises:
        TypeError: Se ``as_of`` nao for ``date`` (validacao explicita no
            inicio para garantir que o erro aparece MESMO quando ``sessions``
            esta' vazia -- sem esta validacao, o early return do generator
            expression抢先 a comparacao que levantaria o TypeError
            naturalmente. Phase 2 introducao + Phase 4 fix
            documentado em ``docs/experience_log.md``).
    """
    # Guard explicito de tipo para ``as_of`` -- senao o early return do
    # generator (quando ``sessions`` esta' vazia)抢先 a comparacao
    # ``_to_date(s.session_start) <= as_of`` que levantaria TypeError
    # naturalmente, e o caller recebe 0 em vez do erro esperado.
    # Custo: 1 comparacao. Ganha: contrato de tipo verificavel
    # independente de ``sessions`` ser vazia ou nao.
    if not isinstance(as_of, date):
        raise TypeError(
            f"as_of deve ser datetime.date (recebido: {type(as_of).__name__}; "
            f"valor: {as_of!r}). Verifique o caller -- o uso de ``None`` ou "
            f"string quebra o calculo de comparecimento silenciosamente."
        )
    return sum(
        1
        for s in sessions
        if s.client_id == cd.client_id
        and s.status == ATTENDED_STATUS
        and _to_date(s.session_start) <= as_of
    )


def _to_date(value: datetime | date) -> date:
    """Coerce a ``datetime`` to its ``date`` part; pass through ``date``.

    Why a helper (N7 E5 -- pure function, no try/except):
      ``ClientSession.session_start`` e' tipicamente ``datetime`` (data_model.md
      §4.3), mas alguns testes/cenarios passam ``date`` direto (mais simples
      para aritmetica). O codigo de comparacao NAO pode assumir o tipo:
      - ``datetime.date()`` falha se o valor ja' e' ``date``
      - comparacao direta ``datetime <= date`` produz resultados errados
        (datetime e' mais especifico, vence no __lt__).

    Esta funcao centraliza a decisao e' usada em ``actual_sessions`` e
    ``max_consecutive_missed`` (que tambem ordena por ``session_start``).
    """
    if isinstance(value, datetime):
        return value.date()
    return value


# ---------------------------------------------------------------------------
# attendance_rate
# ---------------------------------------------------------------------------


def attendance_rate(
    cd: ClientDeliverable,
    d: Deliverable,
    sessions: list[ClientSession],
    as_of: date,
) -> float:
    """Taxa de comparecimento = actual / expected, ou 0.0 se expected=0.

    Args:
        cd: ClientDeliverable.
        d: Deliverable (necessario para ``expected_sessions``).
        sessions: Lista de sessoes (passada para ``actual_sessions``).
        as_of: Data de referencia.

    Returns:
        Float no intervalo [0.0, 1.0]. Retorna ``0.0`` se
        ``expected_sessions == 0`` (plano ainda nao comecou, OU
        ``cd.sessions_expected == 0``). NUNCA levanta ``ZeroDivisionError``.

    Raises:
        ValueError: Se ``cd.sessions_expected < 0`` (propagado de
            ``expected_sessions``).
    """
    expected = expected_sessions(cd, d, as_of)
    if expected == 0:
        return 0.0
    actual = actual_sessions(cd, sessions, as_of)
    return actual / expected


# ---------------------------------------------------------------------------
# max_consecutive_missed
# ---------------------------------------------------------------------------


def max_consecutive_missed(
    cd: ClientDeliverable,
    sessions: list[ClientSession],
) -> int:
    """Maior sequencia de sessoes consecutivas com ``status != 'Atendido'``.

    Algoritmo:
      1. Filtra sessoes pelo cliente do cd.
      2. Ordena por ``session_start`` (crescente).
      3. Walk linear: conta a run atual de sessoes nao-atendidas; atualiza
         o maximo quando a run quebra (sessao Atendida encontrada) OU no
         final do loop.

    Args:
        cd: ClientDeliverable.
        sessions: Lista de sessoes.

    Returns:
        Numero inteiro >= 0. Retorna 0 se nao ha' sessoes, OU se todas
        estao Atendidas, OU se as runs de nao-Atendido tem comprimento 0.
    """
    # Filtra pelo cliente; ordena por session_start (coerido para date para
    # aceitar tanto ``datetime`` quanto ``date`` -- ver _to_date).
    relevant = sorted(
        (s for s in sessions if s.client_id == cd.client_id),
        key=lambda s: _to_date(s.session_start),
    )
    if not relevant:
        return 0

    max_run = 0
    current_run = 0
    for s in relevant:
        if s.status != ATTENDED_STATUS:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


__all__ = [
    "PERIOD_DAYS",
    "ATTENDED_STATUS",
    "expected_sessions",
    "actual_sessions",
    "attendance_rate",
    "max_consecutive_missed",
    # _to_date e' privado (prefixo _) -- nao exportado.
]
