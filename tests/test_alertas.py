"""Tests for the "Frequência" category in `src/pages/alertas.py` (Caminho B, Phase 5).

The plan (``docs/caminho_b_plano.md`` §3 Fase 5) adds the 5th+1st
category "Frequência" to the alerts page, sourced from
``core.alerts.detect_frequency_alerts`` (Phase 3). The category value
in v1 alerts CSV is the literal Portuguese string ``"Frequência"``
(accented), pre-set in ``src/core/alerts.py::_make_alert:241``.

What this file covers (per plan §3 Fase 5 "Testes"):

  1. **test_category_counts_includes_frequency** (plano) — the new
     category appears in the counts dict returned by
     ``_category_counts(alerts)`` and is incremented for matching rows.
  2. **test_frequency_alerts_visible** (plano) — when filtered by
     "Frequência", the frequency alerts are still present in the
     rendered table.
  3. **test_filter_by_frequency_works** (plano) — the category filter
     actually excludes alerts from other categories.
  4. **test_category_class_only_for_frequency** (extra, lição Fase 4
     TDD-first) — the helper ``_category_class`` returns the indigo
     CSS class only for "Frequência" (and its case/accent-insensitive
     variants), None for everything else.
  5. **test_render_does_not_raise_on_minimal_fixture** (extra,
     AppTest smoke) — ``render(data)`` does not raise under a fixture
     with both frequency and non-frequency alerts.
  6. **test_existing_categories_unchanged** (extra, regression) — the
     4 original categories (Enfermagem/Médica/Comercial/Nutrição)
     still work, and their counts are not affected by the new entry.

N7: page-level tests go through the public ``render()`` function via
``AppTest.from_string`` (pattern established in Phase 3's
``test_mapa_decisao_error_handling.py`` and Phase 4's
``test_mapa_decisao.py``). The boundary defensive try/except in
``render()`` is verified to fire correctly via ``assert not
at.exception``.

Fase 3 lição (UTF-8): after every Write, validate that the literal
"ç" (U+00E7), "ã" (U+00E3), and other PT-BR chars are NOT stripped by
the harness. The companion ``test_existing_categories_unchanged``
below also asserts "Nutrição" with the cedilha survives.
"""
from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.pages import alertas
from src.pages.alertas import (
    CATEGORIES,
    _category_class,
    _category_counts,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_alerts_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal alerts DataFrame (10 columns, per v1 schema)."""
    base = {
        "alert_id": [],
        "patient_id": [],
        "plan_id": [],
        "category": [],
        "alert_type": [],
        "description": [],
        "priority": [],
        "status": [],
        "created_at": [],
        "comment": [],
    }
    for row in rows:
        for key in base:
            base[key].append(row.get(key))
    return pd.DataFrame(base)


def _build_data_dict(
    alerts_rows: list[dict] | None = None,
    *,
    patient_ids: tuple[str, ...] = ("pat_001", "pat_002"),
) -> dict:
    """Constroi o DataDict (formato ``load_all()``) com pacientes e alertas.

    Apenas ``patients`` e ``alerts`` sao populados (a pagina de Alertas
    so' precisa desses 2). Demais tabelas vazias.
    """
    return {
        "patients": pd.DataFrame(
            {
                "patient_id": list(patient_ids),
                "name": [f"Paciente {pid}" for pid in patient_ids],
            }
        ),
        "alerts": _make_alerts_df(alerts_rows or []),
        # Demais tabelas -- vazias (Alertas page nao as consome).
        "treatment_plans": pd.DataFrame(),
        "treatment_plan_items": pd.DataFrame(),
        "execution_summary": pd.DataFrame(),
        "appointments": pd.DataFrame(),
        "appointment_items": pd.DataFrame(),
        "patient_goals": pd.DataFrame(),
        "weight_entries": pd.DataFrame(),
        "satisfaction_entries": pd.DataFrame(),
        "data_quality_issues": pd.DataFrame(),
    }


# ---------------------------------------------------------------------------
# 1. test_category_counts_includes_frequency (plano)
# ---------------------------------------------------------------------------


def test_category_counts_includes_frequency() -> None:
    """``_category_counts`` retorna contagem correta para "Frequência".

    Cobre 3 cenarios:
      a) 0 alertas de Frequência -> count = 0
      b) 3 alertas de Frequência (entre 6 totais) -> count = 3
      c) Apenas Frequência -> count = N, outras = 0
    """
    # a) 0 frequency
    df_a = _make_alerts_df(
        [
            {"alert_id": "a1", "patient_id": "pat_001", "category": "Enfermagem"},
            {"alert_id": "a2", "patient_id": "pat_002", "category": "Médica"},
        ]
    )
    counts = _category_counts(df_a)
    assert "Frequência" in counts, "CATEGORIES deveria incluir 'Frequência'"
    assert counts["Frequência"] == 0
    assert counts["Todos"] == 2
    assert counts["Enfermagem"] == 1
    assert counts["Médica"] == 1

    # b) 3 frequency entre 6
    df_b = _make_alerts_df(
        [
            {"alert_id": f"a{i}", "patient_id": "pat_001", "category": cat}
            for i, cat in enumerate(
                ["Frequência", "Frequência", "Frequência", "Enfermagem", "Médica", "Nutrição"]
            )
        ]
    )
    counts = _category_counts(df_b)
    assert counts["Frequência"] == 3
    assert counts["Todos"] == 6
    assert counts["Enfermagem"] == 1
    assert counts["Nutrição"] == 1

    # c) Apenas Frequência
    df_c = _make_alerts_df(
        [
            {"alert_id": f"a{i}", "patient_id": "pat_001", "category": "Frequência"}
            for i in range(5)
        ]
    )
    counts = _category_counts(df_c)
    assert counts["Frequência"] == 5
    assert counts["Enfermagem"] == 0
    assert counts["Médica"] == 0


# ---------------------------------------------------------------------------
# 2. test_frequency_alerts_visible (plano)
# ---------------------------------------------------------------------------


def test_frequency_alerts_visible() -> None:
    """Quando filtrado por "Frequência", alertas de Frequência permanecem visiveis.

    Testa via AppTest para garantir que o filtro e a tabela renderizam
    end-to-end (sem traceback). Verificamos que:
      a) ``render(data)`` nao levanta.
      b) O HTML renderizado contem o alert_id de cada alerta de Frequência.
      c) O HTML NAO contem alert_ids de outras categorias.

    Licao Fase 5 (1a rodada): ``repr(data_dict)`` produz display tabular do
    pandas SEM aspas, entao datas como ``"2026-06-23"`` viram tokens
    ``2026 - 06 - 23`` no lexer Python (leading zero em ``06`` → SyntaxError).
    Padrao Phase 4 aplicado: construir ``data`` DENTRO do script via
    ``pd.DataFrame({...})`` — strings ficam com aspas explicitas, lexer OK.
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
from src.pages import alertas

data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Paciente 1", "Paciente 2"],
    }),
    "alerts": pd.DataFrame([
        {"alert_id": "freq_000", "patient_id": "pat_001", "plan_id": None,
         "category": "Frequência", "alert_type": "Comparecimento baixo",
         "description": "Alerta de teste 0", "priority": "Alta",
         "status": "Aberto", "created_at": "2026-06-23", "comment": None},
        {"alert_id": "freq_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Frequência", "alert_type": "Comparecimento baixo",
         "description": "Alerta de teste 1", "priority": "Alta",
         "status": "Aberto", "created_at": "2026-06-23", "comment": None},
        {"alert_id": "enf_001", "patient_id": "pat_002", "plan_id": None,
         "category": "Enfermagem", "alert_type": "Pressão alta",
         "description": "Pressão alta detectada", "priority": "Média",
         "status": "Aberto", "created_at": "2026-06-23", "comment": None},
    ]),
}

alertas.render(data)
"""
    at = AppTest.from_string(script).run()

    assert not at.exception, f"Page raised: {[repr(e) for e in at.exception]}"

    # Filter by Frequência via session_state (não via clique no botão porque
    # AppTest nao simula rerun pós-click de forma confiavel).
    at.session_state["alertas_category"] = "Frequência"
    at.run()

    rendered_html = " ".join(
        getattr(m, "value", "") for m in at.markdown if getattr(m, "value", "")
    )

    # Marcadores: o HTML nao renderiza ``alert_id`` (so' patient_id, alert_type,
    # description, etc.). Usar ``description`` unica de cada alerta.
    # a) 2 alertas de Frequência visiveis
    for desc in ("Alerta de teste 0", "Alerta de teste 1"):
        assert desc in rendered_html, f"Description {desc!r} missing from Frequência filter"

    # b) Alerta de Enfermagem NAO visivel (sua description tambem nao pode estar)
    assert "Pressão alta detectada" not in rendered_html, (
        "Alerta de Enfermagem vazou para o filtro Frequência"
    )


# ---------------------------------------------------------------------------
# 3. test_filter_by_frequency_works (plano)
# ---------------------------------------------------------------------------


def test_filter_by_frequency_works() -> None:
    """Filtro "Frequência" exclui alertas de outras categorias.

    Testa via AppTest: apos ativar ``alertas_category = "Frequência"``,
    o HTML renderizado contem APENAS alert_ids de Frequência. 0 de outras.

    Licao Fase 5 (1a rodada): ver ``test_frequency_alerts_visible`` docstring.
    Pattern Phase 4: ``data`` construido DENTRO do script via ``pd.DataFrame``.
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
from src.pages import alertas

data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Paciente 1", "Paciente 2"],
    }),
    "alerts": pd.DataFrame([
        # 2 frequency (devem APARECER com filtro "Frequência")
        {"alert_id": "freq_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Frequência", "alert_type": "Comparecimento baixo",
         "description": "F1", "priority": "Alta", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
        {"alert_id": "freq_002", "patient_id": "pat_002", "plan_id": None,
         "category": "Frequência", "alert_type": "Sem sessões",
         "description": "F2", "priority": "Média", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
        # 1 de cada categoria nao-frequency (devem SUMIR com filtro "Frequência")
        {"alert_id": "enf_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Enfermagem", "alert_type": "Pressão alta",
         "description": "E1", "priority": "Média", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
        {"alert_id": "med_001", "patient_id": "pat_002", "plan_id": None,
         "category": "Médica", "alert_type": "Exame pendente",
         "description": "M1", "priority": "Baixa", "status": "Em análise",
         "created_at": "2026-06-23", "comment": None},
        {"alert_id": "com_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Comercial", "alert_type": "Renovação próxima",
         "description": "C1", "priority": "Baixa", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
        {"alert_id": "nut_001", "patient_id": "pat_002", "plan_id": None,
         "category": "Nutrição", "alert_type": "Plano alimentar",
         "description": "N1", "priority": "Média", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
    ]),
}

alertas.render(data)
"""
    at = AppTest.from_string(script).run()
    assert not at.exception

    at.session_state["alertas_category"] = "Frequência"
    at.run()

    rendered_html = " ".join(
        getattr(m, "value", "") for m in at.markdown if getattr(m, "value", "")
    )

    # Marcadores via ``alert_type`` (unico por alerta). alert_id NAO e'
    # renderizado pelo ``_render_table`` (Fase 1 nao o expoe na UI).
    # Frequência: presente (2 alert_types unicos)
    assert "Comparecimento baixo" in rendered_html
    assert "Sem sessões" in rendered_html

    # Outras 4 categorias: AUSENTES (4 alert_types de outras categorias)
    for non_freq_type in ("Pressão alta", "Exame pendente",
                          "Renovação próxima", "Plano alimentar"):
        assert non_freq_type not in rendered_html, (
            f"Alert type {non_freq_type!r} vazou para o filtro Frequência"
        )


# ---------------------------------------------------------------------------
# 4. test_category_class_only_for_frequency (extra)
# ---------------------------------------------------------------------------


def test_category_class_only_for_frequency() -> None:
    """``_category_class`` retorna indigo CSS so' para "Frequência".

    Tolerante a variacoes de case e accent (Fase 3 licao:
    v1 data pode vir com encoding cp1252 e perder acentos).
    """
    # Casos positivos
    assert _category_class("Frequência") == "alertas-category-frequency"
    assert _category_class("frequência") == "alertas-category-frequency"  # lowercase
    assert _category_class("FREQUÊNCIA") == "alertas-category-frequency"  # uppercase
    assert _category_class("frequencia") == "alertas-category-frequency"   # sem acento
    assert _category_class("Freqüência") == "alertas-category-frequency"   # variante ortografica

    # Casos negativos
    assert _category_class("Enfermagem") is None
    assert _category_class("Médica") is None
    assert _category_class("Comercial") is None
    assert _category_class("Nutrição") is None
    assert _category_class("") is None
    assert _category_class(None) is None


# ---------------------------------------------------------------------------
# 5. test_render_does_not_raise_on_minimal_fixture (extra: AppTest smoke)
# ---------------------------------------------------------------------------


def test_render_does_not_raise_on_minimal_fixture() -> None:
    """AppTest smoke: ``render(data)`` nao levanta com mix de categorias.

    Licao Fase 5 (1a rodada): ``data`` construido DENTRO do script (Phase 4
    pattern) para evitar SyntaxError do ``repr()`` DataFrame no lexer Python.
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
from src.pages import alertas

data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_001"],
        "name": ["Paciente 1"],
    }),
    "alerts": pd.DataFrame([
        {"alert_id": "freq_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Frequência", "alert_type": "Comparecimento baixo",
         "description": "F1", "priority": "Alta", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
        {"alert_id": "enf_001", "patient_id": "pat_001", "plan_id": None,
         "category": "Enfermagem", "alert_type": "Pressão alta",
         "description": "E1", "priority": "Média", "status": "Aberto",
         "created_at": "2026-06-23", "comment": None},
    ]),
}

alertas.render(data)
"""
    at = AppTest.from_string(script).run()

    assert not at.exception, f"Page raised: {[repr(e) for e in at.exception]}"
    # Nenhum error widget no happy path.
    assert not at.error, f"Unexpected error widget: {[repr(e) for e in at.error]}"


# ---------------------------------------------------------------------------
# 6. test_existing_categories_unchanged (extra: regression)
# ---------------------------------------------------------------------------


def test_existing_categories_unchanged() -> None:
    """As 4 categorias originais (Enfermagem/Médica/Comercial/Nutrição) NAO quebraram.

    Cobertura:
      a) ``CATEGORIES`` tem 6 entradas (Todos + 4 originais + Frequência).
      b) Ordem preservada: "Frequência" e' a ULTIMA.
      c) Cedilha/til sobrevivem ao Write tool (UTF-8 intact): "Nutrição",
         "Médica" e "Frequência" tem os acentos originais.
      d) ``_category_counts`` conta as 4 originais + Frequência corretamente
         em um mix de 5 categorias.
    """
    # a) 6 entradas
    assert len(CATEGORIES) == 6, (
        f"CATEGORIES deveria ter 6 entradas (1 'Todos' + 4 originais + 'Frequência'), "
        f"got: {CATEGORIES}"
    )

    # b) Ordem: "Todos" primeiro, "Frequência" ultimo
    assert CATEGORIES[0] == "Todos"
    assert CATEGORIES[-1] == "Frequência"

    # c) UTF-8 intact (validacao explicita dos bytes raw -- Fase 3 licao).
    # Nao usamos b"..." literais porque Python rejeita non-ASCII em bytes
    # literals; em vez disso encodamos a string esperada para comparar.
    raw_src = open("src/pages/alertas.py", "rb").read()
    for acented in ("Nutrição", "Médica", "Frequência"):
        encoded = acented.encode("utf-8")
        assert encoded in raw_src, (
            f"Write tool stripou acento! Procurado: {encoded!r} "
            f"(decoded: {acented!r}) em src/pages/alertas.py. "
            f"Arquivo precisa ser re-escrito via bytes-level replace."
        )

    # d) Mix de 5 categorias
    df = _make_alerts_df(
        [
            {"alert_id": "f1", "patient_id": "pat_001", "category": "Frequência"},
            {"alert_id": "f2", "patient_id": "pat_001", "category": "Frequência"},
            {"alert_id": "e1", "patient_id": "pat_001", "category": "Enfermagem"},
            {"alert_id": "m1", "patient_id": "pat_001", "category": "Médica"},
            {"alert_id": "c1", "patient_id": "pat_001", "category": "Comercial"},
            {"alert_id": "n1", "patient_id": "pat_001", "category": "Nutrição"},
        ]
    )
    counts = _category_counts(df)
    assert counts == {
        "Todos": 6,
        "Enfermagem": 1,
        "Médica": 1,
        "Comercial": 1,
        "Nutrição": 1,
        "Frequência": 2,
    }
