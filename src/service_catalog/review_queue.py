"""Fila de revisao de servicos nao-classificados (MVP Jornada Clinica, Fase 1).

Quando o ``excel_importer`` (Fase 3) ou o ``pdf_importer`` (Fase 2)
encontra um servico que NAO consta em ``service_catalog``, ele o
enfileira aqui via :func:`enqueue_unknown_service`. A equipe
administrativa revisa a fila e decide:
  * classificar (criar entrada em ``service_catalog``) -> ``status=classified``
  * ignorar (ruido / duplicata / erro de digitacao) -> ``status=ignored``
  * deixar pendente -> ``status=pending``

Esta implementacao e' apenas o esqueleto da Fase 1 — o UI de revisao
entra na Fase 6 (junto com o painel de alertas).

Idempotencia:
  - Se o mesmo ``service_name`` ja' existe na fila com
    ``status=pending``, :func:`enqueue_unknown_service` apenas
    incrementa ``occurrences`` e atualiza ``last_seen_at``. Nao
    duplica.
  - Se existe com ``status=classified`` ou ``ignored``, nao faz nada
    (assume que a equipe ja' decidiu).

N7 (exception handling): enqueue nao levanta; coleta errors via
:class:`EnqueueResult`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.data_layer import append_row, load_table, next_id, update_row
from src.service_catalog.types import ReviewEntry, ReviewStatus, SourceTag

logger = logging.getLogger(__name__)

__all__ = [
    "EnqueueResult",
    "enqueue_unknown_service",
    "list_review_queue",
    "mark_review_entry",
]


@dataclass(frozen=True)
class EnqueueResult:
    """Resultado de :func:`enqueue_unknown_service`."""

    action: str  # 'inserted' | 'incremented' | 'skipped'
    review_id: str | None  # id da entry (None se skipped)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_review_queue(
    status: ReviewStatus | None = None,
) -> list[ReviewEntry]:
    """Lista entries da fila. Filtro opcional por status."""
    try:
        df = load_table("service_review_queue")
    except Exception as exc:
        logger.error("list_review_queue: load_table falhou: %s", exc)
        return []
    if df.empty:
        return []
    if status is not None and "status" in df.columns:
        df = df[df["status"].astype(str) == status]
    if df.empty:
        return []
    entries: list[ReviewEntry] = []
    for _, row in df.iterrows():
        entries.append(
            ReviewEntry(
                id=str(row.get("id", "")),
                service_name=str(row.get("service_name", "")),
                source=str(row.get("source", "excel_import")),  # type: ignore[arg-type]
                occurrences=_maybe_int(row.get("occurrences")),
                first_seen_at=(
                    row.get("first_seen_at")
                    if not pd.isna(row.get("first_seen_at"))
                    else None
                ),
                last_seen_at=(
                    row.get("last_seen_at")
                    if not pd.isna(row.get("last_seen_at"))
                    else None
                ),
                status=str(row.get("status", "pending")),  # type: ignore[arg-type]
            )
        )
    return entries


def _maybe_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _normalize_service_name(name: str) -> str:
    """Lowercase + trim + colapsa whitespace para comparacao idempotente.

    Mantem acentos (decisao do Caminho B Fase 6 — ver
    ``src.csv_importer.parse.normalize_name``).
    """
    if not isinstance(name, str):
        return ""
    return " ".join(name.strip().lower().split())


def _find_pending_by_name(
    df: pd.DataFrame, normalized: str
) -> str | None:
    """Retorna o id da entry pending com mesmo service_name normalizado."""
    if df.empty or "service_name" not in df.columns or "status" not in df.columns:
        return None
    pending = df[df["status"].astype(str) == "pending"]
    if pending.empty:
        return None
    matches = pending[
        pending["service_name"].astype(str).apply(_normalize_service_name)
        == normalized
    ]
    if matches.empty:
        return None
    return str(matches.iloc[0]["id"])


def enqueue_unknown_service(
    service_name: str,
    source: SourceTag,
    seen_at: pd.Timestamp | None = None,
) -> EnqueueResult:
    """Enfileira um servico nao-classificado. Idempotente.

    Args:
        service_name: nome como veio no Excel/PDF.
        source: ``excel_import`` ou ``pdf_import``.
        seen_at: timestamp do avistamento (default = now).

    Returns:
        :class:`EnqueueResult` com ``action`` (``inserted`` /
        ``incremented`` / ``skipped``) e ``review_id``.
    """
    if not service_name or not service_name.strip():
        return EnqueueResult(action="skipped", review_id=None)

    normalized = _normalize_service_name(service_name)
    now = seen_at or pd.Timestamp.today()

    try:
        df = load_table("service_review_queue")
    except Exception as exc:
        logger.error(
            "enqueue_unknown_service: load_table falhou para %r: %s",
            service_name,
            exc,
        )
        return EnqueueResult(action="skipped", review_id=None)

    # 1) Ja' existe pending com mesmo nome? -> incrementa occurrences.
    existing_id = _find_pending_by_name(df, normalized)
    if existing_id is not None:
        try:
            row = df[df["id"].astype(str) == existing_id].iloc[0]
            current_occ = _maybe_int(row.get("occurrences")) or 0
            update_row(
                "service_review_queue",
                "id",
                existing_id,
                {
                    "occurrences": current_occ + 1,
                    "last_seen_at": now,
                },
            )
            logger.info(
                "review_queue: incrementado %s (occurrences=%d)",
                existing_id,
                current_occ + 1,
            )
            return EnqueueResult(action="incremented", review_id=existing_id)
        except Exception as exc:
            logger.error(
                "review_queue: falha ao incrementar %s: %s", existing_id, exc
            )
            return EnqueueResult(action="skipped", review_id=existing_id)

    # 2) Nova entry.
    try:
        new_id = next_id("service_review_queue")
    except Exception as exc:
        logger.error("review_queue: next_id falhou: %s", exc)
        return EnqueueResult(action="skipped", review_id=None)

    try:
        append_row(
            "service_review_queue",
            {
                "id": new_id,
                "service_name": service_name.strip(),
                "source": source,
                "occurrences": 1,
                "first_seen_at": now,
                "last_seen_at": now,
                "status": "pending",
            },
        )
        logger.info("review_queue: inserido %s (%r)", new_id, service_name)
        return EnqueueResult(action="inserted", review_id=new_id)
    except Exception as exc:
        logger.error(
            "review_queue: falha ao inserir %s: %s", service_name, exc
        )
        return EnqueueResult(action="skipped", review_id=None)


def mark_review_entry(review_id: str, status: ReviewStatus) -> bool:
    """Marca uma entry como ``classified`` ou ``ignored``.

    Retorna ``True`` se atualizou, ``False`` se nao encontrou.
    """
    try:
        df = load_table("service_review_queue")
    except Exception as exc:
        logger.error("mark_review_entry: load_table falhou: %s", exc)
        return False
    if df.empty or "id" not in df.columns:
        return False
    if not (df["id"].astype(str) == str(review_id)).any():
        return False
    try:
        update_row(
            "service_review_queue",
            "id",
            review_id,
            {"status": status},
        )
        logger.info("review_queue: %s -> %s", review_id, status)
        return True
    except Exception as exc:
        logger.error("mark_review_entry: update_row falhou: %s", exc)
        return False