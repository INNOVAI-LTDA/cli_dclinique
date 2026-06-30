"""Unit tests for src.core.alerts + src.core.persistence (Caminho B, Phase 3).

The plan (``docs/caminho_b_plano.md`` §3 Fase 3) defines:

  * ``src.core.alerts.detect_frequency_alerts(...)`` -- percorre os
    ``ClientDeliverable`` ativos e emite alertas (Alta/Media) baseando-se
    em ``attendance_rate`` e ``max_consecutive_missed`` (e dias desde
    ultima sessao).
  * ``src.core.persistence.save_frequency_alerts(...)`` -- persiste a
    lista de alertas via ``data_layer.append_row``, idempotente via
    ``alert_id`` deterministico.

7 testes do plano + 2 extras (no_sessions + threshold override) totalizando
9 testes para cobrir a logica + a fronteira.

N7 (exception handling): the alerts functions are PURE (per N7 E5) --
they raise Python native exceptions for type errors but do not catch
internally. The persistence function is a BOUNDARY (N7 E6) -- it
catches I/O errors and logs in PT-BR. Tests for the boundary live in
``tests/test_exception_handling.py`` (Phase 3 extended that file).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

# Forca backend CSV ANTES de importar src.core.* (algumas funcoes lazy-importam)
os.environ.setdefault("DCLINIQUE_BACKEND", "csv")

import pandas as pd

from src.core.alerts import (
    Thresholds,
    detect_frequency_alerts,
)
from src.core.persistence import save_frequency_alerts
from src.core.types import (
    ClientDeliverable,
    ClientSession,
    Deliverable,
)

# ---------------------------------------------------------------------------
# Constantes de teste -- pinar a data de referencia
# ---------------------------------------------------------------------------

REFERENCE_DATE = date(2026, 6, 23)
DEFAULT_CREATED = datetime(2026, 1, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# Helpers para construir instancias v2
# ---------------------------------------------------------------------------


def _make_deliverable(
    *,
    deliverable_id: int = 1,
    frequencia_tipo: str = "Semanal",
) -> Deliverable:
    return Deliverable(
        id=deliverable_id,
        titulo="Injetaveis EV",
        tipo="Injetável",
        descricao="",
        parent_deliverable_id=None,
        organization_id=1,
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
    parent_cd_id: int | None = 2,
    data_inicio: date | None = REFERENCE_DATE - timedelta(days=21),
    sessions_expected: int = 4,
    sessions_completed: int = 0,
    status: str = "Ativo",
) -> ClientDeliverable:
    """CD sintetico. Default: ITEM de plano (parent_cd_id=2), iniciado 21d atras."""
    return ClientDeliverable(
        id=cd_id,
        client_id=client_id,
        deliverable_id=deliverable_id,
        parent_client_deliverable_id=parent_cd_id,
        organization_id=1,
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
    session_id: int,
    client_id: int = 1,
    session_start: datetime | None = None,
    status: str = "Atendido",
) -> ClientSession:
    if session_start is None:
        session_start = datetime.combine(REFERENCE_DATE, datetime.min.time())
    return ClientSession(
        id=session_id,
        client_id=client_id,
        provider_id=1,
        agendado_por_id=None,
        organization_id=1,
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
# 1. test_no_alert_when_fully_attended -- 100% comparecimento -> 0 alertas
# ---------------------------------------------------------------------------


def test_no_alert_when_fully_attended() -> None:
    """Todas as sessoes Atendido, rate ~ 100% -> 0 alertas."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=14),
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 4 sessoes Atendido nas ultimas 2 semanas
    sessions = [
        _make_client_session(
            session_id=i,
            session_start=REFERENCE_DATE - timedelta(days=14 - i * 3),
            status="Atendido",
        )
        for i in range(1, 5)
    ]
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    assert alerts == [], (
        f"Esperado 0 alertas (100% comparecimento), got: {alerts!r}"
    )


# ---------------------------------------------------------------------------
# 2. test_alta_alert_for_2_consecutive_misses -- 2 Cancelado seguidos -> Alta
# ---------------------------------------------------------------------------


def test_alta_alert_for_2_consecutive_misses() -> None:
    """2 sessoes consecutivas NAO atendidas -> alerta Alta (consecutive_missed)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=21),
        sessions_expected=3,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 1 Atendido, depois 2 Cancelado, 1 Cancelado (max_consecutive = 3)
    sessions = [
        _make_client_session(
            session_id=1, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=20),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=15),
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
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    # Deve ter PELO MENOS 1 alerta Alta (consecutive). Pode ter tambem
    # Media (rate baixo) -- checa que Alta esta' presente.
    alta_alerts = [a for a in alerts if a["priority"] == "Alta"]
    assert any(
        "consecutivas" in a["description"].lower() for a in alta_alerts
    ), (
        f"Esperado alerta Alta sobre sessoes consecutivas, got: {alta_alerts!r}"
    )


# ---------------------------------------------------------------------------
# 3. test_media_alert_for_low_attendance -- rate < 70% com expected >= 3 -> Media
# ---------------------------------------------------------------------------


def test_media_alert_for_low_attendance() -> None:
    """Taxa de comparecimento baixa (< 70%) com sessoes devidas suficientes -> Media."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=21),
        sessions_expected=3,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 3 esperados, 1 atendido (33%)
    sessions = [
        _make_client_session(
            session_id=1, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=15),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=10),
        ),
        _make_client_session(
            session_id=3, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=5),
        ),
    ]
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    media_alerts = [a for a in alerts if a["priority"] == "Média"]
    assert any(
        "Comparecimento" in a["description"] for a in media_alerts
    ), f"Esperado alerta Media sobre comparecimento, got: {media_alerts!r}"
    # O description inclui a porcentagem (ex.: "Comparecimento de 33%").
    sample = media_alerts[0]["description"]
    assert "%" in sample, f"description deve incluir porcentagem, got: {sample!r}"


# ---------------------------------------------------------------------------
# 4. test_no_alert_for_paused_plans -- status != Ativo/Aguardando -> 0 alertas
# ---------------------------------------------------------------------------


def test_no_alert_for_paused_plans() -> None:
    """Plano com status 'Pausado' NAO gera alerta mesmo com metricas ruins."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=30),
        sessions_expected=4,
        status="Pausado",  # chave do teste
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 4 sessoes Cancelado -> max_consecutive = 4 (>= 2)
    sessions = [
        _make_client_session(
            session_id=i, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=30 - i * 7),
        )
        for i in range(1, 5)
    ]
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    assert alerts == [], (
        f"status='Pausado' NAO deve gerar alertas, got: {alerts!r}"
    )


# ---------------------------------------------------------------------------
# 5. test_no_alert_for_plan_root -- parent=None -> 0 alertas (so' ITENS disparam)
# ---------------------------------------------------------------------------


def test_no_alert_for_plan_root() -> None:
    """Plano-pai (parent_client_deliverable_id=None) NAO gera alerta.

    A regra de "30 dias sem sessao" se aplica ao ITEM do plano (a acao
    concreta), NAO ao plano-pai (que e' agregado). Mesmo com metricas
    ruins, o plano-pai e' silencioso.
    """
    cd_pai = _make_client_deliverable(
        cd_id=1,
        parent_cd_id=None,  # <- e' um plano-pai, NAO item
        data_inicio=REFERENCE_DATE - timedelta(days=60),
        sessions_expected=8,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 8 sessoes Cancelado -> max_consecutive = 8 (>= 2)
    sessions = [
        _make_client_session(
            session_id=i, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=60 - i * 7),
        )
        for i in range(1, 9)
    ]
    alerts = detect_frequency_alerts([cd_pai], [d], sessions, REFERENCE_DATE)
    assert alerts == [], (
        f"Plano-pai NAO deve gerar alertas, got: {alerts!r}"
    )


# ---------------------------------------------------------------------------
# 6. test_save_frequency_alerts_idempotent -- rodar 2x -> 2a insere 0
# ---------------------------------------------------------------------------


def test_save_frequency_alerts_idempotent(tmp_path, monkeypatch) -> None:
    """Salvar os mesmos alertas 2x: 2a chamada insere 0 (idempotente).

    Usa tmp_path + monkeypatch no csv_dir para isolar do mock real
    (o teste NAO pode poluir data/csv/alerts.csv).
    """
    from src import data_layer
    from src.data_layer import csv_backend

    # Redireciona CSV para tmp_path
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    # Cria alerts.csv vazio (so' header)
    (csv_dir / "alerts.csv").write_text(
        "alert_id,patient_id,plan_id,category,alert_type,"
        "description,priority,status,created_at,comment\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(csv_backend, "_csv_dir_callable", lambda: csv_dir)
    data_layer.reset_backend_cache()

    cd = _make_client_deliverable(cd_id=5, client_id=1)
    d = _make_deliverable()
    sessions: list[ClientSession] = []  # sem sessoes -> no_sessions Alta
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)

    data1 = data_layer.load_all()
    n1 = save_frequency_alerts(alerts, data1)
    assert n1 == len(alerts), (
        f"1a chamada deve inserir {len(alerts)} alertas, got: {n1}"
    )

    data2 = data_layer.load_all()
    n2 = save_frequency_alerts(alerts, data2)
    assert n2 == 0, (
        f"2a chamada (mesmos alertas) deve inserir 0 (idempotente), got: {n2}"
    )

    # Verifica que o CSV tem exatamente len(alerts) linhas (sem duplicar).
    df = pd.read_csv(csv_dir / "alerts.csv")
    assert len(df) == len(alerts), (
        f"CSV deve ter {len(alerts)} linhas, got: {len(df)}"
    )


# ---------------------------------------------------------------------------
# 7. test_alert_dedup -- mesma chave natural em runs diferentes -> nao duplica
# ---------------------------------------------------------------------------


def test_alert_dedup(tmp_path, monkeypatch) -> None:
    """Dois runs com os mesmos alertas -> segundo run nao duplica (idempotente)."""
    from src import data_layer
    from src.data_layer import csv_backend

    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / "alerts.csv").write_text(
        "alert_id,patient_id,plan_id,category,alert_type,"
        "description,priority,status,created_at,comment\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(csv_backend, "_csv_dir_callable", lambda: csv_dir)
    data_layer.reset_backend_cache()

    cd = _make_client_deliverable(cd_id=7, client_id=3)
    d = _make_deliverable()
    sessions: list[ClientSession] = []
    alerts_run1 = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    # Simula run 2 (mesmo cd, mesmo as_of) -- mesma chave natural
    alerts_run2 = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)

    assert alerts_run1 == alerts_run2, (
        "Mesmo input deve gerar mesmos alertas (idempotente no detect)"
    )

    data1 = data_layer.load_all()
    save_frequency_alerts(alerts_run1, data1)
    data2 = data_layer.load_all()
    n2 = save_frequency_alerts(alerts_run2, data2)
    assert n2 == 0, "2o run dos mesmos alertas nao deve duplicar"

    # Total de linhas = len(alerts_run1), nao 2x.
    df = pd.read_csv(csv_dir / "alerts.csv")
    assert len(df) == len(alerts_run1), (
        f"Total de linhas = {len(alerts_run1)} (1x, nao duplicado), got: {len(df)}"
    )


# ---------------------------------------------------------------------------
# EXTRA: test_no_sessions_alta_threshold -- 30+ dias sem sessao -> Alta
# ---------------------------------------------------------------------------


def test_no_sessions_alta_threshold() -> None:
    """Cliente sem sessoes ha' mais de 30 dias -> alerta Alta (no_sessions_alta)."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=60),
        sessions_expected=8,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # Ultima sessao do cliente foi ha' 45 dias (alem do threshold de 30)
    sessions = [
        _make_client_session(
            session_id=1, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=45),
        ),
    ]
    alerts = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    alta_no_sessions = [
        a for a in alerts
        if a["priority"] == "Alta" and "Sem sessões" in a["description"]
    ]
    assert len(alta_no_sessions) == 1, (
        f"Esperado 1 alerta Alta 'Sem sessões', got: {alta_no_sessions!r}"
    )
    # Description deve mencionar os dias.
    assert "45" in alta_no_sessions[0]["description"], (
        f"description deve mencionar 45 dias, got: {alta_no_sessions[0]['description']!r}"
    )


# ---------------------------------------------------------------------------
# EXTRA: test_threshold_override -- thresholds customizados funcionam
# ---------------------------------------------------------------------------


def test_threshold_override() -> None:
    """Override de thresholds via parametro ``thresholds=`` e' respeitado."""
    cd = _make_client_deliverable(
        data_inicio=REFERENCE_DATE - timedelta(days=21),
        sessions_expected=4,
    )
    d = _make_deliverable(frequencia_tipo="Semanal")
    # 2 Cancelado consecutivos (max_consecutive = 2)
    sessions = [
        _make_client_session(
            session_id=1, status="Atendido",
            session_start=REFERENCE_DATE - timedelta(days=20),
        ),
        _make_client_session(
            session_id=2, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=10),
        ),
        _make_client_session(
            session_id=3, status="Cancelado",
            session_start=REFERENCE_DATE - timedelta(days=5),
        ),
    ]

    # Default THRESHOLDS (consecutive_missed_alta=2) -> gera Alta
    alerts_default = detect_frequency_alerts([cd], [d], sessions, REFERENCE_DATE)
    alta_default = [a for a in alerts_default if a["priority"] == "Alta"]
    assert any(
        "consecutivas" in a["description"].lower() for a in alta_default
    ), "Default threshold=2 deveria gerar alerta Alta para 2 consecutivos"

    # Override: consecutive_missed_alta=5 -> NAO gera Alta (max=2)
    custom = Thresholds(
        consecutive_missed_alta=5,
        attendance_rate_media=0.70,
        no_sessions_alta_days=30,
        min_expected_for_rate_alert=3,
    )
    alerts_custom = detect_frequency_alerts(
        [cd], [d], sessions, REFERENCE_DATE, thresholds=custom,
    )
    alta_custom = [
        a for a in alerts_custom
        if a["priority"] == "Alta" and "consecutivas" in a["description"].lower()
    ]
    assert alta_custom == [], (
        f"Override threshold=5 nao deveria gerar alerta Alta para 2 consecutivos, "
        f"got: {alta_custom!r}"
    )


# ---------------------------------------------------------------------------
# EXTRA: test_alert_id_is_deterministic -- mesma chave natural -> mesmo alert_id
# ---------------------------------------------------------------------------


def test_alert_id_is_deterministic() -> None:
    """O ``alert_id`` gerado por ``_make_alert`` e' deterministico (chave natural).

    Mesmo ``cd`` + mesma ``priority`` -> mesmo ``alert_id`` -- propriedade
    essencial para a idempotencia em ``save_frequency_alerts``.
    """
    from src.core.alerts import _make_alert

    cd = _make_client_deliverable(cd_id=42, client_id=7)
    a1 = _make_alert(cd, "Alta", "teste 1", REFERENCE_DATE)
    a2 = _make_alert(cd, "Alta", "teste 2", REFERENCE_DATE)
    assert a1["alert_id"] == a2["alert_id"], (
        f"alert_id deve ser deterministico, got: {a1['alert_id']!r} vs {a2['alert_id']!r}"
    )
    # Prioridade diferente -> alert_id diferente.
    a3 = _make_alert(cd, "Média", "teste 3", REFERENCE_DATE)
    assert a1["alert_id"] != a3["alert_id"], (
        "Prioridades diferentes devem gerar alert_ids diferentes"
    )


# ---------------------------------------------------------------------------
# EXTRA: test_save_with_empty_alerts -- sem alertas -> retorna 0 sem erro
# ---------------------------------------------------------------------------


def test_save_with_empty_alerts() -> None:
    """save_frequency_alerts([], data) retorna 0 sem chamar append_row."""
    from src import data_layer

    data = data_layer.load_all()
    n = save_frequency_alerts([], data)
    assert n == 0, f"Lista vazia deve retornar 0, got: {n}"


# ---------------------------------------------------------------------------
# EXTRA: test_alerts_csv_pollution_guard -- smoke test contra poluicao do mock
# ---------------------------------------------------------------------------


def test_alerts_csv_pollution_guard() -> None:
    """Os testes de alerta NAO devem poluir data/csv/alerts.csv.

    Este teste fica por ULTIMO no arquivo (pytest respeita a ordem do
    codigo-fonte). Ele verifica que o CSV real ``data/csv/alerts.csv``
    continua com apenas o header -- nenhum teste deste arquivo deve
    ter vazado dados no mock.

    Os testes de persistencia (``test_save_frequency_alerts_idempotent``
    e ``test_alert_dedup``) usam ``tmp_path`` + ``monkeypatch`` para
    isolar do mock. O teste ``test_save_with_empty_alerts`` nao chama
    ``append_row``. Entao, se o CSV real tem mais de 1 linha apos o
    suite, algum teste vazou -- provavelmente um smoke test manual.
    """
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "csv", "alerts.csv",
    )
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()
    # 1 header + 0 data lines (CSV mock deve estar vazio)
    assert len(lines) == 1, (
        f"data/csv/alerts.csv deve ter apenas o header (1 linha), got: {len(lines)} "
        f"-- algum teste poluiu o CSV. Linhas: {lines!r}"
    )
    assert lines[0].startswith("alert_id,"), (
        f"Header do alerts.csv parece incorreto: {lines[0]!r}"
    )
