"""Tipos do modulo service_catalog (MVP Jornada Clinica, Fase 1).

Define as dataclasses ``ServiceEntry`` (linha do catalogo) e
``ReviewEntry`` (linha da fila de revisao), mais os Literal types
que restringem os valores validos nas colunas de categoria.

N7 (exception handling): nenhuma dataclass levanta excecao no
``__init__``. Validacao acontece nos parsers, que retornam
``ServiceEntry`` ou pulam a linha (ver :mod:`parse`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

# ---------------------------------------------------------------------------
# Literal types (constraints do schema)
# ---------------------------------------------------------------------------

# Classificacao editorial do servico no catalogo (D4 + matriz do §9 da ata).
Classification = Literal["active", "rare", "obsolete"]

# Categoria clinica do servico. Usada na regra de periodicidade do §6 da ata
# (injetaveis = semanal, profissional = mensal). Nullable porque alguns
# servicos nao se encaixam nessas 3 categorias (ex.: "outros").
Category = Literal["injectable", "professional", "other"]

# Status de uma entrada na fila de revisao.
#   pending    -> apareceu no Excel/PDF mas ainda nao foi classificada
#   classified -> administrador moveu a entrada para o catalogo
#   ignored    -> administrador marcou como ruído (nao vai virar servico)
ReviewStatus = Literal["pending", "classified", "ignored"]

# Origem da entrada (qual fonte produziu a linha).
#   lista_ativa  -> upload da lista ativa de servicos (Jader)
#   dane         -> upload da lista usada pela Dane nos orcamentos
#   manual       -> entrada manual via UI (placeholder, nao implementado na Fase 1)
#   excel_import -> enfileirada pelo excel_importer (Fase 3) por nao estar no catalogo
#   pdf_import   -> enfileirada pelo pdf_importer (Fase 2) por nao estar no catalogo
SourceTag = Literal["lista_ativa", "dane", "manual", "excel_import", "pdf_import"]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceEntry:
    """Uma entrada canonica do catalogo de servicos.

    Campos seguem a ordem das colunas em
    :data:`src.schemas.EXPECTED_SCHEMAS['service_catalog']`.
    """

    service_code: str  # PK — codigo canonico (ex.: "MORPHEUS_FORMA_V")
    name: str  # nome de exibicao (ex.: "Morpheus - FORMA V")
    classification: Classification
    category: Category | None  # nullable — alguns servicos nao se encaixam
    default_periodicity_days: int | None  # nullable — servico pontual
    source: SourceTag
    # Timestamp de importacao. No CSV fica como ISO string ate
    # ``_coerce_dtypes`` converter para ``pd.Timestamp`` no load.
    # Pode ser None se a fonte nao trouxe o valor.
    created_at: pd.Timestamp | None


@dataclass(frozen=True)
class ReviewEntry:
    """Uma entrada da fila de revisao (servico nao-classificado)."""

    id: str  # PK — srv_new_NNN (gerado por next_id)
    service_name: str  # nome como veio no Excel/PDF
    source: SourceTag  # excel_import | pdf_import
    occurrences: int | None  # quantas vezes o servico apareceu (incremental)
    first_seen_at: pd.Timestamp | None
    last_seen_at: pd.Timestamp | None
    status: ReviewStatus