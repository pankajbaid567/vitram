"""Receipt / invoice extraction (M13) — deterministic pattern matching over page text (digital or OCR).

Every value keeps the line it came from. Nothing is confirmed automatically, and a receipt is never
treated as proof that a payment went through: it only helps the user match a bank transaction.
Full card numbers are never kept — long digit runs are masked in values, snippets and search chunks.
"""

from __future__ import annotations

import re

from app.services.extractors.common import Extraction, Fact, chunk_pages, clean, looks_like_injection, parse_any_date, snippet

_NUM = r"(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})|\d+(?:\.\d{1,2})?)"
_LAST_AMOUNT = re.compile(rf"(?:₹|rs\.?|inr)?\s*{_NUM}\s*(?:/-)?\s*$", re.I)
_GSTIN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
_DATE = re.compile(
    r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}[\s\-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s\-,]*\d{2,4}|\d{4}-\d{2}-\d{2})\b",
    re.I,
)
_INVOICE = re.compile(r"\b(?:invoice|inv|bill|receipt|order)\s*(?:no|number|#|num)\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,24})", re.I)
_TOTAL_STRONG = re.compile(r"\b(grand\s*total|net\s*(?:amount|payable|total)|amount\s*(?:payable|paid|due)|total\s*(?:amount|payable|due)|bill\s*amount)\b", re.I)
_TOTAL_WEAK = re.compile(r"^\s*total\b", re.I)
_NOT_TOTAL = re.compile(r"\b(sub\s*-?\s*total|total\s*(?:qty|quantity|items?|savings?|discount|tax(?:es)?|gst)|you\s*saved)\b", re.I)
_SUBTOTAL = re.compile(r"\bsub\s*-?\s*total\b", re.I)
_TAX = re.compile(r"\b(cgst|sgst|utgst|igst|cess|gst|vat)\b\s*(?:@\s*)?(\d{1,2}(?:\.\d{1,2})?\s*%)?", re.I)
_SKIP_ITEM = re.compile(r"\b(total|subtotal|sub total|gst|cgst|sgst|igst|cess|tax|round\s*off|discount|change|tendered|balance|paid|upi|card|cash|invoice|bill no|gstin|date|time|phone|mob|tel|qty|hsn)\b", re.I)
# name (may contain sizes like "1kg") · optional quantity token · optional unit rate · line amount
_ITEM = re.compile(rf"^(?P<name>.*?[A-Za-z].*?)\s+(?:(?P<qty>\d{{1,3}}(?:\.\d{{1,3}})?)\s*(?:x|nos?|pcs?)?\s+)?(?:(?P<rate>{_NUM})\s+)?(?P<amount>{_NUM})\s*$")
_HEADER_NOISE = re.compile(r"\b(tax\s*invoice|invoice|receipt|bill|cash\s*memo|gstin|phone|ph\.|mob|tel|www\.|@|address|road|rd\.|street|nagar|thank)\b", re.I)
_LONG_DIGITS = re.compile(r"\b\d(?:[ -]?\d){11,18}\b")
_CARD_LAST4 = re.compile(r"(?:x{2,}|\*{2,}|ending(?:\s*in)?|card\s*no\.?\s*[:\-]?\s*[x*]+)\s*[-\s]?(\d{4})\b", re.I)
_PAYMENT = [
    (re.compile(r"\bupi\b|gpay|google\s*pay|phonepe|paytm|bhim", re.I), "UPI"),
    (re.compile(r"\b(credit\s*card|debit\s*card|visa|master\s*card|mastercard|rupay|amex|card)\b", re.I), "Card"),
    (re.compile(r"\bnet\s*banking|neft|imps\b", re.I), "Net banking"),
    (re.compile(r"\bcash\b", re.I), "Cash"),
    (re.compile(r"\bwallet\b", re.I), "Wallet"),
]


def mask_digits(text: str) -> str:
    """Card-length digit runs → last four only."""
    return _LONG_DIGITS.sub(lambda m: "•••• " + re.sub(r"\D", "", m.group(0))[-4:], text)


def _amount(line: str) -> float | None:
    m = _LAST_AMOUNT.search(line)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def extract_receipt(pages: list[str], ocr_confidence: float | None = None) -> Extraction:
    pages = [mask_digits(p) for p in pages]
    scale = min(1.0, ocr_confidence) if ocr_confidence is not None else 1.0
    facts: list[Fact] = []
    warnings: list[str] = []

    def add(key: str, label: str, value, page: int, line: str, conf: float, unit: str | None = None, section: str | None = None):
        facts.append(Fact("receipt", key, label, value, page, section, snippet(line), round(conf * scale, 3), unit))

    lines = [(pno, clean(raw)) for pno, text in enumerate(pages, start=1) for raw in text.splitlines() if clean(raw)]
    if any(looks_like_injection(t) for _, t in lines):
        warnings.append("This receipt contains text addressed to AI assistants. VITTRM treated it as receipt text only.")

    # merchant: first substantial line near the top that isn't an address/phone/"tax invoice" line
    for pno, t in lines[:8]:
        letters = sum(c.isalpha() for c in t)
        if letters >= 3 and not _HEADER_NOISE.search(t) and not _DATE.search(t) and _amount(t) is None:
            add("merchant", "Merchant", t.title() if t.isupper() else t, pno, t, 0.6)
            break

    for pno, t in lines:
        if m := _GSTIN.search(t):
            add("gstin", "Seller GSTIN", m.group(1), pno, t, 0.9)
            break
    for pno, t in lines:
        if m := _INVOICE.search(t):
            add("invoice_number", "Invoice / bill number", m.group(1), pno, t, 0.7)
            break
    for pno, t in lines:
        if m := _DATE.search(t):
            d = parse_any_date(m.group(1))
            if d:
                add("purchase_date", "Purchase date", d.isoformat(), pno, t, 0.75)
                break

    # totals
    strong = [(pno, t, _amount(t)) for pno, t in lines if _TOTAL_STRONG.search(t) and not _NOT_TOTAL.search(t)]
    weak = [(pno, t, _amount(t)) for pno, t in lines if _TOTAL_WEAK.search(t) and not _NOT_TOTAL.search(t)]
    cands = [c for c in strong if c[2] is not None] or [c for c in weak if c[2] is not None]
    total = None
    if cands:
        pno, t, total = max(cands, key=lambda c: c[2])  # a grand total is the largest of the total lines
        add("total", "Total amount", total, pno, t, 0.85 if strong else 0.65, "INR")
    sub = next(((pno, t, _amount(t)) for pno, t in lines if _SUBTOTAL.search(t) and _amount(t) is not None), None)
    if sub:
        add("subtotal", "Subtotal", sub[2], sub[0], sub[1], 0.75, "INR")

    taxes: dict[str, float] = {}
    for pno, t in lines:
        m = _TAX.search(t)
        if not m or _NOT_TOTAL.search(t) and "gst" not in t.lower():
            continue
        if _GSTIN.search(t) or re.search(r"\b(incl|inclusive)\b", t, re.I):
            continue
        amt = _amount(t)
        if amt is None or (total is not None and amt >= total):
            continue
        kind = m.group(1).upper()
        rate = (m.group(2) or "").replace(" ", "")
        key = kind.lower() if kind.lower() not in taxes else f"{kind.lower()}_{len(taxes)}"
        taxes[key] = amt
        add(key, f"{kind}{' ' + rate if rate else ''}", amt, pno, t, 0.75, "INR", section="Taxes")
    if taxes:
        gst_total = round(sum(taxes.values()), 2)
        add("gst_total", "Total tax", gst_total, facts[-1].page or 1, "Sum of the tax lines above", 0.7, "INR", section="Taxes")
        if total is not None and sub:
            if abs(sub[2] + gst_total - total) > 1.0:
                warnings.append("Subtotal plus taxes doesn't add up to the total — there may be a discount, rounding or a misread number. Check the values.")

    # items: lines above the subtotal/total that look like "name … amount"
    stop = next((i for i, (_, t) in enumerate(lines) if _SUBTOTAL.search(t) or _TOTAL_STRONG.search(t) or _TOTAL_WEAK.search(t)), len(lines))
    items = []
    for pno, t in lines[:stop]:
        if _SKIP_ITEM.search(t) or _GSTIN.search(t) or _DATE.search(t):
            continue
        m = _ITEM.match(t)
        if not m:
            continue
        name = m.group("name").strip(" .:-")
        if len(re.sub(r"[^A-Za-z]", "", name)) < 2:
            continue
        amount = float(m.group("amount").replace(",", ""))
        qty = float(m.group("qty")) if m.group("qty") else None
        if mx := re.search(r"(?:^|\s)[x×]\s?(\d{1,3})$", name):  # "Masala Chai x2  60.00  120.00": x2 is the quantity
            qty = float(mx.group(1))
            name = name[: mx.start()].strip()
        items.append({"name": name, "quantity": qty, "amount": amount, "page": pno})
    if items:
        conf = 0.6
        if sub and abs(sum(i["amount"] for i in items) - sub[2]) <= 1.0:
            conf = 0.8  # line items add up to the subtotal
        facts.append(Fact("receipt", "items", "Items", items, items[0]["page"], "Items", f"{len(items)} item lines", round(conf * scale, 3)))

    for pno, t in lines:
        for pat, label in _PAYMENT:
            if pat.search(t):
                last4 = _CARD_LAST4.search(t)
                value = f"{label} ending {last4.group(1)}" if label == "Card" and last4 else label
                add("payment_method", "Payment method", value, pno, t, 0.6)
                break
        else:
            continue
        break

    if re.search(r"\$|\busd\b|\beur\b|€|£", "\n".join(pages), re.I):
        warnings.append("Some amounts may not be in rupees. Check the currency before matching this receipt.")
    if total is None:
        warnings.append("No total was found. Enter it yourself if you want to match this receipt to a transaction.")

    return Extraction(facts=facts, chunks=chunk_pages(pages), warnings=warnings)
