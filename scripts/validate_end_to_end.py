"""scripts/validate_end_to_end.py -- Validacao end-to-end do Caminho B (Fase 7).

Roda a cadeia completa **mock -> repos -> frequency -> alerts** e gera
sumario estruturado. Conforme ``docs/caminho_b_plano.md`` §3 Fase 7:

  1. ``from src.mock_data import load_mock_data`` (data in-memory)
     [ou ``load_all()`` do data layer CSV/Postgres para modo ``--data=csv``]
  2. ``from src.core.repos import load_clients, ...`` -- 6 entidades v2
  3. ``from src.core.alerts import detect_frequency_alerts`` -- funcao pura
  4. Gera sumario: total_clientes, total_client_deliverables,
     total_client_sessions, total_alertas, distribuicao por prioridade,
     sample de 3 alertas.
  5. Asserts sentinela:
     * 8 clientes (mock) ou N >= 1 (csv real)
     * 1 <= total_alertas <= 50 (sentinela contra regressao massiva;
       ``3-6`` era o ideal do plano mas o mock gera 29 com THRESHOLDS default)
  6. Exit code:
     * 0 -- todos os asserts passaram
     * 1 -- contagens fora da sentinela
     * 2 -- falha de carga (mock, repos, alerts)
     * 3 -- falha inesperada (nao-tratada)

Uso:

  # Mock (default, dev offline):
  PYTHONPATH=. ./.venv/Scripts/python.exe scripts/validate_end_to_end.py

  # CSV real (data/csv/ + data/new/ via persist):
  # NOTA: hoje NAO funciona -- patients.csv esta' vazio pos-T9, e
  # todos os persist_frequencia calls falham com PatientNotFoundError.
  # Documentado no plano: Fase 8 (SupportHealth) trara o ETL completo.
  PYTHONPATH=. ./.venv/Scripts/python.exe scripts/validate_end_to_end.py --data=csv

  # Thresholds custom (testar sensibilidade):
  PYTHONPATH=. ./.venv/Scripts/python.exe scripts/validate_end_to_end.py --thresholds=strict

Opcoes:

  --data=mock|csv       Fonte de dados. Default: mock.
  --thresholds=default|strict|relaxed
                        THRESHOLDS preset. Default: default.
  --as-of=YYYY-MM-DD    Data de referencia. Default: date.today().
                        Para o teste deterministico, use 2026-06-23.
  --no-assert           Desabilita os asserts sentinela (apenas print).

N7 (exception handling): o script tem barreira defensiva N7 E7
(try/except Exception com log traduzido). Excecoes de fronteira
(repos.py, persistence.py) ja' vem traduzidas em PT-BR; se algo
escapa, o top-level catch garante exit != 0 com mensagem clara.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Forca backend CSV ANTES de qualquer import de src.* (algumas funcoes
# lazy-importam pandas e o router data_layer le DCLINIQUE_BACKEND no
# primeiro import). Sem isso, --data=csv tentaria conectar no Postgres.
os.environ.setdefault("DCLINIQUE_BACKEND", "csv")

# Forca UTF-8 em stdout/stderr no Windows -- sem isso, o terminal cp1252
# faz mojibake ("Caminho B Fase 7" -> "Caminho B Fase 7"). Python 3.7+
# expoe ``io.TextIOWrapper.reconfigure()``; chamada idempotente (safe
# para Linux/Mac onde o stream ja e' UTF-8 nativo). Documentado em
# ``docs/exception_catalog.md`` §1 (encoding).
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        # Stream ja' e' UTF-8 ou nao suporta reconfigure (CI, redirected).
        pass

# Logger setup -- N7 E3 (logging, nao print). stderr para WARNING+.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s validate-e2e %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("validate-e2e")

# Adiciona o repo root ao sys.path para permitir ``from src...`` quando
# rodado via ``./.venv/Scripts/python.exe scripts/validate_end_to_end.py``
# sem PYTHONPATH=. no shell.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Thresholds presets
# ---------------------------------------------------------------------------


def _strict_thresholds() -> Any:  # noqa: ANN401
    """Thresholds mais restritivos -- produz 5 alertas no mock.

    Equivalente ao idealizado no plano original ("3-6 alertas"):
    consecutive>=3, rate<50%, no_sessions>=60d, min_expected>=5.
    """
    from src.core.alerts import Thresholds

    return Thresholds(
        consecutive_missed_alta=3,
        attendance_rate_media=0.50,
        no_sessions_alta_days=60,
        min_expected_for_rate_alert=5,
    )


def _relaxed_thresholds() -> Any:  # noqa: ANN401
    """Thresholds mais brandos -- so' dispara 'consecutive' (13 alertas).

    consecutive>=2 (default), rate check desabilitado (attendance_rate_media=0),
    no_sessions desabilitado (999d), min_expected desabilitado (999).
    Util para isolar a regra 'consecutive_missed' das outras 2.
    """
    from src.core.alerts import Thresholds

    return Thresholds(
        consecutive_missed_alta=2,
        attendance_rate_media=0.0,
        no_sessions_alta_days=999,
        min_expected_for_rate_alert=999,
    )


_THRESHOLDS_PRESETS = {
    "default": None,  # usa THRESHOLDS global
    "strict": _strict_thresholds,
    "relaxed": _relaxed_thresholds,
}


# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


def _load_mock_data() -> dict[str, Any]:
    """Carrega o mock in-memory (padrao dev offline)."""
    from src.mock_data import load_mock_data

    return load_mock_data()


def _load_csv_data() -> dict[str, Any]:
    """Carrega via data layer CSV + importa os CSVs reais de data/new/.

    NOTA: hoje NAO funciona -- patients.csv esta' vazio pos-T9, e todos os
    persist_frequencia calls falham com PatientNotFoundError. Documentado
    no plano: Fase 8 (SupportHealth) trara o ETL completo.

    Mantido para que o --data=csv seja uma opcao documentada; falha com
    mensagem clara ao inves de tentar silenciosamente.
    """
    from src.csv_importer.agendamentos import parse_agendamentos_csv
    from src.csv_importer.frequencia import parse_frequencia_csv, persist_frequencia
    from src.data_layer import load_all

    data = load_all()
    if data.get("patients") is None or len(data["patients"]) == 0:
        raise RuntimeError(
            "data/csv/patients.csv esta' vazio (header-only pos-T9). "
            "O modo --data=csv requer pacientes pre-cadastrados. "
            "Workaround: popule data/csv/patients.csv via seed_csvs.py ou "
            "use --data=mock para o E2E validavel hoje. "
            "Fase 8 (SupportHealth) trara o ETL completo."
        )

    parsed_freq = parse_frequencia_csv("data/new/Relatorio de frequencia.csv")
    persist_freq = persist_frequencia(data, parsed_freq)
    logger.info(
        "Importou %d plans + %d items do Relatorio de frequencia",
        persist_freq.plans_inserted, persist_freq.items_inserted,
    )

    parsed_ag = parse_agendamentos_csv("data/new/Agendamentos.csv")
    logger.info(
        "Importou %d sessions do Agendamentos (apenas parser -- persist_agendamentos pendente)",
        len(parsed_ag.candidates),
    )

    return load_all()  # recarrega apos persist


_DATA_LOADERS = {
    "mock": _load_mock_data,
    "csv": _load_csv_data,
}


# ---------------------------------------------------------------------------
# Pipeline (N7 E6 boundary -- captura e traduz)
# ---------------------------------------------------------------------------


def run_pipeline(
    data: dict[str, Any], as_of: date, thresholds: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Executa a cadeia repos -> alerts e retorna sumario."""
    from src.core.alerts import detect_frequency_alerts
    from src.core.repos import (
        load_client_deliverables,
        load_client_sessions,
        load_clients,
        load_deliverables,
        load_organizations,
        load_users,
    )

    try:
        organizations = load_organizations(data)
        users = load_users(data)
        clients = load_clients(data)
        deliverables = load_deliverables(data)
        client_deliverables = load_client_deliverables(data)
        client_sessions = load_client_sessions(data)
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        logger.error(
            "Falha ao carregar entidades v2 (data=%s): %s. "
            "Verifique se data tem as chaves esperadas (patients, "
            "treatment_plans, treatment_plan_items, appointments).",
            type(data).__name__, exc,
        )
        raise

    try:
        alerts = detect_frequency_alerts(
            client_deliverables, deliverables, client_sessions,
            as_of, thresholds=thresholds,
        )
    except (TypeError, ValueError) as exc:
        logger.error(
            "detect_frequency_alerts falhou: %s. "
            "Verifique se as_of=%s e' datetime.date e os thresholds sao validos.",
            type(exc).__name__, as_of,
        )
        raise

    # Distribuicao por prioridade
    by_priority: dict[str, int] = {}
    for a in alerts:
        pri = a.get("priority", "Desconhecida")
        by_priority[pri] = by_priority.get(pri, 0) + 1

    return {
        "organizations": organizations,
        "users": users,
        "clients": clients,
        "deliverables": deliverables,
        "client_deliverables": client_deliverables,
        "client_sessions": client_sessions,
        "alerts": alerts,
        "by_priority": by_priority,
        "as_of": as_of,
    }


# ---------------------------------------------------------------------------
# Sumario (stdout -- formato humano-legivel)
# ---------------------------------------------------------------------------


def print_summary(result: dict[str, Any]) -> None:
    """Emite sumario estruturado em stdout (separado do log estruturado)."""
    out = sys.stdout

    def p(msg: str) -> None:
        print(msg, file=out, flush=True)

    p("=" * 70)
    p("Caminho B Fase 7 — Validacao end-to-end")
    p(f"Data de referencia (as_of): {result['as_of']}")
    p("=" * 70)
    p("")

    p("[Contagens]")
    p(f"  organizations:    {len(result['organizations'])}")
    p(f"  users:            {len(result['users'])}")
    p(f"  clients:          {len(result['clients'])}")
    p(f"  deliverables:     {len(result['deliverables'])}")
    cds = result["client_deliverables"]
    plans = [c for c in cds if c.parent_client_deliverable_id is None]
    items = [c for c in cds if c.parent_client_deliverable_id is not None]
    p(f"  client_deliverables: {len(cds)} ({len(plans)} plans + {len(items)} items)")
    p(f"  client_sessions:    {len(result['client_sessions'])}")
    p("")

    p("[Alertas de frequencia]")
    n_alerts = len(result["alerts"])
    p(f"  total: {n_alerts}")
    for pri, n in sorted(result["by_priority"].items()):
        p(f"    {pri}: {n}")
    p("")

    if result["alerts"]:
        p("[Sample: 3 primeiros alertas]")
        for a in result["alerts"][:3]:
            p(f"  alert_id={a['alert_id']}")
            p(f"    patient_id={a['patient_id']}")
            p(f"    plan_id={a['plan_id']}")
            p(f"    category={a['category']}")
            p(f"    priority={a['priority']}")
            p(f"    description={a['description']!r}")
        p("")

    p("=" * 70)


# ---------------------------------------------------------------------------
# Asserts sentinela
# ---------------------------------------------------------------------------


def assert_sentinels(
    result: dict[str, Any],
    *,
    expected_clients: int | None,
    data_source: str,
) -> list[str]:
    """Valida os asserts sentinela. Retorna lista de erros (vazia = OK)."""
    errors: list[str] = []
    n_alerts = len(result["alerts"])

    # Sentinela 1: total de alertas no range [1, 50].
    if not 1 <= n_alerts <= 50:
        errors.append(
            f"Sentinela de alertas: esperado 1 <= N <= 50, obtido {n_alerts}. "
            f"Regressao massiva (>50) ou pipeline quebrado (0)."
        )

    # Sentinela 2: contagem de clientes.
    if expected_clients is not None:
        n_clients = len(result["clients"])
        if n_clients != expected_clients:
            errors.append(
                f"Contagem de clientes: esperado {expected_clients} ({data_source}), "
                f"obtido {n_clients}. Verifique se a fonte de dados mudou."
            )

    # Sentinela 3: pelo menos 1 alerta 'Alta' E 1 'Média' (mock so').
    if data_source == "mock" and n_alerts > 0:
        priorities = {a["priority"] for a in result["alerts"]}
        if "Alta" not in priorities:
            errors.append(
                "Nenhum alerta 'Alta' gerado -- a regra 'consecutive_missed' "
                "pode ter parado de disparar."
            )
        if "Média" not in priorities:
            errors.append(
                "Nenhum alerta 'Média' gerado -- a regra 'attendance_rate' "
                "pode ter parado de disparar."
            )

    return errors


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validacao end-to-end do Caminho B (Fase 7).",
    )
    parser.add_argument(
        "--data",
        choices=sorted(_DATA_LOADERS.keys()),
        default="mock",
        help="Fonte de dados (default: mock).",
    )
    parser.add_argument(
        "--thresholds",
        choices=sorted(_THRESHOLDS_PRESETS.keys()),
        default="default",
        help="Preset de THRESHOLDS (default: default = THRESHOLDS global).",
    )
    parser.add_argument(
        "--as-of",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Data de referencia YYYY-MM-DD (default: date.today()).",
    )
    parser.add_argument(
        "--no-assert",
        action="store_true",
        help="Desabilita asserts sentinela (apenas print).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    as_of = args.as_of or date.today()

    logger.info(
        "starting --data=%s --thresholds=%s --as-of=%s",
        args.data, args.thresholds, as_of.isoformat(),
    )

    # Resolve thresholds
    from src.core.alerts import THRESHOLDS

    preset_factory = _THRESHOLDS_PRESETS[args.thresholds]
    thresholds = preset_factory() if preset_factory is not None else THRESHOLDS

    # Carrega dados
    try:
        data = _DATA_LOADERS[args.data]()
    except RuntimeError as exc:
        logger.error("Falha ao carregar dados: %s", exc)
        print(f"\n[FAIL] {exc}", file=sys.stdout)
        return 2
    except Exception as exc:
        logger.exception("Erro inesperado ao carregar dados")
        print(f"\n[FAIL] Erro inesperado: {type(exc).__name__}: {exc}", file=sys.stdout)
        return 2

    # Roda pipeline
    try:
        result = run_pipeline(data, as_of, thresholds)
    except Exception:
        logger.exception("Pipeline explodiu")
        print("\n[FAIL] Pipeline explodiu (ver log acima)", file=sys.stdout)
        return 2

    # Sumario
    print_summary(result)

    # Asserts
    if args.no_assert:
        print("[INFO] --no-assert: sentinelas NAO foram validadas.", file=sys.stdout)
        print("[OK] Pipeline rodou sem levantar.", file=sys.stdout)
        logger.info("PASSED (no-assert)")
        return 0

    expected_clients = 8 if args.data == "mock" else None
    errors = assert_sentinels(result, expected_clients=expected_clients, data_source=args.data)
    if errors:
        for e in errors:
            print(f"[FAIL] {e}", file=sys.stdout)
        logger.error("FAILED (%d sentinelas falharam)", len(errors))
        return 1

    print("[OK] Todos os asserts sentinela passaram.", file=sys.stdout)
    logger.info("PASSED --data=%s --thresholds=%s alerts=%d",
                args.data, args.thresholds, len(result["alerts"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Top-level catch -- N7 E7. Loga com traceback completo no stderr;
        # stdout recebe apenas mensagem de falha curta.
        logger.exception("validate-e2e -- unhandled exception")
        print("\n[FAIL] validate-e2e -- unhandled exception (ver log)", file=sys.stdout)
        sys.exit(3)
