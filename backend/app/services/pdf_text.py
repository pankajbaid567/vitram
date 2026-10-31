"""PDF text extraction with explicit failure codes (RD §26)."""

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

log = logging.getLogger("vitram.pdf")


class PdfError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def extract_pages(data: bytes) -> list[str]:
    """Returns text per page (1-indexed page i is list[i-1])."""
    if not data.startswith(b"%PDF"):
        raise PdfError("UNSUPPORTED_FORMAT", "This file isn't a PDF. Upload a PDF or CSV export.")
    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise PdfError("UNREADABLE_PDF", "The PDF looks damaged and couldn't be opened. Download it again and retry.") from exc
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:  # noqa: BLE001
            ok = 0
        if not ok:
            raise PdfError(
                "PASSWORD_PROTECTED",
                "This PDF is password-protected. Download an unlocked copy from your bank or insurer "
                "(or remove the password), then upload it again.",
            )
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001  — keep going, mark page empty
            log.warning("page text extraction failed")
            pages.append("")
    if not any(p.strip() for p in pages):
        raise PdfError(
            "NO_TEXT_LAYER",
            "This PDF appears to be a scanned image. Allow AI processing to try OCR, "
            "or upload a digital PDF or CSV export instead.",
        )
    return pages
