"""Tests for ``src/csv_importer/agendamentos.py`` (Caminho B, Phase 6).

Cobre o fluxo Agendamentos.csv → appointments + appointment_items,
com foco em **multi-valor** (Orcamento e/ou Agendamento) que gera
produto cartesiano.

  1. **test_parse_agendamentos_simple_line** (plano) — 1 linha com
     Orcamento="X", Agendamento="Y" → 1 item (1x1).
  2. **test_parse_agendamentos_multi_orcamento** (plano) — 1 linha com
     Orcamento="A, B", Agendamento="X" → 2 items (2x1).
  3. **test_parse_agendamentos_multi_procedimento** (extra) — 1 linha
     com Orcamento="X", Agendamento="A, B, C" → 3 items (1x3).
  4. **test_parse_agendamentos_cartesian** (extra) — 1 linha com
     Orcamento="A, B", Agendamento="X, Y" → 4 items (2x2).
  5. **test_parse_agendamentos_handles_dash_orcamento** (extra) —
     Orcamento="-" → 1 item com budget_code=None.
  6. **test_parse_agendamentos_skips_empty_line** (extra) — Orcamento=""
     E Agendamento="" → linha pulada.
  7. **test_parse_agendamentos_parses_data_range** (extra) —
     "19/06/2026 12:00 - 14:00" → (start=12:00, end=14:00).
  8. **test_persist_agendamentos_inserts** (plano) — 1 candidate →
     1 appointment + N items.
  9. **test_persist_agendamentos_continues_on_error** (extra) — 2
     candidates, 1 paciente faltando → 1 inserido, 1 erro em
     ``patient_errors``.
 10. **test_persist_agendamentos_missing_patient_raises** (extra) —
     nome nao cadastrado → :class:`PatientNotFoundError` em
     ``patient_errors``.

N7 boundary: parse_agendamentos_csv captura erros de I/O e re-emite
como CsvImportError.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.csv_importer.agendamentos import (
    AgendamentosParseResult,
    parse_agendamentos_csv,
    persist_agendamentos,
)
from src.csv_importer.frequencia import CsvImportError

# ---------------------------------------------------------------------------
# Fixtures — CSV inline (tmp_path)
# ---------------------------------------------------------------------------


# ruff: noqa: E501 (CSV header lines com 11 colunas excedem 100 chars por design)


CSV_SIMPLE = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10707345,Kelly Cristina a Silva Amorim,(62) 98137 - 4664,,4618731,25/05/2026 08:00 - 10:00,Consulta Nutróloga NOVA/AVULSA,Dayane Junqueira Vilela,Morena Gontijo De Araujo,Atendido,22/05/2026 - 14:18:28
"""


CSV_MULTI_ORC = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10367769,Vanessa Carneiro Benati,(62) 98472 - 4002,,"3760573, 3858738",25/05/2026 09:00 - 10:00,Injetáveis IM - Plano,Deborah Daniele Ribeiro,Deborah Daniele Ribeiro,Atendido,30/04/2026 - 12:47:51
"""


CSV_MULTI_PROC = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10738255,Silma Maria de Oliveira Mendes,(91) 60177 - 3629,,4115986,25/05/2026 14:00 - 15:00,"Morpheus - FORMA V, Morpheus - V TONE, Consulta Nutróloga NOVA/AVULSA",Guilherme Angelo Vilela Faria,Madalena Costa,Agendado,25/05/2026 - 16:39:11
"""


CSV_CARTESIAN = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10727234,Kelly Cristina a Silva Amorim,(62) 98137 - 4664,,"4622306, 4622413",25/05/2026 11:30 - 12:30,"Injetáveis EV - Plano, Injetáveis IM - Plano",Deborah Daniele Ribeiro,Deborah Daniele Ribeiro,Atendido,25/05/2026 - 11:31:51
"""


CSV_DASH_ORC = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10714439,VICTOR TROYSI ROCHA,(62) 99980 - 1390,,-,22/05/2026 16:00 - 18:00,Consulta Nutróloga NOVA/AVULSA,Dayane Junqueira Vilela,Morena Gontijo De Araujo,Agendado,22/05/2026 - 18:17:14
"""


CSV_EMPTY_LINE = """\
Código,Paciente,Telefone,Origem,Orçamento,Data,Agendamento,Profissional,Agendado por,Status,Data da criação
10714439,VICTOR TROYSI ROCHA,(62) 99980 - 1390,,,22/05/2026 16:00 - 18:00,,Dayane Junqueira Vilela,Morena Gontijo De Araujo,Agendado,22/05/2026 - 18:17:14
"""


@pytest.fixture
def data_with_2_patients() -> dict:
    """DataDict minimo com Kelly + Vanessa + Victor cadastrados."""
    return {
        "patients": pd.DataFrame(
            {
                "patient_id": ["pat_seed_kelly", "pat_seed_vanessa", "pat_seed_victor"],
                "name": [
                    "Kelly Cristina a Silva Amorim",
                    "Vanessa Carneiro Benati",
                    "VICTOR TROYSI ROCHA",
                ],
                "normalized_name": [
                    "kelly cristina a silva amorim",
                    "vanessa carneiro benati",
                    "victor troysi rocha",
                ],
            }
        ),
        "appointments": pd.DataFrame(),
        "appointment_items": pd.DataFrame(),
        "treatment_plans": pd.DataFrame(),
    }


# ---------------------------------------------------------------------------
# 1. simple line (1x1) (plano)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_simple_line(tmp_path: Path) -> None:
    """1 linha simples → 1 candidate com 1 item."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_SIMPLE, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    assert isinstance(result, AgendamentosParseResult)
    assert len(result.candidates) == 1
    assert result.rows_skipped == 0

    cand = result.candidates[0]
    assert cand.appointment_code == "10707345"
    assert cand.patient_name == "Kelly Cristina a Silva Amorim"
    assert cand.appointment_raw == "Consulta Nutróloga NOVA/AVULSA"
    assert cand.professional == "Dayane Junqueira Vilela"
    assert cand.scheduled_by == "Morena Gontijo De Araujo"
    assert cand.status == "Atendido"
    assert len(cand.items) == 1
    assert cand.items[0].orcamento == "4618731"
    assert cand.items[0].raw_item == "Consulta Nutróloga NOVA/AVULSA"
    # Data range parsed
    assert cand.appointment_start.hour == 8
    assert cand.appointment_end.hour == 10


# ---------------------------------------------------------------------------
# 2. multi-orcamento (2x1) (plano)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_multi_orcamento(tmp_path: Path) -> None:
    """``Orcamento="A, B", Agendamento="X"`` → 2 items (2x1)."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_MULTI_ORC, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    assert len(result.candidates) == 1
    cand = result.candidates[0]
    assert len(cand.items) == 2
    orcamentos = sorted([it.orcamento for it in cand.items])
    assert orcamentos == ["3760573", "3858738"]
    assert all(it.raw_item == "Injetáveis IM - Plano" for it in cand.items)


# ---------------------------------------------------------------------------
# 3. multi-procedimento (1x3) (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_multi_procedimento(tmp_path: Path) -> None:
    """``Orcamento="X", Agendamento="A, B, C"`` → 3 items (1x3)."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_MULTI_PROC, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    cand = result.candidates[0]
    assert len(cand.items) == 3
    procs = sorted([it.raw_item for it in cand.items])
    # CSV tem 3 procedimentos separados por virgula
    assert procs == [
        "Consulta Nutróloga NOVA/AVULSA",
        "Morpheus - FORMA V",
        "Morpheus - V TONE",
    ]
    # Todos os 3 items compartilham o mesmo orcamento
    assert all(it.orcamento == "4115986" for it in cand.items)


# ---------------------------------------------------------------------------
# 4. cartesian (2x2) (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_cartesian(tmp_path: Path) -> None:
    """``Orcamento="A, B", Agendamento="X, Y"`` → 4 items (2x2)."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_CARTESIAN, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    cand = result.candidates[0]
    assert len(cand.items) == 4
    # Combinacoes: (4622306, Injetáveis EV), (4622306, Injetáveis IM),
    #              (4622413, Injetáveis EV), (4622413, Injetáveis IM)
    pairs = {(it.orcamento, it.raw_item) for it in cand.items}
    assert ("4622306", "Injetáveis EV - Plano") in pairs
    assert ("4622306", "Injetáveis IM - Plano") in pairs
    assert ("4622413", "Injetáveis EV - Plano") in pairs
    assert ("4622413", "Injetáveis IM - Plano") in pairs


# ---------------------------------------------------------------------------
# 5. dash orcamento → budget=None (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_handles_dash_orcamento(tmp_path: Path) -> None:
    """``Orcamento="-"`` → 1 item com ``orcamento=None``."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_DASH_ORC, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    cand = result.candidates[0]
    assert len(cand.items) == 1
    assert cand.items[0].orcamento is None
    assert cand.items[0].raw_item == "Consulta Nutróloga NOVA/AVULSA"


# ---------------------------------------------------------------------------
# 6. empty line → skipped (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_skips_empty_line(tmp_path: Path) -> None:
    """Linha com Orcamento vazio E Agendamento vazio → ``rows_skipped += 1``."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_EMPTY_LINE, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    assert len(result.candidates) == 0
    assert result.rows_skipped == 1


# ---------------------------------------------------------------------------
# 7. data range parsed (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_parses_data_range(tmp_path: Path) -> None:
    """``"DD/MM HH:MM - HH:MM"`` → ``(start, end)`` populados no mesmo dia.

    Regressao Fase 6 1a rodada: ``parse_br_date_range("25/05/2026 12:00 - 14:00")``
    retornava ``start=2026-05-25 12:00`` e ``end=HOJE 14:00`` (bug do
    ``pd.to_datetime("14:00", dayfirst=True)`` que assume data atual).
    O teste original so' validava ``start.day/month/year/hour`` e
    ``end.hour``, deixando o bug passar. Agora validamos AMBOS os dates.
    """
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_SIMPLE, encoding="utf-8")

    result = parse_agendamentos_csv(csv)
    cand = result.candidates[0]
    # Start: 25/05/2026 08:00
    assert cand.appointment_start.day == 25
    assert cand.appointment_start.month == 5
    assert cand.appointment_start.year == 2026
    assert cand.appointment_start.hour == 8
    # End: 25/05/2026 10:00 (MESMO DIA do start, nao hoje!)
    assert cand.appointment_end.day == 25
    assert cand.appointment_end.month == 5
    assert cand.appointment_end.year == 2026
    assert cand.appointment_end.hour == 10
    # Mesmo dia explicitamente
    assert cand.appointment_start.date() == cand.appointment_end.date()


# ---------------------------------------------------------------------------
# 8. persist inserts (plano)
# ---------------------------------------------------------------------------


def test_persist_agendamentos_inserts(
    tmp_path: Path,
    data_with_2_patients: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 candidate com 1 item → 1 appointment + 1 item inserido."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_SIMPLE, encoding="utf-8")
    parsed = parse_agendamentos_csv(csv)

    captured: dict[str, list] = {"appointments": [], "items": []}
    counter = {"appt": 100, "item": 100}

    def fake_append(table: str, row: dict) -> None:
        bucket = {"appointments": "appointments", "appointment_items": "items"}[table]
        captured[bucket].append(row)

    def fake_next_id(table: str) -> str:
        prefix_map = {"appointments": "appt_new", "appointment_items": "aitem_new"}
        k = {"appointments": "appt", "appointment_items": "item"}[table]
        v = counter[k]
        counter[k] += 1
        return f"{prefix_map[table]}_{v:03d}"

    import src.csv_importer.agendamentos as ag_mod
    monkeypatch.setattr(ag_mod, "append_row", fake_append)
    monkeypatch.setattr(ag_mod, "next_id", fake_next_id)

    result = persist_agendamentos(data_with_2_patients, parsed)

    assert result.appointments_inserted == 1
    assert result.items_inserted == 1
    assert len(result.patient_errors) == 0
    assert len(captured["appointments"]) == 1
    assert captured["appointments"][0]["appointment_code"] == "10707345"
    assert captured["appointments"][0]["patient_id"] == "pat_seed_kelly"
    assert captured["appointments"][0]["budget_codes"] == "4618731"


# ---------------------------------------------------------------------------
# 9. cartesian persist (extra)
# ---------------------------------------------------------------------------


def test_persist_agendamentos_cartesian_persist(
    tmp_path: Path,
    data_with_2_patients: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV cartesian (2x2) → 1 appointment + 4 items."""
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_CARTESIAN, encoding="utf-8")
    parsed = parse_agendamentos_csv(csv)
    assert len(parsed.candidates[0].items) == 4

    captured: dict[str, list] = {"appointments": [], "items": []}
    counter = {"appt": 100, "item": 100}

    def fake_append(table: str, row: dict) -> None:
        bucket = {"appointments": "appointments", "appointment_items": "items"}[table]
        captured[bucket].append(row)

    def fake_next_id(table: str) -> str:
        prefix_map = {"appointments": "appt_new", "appointment_items": "aitem_new"}
        k = {"appointments": "appt", "appointment_items": "item"}[table]
        v = counter[k]
        counter[k] += 1
        return f"{prefix_map[table]}_{v:03d}"

    import src.csv_importer.agendamentos as ag_mod
    monkeypatch.setattr(ag_mod, "append_row", fake_append)
    monkeypatch.setattr(ag_mod, "next_id", fake_next_id)

    result = persist_agendamentos(data_with_2_patients, parsed)

    assert result.appointments_inserted == 1
    assert result.items_inserted == 4
    assert len(captured["items"]) == 4
    # budget_codes na appointment deve ter ambos os orcamentos (CSV string)
    assert "4622306" in captured["appointments"][0]["budget_codes"]
    assert "4622413" in captured["appointments"][0]["budget_codes"]


# ---------------------------------------------------------------------------
# 10. persist unmatched patient (extra)
# ---------------------------------------------------------------------------


def test_persist_agendamentos_missing_patient_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paciente nao cadastrado → erro em ``patient_errors``; nenhum append."""
    # DataDict VAZIO (nenhum paciente cadastrado)
    data = {
        "patients": pd.DataFrame(),
        "appointments": pd.DataFrame(),
        "appointment_items": pd.DataFrame(),
    }
    csv = tmp_path / "ag.csv"
    csv.write_text(CSV_SIMPLE, encoding="utf-8")
    parsed = parse_agendamentos_csv(csv)

    def fail_append(table: str, row: dict) -> None:
        raise AssertionError("append_row chamado apesar de paciente faltando")

    def fail_next_id(table: str) -> str:
        raise AssertionError("next_id chamado apesar de paciente faltando")

    import src.csv_importer.agendamentos as ag_mod
    monkeypatch.setattr(ag_mod, "append_row", fail_append)
    monkeypatch.setattr(ag_mod, "next_id", fail_next_id)

    result = persist_agendamentos(data, parsed)

    assert result.appointments_inserted == 0
    assert result.items_inserted == 0
    assert len(result.patient_errors) == 1
    assert result.patient_errors[0].name == "Kelly Cristina a Silva Amorim"


# ---------------------------------------------------------------------------
# 11. missing file (extra)
# ---------------------------------------------------------------------------


def test_parse_agendamentos_missing_file(tmp_path: Path) -> None:
    """Path invalido levanta :class:`CsvImportError`."""
    bogus = tmp_path / "nao_existe.csv"
    with pytest.raises(CsvImportError) as excinfo:
        parse_agendamentos_csv(bogus)
    assert "nao encontrado" in str(excinfo.value).lower()
