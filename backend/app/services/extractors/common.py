"""Shared helpers for heuristic, provenance-preserving document extraction (RD §10).

Uploaded text is *data*. Nothing in a document is ever executed or treated as
an instruction (RD §23.3); extractors only pattern-match values.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.services.statements.parser import parse_date


@dataclass
class Fact:
    fact_type: str
    key: str
    label: str
    value: object
    page: int | None
    section: str | None
    snippet: str | None
    confidence: float
    unit: str | None = None


@dataclass
class Section:
    heading: str
    page: int
    lines: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    facts: list[Fact]
    chunks: list[dict]
    warnings: list[str] = field(default_factory=list)

    def get(self, key: str) -> Fact | None:
        return next((f for f in self.facts if f.key == key), None)

    def value(self, key: str, default=None):
        f = self.get(key)
        return f.value if f else default


AMOUNT = r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d{1,2})?)\s*(lakh|lac|crore|cr)?"
_BULLET = re.compile(r"^\s*(?:[-•*▪●◦]|\d{1,2}[.)]|\(?[a-z]\))\s+")


def to_amount(num: str, unit: str | None = None) -> float | None:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit in {"lakh", "lac"}:
        v *= 100_000
    elif unit in {"crore", "cr"}:
        v *= 10_000_000
    return v


def clean(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def snippet(line: str, limit: int = 220) -> str:
    s = clean(line)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def is_heading(line: str) -> bool:
    s = clean(line)
    if not s or len(s) > 60 or _BULLET.match(line):
        return False
    if s.endswith(":") and len(s.split()) <= 7:
        return True
    letters = [c for c in s if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(s.split()) <= 7 and not re.search(r"\d{3,}", s):
        return True
    return bool(re.match(r"^(section\s+)?\d{1,2}(\.\d)?\s+[A-Z][A-Za-z ,&/-]{3,50}$", s))


_INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|(?:note|message) to (?:ai|llm|chatbot|assistant)s?|"
    r"system prompt|you are (?:now )?(?:an? )?(?:ai|assistant)|disregard (?:your|the) (?:rules|instructions)",
    re.I,
)


def looks_like_injection(text: str) -> bool:
    """Text addressed to AI systems inside a document is data, never an instruction (RD §23.3)."""
    return bool(_INJECTION.search(text or ""))


def strip_running_lines(pages: list[str]) -> list[str]:
    """Remove running headers/footers: identical lines that appear on most pages of a multi-page document."""
    if len(pages) < 2:
        return pages
    counts: dict[str, int] = {}
    for text in pages:
        for line in {clean(l) for l in text.splitlines() if clean(l)}:
            counts[line] = counts.get(line, 0) + 1
    threshold = max(2, int(len(pages) * 0.6 + 0.5))
    running = {l for l, n in counts.items() if n >= threshold and len(l) > 3}
    return ["\n".join(l for l in text.splitlines() if clean(l) not in running) for text in pages]


def sections(pages: list[str]) -> list[Section]:
    out: list[Section] = [Section("Document", 1)]
    for pno, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = clean(raw)
            if not line:
                continue
            if is_heading(line):
                out.append(Section(line.rstrip(":").strip(), pno))
            else:
                out[-1].lines.append(raw)
    return [s for s in out if s.lines or s.heading != "Document"]


def bullets(sec: Section) -> list[str]:
    items: list[str] = []
    for raw in sec.lines:
        line = clean(raw)
        if _BULLET.match(raw):
            items.append(_BULLET.sub("", raw).strip())
        elif items and raw.startswith(("  ", "\t")):
            items[-1] += " " + line
        elif line:
            items.append(line)
    return [clean(i) for i in items if len(clean(i)) > 2]


def find_line(pages: list[str], pattern: re.Pattern) -> tuple[re.Match, int, str] | None:
    for pno, text in enumerate(pages, start=1):
        for line in text.splitlines():
            m = pattern.search(line)
            if m:
                return m, pno, line
    return None


def find_section(secs: list[Section], *keywords: str) -> Section | None:
    for s in secs:
        h = s.heading.lower()
        if any(k in h for k in keywords):
            return s
    return None


def section_for_page_line(secs: list[Section], page: int, line: str) -> str | None:
    for s in secs:
        if s.page <= page and line in s.lines:
            return s.heading
    return None


def parse_any_date(raw: str) -> date | None:
    return parse_date(raw.strip().rstrip(".,"))


def chunk_pages(pages: list[str], max_chars: int = 700) -> list[dict]:
    """Paragraph-ish chunks with page + nearest heading, for scoped retrieval."""
    chunks: list[dict] = []
    heading = None
    for pno, text in enumerate(pages, start=1):
        buf: list[str] = []
        for raw in text.splitlines():
            line = clean(raw)
            if not line:
                continue
            if is_heading(line):
                if buf:
                    chunks.append({"page": pno, "section": heading, "text": " ".join(buf)})
                    buf = []
                heading = line.rstrip(":")
                continue
            buf.append(line)
            if sum(len(b) for b in buf) > max_chars:
                chunks.append({"page": pno, "section": heading, "text": " ".join(buf)})
                buf = []
        if buf:
            chunks.append({"page": pno, "section": heading, "text": " ".join(buf)})
    return chunks


def mask_ref(ref: str) -> str:
    ref = ref.strip()
    return "••••" + ref[-4:] if len(ref) > 4 else ref
