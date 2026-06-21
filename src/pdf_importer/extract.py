"""PDF text extraction by zone.

Wraps PyMuPDF's ``page.get_text("text", clip=Rect(...))`` to extract the
text inside a bounding box. The ``fitz`` import is deferred inside the
functions so ``import src.pdf_importer`` is cheap — pymupdf is heavy and
would dominate the cold start if paid on every page visit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

# A "source" is either a file path (str | Path) or raw PDF bytes
# (e.g. coming from ``st.file_uploader``). Both are accepted so the
# wizard can stream uploads without writing to a temporary file.
PdfSource = Union[str, Path, bytes]


def _open_doc(source: PdfSource):
    """Open a PyMuPDF Document from a path or raw bytes."""
    import fitz  # PyMuPDF (deferred to keep cold start flat)

    if isinstance(source, (str, Path)):
        return fitz.open(source)
    return fitz.open(stream=source, filetype="pdf")


def extract_text_from_zone(
    source: PdfSource,
    page_number: int,
    bbox: list[float],
) -> str:
    """Return the text inside ``bbox`` (PDF points) on ``page_number`` (1-based).

    ``fitz`` is imported here (not at module top) so the Streamlit cold
    start stays flat — pymupdf is only paid when an actual PDF is read.
    """
    import fitz  # local: keep cold start flat (paid only when reading a PDF)

    doc = _open_doc(source)
    try:
        page = doc[page_number - 1]
        rect = fitz.Rect(*bbox)
        return page.get_text("text", clip=rect).strip()
    finally:
        doc.close()


def render_pdf_page(
    source: PdfSource,
    page_number: int = 1,
    dpi: int = 150,
):
    """Return the rendered PIL Image of ``page_number`` for dev/visualization.

    Used by ``scripts/pdf_lab.py`` (matplotlib overlay) and by the smoke
    test fixture. Not used in the production import flow — the wizard
    never renders the PDF, it just reads text by zone.
    """
    from PIL import Image

    doc = _open_doc(source)
    try:
        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes(
            "RGB",
            [pix.width, pix.height],
            pix.samples,
        )
    finally:
        doc.close()
