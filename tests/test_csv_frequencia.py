"""Tests for ``src/csv_importer/frequencia.py`` (Caminho B, Phase 6).

Cobre o fluxo Relatorio de frequencia.csv → treatment_plans +
treatment_plan_items + execution_summary (read-model projection).

  1. **test_parse_frequencia_csv_basic** (plano) — Kelly 4 linhas →
     1 plan com 4 items. Verifica agregacao por (Paciente + Orcamento).
  2. **test_parse_frequencia_groups_by_orcamento** (plano) — Erick 10
     linhas com 3 orcamentos → 3 plans separados.
  3. **test_parse_frequencia_status_mapping** (extra) — "Em tratamento"
     → "Em andamento"; "Não iniciado" verbatim.
  4. **test_parse_frequencia_skips_empty_orcamento** (extra) — linhas
     com Orcamento vazio sao descartadas (``rows_skipped > 0``).
  5. **test_parse_frequencia_missing_file** (extra) — path invalido
     levanta :class:`CsvImportError`.
  6. **test_persist_frequencia_inserts_new_plan** (plano) — 1 candidate
     → 1 plan + 4 items + 4 executions inseridos.
  7. **test_persist_frequencia_raises_on_duplicate** (plano) —
     (Kelly, 4622306) ja' existe → :class:`DuplicatePlanError` é
     capturada em ``FrequenciaPersistResult.plan_errors``.
  8. **test_persist_frequencia_raises_on_unmatched_patient** (extra) —
     nome nao cadastrado → :class:`PatientNotFoundError` em
     ``FrequenciaPersistResult.patient_errors``.
  9. **test_persist_frequencia_skips_errors_continues** (extra) — em
     batch com 3 candidates, 1 falha (paciente) mas os outros 2 sao
     inseridos.

N7 boundary: parse_frequencia_csv captura erros de I/O e parsing
do pandas e re-emite como CsvImportError (PT-BR).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.csv_importer.frequencia import (
    CsvImportError,
    FrequenciaParseResult,
    parse_frequencia_csv,
    persist_frequencia,
)

# ---------------------------------------------------------------------------
# Fixtures — CSV inline (tmp_path)
# ---------------------------------------------------------------------------


# ruff: noqa: E501 (CSV header lines com 8 colunas excedem 100 chars por design)


CSV_KELLY = """\
Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento
Kelly Cristina a Silva Amorim,25/05/2026,Injetáveis EV - Plano,Em tratamento,4,1,3,4622306
Kelly Cristina a Silva Amorim,25/05/2026,Injetáveis IM - Plano,Em tratamento,4,1,3,4622306
Kelly Cristina a Silva Amorim,25/05/2026,Acompanhamento Profissional - Plano,Não iniciado,2,,2,4622306
Kelly Cristina a Silva Amorim,25/05/2026,Implante - Plano,Não iniciado,1,,1,4622306
"""


CSV_ERICK_MULTI_ORC = """\
Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento
ERICK DE SOUSA KUBIJAN,01/06/2026,Injetáveis EV - Plano,Não iniciado,12,,12,4671175
ERICK DE SOUSA KUBIJAN,01/06/2026,Injetáveis IM - Plano,Não iniciado,4,,4,4671175
ERICK DE SOUSA KUBIJAN,01/06/2026,Medicamentos Manipulados - Plano,Não iniciado,4,,4,4671175
ERICK DE SOUSA KUBIJAN,01/06/2026,Acompanhamento Profissional - Plano,Não iniciado,5,,5,4671175
ERICK DE SOUSA KUBIJAN,01/06/2026,Teste Intestinal - Origon,Não iniciado,1,,1,4671175
ERICK DE SOUSA KUBIJAN,01/06/2026,1º Sessão EV,Não iniciado,1,,1,4671251
ERICK DE SOUSA KUBIJAN,01/06/2026,1º Sessão EV - 2,Não iniciado,1,,1,4671251
ERICK DE SOUSA KUBIJAN,01/06/2026,1º Sessão IM,Não iniciado,1,,1,4671251
ERICK DE SOUSA KUBIJAN,01/06/2026,Deep Regenera,Não iniciado,10,,10,4671259
"""


CSV_WITH_BLANK_ORC = """\
Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento
Kelly Cristina a Silva Amorim,25/05/2026,Injetáveis EV - Plano,Em tratamento,4,1,3,4622306
Kelly Cristina a Silva Amorim,25/05/2026,Orçamento vazio linha,Não iniciado,1,,1,
Kelly Cristina a Silva Amorim,25/05/2026,Hífen linha,Não iniciado,1,,1,-
"""


@pytest.fixture
def data_with_kelly() -> dict:
    """DataDict minimo com Kelly cadastrada e 1 plan pre-existente."""
    return {
        "patients": pd.DataFrame(
            {
                "patient_id": ["pat_seed_kelly"],
                "name": ["Kelly Cristina a Silva Amorim"],
                "normalized_name": ["kelly cristina a silva amorim"],
            }
        ),
        "treatment_plans": pd.DataFrame(
            {
                "plan_id": ["plan_seed_001"],
                "patient_id": ["pat_seed_kelly"],
                "budget_code": ["4622306"],
                "issue_date": [pd.Timestamp("2026-01-01")],
                "start_date": [pd.Timestamp("2026-01-01")],
                "end_date": [pd.NaT],
                "status": ["Concluído"],
                "main_goal": ["Injetáveis EV - Plano"],
                "is_renewal": [False],
                "notes": ["Plan pre-existente (conflito de dedup)"],
            }
        ),
        "treatment_plan_items": pd.DataFrame(),
        "execution_summary": pd.DataFrame(),
    }


# ---------------------------------------------------------------------------
# 1-2. parse_frequencia_csv (plano)
# ---------------------------------------------------------------------------


def test_parse_frequencia_csv_basic(tmp_path: Path) -> None:
    """Kelly com 4 linhas (mesmo orcamento) → 1 plan com 4 items."""
    csv = tmp_path / "freq.csv"
    csv.write_text(CSV_KELLY, encoding="utf-8")

    result = parse_frequencia_csv(csv)

    assert isinstance(result, FrequenciaParseResult)
    assert len(result.candidates) == 1
    assert result.rows_skipped == 0

    cand = result.candidates[0]
    assert cand.patient_name == "Kelly Cristina a Silva Amorim"
    assert cand.orcamento == "4622306"
    assert len(cand.items) == 4
    # Items estao na ordem de aparicao
    assert cand.items[0].procedimento == "Injetáveis EV - Plano"
    assert cand.items[0].sessoes == 4
    assert cand.items[0].realizadas == 1
    assert cand.items[0].restantes == 3
    assert cand.items[1].procedimento == "Injetáveis IM - Plano"
    assert cand.items[2].procedimento == "Acompanhamento Profissional - Plano"
    assert cand.items[2].sessoes == 2
    assert cand.items[2].realizadas is None  # vazio no CSV → None
    assert cand.items[3].procedimento == "Implante - Plano"


def test_parse_frequencia_groups_by_orcamento(tmp_path: Path) -> None:
    """Erick com 9 linhas em 3 orcamentos → 3 plans separados."""
    csv = tmp_path / "freq.csv"
    csv.write_text(CSV_ERICK_MULTI_ORC, encoding="utf-8")

    result = parse_frequencia_csv(csv)

    assert len(result.candidates) == 3
    assert result.rows_skipped == 0
    orcamentos = sorted(c.orcamento for c in result.candidates)
    assert orcamentos == ["4671175", "4671251", "4671259"]
    # 4671175 tem 5 items, 4671251 tem 3 items, 4671259 tem 1 item
    by_orc = {c.orcamento: c for c in result.candidates}
    assert len(by_orc["4671175"].items) == 5
    assert len(by_orc["4671251"].items) == 3
    assert len(by_orc["4671259"].items) == 1


# ---------------------------------------------------------------------------
# 3-5. parse_frequencia extras
# ---------------------------------------------------------------------------


def test_parse_frequencia_status_mapping(tmp_path: Path) -> None:
    """``Em tratamento`` → ``Em andamento``; ``Não iniciado`` verbatim."""
    csv = tmp_path / "freq.csv"
    csv.write_text(CSV_KELLY, encoding="utf-8")

    result = parse_frequencia_csv(csv)
    cand = result.candidates[0]
    # Kelly tem 2 items "Em tratamento" e 2 "Não iniciado" — mas o status
    # do PLAN e' derivado do 1º item (linha de cabeçalho do grupo)
    assert cand.status == "Em andamento"


def test_parse_frequencia_skips_empty_orcamento(tmp_path: Path) -> None:
    """Linhas com Orcamento vazio sao puladas (rows_skipped > 0)."""
    csv = tmp_path / "freq.csv"
    csv.write_text(CSV_WITH_BLANK_ORC, encoding="utf-8")

    result = parse_frequencia_csv(csv)
    assert len(result.candidates) == 1
    assert result.candidates[0].orcamento == "4622306"
    assert len(result.candidates[0].items) == 1
    assert result.rows_skipped == 2


def test_parse_frequencia_missing_file(tmp_path: Path) -> None:
    """Path invalido levanta :class:`CsvImportError` com mensagem PT-BR."""
    bogus = tmp_path / "nao_existe.csv"
    with pytest.raises(CsvImportError) as excinfo:
        parse_frequencia_csv(bogus)
    assert "nao encontrado" in str(excinfo.value).lower()
    assert str(bogus) in str(excinfo.value)


# ---------------------------------------------------------------------------
# 6. persist_frequencia inserts (plano)
# ---------------------------------------------------------------------------


def test_persist_frequencia_inserts_new_plan(
    tmp_path: Path, data_with_kelly: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1 candidate novo → 1 plan + N items + N executions inseridos.

    Usa um DataLayer fake (captura rows por tabela) via monkeypatch
    em ``src.data_layer.append_row`` e ``next_id``.
    """
    captured: dict[str, list] = {"plans": [], "items": [], "exec": []}
    id_counter = {"plan": 100, "item": 100, "exec": 100}

    def fake_append(table: str, row: dict) -> None:
        if table == "treatment_plans":
            captured["plans"].append(row)
        elif table == "treatment_plan_items":
            captured["items"].append(row)
        elif table == "execution_summary":
            captured["exec"].append(row)

    def fake_next_id(table: str) -> str:
        prefix_map = {
            "treatment_plans": "plan_new",
            "treatment_plan_items": "item_new",
            "execution_summary": "exec_new",
        }
        k = {
            "treatment_plans": "plan",
            "treatment_plan_items": "item",
            "execution_summary": "exec",
        }[table]
        n = id_counter[k]
        id_counter[k] += 1
        return f"{prefix_map[table]}_{n:03d}"

    import src.csv_importer.frequencia as freq_mod
    monkeypatch.setattr(freq_mod, "append_row", fake_append)
    monkeypatch.setattr(freq_mod, "next_id", fake_next_id)

    # CSV com 1 plan NOVO (orcamento diferente do pre-existente)
    csv_text = """\
Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento
Kelly Cristina a Silva Amorim,01/06/2026,Novo Procedimento,Não iniciado,3,,3,9999999
"""
    csv = tmp_path / "freq.csv"
    csv.write_text(csv_text, encoding="utf-8")
    parsed = parse_frequencia_csv(csv)

    result = persist_frequencia(data_with_kelly, parsed)

    assert result.plans_inserted == 1
    assert result.items_inserted == 1
    assert result.executions_inserted == 1
    assert len(result.patient_errors) == 0
    assert len(result.plan_errors) == 0
    assert len(captured["plans"]) == 1
    assert captured["plans"][0]["budget_code"] == "9999999"
    assert captured["plans"][0]["patient_id"] == "pat_seed_kelly"
    assert captured["plans"][0]["status"] == "Não iniciado"


# ---------------------------------------------------------------------------
# 7. persist duplicate detection (plano)
# ---------------------------------------------------------------------------


def test_persist_frequencia_raises_on_duplicate(
    tmp_path: Path, data_with_kelly: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(Kelly, 4622306) ja' existe → :class:`DuplicatePlanError` em plan_errors."""
    # CSV com mesmo orcamento do plan pre-existente (4622306)
    csv = tmp_path / "freq.csv"
    csv.write_text(CSV_KELLY, encoding="utf-8")
    parsed = parse_frequencia_csv(csv)

    # Stub de append_row e next_id (nao devem ser chamados se dedup funcionar)
    def fail_append(table: str, row: dict) -> None:
        raise AssertionError(f"append_row({table}) chamado apesar do dedup")

    def fail_next_id(table: str) -> str:
        raise AssertionError(f"next_id({table}) chamado apesar do dedup")

    import src.csv_importer.frequencia as freq_mod
    monkeypatch.setattr(freq_mod, "append_row", fail_append)
    monkeypatch.setattr(freq_mod, "next_id", fail_next_id)

    result = persist_frequencia(data_with_kelly, parsed)

    assert result.plans_inserted == 0
    assert result.items_inserted == 0
    assert result.executions_inserted == 0
    assert len(result.plan_errors) == 1
    assert result.plan_errors[0].existing_plan_id == "plan_seed_001"
    assert result.plan_errors[0].orcamento == "4622306"


# ---------------------------------------------------------------------------
# 8. persist unmatched patient
# ---------------------------------------------------------------------------


def test_persist_frequencia_raises_on_unmatched_patient(
    tmp_path: Path, data_with_kelly: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nome nao cadastrado → :class:`PatientNotFoundError` em patient_errors."""
    csv = tmp_path / "freq.csv"
    csv.write_text(
        "Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento\n"
        "Fantasma da Silva,25/05/2026,Injetáveis EV,Não iniciado,4,,4,1234567\n",
        encoding="utf-8",
    )
    parsed = parse_frequencia_csv(csv)

    # Nenhum append/next_id deve ser chamado
    def fail_append(table: str, row: dict) -> None:
        raise AssertionError("append_row chamado apesar de paciente faltando")

    def fail_next_id(table: str) -> str:
        raise AssertionError("next_id chamado apesar de paciente faltando")

    import src.csv_importer.frequencia as freq_mod
    monkeypatch.setattr(freq_mod, "append_row", fail_append)
    monkeypatch.setattr(freq_mod, "next_id", fail_next_id)

    result = persist_frequencia(data_with_kelly, parsed)

    assert result.plans_inserted == 0
    assert len(result.patient_errors) == 1
    assert result.patient_errors[0].name == "Fantasma da Silva"
    assert result.patient_errors[0].orcamento == "1234567"


# ---------------------------------------------------------------------------
# 9. persist skips errors and continues
# ---------------------------------------------------------------------------


def test_persist_frequencia_skips_errors_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Em batch com 3 candidates (1 erro de paciente, 1 erro de plan dup,
    1 sucesso), apenas o terceiro e' inserido.
    """
    # DataDict com 2 pacientes + 1 plan pre-existente
    data = {
        "patients": pd.DataFrame(
            {
                "patient_id": ["pat_seed_kelly", "pat_seed_erick"],
                "name": ["Kelly Cristina a Silva Amorim", "ERICK DE SOUSA KUBIJAN"],
                "normalized_name": [
                    "kelly cristina a silva amorim",
                    "erick de sousa kubijan",
                ],
            }
        ),
        "treatment_plans": pd.DataFrame(
            {
                "plan_id": ["plan_seed_dup"],
                "patient_id": ["pat_seed_erick"],
                "budget_code": ["8888888"],
            }
        ),
        "treatment_plan_items": pd.DataFrame(),
        "execution_summary": pd.DataFrame(),
    }

    csv = tmp_path / "freq.csv"
    csv.write_text(
        # 1) Fantasma (nao cadastrado) → erro patient
        "Paciente,Criação do plano,Procedimento,Status,Sessões,Realizadas,Restantes,Orçamento\n"
        "Fantasma da Silva,25/05/2026,Proc 1,Não iniciado,1,,1,1111111\n"
        # 2) Erick 8888888 (ja' existe) → erro plan dup
        "ERICK DE SOUSA KUBIJAN,25/05/2026,Proc 2,Não iniciado,1,,1,8888888\n"
        # 3) Kelly 7777777 (novo) → sucesso
        "Kelly Cristina a Silva Amorim,25/05/2026,Proc 3,Em tratamento,2,1,1,7777777\n",
        encoding="utf-8",
    )
    parsed = parse_frequencia_csv(csv)
    assert len(parsed.candidates) == 3

    captured: dict[str, list] = {"plans": [], "items": [], "exec": []}
    counter = {"plan": 100, "item": 100, "exec": 100}

    def fake_append(table: str, row: dict) -> None:
        bucket = {"treatment_plans": "plans", "treatment_plan_items": "items", "execution_summary": "exec"}[table]
        captured[bucket].append(row)

    def fake_next_id(table: str) -> str:
        prefix_map = {
            "treatment_plans": "plan_new",
            "treatment_plan_items": "item_new",
            "execution_summary": "exec_new",
        }
        k = {
            "treatment_plans": "plan",
            "treatment_plan_items": "item",
            "execution_summary": "exec",
        }[table]
        v = counter[k]
        counter[k] += 1
        return f"{prefix_map[table]}_{v:03d}"

    import src.csv_importer.frequencia as freq_mod
    monkeypatch.setattr(freq_mod, "append_row", fake_append)
    monkeypatch.setattr(freq_mod, "next_id", fake_next_id)

    result = persist_frequencia(data, parsed)

    assert result.plans_inserted == 1
    assert result.items_inserted == 1
    assert result.executions_inserted == 1
    assert len(result.patient_errors) == 1
    assert len(result.plan_errors) == 1
    # Apenas o plan da Kelly 7777777 foi inserido
    assert len(captured["plans"]) == 1
    assert captured["plans"][0]["budget_code"] == "7777777"
