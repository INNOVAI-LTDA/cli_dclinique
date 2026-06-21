"""Event log for the PDF import pipeline.

The MAP PDF import wizard goes through three stages — ``parse``,
``validate``, ``persist`` — and a wrong field at any step can leave
the user staring at a ``None`` in the preview with no idea why
(e.g. "the CPF is missing, is the regex wrong? is the zone too
small? did the text extractor skip the right bbox?"). This module
provides a single :class:`PdfImportLogger` that the wizard threads
through all three stages so each decision is recorded with a
timestamp, a level (``INFO``/``WARN``/``ERROR``) and a structured
payload (zone id, field name, value, etc.).

Design choices:

* **Pure (no Streamlit dep)** — the logger is a plain class so it
  can be unit-tested with pytest without a runtime, and the wizard
  is the only thing that knows about ``st.session_state``.
* **Structured events** — each entry is a dict
  ``{"ts", "ts_hms", "level", "stage", "msg", "payload"}`` so the
  wizard can pick what to render (text view, table view, JSON
  download) without re-parsing strings.
* **Optional disk sink** — :meth:`flush_to_disk` writes a plain-text
  rendering to ``data/test_logs/pdf_import_<session>_<ts>.log``
  (same naming convention as the existing
  ``neon_validate_*.log`` / ``scrum_*.log`` files). Used by the
  wizard at the end of a batch; tests use it to assert the format.
* **Verbose mode off by default** — the env var
  ``PDF_IMPORT_DEBUG=1`` enables DEBUG-level events (raw extracted
  text, regex match groups) that would otherwise drown the
  INFO-level trace.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> float:
    """Wall-clock seconds since the epoch (monotonic-ish, not used for ordering)."""
    return time.time()


def _hms(ts: float) -> str:
    """Format ``ts`` as local ``HH:MM:SS.mmm`` for human-readable log lines.

    Uses :func:`time.localtime` to pick the wall-clock hours (modulo
    24). The naive ``ts / 3600`` approach gives the absolute hours
    since the epoch (~47M for a 2026 timestamp) which is useless in
    a log line.
    """
    lt = time.localtime(ts)
    millis = int((ts - int(ts)) * 1000)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}:{lt.tm_sec:02d}.{millis:03d}"


def _is_debug() -> bool:
    """Return True when DEBUG-level events should be recorded.

    Read once at logger construction so the caller cannot flip the
    bit mid-batch and confuse the timestamps.
    """
    return os.environ.get("PDF_IMPORT_DEBUG", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


@dataclass
class PdfImportEvent:
    """One entry in the import log.

    ``ts`` is the wall-clock seconds since the epoch (recorded at
    event creation, not lazily on dump). ``ts_hms`` is the
    pre-formatted ``HH:MM:SS.mmm`` string for direct use in the
    plain-text renderer — kept on the dataclass so tests don't have
    to mock ``time.time`` to assert the format.
    """

    ts: float
    ts_hms: str
    level: str  # "DEBUG" | "INFO" | "WARN" | "ERROR"
    stage: str  # free-form: "parse" | "zone" | "field" | "validate" | "persist" | ...
    msg: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        """Return the event as a plain dict (JSON-friendly)."""
        return {
            "ts": self.ts,
            "ts_hms": self.ts_hms,
            "level": self.level,
            "stage": self.stage,
            "msg": self.msg,
            "payload": self.payload,
        }


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------


class PdfImportLogger:
    """In-memory event log for one PDF import batch.

    Constructed once per ``_handle_read_click`` invocation in the
    wizard. The wizard passes the same instance through
    :func:`parse_pdf_to_rows`, :func:`validate_rows` and
    :func:`persist_rows` so all three stages land in one ordered
    list. The wizard reads :meth:`events` to render the trace in an
    ``st.expander`` and calls :meth:`flush_to_disk` at the end of
    the batch.

    Parameters
    ----------
    sink_path
        Optional path where :meth:`flush_to_disk` will write the
        plain-text rendering. The wizard passes
        ``data/test_logs/pdf_import_<session>_<ts>.log`` so the
        log joins the existing ``neon_validate_*.log`` /
        ``scrum_*.log`` family there.
    debug
        When True (or when ``PDF_IMPORT_DEBUG=1`` is set in the
        environment), record DEBUG events too. Default follows the
        env var so the wizard doesn't have to know about it.
    """

    def __init__(
        self,
        sink_path: Path | None = None,
        debug: bool | None = None,
    ) -> None:
        self._events: list[PdfImportEvent] = []
        self._sink_path = Path(sink_path) if sink_path is not None else None
        self._debug = bool(debug) if debug is not None else _is_debug()
        self._start_ts: float | None = None
        self._finished = False

    # --- public API ---

    def start(self, filename: str, *, total_zones: int, **payload: Any) -> None:
        """Emit the first event of a batch.

        ``filename`` is shown in the log header so multiple PDFs
        imported in the same batch are easy to tell apart; the
        wizard passes the uploaded file's ``.name``. ``total_zones``
        is the count from ``zones_config`` so the trace makes the
        work scope explicit (and the absence of ``field_mappings``
        on those zones — the most common cause of empty candidates
        — is visible in the very first line).
        """
        self._start_ts = _now()
        self._record(
            level="INFO",
            stage="start",
            msg=f"import started: {filename}",
            payload={"filename": filename, "total_zones": total_zones, **payload},
        )

    def stage(self, name: str, **payload: Any) -> None:
        """Emit a structural marker (e.g. ``"parse"``, ``"validate"``, ``"commit"``).

        Stages are coarse breadcrumbs the user follows when
        scrolling the log: ``start → parse → validate → persist →
        finish``. Within ``parse``, :meth:`field` provides the
        fine-grained per-field trace.
        """
        self._record(level="INFO", stage=name, msg=name, payload=payload)

    def field(
        self,
        zone: str,
        field_name: str,
        status: str,
        *,
        value: Any = None,
        pattern: str | None = None,
    ) -> None:
        """Emit one per-field event.

        ``status`` is one of:

        * ``MATCHED`` — regex matched and normalizer returned a value
        * ``MISSING_REQUIRED`` — no regex match for a required field
        * ``MISSING_OPTIONAL`` — no regex match for an optional field
        * ``NORMALIZER_FAILED`` — regex matched but the normalizer raised

        Only ``MATCHED`` carries a ``value``; the others emit
        ``value=None`` so the log line is still self-contained.
        """
        payload: dict[str, Any] = {"zone": zone, "field": field_name, "status": status}
        if value is not None:
            payload["value"] = value
        if pattern is not None and self._debug:
            payload["pattern"] = pattern
        # Missing-required fields bump the level to WARN so they
        # stand out in a glance over the log even when the user
        # doesn't filter.
        level = "WARN" if status in {"MISSING_REQUIRED", "NORMALIZER_FAILED"} else "INFO"
        # Truncate the message so a long extracted field doesn't
        # blow up the line width in the plain-text view.
        msg_value = "" if value is None else f" value={value!r:.80}"
        self._record(
            level=level,
            stage="field",
            msg=f"{zone}.{field_name}={status}{msg_value}",
            payload=payload,
        )

    def warn(self, msg: str, **payload: Any) -> None:
        """Emit a warning (e.g. validator rule violation)."""
        self._record(level="WARN", stage="warn", msg=msg, payload=payload)

    def error(self, msg: str, **payload: Any) -> None:
        """Emit an error (e.g. parser exception caught at wizard level)."""
        self._record(level="ERROR", stage="error", msg=msg, payload=payload)

    def debug(self, msg: str, **payload: Any) -> None:
        """Emit a debug event. Silently dropped unless debug mode is on."""
        if not self._debug:
            return
        self._record(level="DEBUG", stage="debug", msg=msg, payload=payload)

    def finish(self, success: bool, **summary: Any) -> None:
        """Emit the last event and flush to disk if a sink was set.

        ``summary`` is a free-form kwargs dict that lands in the
        final event's payload — the wizard passes
        ``imported_pids=[...]`` so the user can match log lines to
        the resulting patient ids without cross-referencing the
        data layer. Idempotent: a second call is a no-op so the
        wizard can call ``finish`` in both the success and error
        branches without worrying about double-flushing.
        """
        if self._finished:
            return
        self._finished = True
        duration_ms = None
        if self._start_ts is not None:
            duration_ms = int((_now() - self._start_ts) * 1000)
        payload = {"success": success, "duration_ms": duration_ms, **summary}
        self._record(
            level="INFO" if success else "ERROR",
            stage="finish",
            msg=f"import {'succeeded' if success else 'failed'}",
            payload=payload,
        )
        if self._sink_path is not None:
            try:
                self.flush_to_disk(self._sink_path)
            except OSError:
                # Disk failure must not break the import flow —
                # the in-memory log is still available to the
                # wizard, and the failure is itself recorded so
                # the user sees something went wrong on persist.
                self._record(
                    level="ERROR",
                    stage="finish",
                    msg=f"failed to flush log to {self._sink_path}",
                    payload={"sink_path": str(self._sink_path)},
                )

    def events(self) -> list[dict[str, Any]]:
        """Return all events as plain dicts (for the wizard's renderer)."""
        return [e.to_row() for e in self._events]

    def to_text(self) -> str:
        """Render the log as plain text (for ``st.code`` and the disk sink).

        Each line is::

            [HH:MM:SS.mmm] [LEVEL] stage: msg | key=value, key=value, ...

        Empty payloads omit the trailing ``| ...``. DEBUG events
        are only included when debug mode is on (same gating as
        :meth:`debug`).
        """
        lines: list[str] = []
        for e in self._events:
            if e.level == "DEBUG" and not self._debug:
                continue
            payload_str = ""
            if e.payload:
                # Use a stable ordering so the same log produces the
                # same text across runs (helps test_pdf_import_log.py).
                items = ", ".join(
                    f"{k}={_short_repr(v)}"
                    for k, v in sorted(e.payload.items())
                )
                payload_str = f" | {items}"
            lines.append(
                f"[{e.ts_hms}] [{e.level:<5s}] {e.stage}: {e.msg}{payload_str}"
            )
        return "\n".join(lines)

    def flush_to_disk(self, path: Path | None = None) -> Path:
        """Write :meth:`to_text` to ``path``. Returns the actual path used.

        Creates parent directories as needed. If ``path`` is None,
        falls back to the logger's ``sink_path``. The file is
        written atomically (``tmp`` + rename) so a partial write
        never replaces a previous good log — useful when the user
        inspects ``data/test_logs/`` between batches.
        """
        target = Path(path) if path is not None else self._sink_path
        if target is None:
            raise ValueError(
                "flush_to_disk called with no path and no sink_path set"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(self.to_text() + "\n", encoding="utf-8")
        tmp.replace(target)
        return target

    # --- introspection ---

    @property
    def sink_path(self) -> Path | None:
        """Path where :meth:`flush_to_disk` will write (or has written)."""
        return self._sink_path

    @property
    def finished(self) -> bool:
        """True once :meth:`finish` has been called (idempotent guard)."""
        return self._finished

    def __len__(self) -> int:
        """Number of events recorded so far (debug-gated events excluded)."""
        if self._debug:
            return len(self._events)
        return sum(1 for e in self._events if e.level != "DEBUG")

    # --- internals ---

    def _record(
        self,
        *,
        level: str,
        stage: str,
        msg: str,
        payload: dict[str, Any],
    ) -> None:
        ts = _now()
        self._events.append(
            PdfImportEvent(
                ts=ts,
                ts_hms=_hms(ts),
                level=level,
                stage=stage,
                msg=msg,
                payload=payload,
            )
        )


def _short_repr(value: Any) -> str:
    """Render a payload value for ``to_text`` with a hard length cap.

    Long strings (e.g. a 300-char extracted address) would
    dominate the line; truncate with an ellipsis marker. Numbers,
    bools, and short strings pass through unchanged.
    """
    if isinstance(value, str):
        if len(value) > 80:
            return f"{value[:77]!r}..."
        return repr(value)
    if isinstance(value, (list, tuple)):
        if len(value) > 6:
            head = ", ".join(_short_repr(v) for v in value[:6])
            return f"[{head}, ... ({len(value)} items)]"
        return "[" + ", ".join(_short_repr(v) for v in value) + "]"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return repr(value)
