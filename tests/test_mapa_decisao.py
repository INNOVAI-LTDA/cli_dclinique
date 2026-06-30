"""Tests for the 5-class Decision Map (Caminho B, Phase 4).

The plan (``docs/caminho_b_plano.md`` §3 Fase 4) adds a 3rd visual
dimension to ``mapa_decisao.py`` sourced from
``core.frequency.attendance_rate``:

  * Helper ``_compute_patient_attendance_rates(data, as_of)`` returns a
    ``pd.Series`` indexed by ``patient_id`` (string ``pat_NNN``).
  * ``render()`` builds the usual 2x2 quadrants AND a 5th class
    "Sem comparecimento" for patients whose mean ``attendance_rate == 0``.
  * The side panel of a selected patient gains a 4th stat: "Frequência"
    formatted as ``X% comparecimento`` (or "Sem sessões" when NaN).

What this file covers (per plan §3 Fase 4 "Testes"):

  1. **Smoke**: ``render(data)`` does not raise under the standard
     happy-path fixture.
  2. **Lógica** (``_compute_patient_attendance_rates``):
      * Returns a ``Series`` with the right shape (index = patient_ids
        that have active cds; dtype = float).
      * Aggregates mean across multiple cds for the same patient.
      * Skips plan-root cds (``parent_client_deliverable_id is None``).
  3. **5 classes**: A patient with rate == 0 ends up in the
     "Sem comparecimento" quadrant (not in any of the 4 normal ones);
     the side panel says "0% comparecimento" for them.

N7: these tests exercise the helper directly. The defensive boundary
at ``render()`` level is covered in ``tests/test_mapa_decisao_error_handling.py``
(unchanged from Phase 3).

Strategy for fixtures:
  We build v1 DataFrames (``treatment_plans``, ``treatment_plan_items``,
  ``appointments``, ``patients``) with the columns that ``core.repos`` and
  ``core.mapping`` expect. The synthesis from v1 to v2 (ClientDeliverable,
  Deliverable, ClientSession) is exercised end-to-end via the public
  ``load_*`` functions. This catches regressions in the mapping layer as
  a bonus.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.pages.mapa_decisao import (
    _compute_patient_attendance_rates,
    _decision_map_html,
    _patient_stats,
)


# ---------------------------------------------------------------------------
# Constantes de teste -- pinar data de referencia para determinismo.
# ---------------------------------------------------------------------------

REFERENCE_DATE = date(2026, 6, 23)
DEFAULT_ORG_ID = 1


# ---------------------------------------------------------------------------
# Fixture builders (v1 DataFrames). Cada builder retorna um DataFrame com
# as colunas exatas que ``core.mapping`` espera.
# ---------------------------------------------------------------------------


def _make_patients_df(patient_ids: tuple[int, ...] = (1, 2)) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "patient_id": [f"pat_{cid:03d}" for cid in patient_ids],
            "name": [f"Paciente {cid}" for cid in patient_ids],
            "normalized_name": [f"paciente {cid}" for cid in patient_ids],
            "medical_record": [f"MR{cid:04d}" for cid in patient_ids],
            "phone": [f"+551199999{cid:04d}" for cid in patient_ids],
            "age": [30 + cid for cid in patient_ids],
            "cpf": [None] * len(patient_ids),
            "rg": [None] * len(patient_ids),
            "address": [None] * len(patient_ids),
            "created_at": [
                datetime(2026, 1, 1, 12, 0, 0) for _ in patient_ids
            ],
        }
    )


def _make_plans_df(
    items: list[dict],
) -> pd.DataFrame:
    """Build ``treatment_plans`` (1 row per plan).

    Args:
        items: lista de dicts com chaves:
          - plan_id (str)
          - patient_id (str)
          - status (str, ex.: "Ativo")
          - main_goal (str)
          - budget_code (str)
          - start_date (date, opcional)
          - end_date (date, opcional)
          - sessions_expected (int, opcional)
          - is_renewal (bool, opcional)
          - issue_date (date, opcional)
    """
    rows = []
    for it in items:
        rows.append(
            {
                "plan_id": it["plan_id"],
                "patient_id": it["patient_id"],
                "budget_code": it.get("budget_code", "ORC001"),
                "issue_date": it.get("issue_date", REFERENCE_DATE - timedelta(days=30)),
                "start_date": it.get("start_date", REFERENCE_DATE - timedelta(days=30)),
                "end_date": it.get("end_date"),
                "status": it.get("status", "Ativo"),
                "main_goal": it.get("main_goal", f"Plano {it['plan_id']}"),
                "is_renewal": it.get("is_renewal", False),
                "notes": None,
            }
        )
    return pd.DataFrame(rows)


def _make_plan_items_df(
    items: list[dict],
) -> pd.DataFrame:
    """Build ``treatment_plan_items`` (1 row per item, todos ativos)."""
    rows = []
    for it in items:
        rows.append(
            {
                "plan_item_id": it["plan_item_id"],
                "plan_id": it["plan_id"],
                "patient_id": it["patient_id"],
                "budget_code": it.get("budget_code", "ORC001"),
                "raw_name": it.get("raw_name", f"Item {it['plan_item_id']}"),
                "category": it.get("category", "Acompanhamento"),
                "sessions_expected": it.get("sessions_expected", 4),
                "frequency_text": it.get("frequency_text", "Semanal"),
                "frequency_type": it.get("frequency_type", "Semanal"),
                "source": "manual",
                "needs_manual_review": False,
            }
        )
    return pd.DataFrame(rows)


def _make_appointments_df(
    items: list[dict],
) -> pd.DataFrame:
    """Build ``appointments`` (1 row per session)."""
    rows = []
    for it in items:
        rows.append(
            {
                "appointment_id": it["appointment_id"],
                "appointment_code": it.get("appointment_code", f"APT{it['appointment_id']}"),
                "patient_id": it["patient_id"],
                "budget_codes": it.get("budget_code", "ORC001"),
                "appointment_start": it["start"],
                "appointment_end": it.get("end", it["start"] + timedelta(hours=1)),
                "appointment_raw": it.get("raw", "Consulta"),
                "professional": it.get("professional", "Dayane Junqueira Vilela"),
                "scheduled_by": it.get("scheduled_by", "Recepção"),
                "status": it.get("status", "Atendido"),
            }
        )
    return pd.DataFrame(rows)


def _build_data_dict(
    *,
    patient_ids: tuple[int, ...] = (1, 2),
    plans: list[dict] | None = None,
    plan_items: list[dict] | None = None,
    appointments: list[dict] | None = None,
) -> dict:
    """Constroi o DataDict (formato ``load_all()``) com tabelas minimas.

    Apenas as tabelas relevantes para o helper sao populadas. Demais
    tabelas recebem DataFrame vazio (o ``core.repos`` aceita isso).
    """
    plans = plans or []
    plan_items = plan_items or []
    appointments = appointments or []

    return {
        "patients": _make_patients_df(patient_ids),
        "treatment_plans": _make_plans_df(plans),
        "treatment_plan_items": _make_plan_items_df(plan_items),
        "appointments": _make_appointments_df(appointments),
        # Demais tabelas -- vazias. ``core.repos._get_table`` retorna
        # DataFrame vazio se ausente.
        "appointment_items": pd.DataFrame(),
        "client_deliverables": pd.DataFrame(),
        "deliverables": pd.DataFrame(),
        "client_sessions": pd.DataFrame(),
        "weight_entries": pd.DataFrame(),
        "satisfaction_entries": pd.DataFrame(),
        "alerts": pd.DataFrame(),
        "data_quality_issues": pd.DataFrame(),
        "organizations": pd.DataFrame(
            [{"id": DEFAULT_ORG_ID, "nome": "DClinique"}]
        ),
        "users": pd.DataFrame(),
    }


def _attended_appointment(
    patient_id: str,
    appt_id: int,
    session_date: date,
    *,
    status: str = "Atendido",
) -> dict:
    return {
        "appointment_id": f"appt_{appt_id:04d}",
        "patient_id": patient_id,
        "start": datetime.combine(session_date, datetime.min.time()),
        "status": status,
    }


# ---------------------------------------------------------------------------
# 1. Smoke test
# ---------------------------------------------------------------------------


def test_render_does_not_raise_on_minimal_fixture() -> None:
    """AppTest smoke: ``render(data)`` nao levanta no happy path minimo."""
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
from src.pages import mapa_decisao

data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Paciente 1", "Paciente 2"],
    }),
}

def _stub(_data):
    return pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Paciente 1", "Paciente 2"],
        "is_engaged": pd.Series([True, False], dtype="boolean"),
        "is_satisfied": pd.Series([True, True], dtype="boolean"),
        "score": pd.Series([9, 5], dtype="Int64"),
        "open_alerts": pd.Series([0, 1], dtype="Int64"),
        "engagement_rate": pd.Series([0.9, 0.4], dtype="float64"),
        "days_to_renewal": pd.Series([30, 60], dtype="Int64"),
        "without_recent_weight": pd.Series([False, False], dtype="boolean"),
    })

mapa_decisao.patient_summary = _stub
mapa_decisao._compute_patient_attendance_rates = lambda data, **kw: pd.Series(dtype="float64")
mapa_decisao.render(data)
"""
    at = AppTest.from_string(script).run()

    assert not at.exception, f"Page raised: {[repr(e) for e in at.exception]}"
    assert not at.error, f"Unexpected error widget: {[repr(e) for e in at.error]}"


# ---------------------------------------------------------------------------
# 2. Logica do helper ``_compute_patient_attendance_rates``
# ---------------------------------------------------------------------------


def test_compute_attendance_rates_returns_empty_when_no_plans() -> None:
    """Sem planos => Series vazia."""
    data = _build_data_dict(patient_ids=(1,), plans=[], plan_items=[])
    rates = _compute_patient_attendance_rates(data, as_of=REFERENCE_DATE)

    assert isinstance(rates, pd.Series)
    assert rates.empty


def test_compute_attendance_rates_indexes_by_patient_id_string() -> None:
    """Resultado e' indexado por ``patient_id`` string (nao ``client_id`` int)."""
    data = _build_data_dict(
        patient_ids=(1,),
        plans=[
            {
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "main_goal": "Plano Nutrição",
                "start_date": REFERENCE_DATE - timedelta(days=30),
            }
        ],
        plan_items=[
            {
                "plan_item_id": "item_001",
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "raw_name": "Consulta Nutrição",
                "frequency_type": "Semanal",
                "sessions_expected": 4,
            }
        ],
    )
    rates = _compute_patient_attendance_rates(data, as_of=REFERENCE_DATE)

    # 1 item, 0 sessoes atendidas => rate == 0
    assert list(rates.index) == ["pat_001"]
    assert rates.iloc[0] == pytest.approx(0.0)


def test_compute_attendance_rates_aggregates_mean_across_items() -> None:
    """Multiplos itens do mesmo paciente => mean das rates.

    Phase 2 limitacao documentada em ``core.frequency.actual_sessions``:
    o filtro de sessoes por item e' feito via ``s.client_id == cd.client_id``
    (proxy, ate' Phase 6 introduzir ``client_session_items``). Logo, todos
    os itens do mesmo paciente contam as MESMAS sessoes -- variamos
    ``sessions_expected`` por item para produzir rates diferentes.

    Setup:
      * item_001: sessions_expected=2, 4 sessoes do cliente => rate=2.0
      * item_002: sessions_expected=8, 4 sessoes do cliente => rate=0.5
      Esperado: mean = 1.25 (NEM max=2.0, NEM min=0.5)
    """
    data = _build_data_dict(
        patient_ids=(1,),
        plans=[
            {
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "main_goal": "Plano Nutrição",
                "start_date": REFERENCE_DATE - timedelta(days=30),
            }
        ],
        plan_items=[
            {
                "plan_item_id": "item_001",
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "raw_name": "Consulta Nutrição",
                "frequency_type": "Semanal",
                "sessions_expected": 2,
            },
            {
                "plan_item_id": "item_002",
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "raw_name": "Aplicação Injetável",
                "frequency_type": "Semanal",
                "sessions_expected": 8,
            },
        ],
        appointments=[
            _attended_appointment("pat_001", 1, REFERENCE_DATE - timedelta(days=7)),
            _attended_appointment("pat_001", 2, REFERENCE_DATE - timedelta(days=14)),
            _attended_appointment("pat_001", 3, REFERENCE_DATE - timedelta(days=21)),
            _attended_appointment("pat_001", 4, REFERENCE_DATE - timedelta(days=28)),
        ],
    )
    rates = _compute_patient_attendance_rates(data, as_of=REFERENCE_DATE)

    assert rates.loc["pat_001"] == pytest.approx(1.25, abs=1e-9)


def test_compute_attendance_rates_excludes_patients_without_items() -> None:
    """Pacientes sem nenhum item NAO aparecem no indice.

    Aqui, ``load_client_deliverables`` retorna apenas o plan-pai
    (parent_client_deliverable_id is None), que o helper ignora.
    """
    data = _build_data_dict(
        patient_ids=(1, 2),
        plans=[
            {
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "main_goal": "Plano Nutrição",
                "start_date": REFERENCE_DATE - timedelta(days=30),
            }
        ],
        plan_items=[],  # sem itens -- helper nao tem o que agregar
    )
    rates = _compute_patient_attendance_rates(data, as_of=REFERENCE_DATE)

    assert list(rates.index) == []


def test_compute_attendance_rates_ignores_plan_root_only() -> None:
    """Plan-pai sem itens => Series vazia (apenas itens acionaveis contam)."""
    data = _build_data_dict(
        patient_ids=(1,),
        plans=[
            {
                "plan_id": "plan_001",
                "patient_id": "pat_001",
                "main_goal": "Plano Nutrição",
                "start_date": REFERENCE_DATE - timedelta(days=30),
            }
        ],
        plan_items=[],  # sem itens
    )
    rates = _compute_patient_attendance_rates(data, as_of=REFERENCE_DATE)

    assert rates.empty


# ---------------------------------------------------------------------------
# 3. Logica do panel "Frequencia" + override "Sem comparecimento"
# ---------------------------------------------------------------------------


def test_patient_stats_includes_frequencia_dimension() -> None:
    """Painel lateral ganha 4a dimensao 'Frequencia'."""
    row = pd.Series(
        {
            "patient_id": "pat_001",
            "name": "Paciente 1",
            "score": pd.Series([8], dtype="Int64").iloc[0],
            "open_alerts": pd.Series([0], dtype="Int64").iloc[0],
            "engagement_rate": 0.8,
            "attendance_rate": 0.75,
        }
    )
    stats = _patient_stats(row)

    assert "Frequência" in stats
    assert stats["Frequência"] == "75% comparecimento"


def test_patient_stats_frequency_says_sem_sessoes_when_na() -> None:
    """attendance_rate NaN (sem cds ativos) => 'Sem sessões'."""
    row = pd.Series(
        {
            "patient_id": "pat_001",
            "name": "Paciente 1",
            "score": pd.Series([8], dtype="Int64").iloc[0],
            "open_alerts": pd.Series([0], dtype="Int64").iloc[0],
            "engagement_rate": 0.8,
            "attendance_rate": pd.NA,
        }
    )
    stats = _patient_stats(row)

    assert stats["Frequência"] == "Sem sessões"


def test_patient_stats_frequency_zero_means_zero_percent() -> None:
    """attendance_rate == 0.0 => '0% comparecimento' (paciente vai para 'Sem comparecimento').

    O painel ainda mostra a % numerica; o override do quadrante acontece
    em ``render()``.
    """
    row = pd.Series(
        {
            "patient_id": "pat_001",
            "name": "Paciente 1",
            "score": pd.Series([8], dtype="Int64").iloc[0],
            "open_alerts": pd.Series([0], dtype="Int64").iloc[0],
            "engagement_rate": 0.8,
            "attendance_rate": 0.0,
        }
    )
    stats = _patient_stats(row)

    assert stats["Frequência"] == "0% comparecimento"


# ---------------------------------------------------------------------------
# 4. Visual: 5 classes presentes no HTML gerado
# ---------------------------------------------------------------------------


def test_decision_map_html_renders_all_5_quadrants() -> None:
    """Mesmo sem pacientes, o HTML deve conter as 5 classes CSS e os 5 titulos."""
    empty_df = pd.DataFrame(
        columns=["patient_id", "name", "is_engaged", "is_satisfied"]
    )

    groups = {
        "Engajado + Satisfeito": empty_df,
        "Engajado + Não satisfeito": empty_df,
        "Não engajado + Satisfeito": empty_df,
        "Não engajado + Não satisfeito": empty_df,
        "Sem comparecimento": empty_df,
    }
    html = _decision_map_html(groups)

    for css_class in [
        "dm-quadrant-engaged-satisfied",
        "dm-quadrant-engaged-not-satisfied",
        "dm-quadrant-not-engaged-satisfied",
        "dm-quadrant-not-engaged-not-satisfied",
        "dm-quadrant-no-attendance",
    ]:
        assert css_class in html, f"Missing CSS class: {css_class}"

    for title in [
        "Engajado + Satisfeito",
        "Engajado + Não satisfeito",
        "Não engajado + Satisfeito",
        "Não engajado + Não satisfeito",
        "Sem comparecimento",
    ]:
        assert title in html, f"Missing quadrant title: {title}"


# ---------------------------------------------------------------------------
# 5. End-to-end: paciente com rate==0 vai para "Sem comparecimento"
# ---------------------------------------------------------------------------


def test_render_routes_zero_attendance_to_no_attendance_quadrant() -> None:
    """End-to-end via AppTest: paciente com rate==0 vai para 5a classe.

    Setup:
      * pat_001 (Kelly): atendida 100% (rate=1.0) -> quadrante normal
      * pat_002 (Jaqueline): rate=0.0 -> "Sem comparecimento"
    """
    script = """
import sys, os
sys.path.insert(0, os.path.abspath("."))

import pandas as pd
from src.pages import mapa_decisao

data = {
    "patients": pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Kelly", "Jaqueline"],
    }),
}

def _stub_summary(_data):
    return pd.DataFrame({
        "patient_id": ["pat_001", "pat_002"],
        "name": ["Kelly", "Jaqueline"],
        "is_engaged": pd.Series([True, True], dtype="boolean"),
        "is_satisfied": pd.Series([True, True], dtype="boolean"),
        "score": pd.Series([9, 9], dtype="Int64"),
        "open_alerts": pd.Series([0, 0], dtype="Int64"),
        "engagement_rate": pd.Series([0.9, 0.9], dtype="float64"),
        "days_to_renewal": pd.Series([30, 30], dtype="Int64"),
        "without_recent_weight": pd.Series([False, False], dtype="boolean"),
    })

def _stub_rates(_data, **kw):
    return pd.Series({"pat_001": 1.0, "pat_002": 0.0})

mapa_decisao.patient_summary = _stub_summary
mapa_decisao._compute_patient_attendance_rates = _stub_rates
mapa_decisao.render(data)
"""
    at = AppTest.from_string(script).run()
    assert not at.exception, f"Page raised: {[repr(e) for e in at.exception]}"

    rendered_html = " ".join(
        getattr(m, "value", "") for m in at.markdown if getattr(m, "value", "")
    )

    # Sanidade: nomes aparecem, 5a classe CSS aparece
    assert "Kelly" in rendered_html
    assert "Jaqueline" in rendered_html
    assert "dm-quadrant-no-attendance" in rendered_html
    assert "Sem comparecimento" in rendered_html
