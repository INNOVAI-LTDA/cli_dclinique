"""Unit tests for src.core.frequency (Caminho B, Phase 2).

The plan (``docs/caminho_b_plano.md`` §3 Fase 2) defines 4 pure functions
in ``src/core/frequency.py``:

  * ``expected_sessions(cd, d, as_of) -> int`` -- quantas sessoes DEVERIAM
    ter ocorrido entre ``data_inicio`` e ``as_of``.
  * ``actual_sessions(cd, sessions, as_of) -> int`` -- quantas sessoes com
    ``status='Atendido'`` para o cliente do ``cd`` ate ``as_of``.
  * ``attendance_rate(cd, d, sessions, as_of) -> float`` -- ratio
    actual / expected (0.0 se expected == 0).
  * ``max_consecutive_missed(cd, sessions) -> int`` -- maior sequencia
    consecutiva de sessoes NAO atendidas.

N7 (exception handling): the frequency functions are PURE (per N7 E5) --
they raise Python native exceptions for type errors (e.g., None instead of
date) but do not catch internally. The N7 tests for purity live in
``tests/test_exception_handling.py`` (Phase 2 added that file).

Why a fixed reference date:
  The plan tests reference "10 dias" and "21 dias" as elapsed windows. We
  pin a single ``REFERENCE_DATE = date(2026, 6, 23)`` (today) and build
  ``data_inicio`` offsets from it. This keeps tests deterministic and
  timezone-independent (we use ``date`` arithmetic, not ``datetime``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.frequency import (
    PERIOD_DAYS,
    actual_sessions,
    attendance_rate,
    expected_sessions,
    max_consecutive_missed,
)
from src.core.types import (
    ClientDeliverable,
    ClientSession,
    Deliverable,
    Organization,
)

# ---------------------------------------------------------------------------
# Constantes de teste -- pinar a data de referencia para que os testes nao
# quebrem quando o relogio do CI mudar. "Hoje" = 2026-06-23 (mesmo dia do
# phase_1_report.md). Os offsets em dias sao RELATIVOS a essa data.
# ---------------------------------------------------------------------------

REFERENCE_DATE = date(2026, 6, 23)
DEFAULT_ORG_ID = 1
DEFAULT_CREATED = datetime(2026, 1, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# Fixtures / helpers para construir instancias v2 com defaults sensatos.
# Manter simples: cada teste fornece apenas os campos relevantes.
# ---------------------------------------------------------------------------


def _make_organization() -> Organization:
    """Organization sintetica para os testes (Phase 1: hard-coded DClinique)."""
    return Organization(
        id=DEFAULT_ORG_ID,
        nome="DClinique",
        cnpj=None,
        endereco=None,
        telefone=None,
        url=None,
        config=None,
        ativo=True,
        criado_em=DEFAULT_CREATED,
        atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_deliverable(
    *,
    deliverable_id: int = 1,
    titulo: str = "Injetaveis EV",
    tipo: str = "Injetavel",
    frequencia_tipo: str | None = "Semanal",
) -> Deliverable:
    """Deliverable sintetica. Default = Semanal para a maioria dos testes."""
    return Deliverable(
        id=deliverable_id,
        titulo=titulo,
        tipo=tipo,  # type: ignore[arg-type]
        descricao="",
        parent_deliverable_id=None,
        organization_id=DEFAULT_ORG_ID,
        frequencia_tipo=frequencia_tipo,  # type: ignore[arg-type]
        frequencia_texto=None,
        metadata=None,
        ativo=True,
        criado_em=DEFAULT_CREATED,
        atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_client_deliverable(
    *,
    cd_id: int = 1,
    client_id: int = 1,
    deliverable_id: int = 1,
    parent_cd_id: int | None = 2,  # default: e' um item de plano
    data_inicio: date | None = REFERENCE_DATE - timedelta(days=10),
    sessions_expected: int = 4,
    sessions_completed: int = 0,
    status: str = "Ativo",
) -> ClientDeliverable:
    """ClientDeliverable sintetica. Default: item de plano, iniciado 10 dias atras."""
    return ClientDeliverable(
        id=cd_id,
        client_id=client_id,
        deliverable_id=deliverable_id,
        parent_client_deliverable_id=parent_cd_id,
        organization_id=DEFAULT_ORG_ID,
        status=status,  # type: ignore[arg-type]
        orcamento="TEST-001",
        is_renovacao=False,
        data_inicio=data_inicio,
        data_fim=None,
        sessions_expected=sessions_expected,
        sessions_completed=sessions_completed,
        sessions_remaining=sessions_expected - sessions_completed,
        metadata=None,
        criado_em=DEFAULT_CREATED,
        atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_client_session(
    *,
    session_id: int = 1,
    client_id: int = 1,
    provider_id: int = 1,
    session_start: datetime | None = None,
    status: str = "Atendido",
) -> ClientSession:
    """ClientSession sintetica. Default: Atendido (a status que conta em
    actual_sessions).

    ``session_start`` e' opcional: testes que nao precisam de filtro por
    data (ex.: ``test_max_consecutive_missed_all_attended``) nao precisam
    especificar. Default = ``REFERENCE_DATE`` (constante de teste).
    """
    if session_start is None:
        session_start = datetime.combine(REFERENCE_DATE, datetime.min.time())
    return ClientSession(
        id=session_id,
        client_id=client_id,
        provider_id=provider_id,
        agendado_por_id=None,
        organization_id=DEFAULT_ORG_ID,
        session_start=session_start,
        session_end=session_start + timedelta(hours=1),
        status=status,  # type: ignore[arg-type]
        session_type=None,
        codigo_origem=None,
        metadata=None,
        criado_em=session_start,
        atualizado_em=session_start,
        deleted_at=None,
    )


# ---------------------------------------------------------------------------
# PERIOD_DAYS constant
# ---------------------------------------------------------------------------


def test_period_days_keys_match_data_model() -> None:
    """PERIOD_DAYS deve ter 6 chaves correspondendo a DeliverableFrequencia."""
    expected = {"Diário", "Semanal", "Quinzenal", "Mensal", "Única", "Outro"}
    assert set(PERIOD_DAYS.keys()) == expected


def test_period_days_values_are_int_or_none() -> None:
    """Apenas 'Única' tem None; os demais tem dias inteiros >= 0.

    Excecao: "Outro" tem valor 0 (marcador de "sem regra canonica --
    cai no fallback do plano"). NUNCA deve ser negativo, mas pode ser 0.
    """
    assert PERIOD_DAYS["Única"] is None
    for key in ("Diário", "Semanal", "Quinzenal", "Mensal", "Outro"):
        assert isinstance(PERIOD_DAYS[key], int)
        assert PERIOD_DAYS[key] >= 0, f"{key} nao pode ser negativo (got: {PERIOD_DAYS[key]})"
    # Apenas chaves com regra canonica precisam ser > 0.
    for key in ("Diário", "Semanal", "Quinzenal", "Mensal"):
        assert PERIOD_DAYS[key] > 0, f"{key} deve ter dias > 0 (got: {PERIOD_DAYS[key]})"


# ---------------------------------------------------------------------------
# expected_sessions
# ---------------------------------------------------------------------------


def test_expected_sessions_daily() -> None:
    """Injetavel Diário, 10 dias decorridos, sessions_expected=10 -> 10."""
    cd = _make_client_deliverable(sessions_expected=10)
    d = _make_deliverable(frequencia_tipo="Diário")
    # data_inicio = REFERENCE_DATE - 10d, as_of = REFERENCE_DATE -> 10 dias
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 10


def test_expected_sessions_weekly() -> None:
    """Injetavel Semanal, 21 dias decorridos, sessions_expected=4 -> 3."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=21),
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 21 dias // 7 = 3 sessoes devidas
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 3


def test_expected_sessions_caps_at_expected() -> None:
    """Se elapsed > expected * period, retorna expected (cap)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=100),
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 100 // 7 = 14, mas cap em 4
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 4


def test_expected_sessions_before_start() -> None:
    """as_of < data_inicio -> 0 (nao ha sessoes devidas ainda)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE + timedelta(days=5),  # comeca no futuro
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 0


def test_expected_sessions_unique() -> None:
    """frequencia_tipo='Única' -> retorna cd.sessions_expected (sem calculo)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=30),
        sessions_expected=1,
    )
    d = _make_deliverable(frequencia_tipo="Única")
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 1


def test_expected_sessions_no_frequency() -> None:
    """frequencia_tipo=None -> retorna cd.sessions_expected (sem calculo)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=30),
        sessions_expected=6,
    )
    d = _make_deliverable(frequencia_tipo=None)
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 6


def test_expected_sessions_outro_frequency_falls_back() -> None:
    """frequencia_tipo='Outro' (nao no PERIOD_DAYS) -> fallback para expected."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=30),
        sessions_expected=8,
    )
    d = _make_deliverable(frequencia_tipo="Outro")
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 8


def test_expected_sessions_none_data_inicio_falls_back() -> None:
    """cd.data_inicio=None -> retorna cd.sessions_expected (sem subtrair)."""
    cd = _make_client_deliverable(
        data_inicio=None,
        sessions_expected=5,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    result = expected_sessions(cd, d, REFERENCE_DATE)
    assert result == 5


# ---------------------------------------------------------------------------
# actual_sessions
# ---------------------------------------------------------------------------


def test_actual_sessions_filters_by_date() -> None:
    """Sessoes futuras (alem de as_of) nao contam."""
    cd = _make_client_deliverable(client_id=1)
    # 2 sessoes no passado, 1 no futuro
    sessions = [
        _make_client_session(
            session_id=1,
            session_start=REFERENCE_DATE - timedelta(days=20),  # OK
        ),
        _make_client_session(
            session_id=2,
            session_start=REFERENCE_DATE - timedelta(days=10),  # OK
        ),
        _make_client_session(
            session_id=3,
            session_start=REFERENCE_DATE + timedelta(days=10),  # futuro
        ),
    ]
    result = actual_sessions(cd, sessions, REFERENCE_DATE)
    assert result == 2


def test_actual_sessions_filters_by_status() -> None:
    """Sessoes com status != 'Atendido' nao contam."""
    cd = _make_client_deliverable(client_id=1)
    sessions = [
        _make_client_session(session_id=1, status="Atendido"),
        _make_client_session(session_id=2, status="Cancelado"),
        _make_client_session(session_id=3, status="Confirmado"),
        _make_client_session(session_id=4, status="Atrasado"),
        _make_client_session(session_id=5, status="Atendido"),
    ]
    result = actual_sessions(cd, sessions, REFERENCE_DATE)
    assert result == 2  # apenas as 2 com status "Atendido"


def test_actual_sessions_filters_by_client() -> None:
    """Sessoes de OUTRO cliente nao contam (Phase 2: filtra por client_id)."""
    cd = _make_client_deliverable(client_id=42)
    sessions = [
        _make_client_session(session_id=1, client_id=42, status="Atendido"),
        _make_client_session(session_id=2, client_id=99, status="Atendido"),
    ]
    result = actual_sessions(cd, sessions, REFERENCE_DATE)
    assert result == 1  # apenas a do cliente 42


# ---------------------------------------------------------------------------
# attendance_rate
# ---------------------------------------------------------------------------


def test_attendance_rate_zero_expected() -> None:
    """expected=0 -> retorna 0.0 (sem divisao por zero)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE + timedelta(days=5),  # as_of < inicio
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    sessions: list[ClientSession] = []
    # expected_sessions(cd, d, REFERENCE_DATE) = 0 (before_start)
    # attendance_rate deve retornar 0.0, nao levantar ZeroDivisionError
    result = attendance_rate(cd, d, sessions, REFERENCE_DATE)
    assert result == 0.0


def test_attendance_rate_normal_case() -> None:
    """3 esperados, 2 atendidos -> 2/3 ~= 0.6667."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=21),
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")  # 21 // 7 = 3
    sessions = [
        _make_client_session(session_id=1, status="Atendido"),
        _make_client_session(session_id=2, status="Atendido"),
        _make_client_session(session_id=3, status="Cancelado"),
    ]
    result = attendance_rate(cd, d, sessions, REFERENCE_DATE)
    assert result == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# max_consecutive_missed
# ---------------------------------------------------------------------------


def test_max_consecutive_missed_empty() -> None:
    """Sem sessoes -> 0 (nada foi perdido)."""
    cd = _make_client_deliverable(client_id=1)
    result = max_consecutive_missed(cd, [])
    assert result == 0


def test_max_consecutive_missed_all_attended() -> None:
    """Todas atendidas -> 0 (nenhuma falha consecutiva)."""
    cd = _make_client_deliverable(client_id=1)
    sessions = [
        _make_client_session(session_id=i, status="Atendido")
        for i in range(1, 6)
    ]
    result = max_consecutive_missed(cd, sessions)
    assert result == 0


def test_max_consecutive_missed_three_in_a_row() -> None:
    """3 canceladas em sequencia -> 3."""
    cd = _make_client_deliverable(client_id=1)
    sessions = [
        _make_client_session(
            session_id=1, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=30),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=20),
        ),
        _make_client_session(
            session_id=3, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=10),
        ),
        _make_client_session(
            session_id=4, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=5),
        ),
    ]
    result = max_consecutive_missed(cd, sessions)
    assert result == 3


def test_max_consecutive_missed_with_gap() -> None:
    """Sequencia quebrada por Atendido -> conta apenas a maior subsequencia."""
    cd = _make_client_deliverable(client_id=1)
    sessions = [
        # 2 canceladas
        _make_client_session(
            session_id=1, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=40),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=30),
        ),
        # quebra
        _make_client_session(
            session_id=3, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=20),
        ),
        # 3 canceladas (maior subsequencia)
        _make_client_session(
            session_id=4, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=15),
        ),
        _make_client_session(
            session_id=5, status="Atrasado",
            session_start=REFERENCE_DATE - timedelta(days=10),
        ),
        _make_client_session(
            session_id=6, status="Reagendado",
            session_start=REFERENCE_DATE - timedelta(days=5),
        ),
    ]
    result = max_consecutive_missed(cd, sessions)
    assert result == 3  # sessoes 4, 5, 6


def test_max_consecutive_missed_unsorted_input() -> None:
    """Funcao deve ordenar por data, nao depender da ordem de entrada."""
    cd = _make_client_deliverable(client_id=1)
    # Input em ordem NAO-cronologica
    sessions = [
        _make_client_session(
            session_id=3, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=5),
        ),
        _make_client_session(
            session_id=1, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=15),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=10),
        ),
    ]
    # Apos ordenar: sessoes 1, 2, 3 todas canceladas -> 3
    result = max_consecutive_missed(cd, sessions)
    assert result == 3


def test_max_consecutive_missed_filters_by_client() -> None:
    """Sessoes de outro cliente nao contam."""
    cd = _make_client_deliverable(client_id=42)
    sessions = [
        _make_client_session(session_id=1, client_id=99, status="Cancelado"),
        _make_client_session(session_id=2, client_id=42, status="Cancelado"),
        _make_client_session(session_id=3, client_id=42, status="Cancelado"),
    ]
    result = max_consecutive_missed(cd, sessions)
    assert result == 2  # apenas as 2 do cliente 42
