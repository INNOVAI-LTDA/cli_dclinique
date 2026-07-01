"""Tests for :mod:`src.pdf_importer.frequency` (MVP Jornada Clinica, Fase 2).

Cobre os 9 valores de :data:`src.components.importar_pdf_wizard.FREQUENCY_OPTIONS`
(capitalizado e lowercase), alem de:

  - None / vazio -> None.
  - Rotulo desconhecido -> None.
  - ``dose única`` -> ``None`` (sentinela, NAO ``0`` -- lição Caminho B Fase 6).
  - Whitespace residual tratado.

Padronizacao: ``test_period_days_covers_all_frequency_options`` garante
que a evolucao do dropdown nao introduz opcoes sem mapeamento no
:data:`PERIOD_DAYS` (sincronia wizard <-> frequency module). Se um dia
adicionarmos ``"semestral"`` no dropdown, este teste quebra ate
``PERIOD_DAYS`` ser atualizado.
"""
from __future__ import annotations

import pytest

from src.pdf_importer.frequency import PERIOD_DAYS, derive_periodicity


def _canonical() -> list[str]:
    """Pega os 9 valores canonicos definidos pelo wizard."""
    from src.components.importar_pdf_wizard import FREQUENCY_OPTIONS

    return list(FREQUENCY_OPTIONS)


# ---------------------------------------------------------------------------
# 1. Mapeamento canonico -- capitalizado (forma que o parser produz)
# ---------------------------------------------------------------------------


def test_diario_capitalized_returns_1() -> None:
    assert derive_periodicity("Diário") == 1


def test_diario_with_accent_lowercase_returns_1() -> None:
    """``"diário"`` lowercase com acento (forma que o parser produz apos
    ``.lower()``) -- precisa casar com a chave ``"diário"``."""
    assert derive_periodicity("diário") == 1


def test_semanal_capitalized_returns_7() -> None:
    assert derive_periodicity("Semanal") == 7


def test_quinzenal_capitalized_returns_15() -> None:
    assert derive_periodicity("Quinzenal") == 15


def test_mensal_capitalized_returns_30() -> None:
    assert derive_periodicity("Mensal") == 30


# ---------------------------------------------------------------------------
# 2. Mapeamento canonical -- lowercase (forma que o wizard grava)
# ---------------------------------------------------------------------------


def test_diario_lowercase_returns_1() -> None:
    assert derive_periodicity("diario") == 1


def test_semanal_lowercase_returns_7() -> None:
    assert derive_periodicity("semanal") == 7


def test_quinzenal_lowercase_returns_15() -> None:
    assert derive_periodicity("quinzenal") == 15


def test_mensal_lowercase_returns_30() -> None:
    assert derive_periodicity("mensal") == 30


# ---------------------------------------------------------------------------
# 3. Opcoes estendidas do wizard (a cada N dias, bimestral, trimestral)
# ---------------------------------------------------------------------------


def test_a_cada_5_dias_returns_5() -> None:
    assert derive_periodicity("a cada 5 dias") == 5


def test_a_cada_10_dias_returns_10() -> None:
    assert derive_periodicity("a cada 10 dias") == 10


def test_bimestral_returns_60() -> None:
    assert derive_periodicity("bimestral") == 60


def test_trimestral_returns_90() -> None:
    assert derive_periodicity("trimestral") == 90


# ---------------------------------------------------------------------------
# 4. Dose única -- SENTINELA (None, NAO 0)
# ---------------------------------------------------------------------------


def test_dose_unica_capitalized_returns_none_sentinel() -> None:
    """``dose única`` -> ``None`` por design (sentinela)."""
    assert derive_periodicity("Dose única") is None


def test_dose_unica_lowercase_returns_none_sentinel() -> None:
    assert derive_periodicity("dose única") is None


def test_period_days_dose_unica_is_explicit_none() -> None:
    """Lição Caminho B Fase 6: NAO usar 0 como sentinela (0 e' numero legitimo
    em outras escalas); explicit None força o caller a tratar."""
    assert PERIOD_DAYS["dose única"] is None


# ---------------------------------------------------------------------------
# 5. Empty / unknown / None -> None (N7)
# ---------------------------------------------------------------------------


def test_none_input_returns_none() -> None:
    assert derive_periodicity(None) is None


def test_empty_string_returns_none() -> None:
    assert derive_periodicity("") is None


def test_whitespace_only_returns_none() -> None:
    assert derive_periodicity("   ") is None


def test_unknown_label_returns_none() -> None:
    """Rotulo fora do vocabulario -- nao levanta, retorna None."""
    assert derive_periodicity("quinquenal") is None


def test_handles_leading_and_trailing_whitespace() -> None:
    assert derive_periodicity("  Semanal  ") == 7


# ---------------------------------------------------------------------------
# 6. Sanity: todas as FREQUENCY_OPTIONS tem mapeamento
# ---------------------------------------------------------------------------


def test_period_days_covers_all_frequency_options() -> None:
    """Sincronia wizard <-> frequency module.

    Se o dropdown adicionar um rotulo sem mapeamento em
    :data:`PERIOD_DAYS`, este teste quebra. Força o caller a
    atualizar a tabela ao mesmo tempo que o wizard.
    """
    for opt in _canonical():
        key = opt.strip().lower()
        assert key in PERIOD_DAYS, (
            f"FREQUENCY_OPTIONS {opt!r} (key={key!r}) sem mapeamento "
            f"em PERIOD_DAYS; caller precisa de periodicidade explicita"
        )


# ---------------------------------------------------------------------------
# 7. Tabela de mapeamento e' bem-formada
# ---------------------------------------------------------------------------


def test_period_days_has_no_collisions_for_periodic_labels() -> None:
    """Todos os valores periodicos (≠ None) sao inteiros positivos."""
    for key, value in PERIOD_DAYS.items():
        if value is not None:
            assert isinstance(value, int)
            assert value > 0, f"periodicity para {key!r} deve ser >0, got {value}"


def test_period_days_has_only_known_labels() -> None:
    """Nenhuma chave inesperada em PERIOD_DAYS (whitelist: 9 opcoes
    canonicas + 2 aliases com acento para ``diario`` e ``dose unica``).

    Aliases com acento existem porque ``_norm_frequency_type``
    retorna ``"Diário"`` e ``"Dose única"`` -- o lookup apos
    ``.lower()`` nao removeria o acento, entao precisamos de
    ambas as variantes da chave para resolver o lookup sem
    normalizacao adicional (sem dep ``unidecode``).
    """
    expected_keys = {
        "dose unica",
        "dose única",
        "diario",
        "diário",
        "a cada 5 dias",
        "semanal",
        "a cada 10 dias",
        "quinzenal",
        "mensal",
        "bimestral",
        "trimestral",
    }
    assert set(PERIOD_DAYS.keys()) == expected_keys, (
        f"chaves inesperadas em PERIOD_DAYS: "
        f"{set(PERIOD_DAYS.keys()) ^ expected_keys}"
    )


# ---------------------------------------------------------------------------
# 8. Idempotencia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("freq_type", _canonical())
def test_periodicity_is_pure_and_idempotent(freq_type: str) -> None:
    """Derivar 2x devolve o mesmo resultado (sem estado, sem cache)."""
    first = derive_periodicity(freq_type)
    second = derive_periodicity(freq_type)
    assert first == second
