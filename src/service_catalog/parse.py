"""Parser de CSV de service_catalog (MVP Jornada Clinica, Fase 1).

Le CSV de entrada (lista ativa de servicos OU lista da Dane) com
colunas canonicas (ver :data:`EXPECTED_SCHEMAS['service_catalog']`)
e retorna uma lista de :class:`ServiceEntry`.

Heuristicas (todas em PT-BR via :mod:`logging`):

  * ``service_code`` vazio ou NaN  -> linha pulada (linha_count++).
  * ``name`` vazio                -> linha pulada.
  * ``classification`` fora de {active, rare, obsolete} -> classificada
    como ``active`` (default conservador) + warning logado.
  * ``category`` vazia ou fora do conjunto -> None + warning logado.
  * ``default_periodicity_days`` vazia ou nao-numerica -> None.
  * ``source`` ausente            -> default ``lista_ativa`` (Q7).

N7 (exception handling): o parser nao levanta. Linhas problematicas
sao puladas com warning; o caller recebe ``(entries, rows_skipped)``
e decide como reportar ao usuario.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.service_catalog.types import (
    Category,
    Classification,
    ServiceEntry,
    SourceTag,
)

logger = logging.getLogger(__name__)

__all__ = ["parse_catalog_csv", "CatalogParseResult"]


# ---------------------------------------------------------------------------
# Defaults + helpers
# ---------------------------------------------------------------------------


_VALID_CLASSIFICATIONS: frozenset[str] = frozenset({"active", "rare", "obsolete"})
_VALID_CATEGORIES: frozenset[str] = frozenset({"injectable", "professional", "other"})
_VALID_SOURCES: frozenset[str] = frozenset(
    {"lista_ativa", "dane", "manual", "excel_import", "pdf_import"}
)

_REQUIRED_COLUMNS: tuple[str, ...] = (
    "service_code",
    "name",
    "classification",
    "category",
    "default_periodicity_days",
    "source",
    "created_at",
)


def _safe_classification(raw: object) -> Classification:
    """Coerce ``raw`` para Classification valida. Default = ``active``."""
    if not isinstance(raw, str):
        return "active"
    value = raw.strip().lower()
    if value in _VALID_CLASSIFICATIONS:
        return value  # type: ignore[return-value]
    logger.warning(
        "classification invalida %r — usando 'active' como default conservador",
        raw,
    )
    return "active"


def _safe_category(raw: object) -> Category | None:
    """Coerce ``raw`` para Category valida. Vazio / fora -> ``None``."""
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if value in _VALID_CATEGORIES:
        return value  # type: ignore[return-value]
    logger.warning(
        "category invalida %r — definida como None (sera revisada manualmente)",
        raw,
    )
    return None


def _safe_periodicity_days(raw: object) -> int | None:
    """Coerce ``raw`` para ``int``. Vazio / nao-numerico -> ``None``."""
    if raw is None:
        return None
    try:
        # Aceita float tipo 7.0; ``is_integer`` evita pegar 7.5.
        f = float(raw)
    except (TypeError, ValueError):
        logger.warning("default_periodicity_days invalido %r — None", raw)
        return None
    if pd.isna(f):
        return None
    if not f.is_integer():
        logger.warning("default_periodicity_days nao-inteiro %r — None", raw)
        return None
    return int(f)


def _safe_source(raw: object, default: SourceTag = "lista_ativa") -> SourceTag:
    """Coerce ``raw`` para SourceTag valida. Default = ``lista_ativa``."""
    if not isinstance(raw, str):
        return default
    value = raw.strip().lower()
    if value in _VALID_SOURCES:
        return value  # type: ignore[return-value]
    logger.warning("source invalido %r — usando %r", raw, default)
    return default


def _safe_created_at(raw: object) -> pd.Timestamp | None:
    """Coerce ``raw`` para ``pd.Timestamp``. Invalido -> ``None``."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, pd.Timestamp):
        return raw
    try:
        ts = pd.to_datetime(raw, errors="coerce")
    except (TypeError, ValueError) as exc:
        logger.warning("created_at invalido %r: %s", raw, exc)
        return None
    if pd.isna(ts):
        return None
    return ts


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


from dataclasses import dataclass, field


@dataclass(frozen=True)
class CatalogParseResult:
    """Resultado de :func:`parse_catalog_csv`.

    Attributes:
        entries: dataclasses :class:`ServiceEntry` validas (prontas para UPSERT).
        rows_skipped: quantidade de linhas descartadas (CSV malformado).
        rows_total: total de linhas no CSV (incluindo skipped).
    """

    entries: tuple[ServiceEntry, ...]
    rows_skipped: int = 0
    rows_total: int = 0


# ---------------------------------------------------------------------------
# Public parser (boundary — captura erros de I/O)
# ---------------------------------------------------------------------------


def parse_catalog_csv(
    path: str | Path,
    default_source: SourceTag = "lista_ativa",
) -> CatalogParseResult:
    """Le o CSV e retorna entries + estatisticas.

    Args:
        path: caminho do CSV de entrada (lista ativa ou lista da Dane).
        default_source: source aplicado quando a coluna ``source`` do
            CSV vier vazia ou invalida. Default = ``lista_ativa``.
            Use ``dane`` quando o CSV vier da lista da Dane.

    Returns:
        :class:`CatalogParseResult` com entries + contadores.

    Raises:
        FileNotFoundError: arquivo nao existe.
        PermissionError: sem permissao de leitura.
        pd.errors.EmptyDataError / ParserError: CSV invalido.
        UnicodeDecodeError: encoding nao-UTF-8.
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV de catalogo sem coluna(s) obrigatoria(s): {missing}. "
            f"Esperado: {_REQUIRED_COLUMNS}."
        )

    entries: list[ServiceEntry] = []
    rows_skipped = 0

    for _, row in df.iterrows():
        service_code = str(row["service_code"]).strip()
        name = str(row["name"]).strip()
        if not service_code:
            logger.warning("Linha pulada: service_code vazio")
            rows_skipped += 1
            continue
        if not name:
            logger.warning(
                "Linha pulada: name vazio para service_code=%r", service_code
            )
            rows_skipped += 1
            continue

        entries.append(
            ServiceEntry(
                service_code=service_code,
                name=name,
                classification=_safe_classification(row.get("classification")),
                category=_safe_category(row.get("category")),
                default_periodicity_days=_safe_periodicity_days(
                    row.get("default_periodicity_days")
                ),
                source=_safe_source(row.get("source"), default_source),
                created_at=_safe_created_at(row.get("created_at")),
            )
        )

    return CatalogParseResult(
        entries=tuple(entries),
        rows_skipped=rows_skipped,
        rows_total=len(df),
    )