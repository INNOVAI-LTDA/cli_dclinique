"""Tests for :mod:`src.pdf_importer.split` (MVP Jornada Clinica, Fase 2 -- D5).

Cobre os 4 caminhos canonicos:

  1. Virgula separa items: ``"A, B"`` -> ``["A", "B"]``.
  2. " e " conjuncao: ``"A e B"`` -> ``["A", "B"]``.
  3. Combinacao: ``"A, B e C"`` -> 3 itens.
  4. Virgula decimal NAO divide: ``"1,5 sessões, Drenagem"`` ->
     ``["1,5 sessões", "Drenagem"]`` (a virgula entre "1" e "5"
     e' decimal; a virgula entre "sessões" e "Drenagem" e' separador).

Casos de borda: texto vazio / None / so virgulas / sem split necessario.

Docstring do modulo serve como spec: cada cláusula tem 1 teste.
"""
from __future__ import annotations

import pytest

from src.pdf_importer.split import split_composite_items


# ---------------------------------------------------------------------------
# 1. Virgula como separador (D5 -- caso basico)
# ---------------------------------------------------------------------------


def test_splits_two_items_on_comma() -> None:
    """Caso D5 puro: ``"A, B"`` -> 2 itens."""
    assert split_composite_items("Limpeza, Drenagem") == ["Limpeza", "Drenagem"]


def test_splits_three_items_with_mixed_separators() -> None:
    """``"A, B e C"`` -> 3 itens (virgula + conjuncao)."""
    assert split_composite_items("A, B e C") == ["A", "B", "C"]


def test_splits_real_d5_example() -> None:
    """Exemplo real D5 da ata 2026-06-30."""
    result = split_composite_items(
        "medicamento X, injetaveis IM, injetaveis EV"
    )
    assert result == ["medicamento X", "injetaveis IM", "injetaveis EV"]


# ---------------------------------------------------------------------------
# 2. " e " como conjunção (sem virgula)
# ---------------------------------------------------------------------------


def test_splits_on_e_conjunction() -> None:
    """``"A e B"`` -> 2 itens."""
    assert split_composite_items("Limpeza de Pele e Drenagem") == [
        "Limpeza de Pele",
        "Drenagem",
    ]


def test_splits_on_e_lowercase() -> None:
    """``"a e b"`` (case-insensitive) -> 2 itens."""
    assert split_composite_items("a e b") == ["a", "b"]


def test_splits_with_extra_whitespace_around_e() -> None:
    """``"A  e  B"`` com whitespace duplo ainda split (regex flexivel)."""
    assert split_composite_items("A  e  B") == ["A", "B"]


# ---------------------------------------------------------------------------
# 3. Sem split necessario (item unico)
# ---------------------------------------------------------------------------


def test_keeps_single_item_unchanged() -> None:
    """Sem virgula nem "e" -> retorna lista com 1 item."""
    assert split_composite_items("Apenas Um") == ["Apenas Um"]


def test_keeps_long_description_as_single_item() -> None:
    """Descricao composta MAS sem virgula/e -- preservada como 1 item."""
    assert split_composite_items("Limpeza de Pele Profunda com Extrato de Acai") == [
        "Limpeza de Pele Profunda com Extrato de Acai"
    ]


# ---------------------------------------------------------------------------
# 4. Boundary: vazio / None / whitespace
# ---------------------------------------------------------------------------


def test_returns_empty_for_empty_string() -> None:
    assert split_composite_items("") == []


def test_returns_empty_for_none() -> None:
    assert split_composite_items(None) == []


def test_returns_empty_for_whitespace_only() -> None:
    assert split_composite_items("   ") == []


def test_returns_empty_for_only_separators() -> None:
    """String so com virgulas/spaces -> lista vazia (drop vazios)."""
    assert split_composite_items(",,,   ,  ") == []


# ---------------------------------------------------------------------------
# 5. Virgula decimal NAO divide (boundary critico)
# ---------------------------------------------------------------------------


def test_preserves_decimal_comma_in_number() -> None:
    """``"1,5 sessões"`` -> 1 item (virgula entre 1 e 5 e' decimal)."""
    assert split_composite_items("1,5 sessões") == ["1,5 sessões"]


def test_splits_around_decimal_comma_correctly() -> None:
    """``"1,5 sessões, Drenagem"`` -> 2 itens (a 2a virgula e' separador)."""
    assert split_composite_items("1,5 sessões, Drenagem") == [
        "1,5 sessões",
        "Drenagem",
    ]


def test_preserves_decimal_with_dot_pattern() -> None:
    """``"10,5 sessões, item Y e item Z"`` -> 3 itens (decimal preservado)."""
    assert split_composite_items("10,5 sessões, item Y e item Z") == [
        "10,5 sessões",
        "item Y",
        "item Z",
    ]


# ---------------------------------------------------------------------------
# 6. Strip por item
# ---------------------------------------------------------------------------


def test_strips_whitespace_around_each_item() -> None:
    """``"A,   B  , C"`` -> itens stripados."""
    assert split_composite_items("A,   B  , C") == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# 7. Sanity parametrizado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("A", ["A"]),
        ("A, B", ["A", "B"]),
        ("A, B, C", ["A", "B", "C"]),
        ("A e B", ["A", "B"]),
        ("A e B e C", ["A", "B", "C"]),
        ("", []),
    ],
)
def test_split_variants(line: str, expected: list[str]) -> None:
    assert split_composite_items(line) == expected
