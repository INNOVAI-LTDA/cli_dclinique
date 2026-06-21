"""Router for the MAP data layer.

Seleciona entre :mod:`postgres_backend` (default, Neon) e
:mod:`csv_backend` (fallback) com base na env var ``DCLINIQUE_BACKEND``.
O backend escolhido e' carregado lazy na primeira chamada a uma
funcao publica, entao carregar este modulo NAO dispara nenhum
import externo (psycopg, streamlit, pandas). A escolha fica cacheada
no modulo (uma instancia de backend por processo).

Public API (identica em ambos os backends):
* :func:`load_all`            — le as 11 tabelas
* :func:`load_table`          — le uma tabela
* :func:`append_row`          — insere uma linha
* :func:`update_row`          — atualiza uma linha
* :func:`next_id`             — deriva o proximo id ``{prefix}_NNN``
* :func:`csv_dir`             — path do CSV (csv mode) ou sentinel
                                ``postgres-neon`` (postgres mode)
* :func:`data_dir`            — alias inverso de ``csv_dir``; disponivel
                                para callers que pensam em "data dir"
                                (a conotacao postgres) em vez de "csv dir"
* :func:`reset_backend_cache` — limpa o cache (uso de testes)

Transitive imports:
  - :mod:`os` (stdlib) e :mod:`typing` (stdlib) sao os unicos imports
    de top-level. Os backends sao importados lazy dentro de
    :func:`_select_backend`. Consequencia: ``import src.data_layer``
    funciona sem qualquer dependencia externa instalada.
"""
from __future__ import annotations

import os
from typing import Any

# Cache de backend por processo. Streamlit roda um processo por sessao
# (em PRD) ou um unico processo (em dev local); em ambos os casos,
# cachear o backend apos a primeira resolucao evita o custo do import
# lazy a cada chamada. ``reset_backend_cache`` e' exposto para testes
# que precisam alternar entre backends no mesmo processo.
_BACKEND_CACHE: dict[str, Any] = {}


def _select_backend() -> Any:
    """Resolve o backend ativo lendo ``DCLINIQUE_BACKEND``.

    Default: ``"postgres"`` (Neon em PRD). ``"csv"`` e' fallback
    explicito para dev sem internet e reproducao de bugs a partir
    de fixtures CSV. Qualquer outro valor levanta :class:`ValueError`
    com mensagem acionavel.
    """
    name = os.environ.get("DCLINIQUE_BACKEND", "postgres")
    if name == "postgres":
        from src.data_layer import postgres_backend as b
        return b
    if name == "csv":
        from src.data_layer import csv_backend as b
        return b
    raise ValueError(
        f"DCLINIQUE_BACKEND invalido: {name!r}. "
        f"Use 'postgres' (default) ou 'csv'."
    )


def _get_backend() -> Any:
    """Retorna o backend ativo. Cacheia apos a primeira resolucao."""
    if "mod" not in _BACKEND_CACHE:
        _BACKEND_CACHE["mod"] = _select_backend()
    return _BACKEND_CACHE["mod"]


def reset_backend_cache() -> None:
    """Limpa o cache do backend. Apenas para testes."""
    _BACKEND_CACHE.clear()


# ---------------------------------------------------------------------------
# Public API — wrappers que delegam ao backend ativo
# ---------------------------------------------------------------------------


def load_all(*args, **kwargs):
    return _get_backend().load_all(*args, **kwargs)


def load_table(*args, **kwargs):
    return _get_backend().load_table(*args, **kwargs)


def append_row(*args, **kwargs):
    return _get_backend().append_row(*args, **kwargs)


def update_row(*args, **kwargs):
    return _get_backend().update_row(*args, **kwargs)


def delete_rows(*args, **kwargs):
    """Delete rows by ``key_column == key_value`` (returns rowcount).

    Wraps :func:`csv_backend.delete_rows` /
    :func:`postgres_backend.delete_rows`. Used by the PDF import
    wizard to clear ``execution_summary`` rows when a plan is being
    replaced (the data-layer ``replace_plan`` only clears
    ``treatment_plan_items`` and ``patient_goals``).
    """
    return _get_backend().delete_rows(*args, **kwargs)


def next_id(*args, **kwargs):
    return _get_backend().next_id(*args, **kwargs)


def next_id_with_prefix(*args, **kwargs):
    """Mint a fresh ``{prefix}_NNN`` id from an arbitrary prefix.

    Wraps :func:`csv_backend.next_id_with_prefix` /
    :func:`postgres_backend.next_id_with_prefix`. Used by the PDF
    importer to generate ``orc_new_NNN`` budget codes that don't
    collide with previously imported plans.
    """
    return _get_backend().next_id_with_prefix(*args, **kwargs)


def replace_plan(*args, **kwargs):
    """Replace an existing plan in place (natural-key dedup).

    Wraps :func:`csv_backend.replace_plan` /
    :func:`postgres_backend.replace_plan`. If no plan matches the
    ``(patient_id, issue_date)`` natural key, returns ``None`` so
    the caller can fall back to a normal insert.
    """
    return _get_backend().replace_plan(*args, **kwargs)


def find_plan_by_issue_date(*args, **kwargs):
    """Look up a plan by its natural key ``(patient_id, issue_date)``.

    Wraps :func:`csv_backend.find_plan_by_issue_date` /
    :func:`postgres_backend.find_plan_by_issue_date`.
    """
    return _get_backend().find_plan_by_issue_date(*args, **kwargs)


def csv_dir(*args, **kwargs):
    """Path do CSV (csv mode) ou sentinel ``postgres-neon`` (postgres mode).

    Mantido o nome ``csv_dir`` para compatibilidade com callers
    existentes (e.g. ``tests/test_ficha_unit.py:67``). Internamente
    roteia para ``backend.csv_dir`` (csv) ou ``backend.data_dir``
    (postgres).
    """
    b = _get_backend()
    if hasattr(b, "csv_dir"):
        return b.csv_dir(*args, **kwargs)
    return b.data_dir(*args, **kwargs)


def data_dir(*args, **kwargs):
    """Sentinel ``postgres-neon`` (postgres mode) ou path do CSV (csv mode).

    Alias inverso de :func:`csv_dir`; ambos funcionam. A escolha entre
    um ou outro e' estetica — :func:`csv_dir` para callers que pensam
    em "csv", :func:`data_dir` para callers que pensam em "data".
    """
    b = _get_backend()
    if hasattr(b, "data_dir"):
        return b.data_dir(*args, **kwargs)
    return b.csv_dir(*args, **kwargs)


__all__ = [
    "load_all",
    "load_table",
    "append_row",
    "update_row",
    "delete_rows",
    "next_id",
    "next_id_with_prefix",
    "replace_plan",
    "find_plan_by_issue_date",
    "csv_dir",
    "data_dir",
    "reset_backend_cache",
]
