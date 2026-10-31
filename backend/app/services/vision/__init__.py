"""Document vision: OCR + layout for scanned PDFs, photos and receipts.

One interface, three providers (docs/spec/plan.md M13):
- ``macos``  — Apple Vision on this machine via a small Swift helper. Documents never leave the device.
- ``gemini`` — Gemini multimodal transcription. Only when OCR_PROVIDER=gemini is set explicitly,
                because the document is then sent to Google.
- ``none``   — no OCR; callers get a clear OCR_NOT_CONFIGURED error.

Callers only see :func:`read_document`, which returns page texts with page numbers preserved.
Raw document text is never logged.
"""

from __future__ import annotations

from app.services.vision.base import OcrLine, OcrPage, OcrResult, VisionError
from app.services.vision.images import IMAGE_MIMES, prepare_image, sniff_image
from app.services.vision.layout import page_text
from app.services.vision.providers import active_provider, provider_status, read_document

__all__ = [
    "IMAGE_MIMES", "OcrLine", "OcrPage", "OcrResult", "VisionError", "active_provider", "page_text",
    "prepare_image", "provider_status", "read_document", "sniff_image",
]
