"""Financial Profile, review & correction (RD §9.3–9.4, S06)."""

from typing import Literal

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import Document, ProfileOverride, RecurringGroup, Transaction, User
from app.services import privacy, profile_engine, storage
from app.services.statements.categorizer import CATEGORIES

router = APIRouter(tags=["profile"])

KIND_LABELS = {
    "salary": "Salary", "income_other": "Other regular income", "emi": "Loan EMI", "card_bill": "Credit card bill",
    "rent": "Rent", "premium": "Insurance premium", "subscription": "Subscription", "utility": "Bill / utility",
    "investment": "Investment (SIP)", "transfer": "Regular transfer", "other": "Other",
}


@router.get("/profile")
def get_profile(rebuild: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"currency": "INR", "precision": 2, "profile": profile_engine.get_profile(db, user, rebuild=rebuild)}


def _txn_out(t: Transaction, doc_names: dict) -> dict:
    return {
        "id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "direction": t.direction,
        "description": t.description, "merchant": t.merchant, "channel": t.channel, "category": t.category,
        "category_label": CATEGORIES.get(t.category, t.category), "category_source": t.category_source,
        "confidence": t.confidence, "recurring_group_id": t.recurring_group_id,
        "source": {"document_id": t.source_document_id, "document_name": doc_names.get(t.source_document_id), "ref": t.source_ref},
    }


def _doc_names(db: Session, user: User) -> dict:
    return {d.id: d.display_name for d in db.query(Document).filter(Document.owner_user_id == user.id)}


@router.get("/profile/review")
def review(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = profile_engine.get_profile(db, user)
    names = _doc_names(db, user)
    groups = db.query(RecurringGroup).filter(RecurringGroup.user_id == user.id).all()
    txns_by_group: dict[str, list[Transaction]] = {}
    for t in db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.recurring_group_id.isnot(None)):
        txns_by_group.setdefault(t.recurring_group_id, []).append(t)

    def g_out(g: RecurringGroup) -> dict:
        ts = sorted(txns_by_group.get(g.id, []), key=lambda t: t.txn_date)
        kind = g.user_kind or g.kind
        return {
            "id": g.id, "label": g.label, "kind": kind, "kind_label": KIND_LABELS.get(kind, kind), "direction": g.direction,
            "typical_amount": g.typical_amount, "day_of_month": g.day_of_month, "occurrences": g.occurrences,
            "first_date": g.first_date.isoformat(), "last_date": g.last_date.isoformat(), "confidence": g.confidence,
            "state": g.state, "needs_confirmation": kind in profile_engine.rec.NEEDS_CONFIRMATION and g.state == "extracted",
            "transactions": [_txn_out(t, names) for t in ts[-6:]],
        }

    uncertain = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, Transaction.confidence < 0.6, Transaction.category_source != "user")
        .order_by(Transaction.txn_date.desc()).limit(50).all()
    )
    return {
        "currency": "INR",
        "review_state": profile.get("review_state"),
        "income": profile.get("income_summary"),
        "recurring": [g_out(g) for g in sorted(groups, key=lambda g: (g.direction != "credit", -g.typical_amount)) if g.state != "rejected"],
        "rejected": [g_out(g) for g in groups if g.state == "rejected"],
        "uncertain_transactions": [_txn_out(t, names) for t in uncertain],
        "categories": profile.get("expense_summary", {}).get("category_totals", []),
        "merchants": profile.get("expense_summary", {}).get("merchant_totals", []),
        "high_value_events": profile.get("high_value_events", []),
        "cashflow": profile.get("cashflow_metrics"),
        "category_options": [{"key": k, "label": v} for k, v in CATEGORIES.items()],
        "kind_options": [{"key": k, "label": v} for k, v in KIND_LABELS.items()],
    }


class RecurringAction(BaseModel):
    action: Literal["confirm", "reject", "set_kind"]
    kind: str | None = None


@router.post("/profile/recurring/{group_id}")
def recurring_action(group_id: str, body: RecurringAction, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.query(RecurringGroup).filter(RecurringGroup.id == group_id, RecurringGroup.user_id == user.id).first()
    if not g:
        raise NotFound("Recurring payment")
    if body.action == "set_kind":
        if body.kind not in KIND_LABELS:
            raise DomainError("INVALID_KIND", "Choose a valid type.", field="kind")
        g.user_kind, g.state = body.kind, "confirmed"
    elif body.action == "confirm":
        g.state = "confirmed"
    else:
        g.state = "rejected"
    db.add(ProfileOverride(
        user_id=user.id, path=profile_engine.recurring_path(g.direction, g.counterparty_key),
        prior_value={"kind": g.kind}, corrected_value={"state": g.state, "kind": g.user_kind},
    ))
    audit(db, user.id, f"recurring.{body.action}", "recurring_group", g.id)
    profile_engine._sync_detected_emis(db, user.id)
    profile_engine.build_profile(db, user)
    db.commit()
    return review(user, db)


class OverrideIn(BaseModel):
    path: Literal["income/monthly_estimate"]
    value: float | None = Field(default=None, ge=0, le=100_000_000)
    reason: str | None = Field(default=None, max_length=200)


@router.patch("/profile/overrides")
def set_override(body: OverrideIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prior = (profile_engine.get_profile(db, user).get("income_summary") or {}).get("monthly_estimate", {}).get("value")
    db.add(ProfileOverride(user_id=user.id, path=body.path, prior_value=prior, corrected_value=body.value, reason=body.reason))
    audit(db, user.id, "profile.override", "profile", body.path)
    profile = profile_engine.build_profile(db, user)
    db.commit()
    return {"currency": "INR", "profile": profile}


@router.get("/transactions")
def list_transactions(
    category: str | None = None, q: str | None = Query(default=None, max_length=80), direction: str | None = None,
    limit: int = Query(default=100, le=500), offset: int = 0,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    query = db.query(Transaction).filter(Transaction.user_id == user.id)
    if category:
        query = query.filter(Transaction.category == category)
    if direction in ("credit", "debit"):
        query = query.filter(Transaction.direction == direction)
    if q:
        query = query.filter(Transaction.description.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(Transaction.txn_date.desc()).offset(offset).limit(limit).all()
    names = _doc_names(db, user)
    return {"currency": "INR", "total": total, "items": [_txn_out(t, names) for t in rows]}


class TxnPatch(BaseModel):
    category: str | None = None
    direction: Literal["credit", "debit"] | None = None


@router.patch("/transactions/{txn_id}")
def patch_transaction(txn_id: str, body: TxnPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == user.id).first()
    if not t:
        raise NotFound("Transaction")
    if body.category is not None:
        if body.category not in CATEGORIES:
            raise DomainError("INVALID_CATEGORY", "Choose a valid category.", field="category")
        t.category = body.category
        t.category_source = "user"
    if body.direction is not None:
        t.direction = body.direction
    t.confidence = max(t.confidence, 0.95)
    db.add(ProfileOverride(user_id=user.id, path=f"txn/{t.fingerprint}", corrected_value=body.model_dump(exclude_none=True)))
    audit(db, user.id, "transaction.corrected", "transaction", t.id)
    profile_engine.rebuild_recurring(db, user.id)
    profile_engine.build_profile(db, user)
    db.commit()
    return _txn_out(t, _doc_names(db, user))


@router.get("/profile/spending")
def spending(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = profile_engine.get_profile(db, user)
    return {"currency": "INR", **p.get("expense_summary", {}), "cashflow": p.get("cashflow_metrics")}


class DeleteAllIn(BaseModel):
    confirm: Literal["DELETE"]


@router.post("/profile/delete-all")
def delete_all(body: DeleteAllIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """User-visible delete control (RD §23.1): removes every uploaded file and all profile data; keeps the login."""
    from app.models import (
        BankAccount, Conversation, Emi, FamilyMember, FinancialProfile, Notification, Reminder,
        UserCard, UserLoan, UserPolicy,
    )
    for d in db.query(Document).filter(Document.owner_user_id == user.id).all():
        storage.delete(d.file_key)
        db.delete(d)
    for model in (UserPolicy, Emi, UserLoan, UserCard, RecurringGroup, Transaction, BankAccount, FamilyMember,
                  ProfileOverride, Reminder, Notification, Conversation):
        db.query(model).filter(model.user_id == user.id).delete()
    fp = db.get(FinancialProfile, user.id)
    if fp:
        db.delete(fp)
    user.onboarding_step = "statement"
    audit(db, user.id, "profile.deleted_all")
    db.commit()
    return {"ok": True}


@router.get("/profile/export")
def export_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Download everything we hold about the signed-in user as JSON (data portability, RD §23.1)."""
    data = privacy.export_user(db, user)
    audit(db, user.id, "profile.exported")
    db.commit()
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="vitram-export-{date.today():%Y%m%d}.json"'})
