"""Parser e persistencia de Agendamentos.csv (Caminho B, Fase 6).

Le ``data/new/Agendamentos.csv`` e produz:

  * ``appointments`` (1 row por linha do CSV — 1 sessao pode ter N items)
  * ``appointment_items`` (N rows por appointment — produto cartesiano
    entre os valores de ``Orcamento`` e ``Agendamento``)

Decisao de design: quando uma linha tem multi-valor em ``Orcamento``
(ex.: ``"3760573, 3858738"``) e/ou ``Agendamento``
(ex.: ``"Morpheus - FORMA V, Morpheus - V TONE"``), geramos items via
**produto cartesiano** limitado (cap de 50 items por linha para evitar
explosao em CSVs malformados). O ``appointments.appointment_raw``
guarda a string original (com virgulas) para a Ficha exibir fielmente.

Edge cases tratados:
  * ``Orcamento`` vazio / ``"-"`` → item com ``budget_code=None`` (1 item).
  * ``Agendamento`` vazio → item com ``raw_item="(s/ descrição)"``.
  * Ambos vazios → linha descartada (``rows_skipped += 1``).
  * ``Status`` mapeado verbatim — o v1 ja' tem "Agendado", "Atendido",
    "Cancelado" no badge da Ficha.

N7 (exception handling):
  * :func:`parse_agendamentos_csv` e' boundary — captura erros de I/O
    e parsing, re-emite como :class:`CsvImportError` (PT-BR).
  * :func:`persist_agendamentos` resolve pacientes via
    :func:`resolve_patient` e propaga erros de dominio.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.csv_importer.dedup import (
    PatientNotFoundError,
    resolve_patient,
)
from src.csv_importer.frequencia import CsvImportError
from src.csv_importer.parse import (
    parse_br_date_range,
    split_multi,
)
from src.data_layer import append_row, next_id

logger = logging.getLogger(__name__)

__all__ = [
    "AppointmentItem",
    "AppointmentCandidate",
    "AgendamentosParseResult",
    "parse_agendamentos_csv",
    "persist_agendamentos",
]


# Sentinel para coluna ``category`` em items (D5 — Fase 6 nao categoriza)
DEFAULT_ITEM_RAW_FALLBACK = "(s/ descrição)"
DEFAULT_ITEM_STATUS_FALLBACK = "Agendado"

# Cap de seguranca para cartesian product
MAX_ITEMS_PER_LINE = 50


# ---------------------------------------------------------------------------
# Intermediate dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppointmentItem:
    """1 item dentro de uma sessao (1 procedimento x 1 orcamento)."""

    orcamento: str | None  # None se CSV tinha "-" ou vazio
    raw_item: str


@dataclass(frozen=True)
class AppointmentCandidate:
    """1 sessao (1 linha do CSV)."""

    appointment_code: str
    patient_name: str
    phone: str  # apenas contexto — nao persiste no v1
    appointment_start: pd.Timestamp  # pd.NaT se Data vazia
    appointment_end: pd.Timestamp  # pd.NaT se Data vazia
    appointment_raw: str  # string original de "Agendamento"
    professional: str
    scheduled_by: str
    status: str
    items: tuple[AppointmentItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgendamentosParseResult:
    """Resultado de :func:`parse_agendamentos_csv`."""

    candidates: tuple[AppointmentCandidate, ...]
    rows_skipped: int = 0


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _is_sentinel_orcamento(value: str) -> bool:
    """``"-"`` ou vazio → orcamento sentinela (None no item)."""
    return not value or value.strip() in ("", "-")


def _normalize_status(raw: str) -> str:
    """Status do CSV → verbatim (v1 ja' aceita os valores conhecidos)."""
    if not raw or not isinstance(raw, str):
        return DEFAULT_ITEM_STATUS_FALLBACK
    return raw.strip()


# ---------------------------------------------------------------------------
# Cartesian product
# ---------------------------------------------------------------------------


def _explode_items(
    orcamento_raw: str, agendamento_raw: str
) -> tuple[AppointmentItem, ...]:
    """Constroi items via produto cartesiano limitado.

    Regras:
      * Se ``Orcamento`` E ``Agendamento`` estao vazios → ``tuple()``
        (linha descartada pelo caller; nao geramos item sintetico).
      * ``Orcamento`` vazio (apenas) → ``[None]`` na lista de budgets.
      * ``Agendamento`` vazio (apenas) → ``[DEFAULT_ITEM_RAW_FALLBACK]``
        na lista de procedimentos.
      * Cap MAX_ITEMS_PER_LINE: se len(budgets) * len(procs) > cap,
        trunca e loga warning.
    """
    orcamento_blank = _is_sentinel_orcamento(orcamento_raw)
    agendamento_blank = not agendamento_raw or agendamento_raw.strip() in ("", "-")

    if orcamento_blank and agendamento_blank:
        # Linha sem conteudo util — caller descarta.
        return ()

    if orcamento_blank:
        budgets: list[str | None] = [None]
    else:
        budgets = [b for b in split_multi(orcamento_raw) if b and b != "-"]

    raw_items = split_multi(agendamento_raw)
    procs = raw_items if raw_items else [DEFAULT_ITEM_RAW_FALLBACK]

    total = len(budgets) * len(procs)
    if total > MAX_ITEMS_PER_LINE:
        logger.warning(
            "Linha de Agendamentos excedeu cap de %d items (%dx%d) — truncando",
            MAX_ITEMS_PER_LINE, len(budgets), len(procs),
        )
        budgets = budgets[:MAX_ITEMS_PER_LINE]
        procs = procs[: MAX_ITEMS_PER_LINE // max(len(budgets), 1)]

    items = tuple(
        AppointmentItem(orcamento=b, raw_item=p) for b in budgets for p in procs
    )
    return items


# ---------------------------------------------------------------------------
# Parser (boundary)
# ---------------------------------------------------------------------------


_REQUIRED_COLUMNS = (
    "Código",
    "Paciente",
    "Telefone",
    "Origem",
    "Orçamento",
    "Data",
    "Agendamento",
    "Profissional",
    "Agendado por",
    "Status",
    "Data da criação",
)


def parse_agendamentos_csv(path: str | Path) -> AgendamentosParseResult:
    """Le o CSV e retorna candidatos (sem persistir).

    Cada linha do CSV vira 1 :class:`AppointmentCandidate` com N items
    (cartesian product). Linhas com ``Orcamento`` E ``Agendamento``
    vazios sao descartadas.

    Args:
      path: caminho do CSV.

    Returns:
      :class:`AgendamentosParseResult` com ``candidates`` e ``rows_skipped``.

    Raises:
      CsvImportError: arquivo invalido / faltando coluna obrigatoria.
    """
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except FileNotFoundError as exc:
        raise CsvImportError(
            f"Arquivo de agendamentos nao encontrado: {path!s}"
        ) from exc
    except PermissionError as exc:
        raise CsvImportError(
            f"Sem permissao para ler o arquivo de agendamentos: {path!s}"
        ) from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise CsvImportError(
            f"Falha ao parsear CSV de agendamentos: {exc}"
        ) from exc
    except OSError as exc:
        raise CsvImportError(
            f"Erro de I/O ao ler CSV de agendamentos: {exc}"
        ) from exc

    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise CsvImportError(
            f"CSV de agendamentos sem coluna(s) obrigatoria(s): {missing}. "
            f"Esperado: {_REQUIRED_COLUMNS}."
        )

    candidates: list[AppointmentCandidate] = []
    rows_skipped = 0

    for _, row in df.iterrows():
        try:
            appointment_code = str(row["Código"]).strip()
            paciente = str(row["Paciente"]).strip()
            orcamento_raw = str(row["Orçamento"]).strip()
            agendamento_raw = str(row["Agendamento"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Linha CSV de agendamentos pulada: %s", exc)
            rows_skipped += 1
            continue

        if not appointment_code:
            rows_skipped += 1
            continue
        if not paciente:
            rows_skipped += 1
            continue

        items = _explode_items(orcamento_raw, agendamento_raw)
        if not items:
            rows_skipped += 1
            continue

        start, end = parse_br_date_range(str(row["Data"]))
        cand = AppointmentCandidate(
            appointment_code=appointment_code,
            patient_name=paciente,
            phone=str(row["Telefone"]).strip(),
            appointment_start=start,
            appointment_end=end,
            appointment_raw=agendamento_raw,
            professional=str(row["Profissional"]).strip(),
            scheduled_by=str(row["Agendado por"]).strip(),
            status=_normalize_status(str(row["Status"])),
            items=items,
        )
        candidates.append(cand)

    return AgendamentosParseResult(
        candidates=tuple(candidates), rows_skipped=rows_skipped
    )


# ---------------------------------------------------------------------------
# Row builders (puros — N7 E5)
# ---------------------------------------------------------------------------


def _build_appointment_row(
    appointment_id: str, patient_id: str, cand: AppointmentCandidate
) -> dict:
    """Constroi row para ``appointments`` (1 por candidate)."""
    # ``budget_codes`` armazena CSV string original para a Ficha exibir
    # fielmente (ex: ``"3760573, 3858738"``).
    budgets_str = ",".join(
        str(it.orcamento) for it in cand.items if it.orcamento
    ) or None
    start_ts = cand.appointment_start if not pd.isna(cand.appointment_start) else pd.NaT
    end_ts = cand.appointment_end if not pd.isna(cand.appointment_end) else pd.NaT
    return {
        "appointment_id": appointment_id,
        "appointment_code": cand.appointment_code,
        "patient_id": patient_id,
        "budget_codes": budgets_str,
        "appointment_start": start_ts,
        "appointment_end": end_ts,
        "appointment_raw": cand.appointment_raw,
        "professional": cand.professional,
        "scheduled_by": cand.scheduled_by,
        "status": cand.status,
    }


def _build_appointment_item_row(
    item_id: str,
    appointment_id: str,
    patient_id: str,
    item: AppointmentItem,
    cand: AppointmentCandidate,
) -> dict:
    """Constroi row para ``appointment_items`` (N por candidate)."""
    start_ts = cand.appointment_start if not pd.isna(cand.appointment_start) else pd.NaT
    return {
        "appointment_item_id": item_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "budget_code": item.orcamento,
        "raw_item": item.raw_item,
        "category": None,
        "status": cand.status,
        "appointment_start": start_ts,
        "professional": cand.professional,
    }


# ---------------------------------------------------------------------------
# Persist (boundary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgendamentosPersistResult:
    """Resumo do que foi inserido."""

    appointments_inserted: int
    items_inserted: int
    patient_errors: tuple[PatientNotFoundError, ...] = field(default_factory=tuple)


def persist_agendamentos(
    data: dict,
    parsed: AgendamentosParseResult,
) -> AgendamentosPersistResult:
    """Resolve pacientes + append rows em ``data_layer``.

    Fluxo:
      1. Para cada candidate, resolve ``patient_id`` via
         :func:`resolve_patient`.
      2. Mint ``appointment_id`` / ``appointment_item_id``.
      3. Append 1 appointment + N items.

    Agendamentos NAO tem dedup natural (cada linha do CSV e' um evento
    novo) — sempre insere. Duplicatas seriam ruido humano no IClinic
    export (mesmo codigo = mesma sessao) — se o operador re-rodar o
    import, vai duplicar. Mitigacao futura (Fase 7): dedup por
    ``(appointment_code, appointment_start)``.

    Raises:
      PatientNotFoundError: erros sao coletados em ``patient_errors``
        e o import continua com os candidates seguintes.
    """
    appointments_inserted = 0
    items_inserted = 0
    patient_errors: list[PatientNotFoundError] = []

    for cand in parsed.candidates:
        try:
            patient_id = resolve_patient(data, cand.patient_name, cand.appointment_code)
        except PatientNotFoundError as exc:
            patient_errors.append(exc)
            logger.error(
                "Paciente nao encontrado em agendamentos: %r (codigo=%r) — pulado",
                cand.patient_name, cand.appointment_code,
            )
            continue

        appointment_id = next_id("appointments")
        item_ids = [next_id("appointment_items") for _ in cand.items]

        try:
            append_row(
                "appointments",
                _build_appointment_row(appointment_id, patient_id, cand),
            )
        except Exception as exc:
            logger.error("append_row(appointments) falhou: %s", exc)
            raise

        for item, item_id in zip(cand.items, item_ids, strict=True):
            append_row(
                "appointment_items",
                _build_appointment_item_row(item_id, appointment_id, patient_id, item, cand),
            )
            items_inserted += 1
        appointments_inserted += 1

    return AgendamentosPersistResult(
        appointments_inserted=appointments_inserted,
        items_inserted=items_inserted,
        patient_errors=tuple(patient_errors),
    )
