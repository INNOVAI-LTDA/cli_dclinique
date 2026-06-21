"""Unit tests for the wizard UI (post-June-2026 redesign).

These tests pin the per-item preview table layout and the
section-title / revisão helpers. They are pure (no DB, no
Streamlit runtime) so they can run alongside the rest of the
CSV-mode unit tests.

Why pure: the wizard's full UI lives behind ``streamlit`` widgets
that AppTest doesn't drive deterministically in our environment
(``st.data_editor(on_change=...)`` has subtle rerun behavior). The
helpers tested here are the same functions the wizard calls
during a render, so a regression in the table shape or the
round-trip is caught even if the AppTest path stays green.
"""
from __future__ import annotations

import pandas as pd

from src.components.importar_pdf_wizard import (
    FREQUENCY_OPTIONS,
    _build_preview_rows,
    _from_preview_rows,
    _preview_section_title,
)


def _candidate(
    *,
    filename: str = "fixture.pdf",
    name: str = "Maria da Silva",
    cpf: str | None = "123.456.789-00",
    medical_record: str | None = "8887777",
    items: list[dict] | None = None,
    needs_manual_review: bool = False,
) -> dict:
    """Build a single-candidate dict the helpers can consume."""
    return {
        "filename": filename,
        "patient": {
            "name": name,
            "normalized_name": name.lower(),
            "medical_record": medical_record,
            "phone": "",
            "age": 30,
            "cpf": cpf,
            "rg": "",
            "address": "",
            "created_at": "2026-06-21",
        },
        "plan": {
            "budget_code": "",
            "issue_date": "2026-06-01",
            "start_date": "2026-06-01",
            "end_date": None,
            "status": "Ativo",
            "main_goal": "Emagrecimento",
            "is_renewal": False,
            "notes": "",
        },
        "items": items
        or [
            {
                "raw_name": "Drenagem linfática",
                "category": "Drenagem",
                "sessions_expected": 10,
                "frequency_text": "1x/semana",
                "frequency_type": "semanal",
                "needs_manual_review": needs_manual_review,
            },
            {
                "raw_name": "Massagem modeladora",
                "category": "Massagem",
                "sessions_expected": 8,
                "frequency_text": "1x/semana",
                "frequency_type": "semanal",
                "needs_manual_review": needs_manual_review,
            },
        ],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Layout: build_preview_rows
# ---------------------------------------------------------------------------


def test_build_preview_rows_uses_new_column_layout():
    """The preview table drops the 6 contextual columns and keeps
    only the 6 item-level columns the user edits — plus the
    hidden ``filename`` used for the round-trip. The two
    frequency columns sit side-by-side (Frequência first because
    it's the canonical DB value, then Desc. Frequência)."""
    candidates = [_candidate()]
    df = _build_preview_rows(candidates)
    visible = [c for c in df.columns if c != "filename"]
    assert visible == [
        "procedimento",
        "sessoes",
        "frequencia",
        "desc_frequencia",
        "categoria",
        "revisao",
    ], f"unexpected visible columns: {visible}"
    # ``filename`` is in the DataFrame but not in the visible
    # order — the editor uses ``column_order`` to hide it.
    assert "filename" in df.columns
    assert df["filename"].iloc[0] == "fixture.pdf"


def test_build_preview_rows_keeps_frequency_type_in_dropdown_column():
    """The new ``frequencia`` column carries the normalized
    ``frequency_type`` (one of :data:`FREQUENCY_OPTIONS`) — this
    is what the dropdown is bound to."""
    candidates = [
        _candidate(
            items=[
                {
                    "raw_name": "Radiofrequência",
                    "category": "Estética",
                    "sessions_expected": 6,
                    "frequency_text": "1x/semana",
                    "frequency_type": "semanal",
                    "needs_manual_review": False,
                },
            ]
        )
    ]
    df = _build_preview_rows(candidates)
    assert df["frequencia"].iloc[0] == "semanal"
    assert "semanal" in FREQUENCY_OPTIONS


def test_build_preview_rows_empty_candidates_returns_dataframe_with_columns():
    """When no candidates have items the build function still
    returns a DataFrame with the expected columns (so the
    ``column_config`` keys resolve)."""
    df = _build_preview_rows([])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "procedimento",
        "sessoes",
        "frequencia",
        "desc_frequencia",
        "categoria",
        "revisao",
        "filename",
    ]


def test_build_preview_rows_renames_revisar_to_revisao():
    """The wizard's old "Revisar?" column is now "Revisão". The
    build function reads ``needs_manual_review`` (the parser
    flag) and exposes it under the new column name."""
    candidates = [
        _candidate(
            items=[
                {
                    "raw_name": "Procedimento X",
                    "category": "",
                    "sessions_expected": 1,
                    "frequency_text": "dose única",
                    "frequency_type": "dose única",
                    "needs_manual_review": True,
                },
            ]
        )
    ]
    df = _build_preview_rows(candidates)
    assert df["revisao"].iloc[0] is True or df["revisao"].iloc[0] == True


# ---------------------------------------------------------------------------
# Layout: preview_section_title
# ---------------------------------------------------------------------------


def test_section_title_single_candidate():
    """For a single PDF the title carries the patient's name,
    CPF and prontuário in that exact order, with the CPF /
    Prontuário labels per the ficha header convention."""
    candidates = [_candidate()]
    title = _preview_section_title(candidates)
    assert title == (
        "Pré-visualização Editável: Maria da Silva, "
        "CPF: 123.456.789-00, Prontuário: 8887777"
    )


def test_section_title_multi_candidate_uses_first_and_count_suffix():
    """For N>1 candidates the title shows the first patient's
    identity plus a ``(+N mais)`` suffix so the rest of the
    batch is still visible at a glance."""
    candidates = [
        _candidate(filename="a.pdf", name="Maria da Silva"),
        _candidate(filename="b.pdf", name="João Souza"),
        _candidate(filename="c.pdf", name="Ana Pereira"),
    ]
    title = _preview_section_title(candidates)
    assert title == (
        "Pré-visualização Editável: Maria da Silva, "
        "CPF: 123.456.789-00, Prontuário: 8887777 (+2 mais)"
    )


def test_section_title_handles_missing_patient_fields():
    """When the parser missed the name/CPF/prontuário the title
    falls back to ``"—"`` per field rather than crashing or
    showing a stray empty comma."""
    candidates = [
        _candidate(
            name="",
            cpf=None,
            medical_record=None,
        )
    ]
    title = _preview_section_title(candidates)
    assert title == "Pré-visualização Editável: —, CPF: —, Prontuário: —"


def test_section_title_empty_candidates_returns_placeholder():
    """The wizard never calls this with zero candidates (it
    returns early above), but the helper stays sane if it does."""
    assert _preview_section_title([]) == "Pré-visualização Editável: —"


# ---------------------------------------------------------------------------
# Round-trip: from_preview_rows
# ---------------------------------------------------------------------------


def test_from_preview_rows_round_trips_new_columns():
    """The editor → candidate round-trip carries the new columns
    (incl. ``frequency_type`` from the dropdown) and preserves
    the patient / plan dict verbatim."""
    candidates = [_candidate()]
    rows = _build_preview_rows(candidates)
    # Simulate a user edit: change procedimento + frequencia
    # (dropdown selection) + revisao.
    rows.loc[0, "procedimento"] = "Drenagem profunda"
    rows.loc[0, "frequencia"] = "quinzenal"
    rows.loc[1, "revisao"] = True
    rows.loc[1, "sessoes"] = 12

    out = _from_preview_rows(rows, candidates)
    assert len(out) == 1
    new_items = out[0]["items"]
    assert new_items[0]["raw_name"] == "Drenagem profunda"
    assert new_items[0]["frequency_type"] == "quinzenal"
    # The second item's needs_manual_review was flipped to True
    # via the editor.
    assert new_items[1]["needs_manual_review"] is True
    assert new_items[1]["sessions_expected"] == 12
    # Desc. Frequência (free text) was preserved unchanged.
    assert new_items[0]["frequency_text"] == "1x/semana"


def test_from_preview_rows_empty_frequencia_becomes_none():
    """An empty cell in the dropdown column means "no category";
    we write NULL to the DB, not an empty string. Empty strings
    would land as ``""`` in ``treatment_plan_items`` and break
    the equality checks in the ficha / quality page."""
    candidates = [
        _candidate(
            items=[
                {
                    "raw_name": "Procedimento X",
                    "category": "Estética",
                    "sessions_expected": 4,
                    "frequency_text": "",
                    "frequency_type": "semanal",
                    "needs_manual_review": False,
                },
            ]
        )
    ]
    rows = _build_preview_rows(candidates)
    rows.loc[0, "frequencia"] = ""  # user cleared the dropdown

    out = _from_preview_rows(rows, candidates)
    assert out[0]["items"][0]["frequency_type"] is None


def test_from_preview_rows_groups_by_filename_across_candidates():
    """When multiple PDFs are in flight, the round-trip keeps
    each candidate's items grouped under the right filename so
    the persist step writes them under the right patient."""
    candidates = [
        _candidate(
            filename="a.pdf",
            items=[
                {
                    "raw_name": "Item A1",
                    "category": "",
                    "sessions_expected": 5,
                    "frequency_text": "",
                    "frequency_type": "semanal",
                    "needs_manual_review": False,
                },
            ],
        ),
        _candidate(
            filename="b.pdf",
            items=[
                {
                    "raw_name": "Item B1",
                    "category": "",
                    "sessions_expected": 7,
                    "frequency_text": "",
                    "frequency_type": "mensal",
                    "needs_manual_review": False,
                },
            ],
        ),
    ]
    rows = _build_preview_rows(candidates)
    out = _from_preview_rows(rows, candidates)
    by_filename = {c["filename"]: c for c in out}
    assert by_filename["a.pdf"]["items"][0]["raw_name"] == "Item A1"
    assert by_filename["b.pdf"]["items"][0]["raw_name"] == "Item B1"
    assert by_filename["a.pdf"]["items"][0]["frequency_type"] == "semanal"
    assert by_filename["b.pdf"]["items"][0]["frequency_type"] == "mensal"


# ---------------------------------------------------------------------------
# FREQUENCY_OPTIONS
# ---------------------------------------------------------------------------


def test_frequency_options_match_user_spec():
    """Pin the dropdown's option list — the operator picked
    these exact values in June 2026 and the order is part of the
    UX (frequent → less frequent)."""
    assert FREQUENCY_OPTIONS == [
        "dose única",
        "diario",
        "a cada 5 dias",
        "semanal",
        "a cada 10 dias",
        "quinzenal",
        "mensal",
        "bimestral",
        "trimestral",
    ]