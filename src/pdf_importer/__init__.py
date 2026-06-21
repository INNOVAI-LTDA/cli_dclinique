"""PDF import core for the MAP shell.

Public API (re-exported here so callers do ``from src.pdf_importer import ...``):

* :func:`load_zones`         — load a per-template zone config (or fall back to defaults)
* :func:`zones_dir`          — absolute path to ``data/import_zones/``
* :func:`find_pdfs`          — list PDFs in a directory
* :func:`extract_text_from_zone` — read the text inside a bbox (lazy pymupdf)
* :func:`parse_pdf_to_rows`  — turn a PDF into a candidate row dict
* :func:`validate_rows`      — annotate the candidate with status + warnings
* :func:`persist_rows`       — write the candidate to the data layer
* :class:`PdfImportLogger`   — per-batch event log threaded through parse/validate/persist

The :mod:`scripts.pdf_lab` CLI uses the same primitives to visualize
zones and iterate on the regexes in ``data/import_zones/default.json``
without booting the Streamlit app.
"""
from __future__ import annotations

from src.pdf_importer.extract import extract_text_from_zone, render_pdf_page
from src.pdf_importer.log import PdfImportLogger
from src.pdf_importer.parse import parse_pdf_to_rows
from src.pdf_importer.persist import persist_rows
from src.pdf_importer.validate import validate_rows
from src.pdf_importer.zones import (
    DEFAULT_ZONES,
    find_pdfs,
    load_zones,
    zones_dir,
)

__all__ = [
    "DEFAULT_ZONES",
    "PdfImportLogger",
    "extract_text_from_zone",
    "find_pdfs",
    "load_zones",
    "parse_pdf_to_rows",
    "persist_rows",
    "render_pdf_page",
    "validate_rows",
    "zones_dir",
]
