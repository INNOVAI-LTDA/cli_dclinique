"""Resolve pacientes via nome normalizado (Caminho B, Fase 6).

O CSV do IClinic NAO traz CPF — unica chave natural disponivel e' o
nome do paciente. Esta camada:

  1. Normaliza o nome do CSV via :func:`src.csv_importer.parse.normalize_name`.
  2. Compara com a coluna ``patients.normalized_name`` do data layer
     (preenchida pela ficha no momento do cadastro).
  3. Retorna o ``patient_id`` se encontrado; senao levanta
     :class:`PatientNotFoundError`.

Plano (D3 — Fase 6): **insert-only**. Nao ha' replace de paciente nem
de plan — CSVs do mundo real nao tem sinal claro de "atualizar vs
inserir" e a Fase 6 prefere ser conservadora (append sem destruir dados
existentes). Replace entra na Fase 7 com auditoria de historico.

Decisao de design: a busca e' **exata** sobre ``normalized_name``.
Tolerancia a typo (Levenshtein <= 2) e' DEFERIDA para Fase 7. Por enquanto,
se o CSV trouxer "Kélly" e o cadastro tem "Kelly", o import falha com
erro claro apontando o paciente nao encontrado — o operador resolve
manualmente ou ajusta o cadastro.

N7 (exception handling): cada call externo (``data.get``, ``iterrows``,
comparacao de string) envolvido em try/except especifico. Mensagens em
PT-BR via ``logging``. Excecoes publicas (:class:`PatientNotFoundError`,
:class:`DuplicatePlanError`) sao dataclasses simples com mensagem PT-BR
pronta para a UI exibir.

Convencoes:
  * ``data`` e' o ``DataDict`` retornado por ``src.data_layer.load_all()``.
  * IDs sao strings (``pat_new_NNN``) — nao ints.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.csv_importer.parse import normalize_name

logger = logging.getLogger(__name__)

__all__ = [
    "PatientNotFoundError",
    "DuplicatePlanError",
    "find_patient_by_name",
    "find_plan_by_budget",
    "resolve_patient",
    "resolve_plan_key",
]


# ---------------------------------------------------------------------------
# Public exceptions (dataclasses para UI amigavel)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatientNotFoundError(KeyError):
    """Paciente do CSV nao consta no cadastro (``patients.csv``).

    Atributos:
      * ``name``: nome como veio do CSV (pode ter typo).
      * ``orcamento``: orcamento da linha que disparou a busca
        (contexto para o operador rastrear o CSV de origem).
      * ``normalized``: como o nome foi normalizado (para o operador
        comparar com o cadastro).
    """

    name: str
    orcamento: str
    normalized: str

    def __str__(self) -> str:  # pragma: no cover (trivial)
        return (
            f"Paciente nao encontrado no cadastro: {self.name!r} "
            f"(normalizado: {self.normalized!r}, orcamento: {self.orcamento!r}). "
            f"Verifique se o paciente foi cadastrado na Ficha."
        )


@dataclass(frozen=True)
class DuplicatePlanError(ValueError):
    """Plan com ``(patient_id, orcamento)`` ja' existe no data layer.

    Fase 6 (insert-only): importacao deve falhar em vez de duplicar.
    O operador decide: apagar o plan existente via Ficha, ou remover
    a linha do CSV de origem.
    """

    patient_id: str
    orcamento: str
    existing_plan_id: str

    def __str__(self) -> str:  # pragma: no cover (trivial)
        return (
            f"Plan duplicado: paciente={self.patient_id!r} orcamento={self.orcamento!r} "
            f"ja' existe como plan_id={self.existing_plan_id!r}. "
            f"Fase 6 e' insert-only — remova o plan existente ou ajuste o CSV."
        )


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------


def find_patient_by_name(data: dict, name: str) -> str | None:
    """Busca exata por ``normalized_name`` na tabela ``patients``.

    Retorna o ``patient_id`` (string) ou ``None`` se nao encontrado.

    N7: ``data.get(...)`` envolvido em try/except — se a tabela
    ``patients`` nao existir em ``data``, retornamos ``None``
    (mesma semantica de "nao encontrado").

    Caso 2 pacientes distintos normalizem para a mesma chave (colisao
    improvavel mas possivel), retornamos o **primeiro** match e logamos
    warning. Fase 7 pode sofisticar com ranking por ``created_at``.
    """
    try:
        df = data.get("patients")
    except (AttributeError, TypeError) as exc:
        logger.warning("data.get('patients') falhou: %s", exc)
        return None
    if df is None or len(df) == 0:
        return None
    if "normalized_name" not in df.columns or "patient_id" not in df.columns:
        logger.warning(
            "Tabela 'patients' sem coluna 'normalized_name' ou 'patient_id' — "
            "execute scripts/seed_csvs.py ou cadastre um paciente antes."
        )
        return None
    target = normalize_name(name)
    try:
        matches = df[df["normalized_name"] == target]
    except (TypeError, ValueError) as exc:
        logger.warning("Busca por nome falhou: %s", exc)
        return None
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        logger.warning(
            "Multiplos pacientes com normalized_name=%r: %s — usando o primeiro",
            target, matches["patient_id"].tolist(),
        )
    pid = str(matches.iloc[0]["patient_id"])
    return pid


def find_plan_by_budget(
    data: dict, patient_id: str, orcamento: str
) -> str | None:
    """Busca plan existente por ``(patient_id, budget_code)``.

    Retorna o ``plan_id`` (string) ou ``None``. ``orcamento`` vazio
    retorna ``None`` imediatamente — plan sem budget_code e' anonimo
    e nao conflita com nenhum outro plan.
    """
    if not orcamento:
        return None
    try:
        df = data.get("treatment_plans")
    except (AttributeError, TypeError) as exc:
        logger.warning("data.get('treatment_plans') falhou: %s", exc)
        return None
    if df is None or len(df) == 0:
        return None
    if "patient_id" not in df.columns or "budget_code" not in df.columns:
        logger.warning(
            "Tabela 'treatment_plans' sem coluna 'patient_id' ou 'budget_code'."
        )
        return None
    try:
        matches = df[
            (df["patient_id"].astype(str) == patient_id)
            & (df["budget_code"].astype(str) == str(orcamento))
        ]
    except (TypeError, ValueError) as exc:
        logger.warning("Busca por budget_code falhou: %s", exc)
        return None
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        logger.warning(
            "Multiplos plans para (patient_id=%r, budget_code=%r): %s — usando o primeiro",
            patient_id, orcamento, matches["plan_id"].tolist(),
        )
    return str(matches.iloc[0]["plan_id"])


# ---------------------------------------------------------------------------
# Resolve helpers (boundary — levantam excecao se nao resolvem)
# ---------------------------------------------------------------------------


def resolve_patient(
    data: dict, name: str, orcamento: str
) -> str:
    """Resolve ``name`` → ``patient_id`` ou levanta :class:`PatientNotFoundError`.

    Boundary function (N7 E6): captura excecoes internas e re-emite
    como :class:`PatientNotFoundError` (excecao de dominio, com
    contexto para a UI exibir).

    Args:
      data: ``DataDict`` (saida de ``src.data_layer.load_all()``).
      name: nome do paciente como veio do CSV.
      orcamento: orcamento da linha (incluido na excecao para contexto).

    Returns:
      ``patient_id`` (string ``pat_new_NNN`` ou seed).

    Raises:
      PatientNotFoundError: se nenhum paciente com esse ``normalized_name``.
    """
    try:
        pid = find_patient_by_name(data, name)
    except Exception as exc:  # pragma: no cover (defensiva)
        logger.error("find_patient_by_name levantou excecao nao esperada: %s", exc)
        pid = None
    if pid is None:
        raise PatientNotFoundError(
            name=name,
            orcamento=orcamento,
            normalized=normalize_name(name),
        )
    return pid


def resolve_plan_key(
    data: dict, patient_id: str, orcamento: str, *, allow_duplicate: bool = False
) -> str | None:
    """Resolve ``(patient_id, orcamento)`` → ``plan_id`` existente, ou None.

    Args:
      data: ``DataDict``.
      patient_id: ja' resolvido por :func:`resolve_patient`.
      orcamento: codigo do orcamento (budget) vindo do CSV.
      allow_duplicate: se ``False`` (default), levanta
        :class:`DuplicatePlanError` quando o plan ja' existe.
        Se ``True``, apenas retorna o ``plan_id`` existente.

    Returns:
      ``plan_id`` (string) se ja' existe e ``allow_duplicate=True``;
      ``None`` se plan nao existe (sinal para o caller inserir).
    """
    existing = find_plan_by_budget(data, patient_id, orcamento)
    if existing is None:
        return None
    if not allow_duplicate:
        raise DuplicatePlanError(
            patient_id=patient_id,
            orcamento=orcamento,
            existing_plan_id=existing,
        )
    return existing
