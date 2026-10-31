"""Reconcile *confirmed* card-statement purchases into a card's reward estimate (spec D4).

Statement purchase rows are low-confidence extractions, so nothing counts until the user has confirmed the row.
Confirmed rows are grouped by spend category and stored in ``UserCard.imported_spend`` with their provenance,
**separately** from the spend the user typed in: so the import can be previewed first, undone, and never
overwrites manual entries. Reward estimates use the sum of both (:func:`effective_cycle_spend`).
"""

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Document, DocumentFact, UserCard
from app.services.statements.categorizer import CATEGORIES, categorize

MAX_ROWS = 200


def effective_cycle_spend(card: UserCard) -> dict[str, float]:
    """Manually entered cycle spend plus reconciled statement purchases, per category."""
    total: dict[str, float] = defaultdict(float)
    for cat, amount in (card.cycle_spend or {}).items():
        total[cat] += float(amount)
    for cat, amount in ((card.imported_spend or {}).get("by_category") or {}).items():
        total[cat] += float(amount)
    return {k: round(v, 2) for k, v in total.items()}


def _check(db: Session, doc: Document, card: UserCard) -> None:
    if doc.type != "card_document" or doc.owner_user_id != card.user_id:
        raise DomainError("INVALID_CARD_DOCUMENT", "Choose your own processed card document.")
    if doc.processing_status not in ("needs_review", "ready"):
        raise DomainError("DOCUMENT_NOT_READY", "Wait for this card document to finish processing.")
    last4 = (db.query(DocumentFact).filter(DocumentFact.document_id == doc.id, DocumentFact.key == "last4",
                                           DocumentFact.user_verified.is_(True)).first())
    if last4 is None:
        raise DomainError("CARD_FACTS_UNREVIEWED", "Confirm the card ending on the statement first.")
    if not card.last4 or card.last4 != last4.value:
        raise DomainError("CARD_LAST4_MISMATCH", "The confirmed last four digits must match the saved card.")


def preview(db: Session, doc: Document, card: UserCard) -> dict:
    """What would be counted. Unconfirmed and rejected rows are listed as such and never counted."""
    _check(db, doc, card)
    facts = (db.query(DocumentFact).filter(DocumentFact.document_id == doc.id, DocumentFact.fact_type == "card_spend")
             .order_by(DocumentFact.key).all())
    rows, unconfirmed, rejected = [], 0, 0
    for f in facts:
        if f.state == "rejected":
            rejected += 1
        elif not f.user_verified:
            unconfirmed += 1
        elif isinstance(f.value, dict) and f.value.get("amount_inr", 0) > 0:
            cat, _, _ = categorize(str(f.value.get("merchant", "")), "debit")
            if cat not in CATEGORIES or cat in ("salary", "income_other", "refund", "transfers", "card_payment", "emi", "cash", "investments"):
                cat = "other"
            rows.append({"fact_id": f.id, "date": f.value.get("date"), "merchant": f.value.get("merchant"),
                         "amount": float(f.value["amount_inr"]), "category": cat, "category_label": CATEGORIES[cat],
                         "page": f.page})
    rows = rows[:MAX_ROWS]
    by_category: dict[str, float] = defaultdict(float)
    for r in rows:
        by_category[r["category"]] += r["amount"]
    return {"currency": "INR", "document_id": doc.id, "card_id": card.id, "counted_rows": rows,
            "by_category": {k: round(v, 2) for k, v in by_category.items()}, "total": round(sum(by_category.values()), 2),
            "unconfirmed_rows": unconfirmed, "rejected_rows": rejected,
            "note": "Only purchases you confirmed are counted. Categories are inferred from the merchant name."}


def apply(db: Session, doc: Document, card: UserCard, *, replace_existing: bool) -> dict:
    p = preview(db, doc, card)
    if not p["counted_rows"]:
        raise DomainError("NO_CONFIRMED_PURCHASES", "Confirm at least one purchase row first.")
    existing = card.imported_spend
    if existing and existing.get("document_id") != doc.id and not replace_existing:
        raise DomainError("SPEND_IMPORT_CONFLICT", "This card already counts purchases from a different statement. Confirm replacement first.", status_code=409)
    card.imported_spend = {"document_id": doc.id, "by_category": p["by_category"], "rows": len(p["counted_rows"]), "total": p["total"],
                           "imported_at": datetime.now(timezone.utc).isoformat()}
    return card.imported_spend


def clear(card: UserCard) -> bool:
    had = bool(card.imported_spend)
    card.imported_spend = None
    return had


def clear_for_document(db: Session, doc_id: str) -> int:
    """A statement being re-read or deleted withdraws everything it contributed."""
    n = 0
    for card in db.query(UserCard).filter(UserCard.imported_spend.is_not(None)):
        if (card.imported_spend or {}).get("document_id") == doc_id:
            card.imported_spend = None
            n += 1
    return n
