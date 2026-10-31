"""Explicit, reversible import of reviewed card-document facts into a saved card."""

from datetime import date

from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Document, DocumentFact, UserCard

IMPORT_KEYS = ("outstanding", "due_date", "points_balance")


def reviewed_values(db: Session, doc: Document) -> dict[str, object]:
    facts = db.query(DocumentFact).filter(DocumentFact.document_id == doc.id,
                                          DocumentFact.user_id == doc.owner_user_id,
                                          DocumentFact.key.in_(("last4", *IMPORT_KEYS)),
                                          DocumentFact.user_verified.is_(True)).all()
    values = {fact.key: fact.value for fact in facts}
    if not values.get("last4") or not any(key in values for key in IMPORT_KEYS):
        raise DomainError("CARD_FACTS_UNREVIEWED", "Confirm the card ending and at least one balance, due date or reward fact first.")
    return values


def apply_reviewed(db: Session, doc: Document, card: UserCard, *, replace_existing: bool) -> list[str]:
    if doc.type != "card_document" or doc.owner_user_id != card.user_id:
        raise DomainError("INVALID_CARD_DOCUMENT", "Choose your own processed card document.")
    if doc.processing_status not in ("needs_review", "ready"):
        raise DomainError("DOCUMENT_NOT_READY", "Wait for this card document to finish processing.")
    values = reviewed_values(db, doc)
    if not card.last4 or card.last4 != values["last4"]:
        raise DomainError("CARD_LAST4_MISMATCH", "The confirmed last four digits must match the saved card.")
    if card.source_document_id and card.source_document_id != doc.id and not replace_existing:
        raise DomainError("CARD_IMPORT_CONFLICT", "This card is linked to a different document. Confirm replacement first.", status_code=409)
    occupied = (("outstanding" in values and card.outstanding is not None) or
                ("due_date" in values and card.due_date is not None) or
                ("points_balance" in values and card.points and card.points.get("balance") is not None))
    if occupied and card.source_document_id != doc.id and not replace_existing:
        raise DomainError("CARD_IMPORT_CONFLICT", "This card already has values. Confirm replacement first.", status_code=409)
    if card.source_document_id:
        _clear_card_imported(card)
    imported: list[str] = []
    if "outstanding" in values:
        amount = values["outstanding"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount <= 100_000_000:
            raise DomainError("INVALID_CARD_FACT", "The reviewed amount due is invalid; correct it before importing.")
        card.outstanding = round(float(amount), 2)
        imported.append("outstanding")
    if "due_date" in values:
        try:
            card.due_date = date.fromisoformat(str(values["due_date"]))
        except ValueError as exc:
            raise DomainError("INVALID_CARD_FACT", "The reviewed due date is invalid; correct it before importing.") from exc
        imported.append("due_date")
    if "points_balance" in values:
        points = values["points_balance"]
        if isinstance(points, bool) or not isinstance(points, (int, float)) or not 0 <= points <= 100_000_000:
            raise DomainError("INVALID_CARD_FACT", "The reviewed reward balance is invalid; correct it before importing.")
        card.points = {"balance": float(points), "as_of": None, "expiring": [],
                       "source": "reviewed_document"}
        imported.append("points_balance")
    card.source_document_id = doc.id
    card.source_fields = imported
    return imported


def _clear_card_imported(card: UserCard) -> None:
    fields = set(card.source_fields or [])
    if "outstanding" in fields:
        card.outstanding = None
    if "due_date" in fields:
        card.due_date = None
    if "points_balance" in fields and card.points and card.points.get("source") == "reviewed_document":
        card.points = None
    card.source_document_id = None
    card.source_fields = None


def clear_linked_values(db: Session, doc_id: str) -> int:
    """Remove values whose sole provenance is a document being re-read/deleted."""
    from app.services import card_spend

    cards = db.query(UserCard).filter(UserCard.source_document_id == doc_id).all()
    for card in cards:
        _clear_card_imported(card)
    return len(cards) + card_spend.clear_for_document(db, doc_id)
