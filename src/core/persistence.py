"""Persistence layer for v2-generated alerts (Caminho B, Phase 3).

Motivacao (caminho_b_plano.md §3 Fase 3):
  ``src.core.alerts.detect_frequency_alerts`` produz ``list[dict]`` em
  memoria. Este modulo persiste esses alertas na tabela ``alerts`` v1
  (via :func:`src.data_layer.append_row`) ate' a Fase 8 introduzir a
  entidade v2 ``Alert``.

N7 (exception handling) -- **BOUNDARY FUNCTION** (N7 E6):
  :func:`save_frequency_alerts` e' a unica funcao deste modulo. Ela
  captura excecoes da fronteira I/O (``FileNotFoundError``,
  ``PermissionError``, ``OSError``, ``ValueError`` do schema) e loga
  em PT-BR. NAO levanta -- o caller (pagina Streamlit, script)
  recebe a contagem efetiva e decide o que fazer.

Idempotencia (N7 + design):
  Cada alerta tem ``alert_id`` deterministico
  (``freq_{client_id}_{cd_id}_{priority}`` -- ver alerts.py). Antes
  de inserir, esta funcao verifica se o ``alert_id`` ja' existe em
  ``data['alerts']``. Se existe, pula. Resultado: rodar
  ``detect_frequency_alerts`` + ``save_frequency_alerts`` 2x sobre o
  mesmo dataset produz exatamente as mesmas linhas (sem duplicar).
  Isso e' importante para:
    * Scripts de manutencao (re-roda sem medo).
    * Fase 7 (e2e): o mesmo calculo gera o mesmo resultado.
    * Tolerancia a retentativas em caso de crash mid-batch.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.core._typing import DataDict

logger = logging.getLogger(__name__)

#: Limite para log de debug de cada alerta inserido/pulado. Quando
#: ``len(alerts)`` for maior, loga so' o total (evita spam no log).
_DEBUG_LOG_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_frequency_alerts(alerts: list[dict], data: DataDict) -> int:
    """Persiste a lista de alertas de frequencia na tabela ``alerts`` v1.

    Algoritmo:
      1. Carrega ``existing_ids = set(data['alerts']['alert_id'])`` --
         dedup via chave natural deterministica.
      2. Para cada alerta:
         a. Se ``alert_id`` ja' existe em ``existing_ids`` -> pula.
         b. Senao, chama :func:`src.data_layer.append_row('alerts', a)`.
         c. Em caso de erro de I/O, loga em PT-BR e continua.
         d. Em sucesso, adiciona o ``alert_id`` a ``existing_ids`` e
            incrementa a contagem efetiva.

    Args:
        alerts: lista de dicts (saida de
            :func:`src.core.alerts.detect_frequency_alerts`).
        data: DataDict de :func:`src.data_layer.load_all()`. Usado
            APENAS para leitura (check de duplicatas). NAO e'
            mutado -- a escrita vai via ``append_row`` que reabre o CSV.

    Returns:
        Numero inteiro de alertas efetivamente gravados (0 a N).
        Alertas duplicados (ja' existentes) nao contam.

    Raises:
        Nao levanta. Excecoes do data layer sao capturadas e logadas.
    """
    from src.data_layer import append_row

    if not alerts:
        return 0

    # Carrega IDs existentes (1 leitura, O(1) lookup depois).
    existing_ids = _existing_alert_ids(data)

    inserted = 0
    skipped = 0
    failed = 0
    for a in alerts:
        alert_id = a.get("alert_id")
        if not alert_id:
            logger.error(
                "Alerta sem alert_id -- pulado. Verifique _make_alert em alerts.py."
            )
            failed += 1
            continue
        if alert_id in existing_ids:
            skipped += 1
            continue
        try:
            append_row("alerts", a)
        except FileNotFoundError as exc:
            logger.error(
                "Arquivo de alertas nao encontrado ao salvar %s: %s. "
                "Verifique se a pasta de dados existe.",
                alert_id, exc,
            )
            failed += 1
            continue
        except PermissionError as exc:
            logger.error(
                "Sem permissao para escrever alertas (%s): %s. "
                "Contate o administrador do sistema.",
                alert_id, exc,
            )
            failed += 1
            continue
        except OSError as exc:
            logger.error(
                "Erro de I/O ao salvar alerta %s: %s. "
                "Verifique o disco e tente novamente.",
                alert_id, exc,
            )
            failed += 1
            continue
        except (ValueError, TypeError, KeyError) as exc:
            # ``ValueError`` do schema check em append_row (coluna faltando,
            # tipo errado); ``TypeError`` se dict tem chave nao-string;
            # ``KeyError`` improvavel mas defensivo.
            logger.error(
                "Dados invalidos ao salvar alerta %s: %s. "
                "Verifique se o alerta tem todos os campos do schema.",
                alert_id, exc,
            )
            failed += 1
            continue
        # Sucesso -- atualiza controle local.
        existing_ids.add(alert_id)
        inserted += 1

    # Log consolidado (evita spam quando len(alerts) >> DEBUG_LOG_THRESHOLD).
    if len(alerts) <= _DEBUG_LOG_THRESHOLD:
        logger.info(
            "save_frequency_alerts: %d inseridos, %d duplicados, %d falhas",
            inserted, skipped, failed,
        )
    else:
        logger.info(
            "save_frequency_alerts (batch de %d): %d inseridos, %d duplicados, %d falhas",
            len(alerts), inserted, skipped, failed,
        )

    return inserted


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _existing_alert_ids(data: DataDict) -> set[str]:
    """Coleta os ``alert_id`` ja' presentes em ``data['alerts']``.

    Args:
        data: DataDict de :func:`src.data_layer.load_all`.

    Returns:
        Set de strings (``alert_id``). Vazio se a tabela nao existir
        ou estiver vazia.

    Note:
        Boundary helper -- captura excecoes do pandas (tabela ausente,
        coluna faltando) e retorna set vazio em vez de levantar. O
        caller :func:`save_frequency_alerts` interpreta "set vazio"
        como "nenhum alerta existente -> todos serao inseridos", o
        que e' o comportamento desejado em caso de data layer malformado.
    """
    try:
        alerts_df = data.get("alerts") if hasattr(data, "get") else None
    except (AttributeError, TypeError):
        return set()
    if alerts_df is None or not isinstance(alerts_df, pd.DataFrame):
        return set()
    if alerts_df.empty or "alert_id" not in alerts_df.columns:
        return set()
    try:
        ids = alerts_df["alert_id"].dropna().astype(str).tolist()
    except (ValueError, TypeError):
        return set()
    return set(ids)


__all__ = [
    "save_frequency_alerts",
    # _existing_alert_ids e' privado (prefixo _) -- nao exportado.
]
