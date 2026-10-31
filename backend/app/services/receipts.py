"""Receipts (M13): the user-confirmed view of a scanned receipt and suggested bank-transaction matches.

A receipt is evidence of a purchase, not of a payment: VITTRM never creates a transaction from it,
and a match is only recorded when the user chooses one.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Document, DocumentFact, Transaction

AMOUNT_TOLERANCE = 1.0  # rupees (rounding on receipts)
DAYS_BEFORE, DAYS_AFTER = 2, 5  # card and UPI debits can post a few days after the bill date


def summary(db: Session, doc: Document) -> dict:
    facts = db.query(DocumentFact).filter(DocumentFact.document_id == doc.id).all()
    live = {f.key: f for f in facts if f.state != "rejected"}

    def val(k):
        f = live.get(k)
        return f.value if f else None

    return {
        "merchant": val("merchant"), "purchase_date": val("purchase_date"), "total": val("total"),
        "subtotal": val("subtotal"), "gst_total": val("gst_total"), "payment_method": val("payment_method"),
        "invoice_number": val("invoice_number"), "gstin": val("gstin"), "items": val("items") or [],
        "confirmed": {k: f.state == "confirmed" for k, f in live.items()},
        "linked_transaction_id": (doc.meta or {}).get("linked_transaction_id"),
    }


def _words(s: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower()) if w not in {"the", "and", "pvt", "ltd", "store", "mart"}}


def candidates(db: Session, user_id: str, total: float | None, purchase_date: str | None, merchant: str | None, limit: int = 5) -> list[dict]:
    if total is None:
        return []
    q = db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.direction == "debit",
                                     Transaction.amount >= total - AMOUNT_TOLERANCE, Transaction.amount <= total + AMOUNT_TOLERANCE)
    d0 = None
    if purchase_date:
        try:
            d0 = date.fromisoformat(str(purchase_date))
            q = q.filter(Transaction.txn_date >= d0 - timedelta(days=DAYS_BEFORE), Transaction.txn_date <= d0 + timedelta(days=DAYS_AFTER))
        except ValueError:
            d0 = None
    mw = _words(merchant)
    out = []
    for t in q.limit(50).all():
        overlap = bool(mw & (_words(t.merchant) | _words(t.description)))
        days = abs((t.txn_date - d0).days) if d0 else None
        score = (1.0 if abs(t.amount - total) < 0.01 else 0.7) + (0.5 if overlap else 0) - (0.05 * days if days is not None else 0.2)
        reasons = ["same amount" if abs(t.amount - total) < 0.01 else f"amount within ₹{AMOUNT_TOLERANCE:.0f}"]
        if days is not None:
            reasons.append("same day" if days == 0 else f"{days} day{'s' if days != 1 else ''} {'after' if t.txn_date > d0 else 'before'} the bill")
        if overlap:
            reasons.append("merchant name matches")
        out.append({"id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "description": t.description,
                    "merchant": t.merchant, "score": round(score, 2), "reasons": reasons})
    return sorted(out, key=lambda c: -c["score"])[:limit]
