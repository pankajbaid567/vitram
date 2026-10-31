"""Bank statement parsing: CSV exports and text-layer PDFs (RD §9.1).

The output is a flat list of rows with a `source_ref` (CSV row or PDF page)
so every transaction can be traced back to the statement.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.services.pdf_text import PdfError, extract_pages


class StatementParseError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ParsedRow:
    txn_date: date
    description: str
    amount: float
    direction: str  # credit | debit
    balance: float | None
    source_ref: str
    confidence: float = 0.95


@dataclass
class ParsedStatement:
    rows: list[ParsedRow]
    method: str
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def period(self) -> tuple[date | None, date | None]:
        if not self.rows:
            return None, None
        dates = [r.txn_date for r in self.rows]
        return min(dates), max(dates)


_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %b %y", "%d/%b/%Y", "%b %d, %Y", "%d %B %Y",
]


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


_AMOUNT_RE = re.compile(r"^-?[\d,]+(?:\.\d{1,2})?$")


def parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip().replace("₹", "").replace("INR", "").replace("Rs.", "").replace("Rs", "").strip()
    s = s.replace(" ", "")
    if s in {"", "-", "--"}:
        return None
    suffix = None
    m = re.match(r"^(.*?)(cr|dr)\.?$", s, re.I)
    if m:
        s, suffix = m.group(1), m.group(2).lower()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if not _AMOUNT_RE.match(s):
        return None
    value = float(s.replace(",", ""))
    if suffix == "dr":
        value = -abs(value)
    return value


# --- CSV ------------------------------------------------------------------

_HEADER_ALIASES = {
    "date": ["txn date", "transaction date", "date", "value date", "tran date", "posting date"],
    "description": ["narration", "description", "particulars", "remarks", "transaction details", "details"],
    "debit": ["debit", "withdrawal amt", "withdrawal amount", "withdrawal", "withdrawals", "debit amount", "dr"],
    "credit": ["credit", "deposit amt", "deposit amount", "deposit", "deposits", "credit amount", "cr"],
    "amount": ["amount", "transaction amount", "amount (inr)"],
    "type": ["type", "dr/cr", "cr/dr", "debit/credit", "transaction type"],
    "balance": ["balance", "closing balance", "available balance", "balance (inr)", "running balance"],
}


def _map_header(cells: list[str]) -> dict[str, int] | None:
    norm = [re.sub(r"[^a-z/() ]", "", c.strip().lower()).strip() for c in cells]
    mapping: dict[str, int] = {}
    for field_name, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in norm:
                idx = norm.index(alias)
                if idx not in mapping.values():
                    mapping[field_name] = idx
                    break
    if "date" in mapping and "description" in mapping and (
        ("debit" in mapping and "credit" in mapping) or "amount" in mapping
    ):
        return mapping
    return None


def parse_csv(data: bytes) -> ParsedStatement:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    lines = list(csv.reader(io.StringIO(text)))
    if len(lines) > 20_000:
        raise StatementParseError("TOO_LARGE", "This CSV has more than 20,000 rows. Split it into smaller periods.")
    header_idx, mapping = None, None
    for i, cells in enumerate(lines[:40]):
        mapping = _map_header(cells)
        if mapping:
            header_idx = i
            break
    if mapping is None:
        raise StatementParseError(
            "UNRECOGNISED_COLUMNS",
            "VITRAM couldn't find date, description and amount columns in this CSV. "
            "Export the statement with Date, Narration, Withdrawal, Deposit and Balance columns.",
        )
    rows: list[ParsedRow] = []
    warnings: list[str] = []
    skipped = 0
    for i, cells in enumerate(lines[header_idx + 1:], start=header_idx + 2):
        if not any(c.strip() for c in cells):
            continue
        get = lambda k: cells[mapping[k]] if k in mapping and mapping[k] < len(cells) else None  # noqa: E731
        d = parse_date(get("date") or "")
        desc = (get("description") or "").strip()
        if d is None or not desc:
            skipped += 1
            continue
        direction, amount = None, None
        if "debit" in mapping and "credit" in mapping:
            dr, cr = parse_amount(get("debit")), parse_amount(get("credit"))
            if dr:
                direction, amount = "debit", abs(dr)
            elif cr:
                direction, amount = "credit", abs(cr)
        if amount is None and "amount" in mapping:
            a = parse_amount(get("amount"))
            if a is not None and a != 0:
                t = (get("type") or "").strip().lower()
                if t.startswith("cr") or t == "c":
                    direction = "credit"
                elif t.startswith("dr") or t == "d":
                    direction = "debit"
                else:
                    direction = "credit" if a > 0 else "debit"
                amount = abs(a)
        if amount is None or direction is None:
            skipped += 1
            continue
        rows.append(ParsedRow(d, desc, round(amount, 2), direction, parse_amount(get("balance")), f"row {i}"))
    if skipped:
        warnings.append(f"{skipped} rows without a readable date or amount were skipped.")
    if not rows:
        raise StatementParseError("NO_TRANSACTIONS", "No transactions were found in this file.")
    return ParsedStatement(rows=rows, method="csv", warnings=warnings)


# --- PDF ------------------------------------------------------------------

_LINE_DATE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[ -][A-Za-z]{3}[ -]\d{2,4}|\d{4}-\d{2}-\d{2})\s+(.*)$"
)
_OPENING = re.compile(r"(?:opening|brought forward|b/f)\s*balance\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*(-?[\d,]+\.\d{2}(?:\s?(?:cr|dr))?)", re.I)
_TRAILING_AMOUNTS = re.compile(r"((?:\s+-?[\d,]+\.\d{2}(?:\s?(?:Cr|Dr|CR|DR))?){1,3})\s*$")


def parse_pdf(data: bytes) -> ParsedStatement:
    try:
        pages = extract_pages(data)
    except PdfError as exc:
        raise StatementParseError(exc.code, exc.message) from exc
    return parse_text_pages(pages, method="pdf_text")


def parse_text_pages(pages: list[str], method: str = "pdf_text", base_confidence: float = 0.85) -> ParsedStatement:
    """Parse statement lines from page texts — digital PDFs, or OCR output from scans and photos."""
    rows: list[ParsedRow] = []
    warnings: list[str] = []
    prev_balance: float | None = None
    uncertain = 0
    for page_no, text in enumerate(pages, start=1):
        for line in text.splitlines():
            line = line.strip()
            ob = _OPENING.search(line)
            if ob and prev_balance is None and not rows:
                prev_balance = parse_amount(ob.group(1))
                continue
            m = _LINE_DATE.match(line)
            if not m:
                continue
            d = parse_date(m.group(1))
            if d is None:
                continue
            rest = m.group(2)
            # optional second (value) date
            m2 = _LINE_DATE.match(rest)
            if m2 and parse_date(m2.group(1)):
                rest = m2.group(2)
            am = _TRAILING_AMOUNTS.search(rest)
            if not am:
                continue
            amounts_raw = am.group(1).split()
            # rejoin "123.00 Cr" pairs
            tokens: list[str] = []
            for tok in amounts_raw:
                if tok.lower() in {"cr", "dr"} and tokens:
                    tokens[-1] += tok
                else:
                    tokens.append(tok)
            values = [parse_amount(t) for t in tokens]
            desc = rest[: am.start()].strip()
            if not desc or any(v is None for v in values):
                continue
            balance = values[-1] if len(values) >= 2 else None
            direction, amount, confidence = None, None, base_confidence
            if len(values) == 3:  # withdrawal, deposit, balance with one zero
                wd, dp = values[0], values[1]
                if wd and not dp:
                    direction, amount = "debit", abs(wd)
                elif dp and not wd:
                    direction, amount = "credit", abs(dp)
            if amount is None:
                amt = values[0]
                if tokens[0].lower().endswith("cr"):
                    direction = "credit"
                elif tokens[0].lower().endswith("dr"):
                    direction = "debit"
                elif balance is not None and prev_balance is not None:
                    delta = round(balance - prev_balance, 2)
                    if abs(abs(delta) - abs(amt)) < 0.01:
                        direction = "credit" if delta > 0 else "debit"
                if direction is None:
                    direction = "debit"
                    confidence = 0.5
                    uncertain += 1
                amount = abs(amt)
            if balance is not None:
                prev_balance = abs(balance) if not tokens[-1].lower().endswith("dr") else -abs(balance)
            rows.append(ParsedRow(d, desc, round(amount, 2), direction, balance, f"page {page_no}", confidence))
    if not rows:
        raise StatementParseError(
            "NO_TRANSACTIONS",
            "VITRAM couldn't find transaction lines in this PDF. Try the CSV export from your bank.",
        )
    if uncertain:
        warnings.append(f"{uncertain} transactions have an uncertain debit/credit direction and need review.")
    return ParsedStatement(rows=rows, method=method, page_count=len(pages), warnings=warnings)


def parse_statement(data: bytes, mime: str) -> ParsedStatement:
    if data.startswith(b"%PDF") or mime == "application/pdf":
        return parse_pdf(data)
    return parse_csv(data)
