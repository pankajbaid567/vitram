"""Conservative card-statement facts. Never retain a full PAN, CVV or PIN."""

import re

from app.services.extractors.common import Extraction, Fact, clean, looks_like_injection, to_amount
from app.services.statements.parser import parse_date

_PAN = re.compile(r"(?<!\d)(?:\d[\s-]?){12,19}(?!\d)")
_CVV = re.compile(r"(?i)\b(?:cvv|cvc|pin)\s*[:=-]?\s*\d{3,6}\b")
_LAST4 = re.compile(r"(?i)(?:ending\s*(?:in)?|last\s*4|x{4,}|\*{4,})\s*[:#-]?\s*(\d{4})\b")
_DUE = re.compile(r"(?i)\b(?:payment\s+)?due\s+date\s*[:#-]?\s*(\d{1,2}[-/. ]\w+[-/. ]\d{2,4}|\d{4}-\d{2}-\d{2})")
_OUT = re.compile(r"(?i)\b(?:total\s+amount\s+due|outstanding\s+balance|total\s+due)\s*[:₹Rs. ]*([\d,]+(?:\.\d{1,2})?)")
_POINTS = re.compile(r"(?i)\b(?:reward\s+points|miles)\s+balance\s*[: ]*([\d,]+(?:\.\d{1,2})?)")
_PURCHASE = re.compile(
    r"(?i)^(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s+(?:purchase|pos|ecom(?:merce)?)\s+"
    r"(.{2,80}?)\s+(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)$"
)


def redact(text: str) -> str:
    return _CVV.sub("[redacted credential]", _PAN.sub("[redacted card number]", text))


def extract_card(pages: list[str]) -> Extraction:
    facts: list[Fact] = []
    chunks: list[dict] = []
    warnings: list[str] = ["Card terms and balances are read from the uploaded document, not a live issuer feed. Check all facts before use."]
    patterns = (("last4", "Card ending", _LAST4), ("due_date", "Payment due date", _DUE),
                ("outstanding", "Amount due", _OUT), ("points_balance", "Reward balance", _POINTS))
    found: set[str] = set()
    purchases = 0
    for page_no, raw in enumerate(pages, start=1):
        page = redact(raw)
        chunks.append({"page": page_no, "section": "Card statement", "text": page[:20_000]})
        for line in page.splitlines():
            line = clean(line)
            if not line or looks_like_injection(line):
                continue
            purchase = _PURCHASE.match(line)
            if purchase and purchases < 200:
                purchased_on = parse_date(purchase.group(1))
                amount = to_amount(purchase.group(3))
                merchant = purchase.group(2).strip(" -")
                if purchased_on and amount is not None and amount > 0 and merchant:
                    purchases += 1
                    facts.append(Fact("card_spend", f"purchase_{purchases}", "Possible card purchase",
                                      {"date": purchased_on.isoformat(), "merchant": merchant, "amount_inr": amount},
                                      page_no, "Card statement", line[:220], 0.55, "INR"))
            for key, label, pattern in patterns:
                if key in found:
                    continue
                match = pattern.search(line)
                if not match:
                    continue
                value: object = match.group(1)
                if key == "due_date":
                    parsed = parse_date(str(value))
                    if parsed is None:
                        continue
                    value = parsed.isoformat()
                elif key in ("outstanding", "points_balance"):
                    value = to_amount(str(value))
                    if value is None:
                        continue
                facts.append(Fact("card", key, label, value, page_no, "Card statement", line[:220], 0.72,
                                  "INR" if key == "outstanding" else None))
                found.add(key)
    if not facts:
        warnings.append("No supported card facts were found. Add the card manually using only its last four digits.")
    if purchases:
        warnings.append("Purchase rows are possible card spend, not a verified merchant feed. Review each row; no saved card is updated automatically.")
    return Extraction(facts, chunks, warnings)
