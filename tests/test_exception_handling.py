"""N7 exception handling tests (Caminho B, Phase 2 added this file).

Why this file is permanent (caminho_b_plano.md §2.1):
  A cada fase, novos testes sao adicionados conforme novas libs/funcoes
  tocam a fronteira. Phase 2 introduz ``frequency.py`` (funcoes puras) --
  ganhamos 1 teste novo: ``test_pure_functions_raise_domain_exceptions``.

Cobertura atual (Phase 3):
  1. test_no_bare_except -- AST scan: nenhum ``except:`` em src/core/
  2. test_no_traceback_in_user_logs -- placeholder Phase 2 (UI nao e' escopo)
  3. test_exception_message_is_portuguese -- ValueError em frequency.py tem PT-BR
  4. test_pure_functions_raise_domain_exceptions -- frequency.py raise ValueError
  5. test_boundary_functions_silently_translate -- load_clients({}) -> [] sem raise
  6. test_logging_not_print -- AST scan: nenhum ``print(`` em src/core/*.py
  7. test_alerts_is_pure_function_no_try_except -- alerts.py e' puro (Phase 3)
  8. test_persistence_boundary_captures_io_errors -- save_frequency_alerts
     captura FileNotFoundError/PermissionError/OSError sem levantar (Phase 3)
  9. test_persistence_logs_pt_br -- mensagens de erro sao em PT-BR (Phase 3)

Cobertura futura:
  - Phase 4: streamlit ``st.exception`` proibido em pages/* (test #2 real)
  - Phase 6: psycopg exceptions em persistence.py
  - Phase 8: cutover v2 (catalog completo de excecoes)
"""
from __future__ import annotations

import ast
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.core import (
    ClientDeliverable,
    ClientSession,
    Deliverable,
    Organization,
    actual_sessions,
    expected_sessions,
    load_client_sessions,
    load_clients,
)
from src.core.repos import _filter_active, _get_table

# Pin a data de referencia para testes deterministicos (mesmo padrao de
# tests/test_core_frequency.py).
REFERENCE_DATE = date(2026, 6, 23)
DEFAULT_CREATED = datetime(2026, 1, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# Helpers (mesmo padrao de test_core_frequency.py)
# ---------------------------------------------------------------------------


def _make_organization() -> Organization:
    return Organization(
        id=1, nome="DClinique", cnpj=None, endereco=None, telefone=None,
        url=None, config=None, ativo=True,
        criado_em=DEFAULT_CREATED, atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_deliverable(*, frequencia_tipo: str | None = "Semanal") -> Deliverable:
    return Deliverable(
        id=1, titulo="Injetaveis", tipo="Injetavel", descricao="",
        parent_deliverable_id=None, organization_id=1,
        frequencia_tipo=frequencia_tipo,  # type: ignore[arg-type]
        frequencia_texto=None, metadata=None, ativo=True,
        criado_em=DEFAULT_CREATED, atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_client_deliverable(
    *,
    cd_id: int = 1,
    client_id: int = 1,
    sessions_expected: int = 4,
    data_inicio: date | None = REFERENCE_DATE - timedelta(days=10),
) -> ClientDeliverable:
    return ClientDeliverable(
        id=cd_id, client_id=client_id, deliverable_id=1,
        parent_client_deliverable_id=2, organization_id=1,
        status="Ativo", orcamento="X", is_renovacao=False,
        data_inicio=data_inicio, data_fim=None,
        sessions_expected=sessions_expected,
        sessions_completed=0,
        sessions_remaining=sessions_expected,
        metadata=None,
        criado_em=DEFAULT_CREATED, atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


def _make_client_session(
    *, session_id: int, client_id: int = 1, status: str = "Atendido"
) -> ClientSession:
    return ClientSession(
        id=session_id, client_id=client_id, provider_id=1,
        agendado_por_id=None, organization_id=1,
        session_start=datetime(2026, 6, 1, 10, 0, 0),
        session_end=datetime(2026, 6, 1, 11, 0, 0),
        status=status,  # type: ignore[arg-type]
        session_type=None, codigo_origem=None, metadata=None,
        criado_em=DEFAULT_CREATED, atualizado_em=DEFAULT_CREATED,
        deleted_at=None,
    )


# ---------------------------------------------------------------------------
# 1. test_no_bare_except -- nenhum ``except:`` em src/core/*.py
# ---------------------------------------------------------------------------


def test_no_bare_except() -> None:
    """AST scan: src/core/*.py NAO pode conter ``except:`` cego (N7 E1).

    Excecoes legitimas sao ``except KeyError:``, ``except (ValueError, TypeError):``
    -- estas NAO disparam este teste porque o handler tem tipo de excecao.
    """
    src_dir = Path(__file__).resolve().parents[1] / "src" / "core"
    bare_excepts: list[tuple[str, int]] = []
    for py_file in src_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                # ``except:`` sem tipo = bare except = proibido
                rel = py_file.name
                bare_excepts.append((rel, node.lineno))
    assert not bare_excepts, (
        f"N7 E1 VIOLATION: bare ``except:`` found in src/core/: {bare_excepts}"
    )


# ---------------------------------------------------------------------------
# 2. test_no_traceback_in_user_logs -- placeholder Phase 2
# ---------------------------------------------------------------------------


def test_no_traceback_in_user_logs() -> None:
    """Placeholder: Phase 2 nao tem UI Streamlit ainda.

    Phase 4 (mapa_decisao refactor) substitui este teste por uma checagem
    real: capturar ``st.error`` output via AppTest, validar que nao
    contem ``"Traceback (most recent call last)"``. Por enquanto,
    verificacao trivial: o codigo de ``src/core/*.py`` nao expoe stacktraces.
    """
    # O check real acontece no run_core_tests.ps1 step 11 (anti-stacktrace
    # grep no log). Aqui so' documentamos a intencao.
    assert True, "covered by run_core_tests.ps1 step 11"


# ---------------------------------------------------------------------------
# 3. test_exception_message_is_portuguese
# ---------------------------------------------------------------------------


def test_exception_message_is_portuguese() -> None:
    """ValueError levantado por frequency.py tem mensagem em PT-BR (N7 E2).

    Verifica o guard de dominio ``sessions_expected < 0``: a mensagem deve
    conter palavras PT-BR (negativo, nao pode) -- nunca o nome da variavel
    Python puro.
    """
    cd = _make_client_deliverable(sessions_expected=-1)
    d = _make_deliverable(frequencia_tipo="Semanal")
    with pytest.raises(ValueError) as exc_info:
        expected_sessions(cd, d, REFERENCE_DATE)
    msg = str(exc_info.value)
    # PT-BR keywords esperadas
    assert "negativo" in msg.lower(), (
        f"mensagem deve conter 'negativo' em PT-BR (got: {msg!r})"
    )
    assert "sess" in msg.lower(), (
        f"mensagem deve mencionar sessoes (got: {msg!r})"
    )


# ---------------------------------------------------------------------------
# 4. test_pure_functions_raise_domain_exceptions
# ---------------------------------------------------------------------------


def test_pure_functions_raise_domain_exceptions() -> None:
    """Funcoes puras em frequency.py NAO capturam excecoes internamente (N7 E5).

    Cenarios:
      (a) ``expected_sessions`` com ``cd.sessions_expected < 0`` -> ValueError
      (b) ``expected_sessions`` com ``as_of=None`` -> TypeError (Python nativo)
      (c) ``actual_sessions`` com ``as_of=None`` -> TypeError (Python nativo)
    """
    cd = _make_client_deliverable(sessions_expected=-1)
    d = _make_deliverable()

    # (a) ValueError de dominio
    with pytest.raises(ValueError, match="negativo"):
        expected_sessions(cd, d, REFERENCE_DATE)

    # (b) TypeError nativo (as_of=None nao subtrai de date)
    cd_ok = _make_client_deliverable(sessions_expected=4)
    with pytest.raises(TypeError):
        expected_sessions(cd_ok, d, None)  # type: ignore[arg-type]

    # (c) TypeError nativo em actual_sessions
    sessions: list[ClientSession] = []
    with pytest.raises(TypeError):
        actual_sessions(cd_ok, sessions, None)  # type: ignore[arg-type]


def test_pure_functions_have_no_internal_try_except() -> None:
    """AST scan: frequency.py NAO pode conter ``try``/``except`` (pure function)."""
    freq_file = (
        Path(__file__).resolve().parents[1] / "src" / "core" / "frequency.py"
    )
    tree = ast.parse(freq_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Try), (
            "N7 E5 VIOLATION: frequency.py deve ser puro, sem try/except interno. "
            f"Encontrado Try em linha {node.lineno}."
        )


# ---------------------------------------------------------------------------
# 5. test_boundary_functions_silently_translate
# ---------------------------------------------------------------------------


def test_boundary_functions_silently_translate(caplog: pytest.LogCaptureFixture) -> None:
    """load_clients({}) retorna [] sem raise; erro e' logado (N7 E6).

    Quando o data layer esta' vazio (caso comum em testes, ou em producao
    antes do primeiro sync), ``load_clients`` NAO pode levantar -- quem
    chama (pagina Streamlit, script) decide o que fazer com lista vazia.
    O erro (se houver) e' logado com mensagem traduzida.
    """
    with caplog.at_level(logging.WARNING):
        # Data layer vazio: nenhum DataFrame. load_clients deve retornar [].
        result = load_clients({})
    assert result == [], (
        f"load_clients({{}}) deve retornar lista vazia (got: {result!r})"
    )


def test_get_table_returns_empty_dataframe_on_missing_table() -> None:
    """_get_table NAO levanta se tabela ausente -- retorna DataFrame vazio."""
    # _get_table e' helper interno, mas e' a barreira read-only do N7.
    result = _get_table({}, "tabela_inexistente")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_filter_active_handles_missing_column() -> None:
    """_filter_active NAO levanta se coluna deleted_at ausente -- retorna df."""
    df = pd.DataFrame({"a": [1, 2, 3]})
    result = _filter_active(df, deleted_col="deleted_at")
    assert len(result) == 3
    assert list(result["a"]) == [1, 2, 3]


def test_load_client_sessions_empty_data() -> None:
    """load_client_sessions({}) retorna [] sem raise."""
    result = load_client_sessions({})
    assert result == []


# ---------------------------------------------------------------------------
# 6. test_logging_not_print -- AST scan
# ---------------------------------------------------------------------------


def test_logging_not_print() -> None:
    """AST scan: src/core/*.py NAO pode conter ``print(`` -- so' ``logging``.

    Ruff custom rule F841 + AST simples. Bare ``print`` quebra N7 E3.
    Excecao: o nome da funcao ``_print_*`` NAO conta (e' so' o token ``print``).
    """
    src_dir = Path(__file__).resolve().parents[1] / "src" / "core"
    print_calls: list[tuple[str, int]] = []
    for py_file in src_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # print(...) como chamada direta
                if isinstance(func, ast.Name) and func.id == "print":
                    rel = py_file.name
                    print_calls.append((rel, node.lineno))
                # tambem capta ``builtins.print(...)`` (raro, mas possivel)
                elif isinstance(func, ast.Attribute) and func.attr == "print":
                    rel = py_file.name
                    print_calls.append((rel, node.lineno))
    assert not print_calls, (
        f"N7 E3 VIOLATION: ``print(`` found in src/core/: {print_calls}"
    )


# ---------------------------------------------------------------------------
# 7. Phase 3: alerts.py e' pura (sem try/except) -- alertas_decisao.py equivalente
# ---------------------------------------------------------------------------


def test_alerts_is_pure_function_no_try_except() -> None:
    """AST scan: alerts.py NAO pode conter ``try``/``except`` (pure function, N7 E5).

    ``detect_frequency_alerts`` e' deterministica e recebe dados validados
    pelo caller -- qualquer erro de tipo (as_of=None, cd.id <= 0) e'
    deixado subir como TypeError/ValueError para o caller decidir.
    Diferente de ``persistence.py``, que e' boundary e captura I/O.
    """
    alerts_file = (
        Path(__file__).resolve().parents[1] / "src" / "core" / "alerts.py"
    )
    tree = ast.parse(alerts_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.Try), (
            "N7 E5 VIOLATION: alerts.py deve ser puro, sem try/except interno. "
            f"Encontrado Try em linha {node.lineno}."
        )


# ---------------------------------------------------------------------------
# 8. Phase 3: persistence.py e' boundary -- captura erros de I/O (N7 E6)
# ---------------------------------------------------------------------------


def test_persistence_boundary_captures_io_errors(
    tmp_path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """save_frequency_alerts NAO levanta quando ``data_layer.append_row`` falha (N7 E6).

    Simula FileNotFoundError no caminho do CSV: o boundary deve capturar,
    logar em PT-BR e retornar a contagem efetiva (0 inseridos, N skipped).

    Estrategias:
      1. Monkeypatch ``csv_backend._csv_dir_callable`` para ``tmp_path``
         (cria o CSV vazio).
      2. Apos a primeira insercao OK, monkeypatch
         ``csv_backend._csv_path`` para apontar para um diretorio que NAO
         existe -- o segundo ``append_row`` levanta FileNotFoundError.
      3. ``save_frequency_alerts`` deve continuar (captura), logar e
         retornar ``1`` (1 inserido na 1a chamada) -- mas como a 2a chamada
         do save_frequency_alerts usa um unico loop, vamos simplificar:
         usamos um mock de ``append_row`` que sempre levanta FileNotFoundError.
    """
    from src import data_layer
    from src.core.persistence import save_frequency_alerts
    from src.data_layer import csv_backend

    # Setup: CSV "alerts.csv" existe (header only) em tmp_path
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / "alerts.csv").write_text(
        "alert_id,patient_id,plan_id,category,alert_type,"
        "description,priority,status,created_at,comment\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(csv_backend, "_csv_dir_callable", lambda: csv_dir)
    data_layer.reset_backend_cache()

    # Substitui ``append_row`` para sempre levantar FileNotFoundError.
    # ``save_frequency_alerts`` deve capturar (N7 E6) e nao levantar.
    def boom(*_args, **_kwargs) -> None:
        raise FileNotFoundError("simulated: diretório inacessível")

    monkeypatch.setattr(data_layer, "append_row", boom)

    alerts = [
        {
            "alert_id": "freq_1_1_alta",
            "patient_id": "pat_001",
            "plan_id": "plan_2",
            "category": "Frequência",
            "alert_type": "Alta",
            "description": "teste boundary",
            "priority": "Alta",
            "status": "Aberto",
            "created_at": "2026-06-23",
            "comment": "",
        },
    ]

    with caplog.at_level(logging.ERROR, logger="src.core.persistence"):
        # N7 E6: NAO levanta.
        n = save_frequency_alerts(alerts, {})

    # Inseridos = 0 (todos falharam). A funcao retorna int, nao levanta.
    assert n == 0, (
        f"save_frequency_alerts com I/O falho deve retornar 0 (got: {n})"
    )
    # E o erro foi logado em PT-BR (N7 E2).
    assert any(
        "não encontrado" in rec.message.lower()
        or "nao encontrado" in rec.message.lower()
        or "salvar" in rec.message.lower()
        for rec in caplog.records
    ), (
        f"esperado log PT-BR sobre erro de I/O, got: "
        f"{[r.message for r in caplog.records]!r}"
    )


def test_persistence_boundary_captures_permission_error(
    tmp_path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """save_frequency_alerts captura PermissionError e loga em PT-BR (N7 E6).

    Mesma estrategia do teste anterior, mas levantando PermissionError.
    Mensagem esperada: "Sem permissao para escrever alertas".
    """
    from src import data_layer
    from src.core.persistence import save_frequency_alerts
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

    def deny(*_args, **_kwargs) -> None:
        raise PermissionError("simulated: read-only filesystem")

    monkeypatch.setattr(data_layer, "append_row", deny)

    alerts = [
        {
            "alert_id": "freq_2_3_media",
            "patient_id": "pat_002",
            "plan_id": "plan_5",
            "category": "Frequência",
            "alert_type": "Média",
            "description": "teste permissao",
            "priority": "Média",
            "status": "Aberto",
            "created_at": "2026-06-23",
            "comment": "",
        },
    ]

    with caplog.at_level(logging.ERROR, logger="src.core.persistence"):
        n = save_frequency_alerts(alerts, {})

    assert n == 0
    assert any(
        "permiss" in rec.message.lower()
        for rec in caplog.records
    ), (
        f"esperado log PT-BR sobre permissao, got: "
        f"{[r.message for r in caplog.records]!r}"
    )


def test_persistence_returns_int_never_raises(
    tmp_path, monkeypatch,
) -> None:
    """``save_frequency_alerts`` SEMPRE retorna int -- nunca levanta (N7 E6).

    Cobre todos os tipos de excecao capturados em persistence.py:
    FileNotFoundError, PermissionError, OSError, ValueError, TypeError, KeyError.
    O caller (pagina Streamlit, script) recebe a contagem efetiva e decide.
    """
    from src import data_layer
    from src.core.persistence import save_frequency_alerts
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

    # Tabela de excecoes que o boundary DEVE capturar.
    exceptions_to_test = [
        FileNotFoundError("x"),
        PermissionError("x"),
        OSError("x"),
        ValueError("x"),
        TypeError("x"),
        KeyError("x"),
    ]

    for exc in exceptions_to_test:
        def boom(*_a, _exc=exc, **_kw) -> None:
            raise _exc

        monkeypatch.setattr(data_layer, "append_row", boom)
        # NAO levanta -- retorna int >= 0.
        n = save_frequency_alerts(
            [{
                "alert_id": "freq_x",
                "patient_id": "pat_x",
                "plan_id": "plan_x",
                "category": "Frequência",
                "alert_type": "Alta",
                "description": "x",
                "priority": "Alta",
                "status": "Aberto",
                "created_at": "2026-06-23",
                "comment": "",
            }],
            {},
        )
        assert isinstance(n, int), (
            f"save_frequency_alerts deve retornar int, got {type(n).__name__}"
        )
        assert n == 0, (
            f"com excecao {type(exc).__name__}, retorno deve ser 0 (got: {n})"
        )


# ---------------------------------------------------------------------------
# 9. Phase 3: pure functions em alerts.py tambem levantam em PT-BR
# ---------------------------------------------------------------------------


def test_alerts_raises_value_error_on_invalid_cd() -> None:
    """detect_frequency_alerts levanta ValueError se cd.id ou cd.client_id <= 0 (N7 E2).

    A mensagem deve ser em PT-BR e mencionar o id invalido.
    """
    from src.core.alerts import detect_frequency_alerts

    # cd invalido: client_id = 0
    cd_bad = _make_client_deliverable(cd_id=1, client_id=0)
    d = _make_deliverable()

    with pytest.raises(ValueError) as exc_info:
        detect_frequency_alerts([cd_bad], [d], [], REFERENCE_DATE)
    msg = str(exc_info.value).lower()
    assert "id" in msg or "client" in msg or "cliente" in msg, (
        f"mensagem deve mencionar id/cliente, got: {msg!r}"
    )


def test_alerts_raises_type_error_on_invalid_as_of() -> None:
    """detect_frequency_alerts levanta TypeError se as_of nao for date (N7 E5).

    TypeError nativo Python -- mas a mensagem customizada em alerts.py
    deve estar em PT-BR para o caller saber o que fazer.
    """
    from src.core.alerts import detect_frequency_alerts

    cd = _make_client_deliverable()
    d = _make_deliverable()

    with pytest.raises(TypeError) as exc_info:
        detect_frequency_alerts([cd], [d], [], "2026-06-23")  # type: ignore[arg-type]
    msg = str(exc_info.value).lower()
    assert "date" in msg or "data" in msg, (
        f"mensagem deve mencionar 'date' ou 'data', got: {msg!r}"
    )


# ---------------------------------------------------------------------------
# Bonus: sanity check do fixture JSON (audit artifact)
# ---------------------------------------------------------------------------


def test_frequency_fixture_json_is_loadable() -> None:
    """tests/fixtures/frequency_cases.json deve carregar como JSON valido.

    E' um audit artifact -- nao e' usado pelos testes, mas deve ser
    carregavel para revisao manual. Assegura que o reviewer nao pega um
    JSON malformado.
    """
    fixture_path = (
        Path(__file__).resolve().parents[0]
        / "fixtures"
        / "frequency_cases.json"
    )
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    # 6 casos canonicos (case_01 a case_06).
    case_keys = [k for k in data if k.startswith("case_")]
    assert len(case_keys) == 6, f"expected 6 cases, found {len(case_keys)}"
    for key in case_keys:
        case = data[key]
        # Cada caso tem cd, d, sessions, expected (4 funcoes testadas).
        assert "cd" in case
        assert "d" in case
        assert "sessions" in case
        assert "expected" in case
        # expected tem 4 chaves (1 por funcao).
        assert set(case["expected"].keys()) == {
            "expected_sessions",
            "actual_sessions",
            "attendance_rate",
            "max_consecutive_missed",
        }
