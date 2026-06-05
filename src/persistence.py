"""File-based persistence for session-added extras.

The MAP shell keeps fictional data in memory; the extras added via the
add-patient and cadastro-ficha forms (``extra_patients``,
``extra_treatment_plans``, ``extra_treatment_plan_items``,
``extra_patient_goals``, ``extra_weight_entries``) are persisted to a
single JSON file on disk so they survive browser refreshes, tab
close/reopen, and Streamlit server restarts.

The file is read at most once per page render (when the session-state
key is missing, e.g. right after a hard refresh) and written once per
mutation. A read-modify-write cycle keeps the file atomic even if the
process is killed mid-write.

A path-returning helper (``_get_extras_file``) is used instead of a
module-level constant so the test suite can monkeypatch it to redirect
to a per-test temporary file.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


# All extra session-state keys that the app persists. Centralised here so
# load/save/reset can normalise the on-disk payload.
ALL_KEYS: tuple[str, ...] = (
    "extra_patients",
    "extra_treatment_plans",
    "extra_treatment_plan_items",
    "extra_patient_goals",
    "extra_weight_entries",
)


def _get_extras_file() -> Path:
    """Resolve the extras JSON file path. Default is ``data/extra_data.json``
    next to the project root (one level above ``src/``). Tests override
    this via ``monkeypatch.setattr`` to point at a tmp file."""
    return Path(__file__).resolve().parents[1] / "data" / "extra_data.json"


def _empty_extras() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in ALL_KEYS}


def load_extras() -> dict[str, list[dict[str, Any]]]:
    """Read the extras file and return a normalised structure.

    Returns an empty structure when the file is missing, empty, or
    corrupt (any ``json``/``OSError``). Unknown keys are dropped; known
    keys with a non-list value are coerced to an empty list.
    """
    path = _get_extras_file()
    if not path.exists():
        return _empty_extras()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return _empty_extras()
    if not isinstance(data, dict):
        return _empty_extras()

    result = _empty_extras()
    for key in ALL_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            result[key] = value
    return result


def save_extras(extras: dict[str, list[dict[str, Any]]]) -> None:
    """Atomically write the extras to the JSON file.

    Writes to a temp file in the same directory and renames it over the
    target, so a crash mid-write cannot leave a half-written file. The
    temp file is best-effort cleaned up on failure.
    """
    path = _get_extras_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise payload so the on-disk file only contains known keys.
    payload = {key: extras.get(key, []) for key in ALL_KEYS}

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".extra_data_",
        suffix=".json.tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def reset_extras() -> None:
    """Delete the extras file. Useful for tests / debug only."""
    path = _get_extras_file()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def save_key(key: str, value: list[dict[str, Any]]) -> None:
    """Write a single key to the extras file (read-modify-write).

    Used by the components to persist a single session-state list without
    clobbering other keys that might have been updated by another tab
    or another page render.
    """
    if key not in ALL_KEYS:
        raise ValueError(f"Unknown extras key: {key!r}")
    extras = load_extras()
    extras[key] = value
    save_extras(extras)
