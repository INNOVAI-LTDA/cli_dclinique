"""Persistencia de service_catalog no data layer (MVP Jornada Clinica, Fase 1).

Operacoes:
  * :func:`upsert_service` — INSERT se service_code nao existe,
    UPDATE se ja existe. Idempotente (re-rodar com mesmo CSV nao
    duplica nem perde dados).
  * :func:`import_catalog` — processa resultado de
    :func:`parse_catalog_csv` em batch, retornando
    :class:`ImportResult` com contadores.
  * :func:`list_catalog` — le todo o catalogo via data layer.
  * :func:`get_service` — busca 1 entry por ``service_code``.

Semantica UPSERT no CSV backend:
  - load_table -> DataFrame atual
  - se ``service_code`` existe -> update_row nas colunas nao-PK
  - se nao existe -> append_row com ``created_at`` se estava vazio

Semantica UPSERT no Postgres backend:
  - delega para :func:`src.data_layer.postgres_backend.append_row`
    (que faz INSERT direto). UPDATE nao esta implementado no data
    layer para service_catalog — quando Jader precisar RE-classificar
    um servico, a Fase 1 nao cobre. Cobre na Fase 5 (junto com o
    CRUD de alertas).

N7 (exception handling): todas as chamadas externas estao envolvidas
em try/except especifico. Mensagens em PT-BR via :mod:`logging`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.data_layer import append_row, load_table, update_row
from src.service_catalog.types import ServiceEntry

logger = logging.getLogger(__name__)

__all__ = [
    "ImportResult",
    "get_service",
    "import_catalog",
    "list_catalog",
    "upsert_service",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportResult:
    """Resumo do que foi inserido/atualizado pelo :func:`import_catalog`."""

    inserted: int
    updated: int
    failed: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_catalog() -> pd.DataFrame:
    """Retorna o catalogo inteiro como DataFrame.

    Filtra: nao retorna nada (DataFrame vazio com schema) se a tabela
    nao existir ainda (caso de primeira execucao do script de import).
    """
    return load_table("service_catalog")


def get_service(service_code: str) -> ServiceEntry | None:
    """Busca 1 servico pelo codigo. ``None`` se nao encontrado."""
    try:
        df = load_table("service_catalog")
    except Exception as exc:
        logger.error("get_service: load_table falhou: %s", exc)
        return None
    if df.empty or "service_code" not in df.columns:
        return None
    matches = df[df["service_code"].astype(str) == str(service_code)]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return _row_to_entry(row)


def _row_to_entry(row: pd.Series) -> ServiceEntry:
    """Converte uma linha do DataFrame em :class:`ServiceEntry`."""
    return ServiceEntry(
        service_code=str(row.get("service_code", "")),
        name=str(row.get("name", "")),
        classification=str(row.get("classification", "active")),  # type: ignore[arg-type]
        category=(None if pd.isna(row.get("category")) else str(row.get("category"))),  # type: ignore[arg-type]
        default_periodicity_days=_maybe_int(row.get("default_periodicity_days")),
        source=str(row.get("source", "lista_ativa")),  # type: ignore[arg-type]
        created_at=(row.get("created_at") if not pd.isna(row.get("created_at")) else None),
    )


def _maybe_int(value: object) -> int | None:
    """Converte para int se possivel; senao ``None``."""
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Write — UPSERT
# ---------------------------------------------------------------------------


def upsert_service(entry: ServiceEntry) -> str:
    """Insere ou atualiza 1 servico. Retorna ``service_code``.

    No CSV backend: load_table -> se existe, update_row; senao append_row.
    No Postgres backend: append_row direto (sem ON CONFLICT por enquanto —
    ver nota no modulo docstring sobre Fase 5).

    Auto-preenche ``created_at`` se vier None (usa ``pd.Timestamp.today()``).
    """
    created_at = entry.created_at or pd.Timestamp.today().normalize()

    existing = get_service(entry.service_code)
    row_dict = {
        "service_code": entry.service_code,
        "name": entry.name,
        "classification": entry.classification,
        "category": entry.category,
        "default_periodicity_days": entry.default_periodicity_days,
        "source": entry.source,
        "created_at": created_at,
    }

    if existing is None:
        try:
            append_row("service_catalog", row_dict)
            logger.info("service_catalog: inserido %s", entry.service_code)
        except Exception as exc:
            logger.error(
                "service_catalog: falha ao inserir %s: %s", entry.service_code, exc
            )
            raise
    else:
        # Update only mutable fields (everything except service_code +
        # created_at — created_at e' o timestamp do PRIMEIRO import).
        updates = {k: v for k, v in row_dict.items() if k not in {"service_code", "created_at"}}
        try:
            update_row("service_catalog", "service_code", entry.service_code, updates)
            logger.info("service_catalog: atualizado %s", entry.service_code)
        except Exception as exc:
            logger.error(
                "service_catalog: falha ao atualizar %s: %s", entry.service_code, exc
            )
            raise

    return entry.service_code


def import_catalog(entries: tuple[ServiceEntry, ...]) -> ImportResult:
    """Processa uma lista de :class:`ServiceEntry` em batch.

    Erros em uma linha NAO interrompem o batch — sao coletados em
    ``ImportResult.errors``. Caller decide se quer retry ou rollback.
    """
    inserted = 0
    updated = 0
    failed = 0
    errors: list[str] = []

    for entry in entries:
        existed = get_service(entry.service_code) is not None
        try:
            upsert_service(entry)
        except Exception as exc:
            failed += 1
            errors.append(f"{entry.service_code}: {exc}")
            continue
        if existed:
            updated += 1
        else:
            inserted += 1

    return ImportResult(
        inserted=inserted,
        updated=updated,
        failed=failed,
        errors=tuple(errors),
    )