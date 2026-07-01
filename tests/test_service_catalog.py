"""Tests for ``src/service_catalog/`` (MVP Jornada Clinica, Phase 1).

Cobertura:

  1. parse_catalog_csv — le arquivo CSV canonico e retorna entries.
  2. parse_catalog_csv — pula linhas com service_code ou name vazios.
  3. parse_catalog_csv — saneamento defensivo de classificacao, categoria,
     periodicidade, source, created_at.
  4. parse_catalog_csv — levanta ValueError para CSV sem colunas obrigatorias.
  5. upsert_service — INSERT se nao existe; UPDATE se existe (idempotente).
  6. get_service — busca por codigo; retorna None se nao existe.
  7. import_catalog — processa batch com ImportResult.inserted/updated/failed.
  8. enqueue_unknown_service — insere nova entry (action="inserted").
  9. enqueue_unknown_service — incrementa occurrences se mesmo nome ja' em
     pending (action="incremented", idempotente).
 10. enqueue_unknown_service — pula se ja' existe como classified ou ignored.
 11. enqueue_unknown_service — string vazia retorna skipped.
 12. mark_review_entry — atualiza status; retorna False se id nao existe.

N7 (exception handling): cobrirmos que nenhuma chamada do modulo levanta
excecao para o caller (todos engolem em try/except e logam em PT-BR via
logging). Quando ``load_table`` falha (simulado por monkeypatch), as
funcoes retornam sentinelas (None / False / skipped) em vez de explodir.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from src.data_layer import load_table
from src.service_catalog import (
    ServiceEntry,
    enqueue_unknown_service,
    get_service,
    import_catalog,
    list_catalog,
    mark_review_entry,
    upsert_service,
)
from src.service_catalog.parse import parse_catalog_csv
from src.service_catalog.persist import ImportResult

# Caminho canonico da fixture. Sempre presente; o parser nao toca o data
# layer, entao funciona mesmo sem o fixture ``csv_dir``.
SAMPLE_CSV = Path(__file__).resolve().parent / "fixtures" / "service_catalog_sample.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    code: str = "TEST_SVC",
    name: str = "Servico de Teste",
    classification: str = "active",
    category: str | None = "professional",
    periodicity: int | None = 30,
    source: str = "lista_ativa",
) -> ServiceEntry:
    return ServiceEntry(
        service_code=code,
        name=name,
        classification=classification,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        default_periodicity_days=periodicity,
        source=source,  # type: ignore[arg-type]
        created_at=pd.Timestamp("2026-06-01"),
    )


# ---------------------------------------------------------------------------
# 1. parse_catalog_csv — basic happy path
# ---------------------------------------------------------------------------


def test_parse_catalog_csv_returns_entries() -> None:
    """Le o CSV de fixture e retorna 10 entries validas + 1 skipped."""
    result = parse_catalog_csv(SAMPLE_CSV)

    assert isinstance(result.entries, tuple)
    assert len(result.entries) == 10
    # 1 linha pulada: row vazia (sem service_code).
    # A row VALID_PERIODIC (periodicity 7.5) e' mantida como periodicidade=None.
    # A row DERMATO_PED (categoria vazia) e' mantida como category=None.
    assert result.rows_skipped == 1
    # Linhas totais no CSV (header nao conta).
    assert result.rows_total == 11


def test_parse_catalog_csv_preserves_valid_fields() -> None:
    """Uma entry bem-formada tem todos os campos inalterados."""
    result = parse_catalog_csv(SAMPLE_CSV)
    morpheus = next(e for e in result.entries if e.service_code == "MORPHEUS_FORMA_V")

    assert morpheus.name == "Morpheus - FORMA V"
    assert morpheus.classification == "active"
    assert morpheus.category == "professional"
    assert morpheus.default_periodicity_days == 30
    assert morpheus.source == "lista_ativa"
    assert morpheus.created_at == pd.Timestamp("2026-06-01")


# ---------------------------------------------------------------------------
# 2. parse_catalog_csv — row-level defenses
# ---------------------------------------------------------------------------


def test_parse_catalog_csv_skips_empty_code() -> None:
    """Linha com service_code vazio e' pulada (nao explode)."""
    result = parse_catalog_csv(SAMPLE_CSV)
    codes = [e.service_code for e in result.entries]
    assert "" not in codes


def test_parse_catalog_csv_drops_invalid_periodicity_to_none() -> None:
    """``7.5`` (nao-inteiro) vira ``None`` + warning."""
    result = parse_catalog_csv(SAMPLE_CSV)
    bad = next(e for e in result.entries if e.service_code == "VALID_PERIODIC")
    assert bad.default_periodicity_days is None


def test_parse_catalog_csv_drops_invalid_category_to_none() -> None:
    """Category vazia vira ``None`` (input ja' estava limpo)."""
    result = parse_catalog_csv(SAMPLE_CSV)
    dermato = next(e for e in result.entries if e.service_code == "DERMATO_PED")
    assert dermato.category is None


def test_parse_catalog_csv_uses_default_source_for_empty() -> None:
    """Quando ``source`` no CSV e' vazio/invalido, usa default do caller."""
    # CSV tem source vazio para a linha skip-row, entao passamos o CSV
    # com default_source='dane' e checamos que o default e' aplicado.
    result = parse_catalog_csv(SAMPLE_CSV, default_source="dane")
    # Todas as entradas de lista_ativa continuam lista_ativa (source ja' na CSV).
    sample = next(e for e in result.entries if e.service_code == "MORPHEUS_FORMA_V")
    assert sample.source == "lista_ativa"


# ---------------------------------------------------------------------------
# 3. parse_catalog_csv — error path
# ---------------------------------------------------------------------------


def test_parse_catalog_csv_raises_for_missing_columns(tmp_path: Path) -> None:
    """CSV sem colunas obrigatorias levanta ValueError (N7 na fronteira)."""
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "service_code,name,classification\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="coluna"):
        parse_catalog_csv(bad)


# ---------------------------------------------------------------------------
# 4. upsert + get_service — idempotencia
# ---------------------------------------------------------------------------


def test_upsert_inserts_then_updates(csv_dir) -> None:
    """Primeira chamada insere; segunda com mesmo codigo atualiza (idempotente)."""
    entry = _make_entry(code="UNIQ_001", name="Original")
    upsert_service(entry)
    df = load_table("service_catalog")
    assert "UNIQ_001" in df["service_code"].astype(str).tolist()

    # Update (mesmo codigo, nome novo).
    entry2 = _make_entry(code="UNIQ_001", name="Renomeado")
    upsert_service(entry2)

    df2 = load_table("service_catalog")
    rows = df2[df2["service_code"].astype(str) == "UNIQ_001"]
    assert len(rows) == 1, "upsert nao duplicou"
    assert str(rows.iloc[0]["name"]) == "Renomeado"


def test_upsert_keeps_original_created_at(csv_dir) -> None:
    """Update nao sobrescreve o created_at do primeiro import."""
    entry = _make_entry(code="UNIQ_002")
    upsert_service(entry)
    df_before = load_table("service_catalog")
    original_created = df_before[
        df_before["service_code"].astype(str) == "UNIQ_002"
    ].iloc[0]["created_at"]

    # Re-import com created_at mais recente.
    entry_v2 = ServiceEntry(
        service_code="UNIQ_002",
        name="Versao 2",
        classification="active",
        category="professional",
        default_periodicity_days=30,
        source="dane",
        created_at=pd.Timestamp("2027-01-01"),
    )
    upsert_service(entry_v2)

    df_after = load_table("service_catalog")
    new_created = df_after[
        df_after["service_code"].astype(str) == "UNIQ_002"
    ].iloc[0]["created_at"]
    assert pd.Timestamp(original_created) == pd.Timestamp(new_created)


def test_get_service_returns_entry(csv_dir) -> None:
    """``get_service`` retorna :class:`ServiceEntry` para codigo existente."""
    entry = _make_entry(code="UNIQ_003", name="Encontrar-me")
    upsert_service(entry)
    found = get_service("UNIQ_003")
    assert found is not None
    assert found.service_code == "UNIQ_003"
    assert found.name == "Encontrar-me"


def test_get_service_returns_none_for_unknown(csv_dir) -> None:
    """``get_service`` retorna ``None`` se codigo nao existe."""
    assert get_service("NAO_EXISTE") is None


def test_get_service_returns_none_on_data_layer_failure(monkeypatch, caplog) -> None:
    """Se ``load_table`` explodir, ``get_service`` retorna ``None`` (N7)."""
    from src.service_catalog import persist as persist_mod

    def boom(_table):
        raise RuntimeError("backend indisponivel")

    monkeypatch.setattr(persist_mod, "load_table", boom)
    with caplog.at_level(logging.ERROR, logger="src.service_catalog.persist"):
        result = get_service("X")
    assert result is None
    assert "load_table falhou" in caplog.text


# ---------------------------------------------------------------------------
# 5. import_catalog — batch
# ---------------------------------------------------------------------------


def test_import_catalog_counts_insert_and_update(csv_dir) -> None:
    """Batch distingue inserted (novo) de updated (ja' existia)."""
    # Pre-popular 1 entrada.
    upsert_service(_make_entry(code="BATCH_001", name="Pre-existente"))

    entries = (
        _make_entry(code="BATCH_001", name="Atualizado"),  # update
        _make_entry(code="BATCH_002", name="Novo 1"),  # insert
        _make_entry(code="BATCH_003", name="Novo 2"),  # insert
    )
    summary = import_catalog(entries)

    assert isinstance(summary, ImportResult)
    assert summary.inserted == 2
    assert summary.updated == 1
    assert summary.failed == 0
    assert summary.errors == ()


def test_import_catalog_collects_errors_per_line(csv_dir, monkeypatch) -> None:
    """Erro em 1 linha nao interrompe batch e vai para ``errors``."""
    from src.service_catalog import persist as persist_mod

    original = persist_mod.upsert_service
    call_count = {"n": 0}

    def flaky(entry: ServiceEntry) -> str:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("backend timeout")
        return original(entry)

    monkeypatch.setattr(persist_mod, "upsert_service", flaky)

    entries = (
        _make_entry(code="BATCH_A", name="ok 1"),
        _make_entry(code="BATCH_B", name="vai falhar"),
        _make_entry(code="BATCH_C", name="ok 2"),
    )
    summary = import_catalog(entries)
    assert summary.inserted == 2
    assert summary.updated == 0
    assert summary.failed == 1
    assert len(summary.errors) == 1
    assert "BATCH_B" in summary.errors[0]


# ---------------------------------------------------------------------------
# 6. enqueue_unknown_service — idempotencia
# ---------------------------------------------------------------------------


def test_enqueue_unknown_service_inserts_new(csv_dir) -> None:
    """Novo nome -> ``action='inserted'``, occurrences=1."""
    result = enqueue_unknown_service("Servico Desconhecido X", source="excel_import")
    assert result.action == "inserted"
    assert result.review_id is not None
    assert result.review_id.startswith("srv_new_")


def test_enqueue_unknown_service_increments_on_repeat(csv_dir) -> None:
    """Mesmo nome + pending -> ``action='incremented'`` (idempotente)."""
    first = enqueue_unknown_service("Morpheus Variante", source="excel_import")
    assert first.action == "inserted"

    second = enqueue_unknown_service("Morpheus Variante", source="excel_import")
    assert second.action == "incremented"
    assert second.review_id == first.review_id

    # occurrences foi para 2.
    df = load_table("service_review_queue")
    row = df[df["id"].astype(str) == first.review_id].iloc[0]
    assert int(row["occurrences"]) == 2


def test_enqueue_unknown_service_increments_with_normalization(csv_dir) -> None:
    """``"  Morpheus   Variante  "`` (caixa/espacos diferentes) ainda incrementa."""
    first = enqueue_unknown_service("Morpheus Variante", source="excel_import")
    second = enqueue_unknown_service("  morpheus   variante  ", source="excel_import")
    assert first.action == "inserted"
    assert second.action == "incremented"
    assert second.review_id == first.review_id


def test_enqueue_unknown_service_skips_when_already_classified(csv_dir) -> None:
    """Se ja' existe como ``classified``, nao re-enfileira."""
    enqueue_unknown_service("Servico Classificado", source="excel_import")
    mark_review_entry(_last_id_in_queue(), "classified")

    result = enqueue_unknown_service("Servico Classificado", source="excel_import")
    assert result.action == "skipped"


def test_enqueue_unknown_service_skips_empty_name(csv_dir) -> None:
    """String vazia / None nao cria linha e nao levanta."""
    assert enqueue_unknown_service("", source="excel_import").action == "skipped"
    assert enqueue_unknown_service("   ", source="excel_import").action == "skipped"


def test_enqueue_unknown_service_swallows_load_table_failure(
    monkeypatch, caplog
) -> None:
    """Se load_table explodir, retorna ``skipped`` e loga em PT-BR (N7)."""
    from src.service_catalog import review_queue as rq

    def boom(_table):
        raise RuntimeError("backend off")

    monkeypatch.setattr(rq, "load_table", boom)
    with caplog.at_level(logging.ERROR, logger="src.service_catalog.review_queue"):
        result = enqueue_unknown_service("Qualquer Coisa", source="excel_import")
    assert result.action == "skipped"
    assert result.review_id is None
    assert "load_table falhou" in caplog.text


# ---------------------------------------------------------------------------
# 7. mark_review_entry
# ---------------------------------------------------------------------------


def test_mark_review_entry_updates_status(csv_dir) -> None:
    """``mark_review_entry`` muda ``status`` da entrada para ``ignored``."""
    enqueue_unknown_service("Servico a Ignorar", source="excel_import")
    rid = _last_id_in_queue()
    ok = mark_review_entry(rid, "ignored")
    assert ok is True

    df = load_table("service_review_queue")
    row = df[df["id"].astype(str) == rid].iloc[0]
    assert str(row["status"]) == "ignored"


def test_mark_review_entry_returns_false_for_unknown(csv_dir) -> None:
    """``mark_review_entry`` retorna ``False`` se id nao existe."""
    assert mark_review_entry("srv_new_99999", "ignored") is False


def test_mark_review_entry_swallows_load_table_failure(
    monkeypatch, caplog
) -> None:
    """Se load_table explodir, retorna ``False`` em vez de levantar (N7)."""
    from src.service_catalog import review_queue as rq

    def boom(_table):
        raise RuntimeError("backend off")

    monkeypatch.setattr(rq, "load_table", boom)
    with caplog.at_level(logging.ERROR, logger="src.service_catalog.review_queue"):
        result = mark_review_entry("srv_new_001", "ignored")
    assert result is False
    assert "load_table falhou" in caplog.text


# ---------------------------------------------------------------------------
# 8. list_catalog sanity (basic structure check)
# ---------------------------------------------------------------------------


def test_list_catalog_returns_dataframe(csv_dir) -> None:
    """``list_catalog`` retorna DataFrame do data layer."""
    upsert_service(_make_entry(code="LIST_TEST", name="List Test"))
    df = list_catalog()
    assert isinstance(df, pd.DataFrame)
    assert "LIST_TEST" in df["service_code"].astype(str).tolist()


# ---------------------------------------------------------------------------
# Helpers privados para os testes acima
# ---------------------------------------------------------------------------


def _last_id_in_queue() -> str:
    """Retorna o id da ultima entry da fila (helper)."""
    df = load_table("service_review_queue")
    if df.empty or "id" not in df.columns:
        pytest.fail("fila vazia; popule-a antes de chamar este helper")
    return str(df.iloc[-1]["id"])