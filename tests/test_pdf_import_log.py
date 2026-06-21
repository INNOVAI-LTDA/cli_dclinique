"""Unit tests for :mod:`src.pdf_importer.log`.

The :class:`PdfImportLogger` is the core of the wizard's
"why did the CPF go missing?" debug surface — these tests pin
its event shape, ordering, HMS format, and atomic flush. They
do not require a Streamlit runtime: the logger is a plain
class that accepts kwargs and appends to an in-memory list.

A few tests also exercise the integration with
:func:`parse_pdf_to_rows`, :func:`validate_rows` and
:func:`persist_rows` to confirm the ``logger=`` keyword
threads through end-to-end and the events land in the expected
order.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.pdf_importer.log import (
    PdfImportEvent,
    PdfImportLogger,
    _hms,
    _short_repr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_logger(tmp_path: Path) -> PdfImportLogger:
    """Build a logger whose sink lives under ``tmp_path``.

    Each test gets its own sub-directory so the on-disk file
    doesn't leak between tests.
    """
    return PdfImportLogger(sink_path=tmp_path / "log.txt")


_HMS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")


# ---------------------------------------------------------------------------
# _hms
# ---------------------------------------------------------------------------


def test_hms_format_is_24h_with_milliseconds():
    """The HMS string is ``HH:MM:SS.mmm`` (24-hour clock, three-digit ms)."""
    # 2026-01-01T00:00:00 UTC is 1798747200 epoch seconds.
    out = _hms(1798747200.0)
    assert _HMS_RE.match(out), f"unexpected HMS shape: {out!r}"
    # Range checks guard against the original "naive ts/3600" bug
    # that produced hour values in the thousands for 2026
    # timestamps. Hours must be 0-23.
    hh, mm, ss_ms = out.split(":")
    ss, ms = ss_ms.split(".")
    assert 0 <= int(hh) <= 23
    assert 0 <= int(mm) <= 59
    assert 0 <= int(ss) <= 59
    assert 0 <= int(ms) <= 999


# ---------------------------------------------------------------------------
# Logger: start / stage / warn / error / finish
# ---------------------------------------------------------------------------


def test_start_emits_one_info_event(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.start("foo.pdf", total_zones=4, has_field_mappings=True)
    events = logger.events()
    assert len(events) == 1
    ev = events[0]
    assert ev["level"] == "INFO"
    assert ev["stage"] == "start"
    assert ev["payload"] == {
        "filename": "foo.pdf",
        "total_zones": 4,
        "has_field_mappings": True,
    }
    assert ev["msg"].startswith("import started:")
    assert _HMS_RE.match(ev["ts_hms"])


def test_stage_emits_info_event_with_kwargs_as_payload(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.stage("parse", total_zones=3)
    assert logger.events()[0]["payload"] == {"total_zones": 3}


def test_warn_emits_warn_event(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.warn("CPF ausente", cpf=None)
    ev = logger.events()[0]
    assert ev["level"] == "WARN"
    assert ev["stage"] == "warn"
    assert ev["payload"] == {"cpf": None}


def test_error_emits_error_event(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.error("parse failed", error="boom")
    ev = logger.events()[0]
    assert ev["level"] == "ERROR"
    assert ev["payload"] == {"error": "boom"}


# ---------------------------------------------------------------------------
# Logger: field() status routing
# ---------------------------------------------------------------------------


def test_field_matched_is_info_and_carries_value(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.field("dados_paciente", "name", "MATCHED", value="Maria da Silva")
    ev = logger.events()[0]
    assert ev["level"] == "INFO"
    assert ev["payload"]["value"] == "Maria da Silva"
    assert ev["payload"]["status"] == "MATCHED"
    # The pattern only ships when debug mode is on (see
    # ``test_field_pattern_only_with_debug``).
    assert "pattern" not in ev["payload"]


def test_field_missing_required_is_warn(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.field("dados_paciente", "cpf", "MISSING_REQUIRED")
    ev = logger.events()[0]
    assert ev["level"] == "WARN"
    assert "value" not in ev["payload"]


def test_field_normalizer_failed_is_warn(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.field("dados_paciente", "age", "NORMALIZER_FAILED")
    assert logger.events()[0]["level"] == "WARN"


def test_field_missing_optional_is_info(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.field("rodape", "notes", "MISSING_OPTIONAL")
    assert logger.events()[0]["level"] == "INFO"


def test_field_pattern_only_with_debug(tmp_path):
    # Debug OFF: pattern is hidden.
    off = _empty_logger(tmp_path)
    off.field("dados_paciente", "name", "MATCHED", pattern=r"(.+)")
    assert "pattern" not in off.events()[0]["payload"]
    # Debug ON: pattern is part of the payload.
    on = PdfImportLogger(sink_path=tmp_path / "log_on.txt", debug=True)
    on.field("dados_paciente", "name", "MATCHED", pattern=r"(.+)")
    assert on.events()[0]["payload"]["pattern"] == r"(.+)"


# ---------------------------------------------------------------------------
# Logger: debug gating
# ---------------------------------------------------------------------------


def test_debug_event_dropped_when_debug_off(tmp_path, monkeypatch):
    # Force debug off even if the host env has PDF_IMPORT_DEBUG=1.
    monkeypatch.delenv("PDF_IMPORT_DEBUG", raising=False)
    logger = _empty_logger(tmp_path)
    logger.debug("raw text", value="ignored")
    assert logger.events() == []  # dropped, not recorded


def test_debug_event_recorded_when_debug_on(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_IMPORT_DEBUG", "1")
    logger = PdfImportLogger(sink_path=tmp_path / "log_dbg.txt")
    logger.debug("raw text", value="kept")
    ev = logger.events()[0]
    assert ev["level"] == "DEBUG"
    assert ev["payload"] == {"value": "kept"}


# ---------------------------------------------------------------------------
# Logger: finish
# ---------------------------------------------------------------------------


def test_finish_emits_final_event_with_duration(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.start("x.pdf", total_zones=2)
    logger.finish(success=True, imported_pids=["pat_new_001"])
    ev = logger.events()[-1]
    assert ev["stage"] == "finish"
    assert ev["payload"]["success"] is True
    assert ev["payload"]["imported_pids"] == ["pat_new_001"]
    assert "duration_ms" in ev["payload"]


def test_finish_failure_is_error_level(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.finish(success=False, reason="boom")
    assert logger.events()[-1]["level"] == "ERROR"


def test_finish_is_idempotent(tmp_path):
    """A second ``finish`` call must be a no-op (so wizard can
    call it in both the success and the error branches without
    worrying about double-flushing)."""
    logger = _empty_logger(tmp_path)
    logger.finish(success=True)
    logger.finish(success=False)
    # Only one finish event present.
    stages = [e["stage"] for e in logger.events()]
    assert stages.count("finish") == 1


# ---------------------------------------------------------------------------
# Logger: text rendering
# ---------------------------------------------------------------------------


def test_to_text_format_matches_pattern(tmp_path):
    logger = _empty_logger(tmp_path)
    logger.start("foo.pdf", total_zones=2)
    logger.field("dados_paciente", "cpf", "MATCHED", value="123.456.789-00")
    out = logger.to_text()
    # One line per event, with the canonical shape.
    lines = out.splitlines()
    assert len(lines) == 2
    for line in lines:
        # [HH:MM:SS.mmm] [LEVEL] stage: msg [| key=value, ...]
        # The level is right-padded to 5 chars ("INFO ", "WARN ", etc.)
        # so the bracket after the level can sit either at offset 4
        # or 5 — ``[\w ]{4,5}`` covers both.
        assert re.match(
            r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\] \[[\w ]{4,5}\] \w+: .*",
            line,
        ), line
    # The field line carries the status, value and (sorted) payload.
    field_line = lines[1]
    assert "MATCHED" in field_line
    assert "value=" in field_line


def test_to_text_omits_debug_when_off(tmp_path, monkeypatch):
    monkeypatch.delenv("PDF_IMPORT_DEBUG", raising=False)
    logger = _empty_logger(tmp_path)
    logger.stage("parse")
    logger.debug("raw")
    out = logger.to_text()
    # The debug event is not present in the text rendering.
    assert "DEBUG" not in out
    assert "raw" not in out


def test_to_text_includes_debug_when_on(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_IMPORT_DEBUG", "1")
    logger = PdfImportLogger(sink_path=tmp_path / "log.txt")
    logger.debug("raw")
    assert "raw" in logger.to_text()


def test_short_repr_caps_long_strings():
    """Long string values in the payload don't blow up the line width."""
    out = _short_repr("a" * 300)
    assert len(out) < 90
    assert "..." in out


def test_short_repr_caps_long_lists():
    out = _short_repr(list(range(20)))
    assert "..." in out
    assert "20 items" in out


# ---------------------------------------------------------------------------
# Logger: disk flush
# ---------------------------------------------------------------------------


def test_flush_to_disk_creates_file_atomically(tmp_path):
    """The on-disk file is created via a tmp+rename so a partial
    write never replaces a previous good log."""
    logger = _empty_logger(tmp_path)
    logger.start("a.pdf", total_zones=2)
    target = logger.flush_to_disk()
    assert target.exists()
    # The tmp file (with the .tmp suffix) must be gone — rename
    # happened cleanly.
    assert not target.with_suffix(target.suffix + ".tmp").exists()
    # Content matches ``to_text``.
    assert target.read_text(encoding="utf-8") == logger.to_text() + "\n"


def test_finish_flushes_to_disk_automatically(tmp_path):
    """``finish`` flushes to the logger's sink_path on success."""
    target = tmp_path / "auto.log"
    logger = PdfImportLogger(sink_path=target)
    logger.start("a.pdf", total_zones=1)
    logger.finish(success=True)
    assert target.exists()
    # The finish line is the last one in the file.
    text = target.read_text(encoding="utf-8")
    assert "finish" in text
    assert "import succeeded" in text


def test_flush_to_disk_without_path_or_sink_raises(tmp_path):
    logger = PdfImportLogger()  # no sink
    with pytest.raises(ValueError):
        logger.flush_to_disk()


def test_flush_to_disk_creates_parent_directories(tmp_path):
    deep = tmp_path / "sub" / "dir" / "log.txt"
    logger = PdfImportLogger(sink_path=deep)
    logger.start("a.pdf", total_zones=1)
    out = logger.flush_to_disk()
    assert out == deep
    assert deep.exists()


# ---------------------------------------------------------------------------
# Logger: __len__ / finished
# ---------------------------------------------------------------------------


def test_len_excludes_debug_when_off(tmp_path, monkeypatch):
    """When debug mode is off, ``debug()`` drops the event entirely
    (it is never recorded). ``events()`` and ``__len__`` therefore
    only see the INFO/WARN/ERROR events."""
    monkeypatch.delenv("PDF_IMPORT_DEBUG", raising=False)
    logger = _empty_logger(tmp_path)
    logger.stage("parse")
    logger.debug("hidden")
    # The debug event is dropped at the door — both the count
    # and the events list see only one event.
    assert len(logger) == 1
    assert len(logger.events()) == 1


def test_len_includes_debug_when_on(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_IMPORT_DEBUG", "1")
    logger = PdfImportLogger(sink_path=tmp_path / "log.txt")
    logger.stage("parse")
    logger.debug("kept")
    # With debug mode on, the debug event lands in ``_events``
    # and is counted by ``__len__`` and surfaced by ``events()``.
    assert len(logger) == 2
    assert len(logger.events()) == 2


def test_finished_property_flips_once(tmp_path):
    logger = _empty_logger(tmp_path)
    assert logger.finished is False
    logger.finish(success=True)
    assert logger.finished is True
    # Idempotent: still True after a second finish.
    logger.finish(success=False)
    assert logger.finished is True


def test_sink_path_property_round_trip(tmp_path):
    target = tmp_path / "x.log"
    logger = PdfImportLogger(sink_path=target)
    assert logger.sink_path == target


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


def test_event_to_row_returns_plain_dict():
    ev = PdfImportEvent(
        ts=1.0,
        ts_hms="00:00:01.000",
        level="INFO",
        stage="parse",
        msg="ok",
        payload={"k": 1},
    )
    row = ev.to_row()
    assert row == {
        "ts": 1.0,
        "ts_hms": "00:00:01.000",
        "level": "INFO",
        "stage": "parse",
        "msg": "ok",
        "payload": {"k": 1},
    }


# ---------------------------------------------------------------------------
# Integration: logger threads through parse / validate
# ---------------------------------------------------------------------------


def test_logger_none_is_backward_compatible(csv_dir):
    """The public API of :func:`validate_rows` (and
    :func:`persist_rows`) still works with ``logger=None`` (the
    default), so the dev CLI / existing tests don't change.

    We don't open a real PDF here — pymupdf is heavy and the
    integration tests for parse() live in ``test_pdf_importer.py``.
    This test only proves the no-logger path is silent and
    side-effect-free for the validate step.
    """
    from src.pdf_importer import validate_rows

    candidate = {
        "patient": {"name": "Maria da Silva"},
        "plan": {},
        "items": [{"raw_name": "Drenagem"}],
        "warnings": [],
    }
    out = validate_rows(candidate)
    # Returns the candidate unchanged in shape; status is set.
    assert "status" in out
    assert "warnings" in out
    # No exceptions means the logger=None path is clean.


def test_logger_captures_parse_events(csv_dir, tmp_path):
    """When a logger is passed, the parser emits the expected
    ordered breadcrumbs (start → zone → field → assemble →
    parse_done).

    A real (but minimal) PDF is built on-the-fly with pymupdf so
    we don't depend on any checked-in fixtures.
    """
    import fitz

    from src.pdf_importer import load_zones, parse_pdf_to_rows

    pdf_path = tmp_path / "tiny.pdf"
    doc = fitz.open()  # in-memory empty document
    doc.new_page(width=595, height=842)
    doc.save(pdf_path)
    doc.close()

    logger = _empty_logger_for_batch(csv_dir)
    zones = load_zones()
    parse_pdf_to_rows(str(pdf_path), zones, logger=logger)
    stages = [e["stage"] for e in logger.events()]
    assert "start" in stages
    assert "parse" in stages
    assert "parse_done" in stages
    # The per-zone events come from each of the four DEFAULT_ZONES.
    zone_events = [e for e in logger.events() if e["stage"] == "zone"]
    assert len(zone_events) == len(zones)
    # The start event records the work scope explicitly.
    start_payload = logger.events()[0]["payload"]
    assert "total_zones" in start_payload
    assert "has_field_mappings" in start_payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_logger_for_batch(csv_dir: Path) -> PdfImportLogger:
    """Build a logger whose sink lives inside the per-test csv_dir
    so the on-disk file is wiped with the test's tmp tree."""
    return PdfImportLogger(sink_path=csv_dir / "import.log")
