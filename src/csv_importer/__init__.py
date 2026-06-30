"""Importador CSV (Caminho B, Fase 6).

Espelho do ``src.pdf_importer/`` para CSVs de exportacao do IClinic:

  * ``Relatorio de frequencia.csv`` → ``treatment_plans`` + ``treatment_plan_items``
    + ``execution_summary`` (read-model projection).
  * ``Agendamentos.csv`` → ``appointments`` + ``appointment_items``.

Modulos:

  * :mod:`.parse`        — helpers puros (split_multi, parse_br_date, normalize_name).
  * :mod:`.dedup`        — resolve (name, orcamento) → patient_id.
  * :mod:`.frequencia`   — parser do relatorio de frequencia.
  * :mod:`.agendamentos` — parser de agendamentos.

O wizard Streamlit (UI) e' deferido para Fase 6.5; este pacote expoe apenas
a camada pura (parse + dedup + persist), testavel sem subir o Streamlit.
"""
from __future__ import annotations

__all__ = [
    "parse",
    "dedup",
    "frequencia",
    "agendamentos",
]
