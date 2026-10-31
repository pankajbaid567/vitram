from __future__ import annotations

from dataclasses import dataclass, field


class VisionError(Exception):
    """A user-facing failure with a stable code (shown on the document, never includes document content)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class OcrLine:
    text: str
    confidence: float
    # normalised [x, y, w, h], origin top-left; None when the provider gives no geometry
    box: tuple[float, float, float, float] | None = None


@dataclass
class OcrPage:
    page: int
    lines: list[OcrLine] = field(default_factory=list)
    text: str = ""  # rebuilt reading-order text (see layout.page_text)

    @property
    def mean_confidence(self) -> float | None:
        if not self.lines:
            return None
        return sum(ln.confidence for ln in self.lines) / len(self.lines)


@dataclass
class OcrResult:
    provider: str  # macos | gemini
    pages: list[OcrPage]

    @property
    def texts(self) -> list[str]:
        return [p.text for p in self.pages]

    @property
    def mean_confidence(self) -> float:
        vals = [p.mean_confidence for p in self.pages if p.mean_confidence is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0
