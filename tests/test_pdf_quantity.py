"""Tests for :mod:`src.pdf_importer.quantity` (MVP Jornada Clinica, Fase 2).

Cobre os 4 caminhos canonicos do ``parse_quantity``:

  1. Plural com acento: ``"10 sessões"`` / ``"6 aplicações"``.
  2. Singular com acento: ``"1 sessão"`` / ``"1 aplicação"``.
  3. Texto vazio / None / sem match -> ``None``.
  4. Compound text retorna primeira ocorrência.

Docstring do modulo serve como spec: cada cláusula
("Se X entao Y") tem ao menos 1 teste. Lição N8 / Caminho B Fase 6.
"""
from __future__ import annotations

import pytest

from src.pdf_importer.quantity import parse_quantity


# ---------------------------------------------------------------------------
# 1. Plural com acento (caminho feliz)
# ---------------------------------------------------------------------------


def test_parses_10_sessoes() -> None:
    assert parse_quantity("10 sessões") == 10


def test_parses_6_aplicacoes() -> None:
    assert parse_quantity("6 aplicações") == 6


def test_parses_3_sessoes_sem_acento() -> None:
    """``sessoes`` sem acento (PDF mais antigo ou fonte sem UTF-8) -- ainda casa."""
    assert parse_quantity("3 sessoes") == 3


def test_parses_5_aplicacoes_sem_acento() -> None:
    assert parse_quantity("5 aplicacoes") == 5


# ---------------------------------------------------------------------------
# 2. Singular (boundary: número = 1)
# ---------------------------------------------------------------------------


def test_parses_1_sessao() -> None:
    assert parse_quantity("1 sessão") == 1


def test_parses_1_aplicacao() -> None:
    assert parse_quantity("1 aplicação") == 1


# ---------------------------------------------------------------------------
# 3. Vazio / None / sem match -> None (N7)
# ---------------------------------------------------------------------------


def test_returns_none_for_empty_string() -> None:
    assert parse_quantity("") is None


def test_returns_none_for_whitespace_only() -> None:
    assert parse_quantity("   ") is None


def test_returns_none_for_none_input() -> None:
    assert parse_quantity(None) is None


def test_returns_none_when_no_number() -> None:
    """Texto sem o numeral casar -- retorna None em vez de explodir."""
    assert parse_quantity("sem numero") is None


def test_returns_none_when_no_keyword() -> None:
    """Numero sem 'sessão'/'aplicação' -- nao confunde com sessions_expected."""
    assert parse_quantity("10 abc def") is None


# ---------------------------------------------------------------------------
# 4. Compound text: sempre a PRIMEIRA ocorrência
# ---------------------------------------------------------------------------


def test_returns_first_occurrence_in_compound_text() -> None:
    """``"10 sessões, 1x/semana"`` retorna 10 (a primeira -- sessions)."""
    assert parse_quantity("10 sessões, 1x/semana") == 10


def test_handles_text_with_frequency_at_end() -> None:
    """``"4 sessões, 1 vez por semana"`` retorna 4 (nao confunde com \"1 vez\")."""
    assert parse_quantity("4 sessões, 1 vez por semana") == 4


# ---------------------------------------------------------------------------
# 5. Sanity parametrizado de boundaries numericos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("100 sessões", 100),
        ("2 aplicações", 2),
        ("12 sessões, mensal", 12),
    ],
)
def test_parses_varied_quantities(text: str, expected: int) -> None:
    assert parse_quantity(text) == expected
