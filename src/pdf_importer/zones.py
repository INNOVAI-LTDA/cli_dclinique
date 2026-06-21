"""PDF zone configuration: defaults, JSON loader, and path resolution.

This module is the single source of truth for the list of zones
(bounding boxes in PyMuPDF points) used by the PDF import feature.
The data can come from:

- the in-code ``DEFAULT_ZONES`` (kept as a fallback for tests and ad-hoc
  use);
- a JSON file under ``data/import_zones/<template_id>.json`` (the
  per-template config used by the wizard and the dev CLI).

The module follows the same indirection pattern as
:mod:`src.data_layer.csv_backend`: the directory is resolved by
``_zones_dir_callable`` so tests can monkeypatch the path without
touching the module-level constant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# Default zones extracted from the original lab script
# (``data/pdf_zone_lab.py``, retired when the lab was promoted to
# ``src/pdf_importer/`` + ``scripts/pdf_lab.py``). Coordinates are in
# PyMuPDF points, with the origin at the top-left corner of the page.
DEFAULT_ZONES: list[dict[str, Any]] = [
    {
        "id": "cabecalho",
        "type": "text",
        "bbox": [30, 20, 565, 110],
    },
    {
        "id": "dados_paciente",
        "type": "text",
        "bbox": [30, 115, 565, 230],
    },
    {
        "id": "procedimentos",
        "type": "text",
        "bbox": [30, 240, 565, 640],
    },
    {
        "id": "rodape",
        "type": "text",
        "bbox": [30, 650, 565, 820],
    },
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_zones_dir() -> Path:
    return _project_root() / "data" / "import_zones"


# Module-level callable resolved at import time. Tests override it via
# ``monkeypatch.setattr(zones, "_zones_dir_callable", lambda: test_dir)``.
_zones_dir_callable: Callable[[], Path] = _default_zones_dir


def zones_dir() -> Path:
    """Return the absolute path to the zones config directory used at runtime."""
    return _zones_dir_callable()


def find_pdfs(input_dir: Path, recursive: bool = False) -> list[Path]:
    """List PDF files in ``input_dir`` (non-recursive by default)."""
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(input_dir.glob(pattern))


def load_zones(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load a zone config from a JSON file.

    The file may be either a list of zone dicts
    (``[{"id": ..., "bbox": ...}]``) or a dict with a ``zones`` key
    (``{"zones": [...], "field_mappings": ...}``). If ``path`` is None,
    falls back to ``zones_dir() / "default.json"``; if that file is
    missing, returns :data:`DEFAULT_ZONES`.
    """
    if path is None:
        path = zones_dir() / "default.json"
    path = Path(path)
    if not path.exists():
        return DEFAULT_ZONES
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if "zones" in data:
        return data["zones"]
    raise ValueError(
        f"Invalid zones config at {path}: expected a list or a dict with a 'zones' key."
    )
