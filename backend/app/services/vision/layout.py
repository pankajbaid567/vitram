"""Layout reconstruction: turn OCR word/line boxes into reading-order text.

OCR engines return text regions, not lines: on a receipt, "Subtotal" and "1118.00" come back as two
boxes. We group boxes whose vertical centres are close into one row (sorted left to right) and keep
wide horizontal gaps as runs of spaces, so the existing text extractors (which look for label … value
on one line, and for table columns) work on scans the same way they do on digital PDFs.
"""

from __future__ import annotations

from statistics import median

from app.services.vision.base import OcrLine

# characters per unit of normalised width, used to turn gaps into spaces (rough monospace estimate)
_CHARS_PER_WIDTH = 90


def rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    boxed = [ln for ln in lines if ln.box and ln.text.strip()]
    if not boxed:
        return [[ln] for ln in lines if ln.text.strip()]
    heights = [ln.box[3] for ln in boxed if ln.box[3] > 0] or [0.02]
    tol = 0.6 * median(heights)
    out: list[list[OcrLine]] = []
    for ln in sorted(boxed, key=lambda b: b.box[1] + b.box[3] / 2):
        cy = ln.box[1] + ln.box[3] / 2
        if out:
            row = out[-1]
            rcy = sum(r.box[1] + r.box[3] / 2 for r in row) / len(row)
            if abs(cy - rcy) <= tol:
                row.append(ln)
                continue
        out.append([ln])
    return [sorted(r, key=lambda b: b.box[0]) for r in out]


def row_text(row: list[OcrLine]) -> str:
    parts: list[str] = []
    prev_end: float | None = None
    for ln in row:
        if prev_end is not None and ln.box:
            gap = ln.box[0] - prev_end
            n = int(gap * _CHARS_PER_WIDTH)
            parts.append("   " if n >= 3 else " ")
        parts.append(ln.text.strip())
        prev_end = (ln.box[0] + ln.box[2]) if ln.box else prev_end
    return "".join(parts)


def page_text(lines: list[OcrLine]) -> str:
    return "\n".join(row_text(r) for r in rows(lines))
