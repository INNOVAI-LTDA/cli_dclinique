"""Parser e persistencia do Relatorio de frequencia (Caminho B, Fase 6).

Le ``data/new/Relatorio de frequencia.csv`` e produz:

  * ``treatment_plans`` (1 row por Paciente + Orcamento)
  * ``treatment_plan_items`` (N rows por plan, 1 por Procedimento)
  * ``execution_summary`` (N rows por plan — read-model projection)

Decisao de design (D2): a chave natural do plan no CSV e' ``(patient,
orcamento)`` — o orcamento (budget_code) identifica unicamente um plano,
independente da data de emissao. Isto difere do PDF (que usa
``issue_date``) porque o relatorio do IClinic traz orcamento explicito.

Decisao de design (D5): ``frequency_type``, ``category`` e
``needs_manual_review`` ficam None nos items importados — o CSV nao
traz essa informacao; derivacao heuristica fica para Fase 7.

N7 (exception handling):
  * :func:`parse_frequencia_csv` e' boundary — captura excecoes de I/O
    e parsing do pandas, re-emite como :class:`CsvImportError` (PT-BR).
  * :func:`persist_frequencia` resolve pacientes via :func:`resolve_patient`
    e plans via :func:`resolve_plan_key`; levantam excecoes de dominio
    ja' tipadas.
  * Helpers de projecao (build_*) sao puros — N7 E5 (propagate).

Conventions:
  * ``source`` column em items = ``"csv-frequencia"`` (D7 — distingue
    origem na Ficha).
  * ``status`` em ``treatment_plans`` e' mapeado para os valores do v1:
    ``"Em tratamento"`` → ``"Em andamento"``; demais passam verbatim.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.csv_importer.dedup import (
    DuplicatePlanError,
    PatientNotFoundError,
    resolve_patient,
    resolve_plan_key,
)
from src.csv_importer.parse import parse_br_date
from src.data_layer import append_row, next_id

logger = logging.getLogger(__name__)

__all__ = [
    "CsvImportError",
    "FrequencyItem",
    "FrequencyCandidate",
    "FrequenciaParseResult",
    "parse_frequencia_csv",
    "persist_frequencia",
]


# Sentinel para coluna ``source`` em items (D7)
SOURCE_TAG = "csv-frequencia"


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class CsvImportError(RuntimeError):
    """Erro de leitura/parsing do CSV de origem (Relatorio de frequencia).

    Captura :class:`OSError` (arquivo nao encontrado / sem permissao),
    :class:`pd.errors.EmptyDataError`, :class:`pd.errors.ParserError`,
    e :class:`KeyError` (coluna obrigatoria ausente).
    """


# ---------------------------------------------------------------------------
# Intermediate dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrequencyItem:
    """1 linha do CSV (1 procedimento dentro de um plan)."""

    procedimento: str
    sessoes: int | None
    realizadas: int | None
    restantes: int | None


@dataclass(frozen=True)
class FrequencyCandidate:
    """1 plan (Paciente + Orcamento) com seus items agregados."""

    patient_name: str
    orcamento: str
    issue_date: pd.Timestamp  # pd.NaT se vazio
    status: str
    items: tuple[FrequencyItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FrequenciaParseResult:
    """Resultado de :func:`parse_frequencia_csv`."""

    candidates: tuple[FrequencyCandidate, ...]
    rows_skipped: int = 0  # linhas descartadas (orcamento vazio, etc.)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


# Mapa CSV → v1 (treatment_plans.status). Valores desconhecidos passam
# verbatim (logamos warning para a UI revisar).
_STATUS_MAP: dict[str, str] = {
    "Em tratamento": "Em andamento",
    "Não iniciado": "Não iniciado",
    "Concluído": "Concluído",
    "Cancelado": "Cancelado",
}


def _normalize_status(raw: str) -> str:
    """Mapeia ``status`` do CSV para o valor canonico do v1."""
    if not raw or not isinstance(raw, str):
        return "Não iniciado"
    mapped = _STATUS_MAP.get(raw.strip(), raw.strip())
    if mapped != raw.strip() and raw.strip() not in _STATUS_MAP:
        logger.warning("Status do CSV nao mapeado: %r (passou verbatim)", raw)
    return mapped


def _coerce_int(value: object) -> int | None:
    """Coerce valor para ``int`` ou ``None`` (sem levantar)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Parser (boundary)
# ---------------------------------------------------------------------------


_REQUIRED_COLUMNS = (
    "Paciente",
    "Criação do plano",
    "Procedimento",
    "Status",
    "Sessões",
    "Realizadas",
    "Restantes",
    "Orçamento",
)


def parse_frequencia_csv(path: str | Path) -> FrequenciaParseResult:
    """Le o CSV e retorna candidatos intermediarios (sem persistir).

    Agrega linhas por ``(Paciente, Orcamento)``: cada combinacao unica
    vira 1 :class:`FrequencyCandidate` com seus items agregados.
    Linhas com Orcamento vazio sao descartadas (plan sem budget e'
    anonimo e nao pode ser dedupado).

    Args:
      path: caminho do CSV (string ou ``pathlib.Path``).

    Returns:
      :class:`FrequenciaParseResult` com ``candidates`` (tupla) e
      ``rows_skipped`` (contador).

    Raises:
      CsvImportError: se o arquivo nao puder ser lido, estiver vazio,
        ou faltar coluna obrigatoria.
    """
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except FileNotFoundError as exc:
        raise CsvImportError(
            f"Arquivo do relatorio de frequencia nao encontrado: {path!s}"
        ) from exc
    except PermissionError as exc:
        raise CsvImportError(
            f"Sem permissao para ler o relatorio de frequencia: {path!s}"
        ) from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise CsvImportError(
            f"Falha ao parsear CSV de frequencia: {exc}"
        ) from exc
    except OSError as exc:
        raise CsvImportError(
            f"Erro de I/O ao ler CSV de frequencia: {exc}"
        ) from exc

    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CsvImportError(
            f"CSV de frequencia sem coluna(s) obrigatoria(s): {missing}. "
            f"Esperado: {_REQUIRED_COLUMNS}."
        )

    # Agregacao por (Paciente, Orcamento) preservando ordem de aparicao
    grouped: dict[tuple[str, str], list[FrequencyItem]] = {}
    issue_dates: dict[tuple[str, str], pd.Timestamp] = {}
    statuses: dict[tuple[str, str], str] = {}
    rows_skipped = 0

    for _, row in df.iterrows():
        try:
            paciente = str(row["Paciente"]).strip()
            orcamento = str(row["Orçamento"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Linha CSV de frequencia pulada (coluna invalida): %s", exc)
            rows_skipped += 1
            continue

        if not paciente:
            rows_skipped += 1
            continue
        if not orcamento or orcamento == "-":
            # Plan sem budget_code e' anonimo — descartado (D2).
            rows_skipped += 1
            continue

        key = (paciente, orcamento)
        item = FrequencyItem(
            procedimento=str(row["Procedimento"]).strip(),
            sessoes=_coerce_int(row["Sessões"]),
            realizadas=_coerce_int(row["Realizadas"]),
            restantes=_coerce_int(row["Restantes"]),
        )
        grouped.setdefault(key, []).append(item)

        if key not in issue_dates:
            issue_dates[key] = parse_br_date(str(row["Criação do plano"]))
            statuses[key] = str(row["Status"]).strip()

    candidates = tuple(
        FrequencyCandidate(
            patient_name=paciente,
            orcamento=orcamento,
            issue_date=issue_dates[(paciente, orcamento)],
            status=_normalize_status(statuses[(paciente, orcamento)]),
            items=tuple(items),
        )
        for (paciente, orcamento), items in grouped.items()
    )
    return FrequenciaParseResult(candidates=candidates, rows_skipped=rows_skipped)


# ---------------------------------------------------------------------------
# Row builders (puros — N7 E5: propagate)
# ---------------------------------------------------------------------------


def _build_plan_row(
    plan_id: str, patient_id: str, candidate: FrequencyCandidate
) -> dict:
    """Constroi row para ``treatment_plans``."""
    return {
        "plan_id": plan_id,
        "patient_id": patient_id,
        "budget_code": candidate.orcamento,
        "issue_date": candidate.issue_date if not pd.isna(candidate.issue_date) else pd.NaT,
        "start_date": candidate.issue_date if not pd.isna(candidate.issue_date) else pd.NaT,
        "end_date": pd.NaT,
        "status": candidate.status,
        "main_goal": candidate.items[0].procedimento if candidate.items else None,
        "is_renewal": False,
        "notes": f"Importado de Relatorio de frequencia ({len(candidate.items)} item(s))",
    }


def _build_item_row(
    item_id: str, plan_id: str, patient_id: str, orcamento: str,
    item: FrequencyItem,
) -> dict:
    """Constroi row para ``treatment_plan_items``."""
    return {
        "plan_item_id": item_id,
        "plan_id": plan_id,
        "patient_id": patient_id,
        "budget_code": orcamento,
        "raw_name": item.procedimento,
        "category": None,
        "sessions_expected": item.sessoes,
        "frequency_text": None,
        "frequency_type": None,
        "source": SOURCE_TAG,
        "needs_manual_review": False,
    }


def _build_execution_row(
    execution_id: str, plan_id: str, patient_id: str, orcamento: str,
    item: FrequencyItem, plan_created_at: pd.Timestamp,
) -> dict:
    """Constroi row para ``execution_summary`` (read-model projection).

    Status default: ``"Aguardando início"`` (mesmo valor que o PDF importer
    usa em ``src.pdf_importer.persist._DEFAULT_EXEC_STATUS``).
    """
    return {
        "execution_id": execution_id,
        "patient_id": patient_id,
        "plan_id": plan_id,
        "budget_code": orcamento,
        "procedure_raw": item.procedimento,
        "procedure_category": None,
        "status": "Aguardando início",
        "sessions_expected": item.sessoes,
        "sessions_completed": item.realizadas or 0,
        "sessions_remaining": item.restantes if item.restantes is not None else item.sessoes,
        "plan_created_at": plan_created_at if not pd.isna(plan_created_at) else pd.NaT,
        "frequency_type": None,
    }


# ---------------------------------------------------------------------------
# Persist (boundary — captura dedup errors e propaga)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrequenciaPersistResult:
    """Resumo do que foi inserido."""

    plans_inserted: int
    items_inserted: int
    executions_inserted: int
    patient_errors: tuple[PatientNotFoundError, ...] = field(default_factory=tuple)
    plan_errors: tuple[DuplicatePlanError, ...] = field(default_factory=tuple)


def persist_frequencia(
    data: dict,
    parsed: FrequenciaParseResult,
) -> FrequenciaPersistResult:
    """Resolve pacientes + dedup + append rows em ``data_layer``.

    Fluxo:
      1. Para cada candidate, resolve ``patient_id`` via
         :func:`resolve_patient` (pode levantar :class:`PatientNotFoundError`).
      2. Verifica duplicata de plan via :func:`resolve_plan_key` (pode
         levantar :class:`DuplicatePlanError`).
      3. Mint ``plan_id`` / ``item_id`` / ``execution_id`` via
         :func:`src.data_layer.next_id`.
      4. Append das rows (1 plan + N items + N executions por candidate).

    Atomicidade: N7 E6 (boundary) — **nao** envolve tudo em 1 transacao
    (data layer CSV nao tem transacao). Se um candidate falhar no meio,
    os anteriores permanecem. O caller deve revisar ``FrequenciaPersistResult``
    para detectar erros parciais.

    Raises:
      PatientNotFoundError: se **algum** paciente nao for encontrado.
        O caller pode decidir se quer parar ou continuar (skip).
      DuplicatePlanError: se **algum** plan ja' existir. Mesmo semantica.
    """
    plans_inserted = 0
    items_inserted = 0
    executions_inserted = 0
    patient_errors: list[PatientNotFoundError] = []
    plan_errors: list[DuplicatePlanError] = []

    for cand in parsed.candidates:
        try:
            patient_id = resolve_patient(data, cand.patient_name, cand.orcamento)
        except PatientNotFoundError as exc:
            patient_errors.append(exc)
            logger.error(
                "Paciente nao encontrado: %r (orcamento=%r) — candidato pulado",
                cand.patient_name, cand.orcamento,
            )
            continue

        try:
            resolve_plan_key(data, patient_id, cand.orcamento)
            # Se chegou aqui sem raise, e' plan novo.
        except DuplicatePlanError as exc:
            plan_errors.append(exc)
            logger.error(
                "Plan duplicado (patient=%r, orcamento=%r, existing=%r) — pulado",
                patient_id, cand.orcamento, exc.existing_plan_id,
            )
            continue

        # Mint IDs
        plan_id = next_id("treatment_plans")
        # Mint item + execution IDs uma vez por plan (mais barato)
        item_ids = [next_id("treatment_plan_items") for _ in cand.items]
        execution_ids = [next_id("execution_summary") for _ in cand.items]

        plan_row = _build_plan_row(plan_id, patient_id, cand)
        try:
            append_row("treatment_plans", plan_row)
        except Exception as exc:
            logger.error("append_row(treatment_plans) falhou: %s", exc)
            raise

        for item, item_id, execution_id in zip(cand.items, item_ids, execution_ids, strict=True):
            append_row(
                "treatment_plan_items",
                _build_item_row(item_id, plan_id, patient_id, cand.orcamento, item),
            )
            append_row(
                "execution_summary",
                _build_execution_row(
                    execution_id, plan_id, patient_id, cand.orcamento,
                    item, cand.issue_date,
                ),
            )
            items_inserted += 1
            executions_inserted += 1
        plans_inserted += 1

    return FrequenciaPersistResult(
        plans_inserted=plans_inserted,
        items_inserted=items_inserted,
        executions_inserted=executions_inserted,
        patient_errors=tuple(patient_errors),
        plan_errors=tuple(plan_errors),
    )
