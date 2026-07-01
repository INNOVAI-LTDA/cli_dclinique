"""Catalogo de servicos clinicos (MVP Jornada Clinica, Fase 1).

Modulo responsavel por:
  * Parsing de CSV de entrada (lista ativa / lista da Dane) em
    ``ServiceEntry`` dataclasses (ver :mod:`types`).
  * Persistencia no data layer (CSV ou Postgres Neon) com semantica
    de UPSERT (chave natural = ``service_code``).
  * Fila de revisao para servicos encontrados em Excel/PDF que nao
    estao no catalogo (ver :mod:`review_queue`).

Contexto (MVP):
  Decisao D4 da reuniao de 2026-06-30: a nomenclatura do plano e'
  canonica. Matching em Excel/PDF so' aceita servicos que existam
  no catalogo. Servicos fora do catalogo vao para ``service_review_queue``
  para classificacao manual pela equipe (D4 + §7 da ata).

Restricoes:
  * NUNCA fazer matching semantico agressivo (§7 da ata). Servicos
    fora da whitelist vao para a fila, nao para o calculo principal.
  * PK do catalogo (``service_code``) e' fornecido pelo import
    (codigo externo decidido pela equipe / lista da Dane). Nao passa
    por :func:`src.data_layer.next_id`.
  * PK da fila (``id``) e' gerado por :func:`src.data_layer.next_id`
    com prefixo ``srv_new``.

N7 (exception handling): todos os parsers retornam dataclasses com
campos opcionais em vez de levantar excecao. Mensagens em PT-BR
via :mod:`logging`.
"""
from __future__ import annotations

from src.service_catalog.persist import (
    get_service,
    import_catalog,
    list_catalog,
    upsert_service,
)
from src.service_catalog.review_queue import (
    enqueue_unknown_service,
    list_review_queue,
    mark_review_entry,
)
from src.service_catalog.types import (
    Category,
    Classification,
    ReviewEntry,
    ReviewStatus,
    ServiceEntry,
    SourceTag,
)

__all__ = [
    "Category",
    "Classification",
    "ReviewEntry",
    "ReviewStatus",
    "ServiceEntry",
    "SourceTag",
    "enqueue_unknown_service",
    "get_service",
    "import_catalog",
    "list_catalog",
    "list_review_queue",
    "mark_review_entry",
    "upsert_service",
]