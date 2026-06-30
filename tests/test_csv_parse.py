"""Tests for ``src/csv_importer/parse.py`` (Caminho B, Phase 6).

Helpers compartilhados pelos parsers CSV (Relatorio de frequencia +
Agendamentos). Todos os 5 helpers sao funcoes puras; nao tocam
streamlit nem data layer. Mensagens de erro PT-BR (N7).

O que este arquivo cobre:

  1. ``test_split_multi_basic`` (plano) — divide "A, B, C" → ["A","B","C"].
  2. ``test_split_multi_empty`` (plano) — string vazia e None retornam [].
  3. ``test_split_multi_collapsed`` (extra) — "A,, B" nao gera vazios.
  4. ``test_parse_br_date_basic`` (plano) — "25/05/2026" → Timestamp 2026-05-25.
  5. ``test_parse_br_date_invalid`` (extra) — "" / None / "abc" → NaT.
  6. ``test_parse_br_datetime_with_seconds`` (extra) — formato completo.
  7. ``test_parse_br_datetime_short`` (extra) — formato curto.
  8. ``test_parse_br_date_range_basic`` (plano) — "25/05 12:00 - 14:00" → (start, end).
  9. ``test_parse_br_date_range_dash`` (extra) — "-" → (NaT, NaT).
 10. ``test_normalize_name_basic`` (plano) — lowercase + trim + colapsa whitespace.
 11. ``test_normalize_name_empty`` (extra) — None / "" → "".
 12. ``test_normalize_name_keeps_accents`` (extra) — "Médica" → "médica" (Fase 6 dedup).

Licao Fase 5 (bytes literal): NAO usar b"..." literals para validar UTF-8
em string normalize — a funcao nao codifica. A verificacao de acentos e'
estrutural via igualdade de strings.
"""
from __future__ import annotations

import pandas as pd

from src.csv_importer.parse import (
    normalize_name,
    parse_br_date,
    parse_br_date_range,
    parse_br_datetime,
    split_multi,
)

# ---------------------------------------------------------------------------
# 1-3. split_multi (plano + extras)
# ---------------------------------------------------------------------------


def test_split_multi_basic() -> None:
    """``split_multi`` divide "A, B, C" por virgula."""
    assert split_multi("A, B, C") == ["A", "B", "C"]
    # Sem espaços
    assert split_multi("A,B,C") == ["A", "B", "C"]
    # Misturado
    assert split_multi("A ,B,  C ") == ["A", "B", "C"]


def test_split_multi_empty() -> None:
    """String vazia, None e "-" retornam lista vazia (sem excecao)."""
    assert split_multi("") == []
    assert split_multi(None) == []
    assert split_multi("-") == ["-"]  # '-' e' sentinel, nao vazio


def test_split_multi_collapsed() -> None:
    """Virgulas duplicadas nao geram strings vazias."""
    assert split_multi("A,, B") == ["A", "B"]
    assert split_multi("A,") == ["A"]
    assert split_multi(",") == []


# ---------------------------------------------------------------------------
# 4-5. parse_br_date (plano + extras)
# ---------------------------------------------------------------------------


def test_parse_br_date_basic() -> None:
    """``"DD/MM/YYYY"`` parseia para Timestamp normalizado."""
    result = parse_br_date("25/05/2026")
    assert isinstance(result, pd.Timestamp)
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 25
    assert result.hour == 0
    assert result.minute == 0


def test_parse_br_date_invalid() -> None:
    """Inputs invalidos retornam ``NaT`` (sem levantar)."""
    assert pd.isna(parse_br_date(""))
    assert pd.isna(parse_br_date(None))
    assert pd.isna(parse_br_date("abc"))
    assert pd.isna(parse_br_date("2026-05-25"))  # formato ISO nao aceito no helper BR


def test_parse_br_datetime_with_seconds() -> None:
    """``"DD/MM/YYYY HH:MM:SS"`` parseia com segundos."""
    result = parse_br_datetime("25/05/2026 14:30:45")
    assert isinstance(result, pd.Timestamp)
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 25
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 45


def test_parse_br_datetime_short() -> None:
    """``"DD/MM/YYYY HH:MM"`` (sem segundos) parseia."""
    result = parse_br_datetime("25/05/2026 14:30")
    assert isinstance(result, pd.Timestamp)
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 0


# ---------------------------------------------------------------------------
# 8-9. parse_br_date_range (plano + extras)
# ---------------------------------------------------------------------------


def test_parse_br_date_range_basic() -> None:
    """``"DD/MM HH:MM - HH:MM"`` retorna (start, end)."""
    start, end = parse_br_date_range("25/05/2026 12:00 - 14:00")
    assert isinstance(start, pd.Timestamp)
    assert isinstance(end, pd.Timestamp)
    assert start.hour == 12
    assert end.hour == 14
    # Mesmo dia
    assert start.date() == end.date() == pd.Timestamp("2026-05-25").date()


def test_parse_br_date_range_dash() -> None:
    """``"-"`` ou vazio → (NaT, NaT)."""
    start, end = parse_br_date_range("-")
    assert pd.isna(start)
    assert pd.isna(end)
    start, end = parse_br_date_range("")
    assert pd.isna(start)
    assert pd.isna(end)
    start, end = parse_br_date_range(None)
    assert pd.isna(start)
    assert pd.isna(end)


# ---------------------------------------------------------------------------
# 10-12. normalize_name (plano + extras)
# ---------------------------------------------------------------------------


def test_normalize_name_basic() -> None:
    """Lowercase + trim + colapsa whitespace multiplo."""
    assert normalize_name("Kelly Cristina a Silva Amorim") == "kelly cristina a silva amorim"
    assert normalize_name("  João  da  Silva  ") == "joão da silva"
    assert normalize_name("ERICK DE SOUSA KUBIJAN") == "erick de sousa kubijan"


def test_normalize_name_empty() -> None:
    """None e string vazia retornam string vazia."""
    assert normalize_name(None) == ""
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""


def test_normalize_name_keeps_accents() -> None:
    """Acentos NAO sao stripados (Fase 6 dedup tolerante)."""
    # Cedilha
    assert normalize_name("Nutrição") == "nutrição"
    # Til
    assert normalize_name("Cláudia") == "cláudia"
    # Agudo
    assert normalize_name("Médica") == "médica"
