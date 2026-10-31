"""Spending insights, explain-this-transaction and the cash-flow estimate (M13)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import ExpectedPayment, ProfileOverride, RecurringGroup, User
from app.services import forecast, insights

router = APIRouter(tags=["insights"])


@router.get("/insights/spending")
def spending(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return insights.spending_insights(db, user.id)


class SubscriptionDecision(BaseModel):
    decision: Literal["confirm", "dismiss", "reset"]


@router.post("/insights/subscriptions/{group_id}")
def decide_subscription(group_id: str, body: SubscriptionDecision, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.query(RecurringGroup).filter(RecurringGroup.id == group_id, RecurringGroup.user_id == user.id).first()
    if not g:
        raise NotFound("Recurring payment")
    g.user_kind = {"confirm": "subscription", "dismiss": "not_subscription", "reset": None}[body.decision]
    audit(db, user.id, f"insight.subscription_{body.decision}", "recurring_group", g.id)
    db.commit()
    return {"ok": True, "group_id": g.id, "user_kind": g.user_kind}


class UnusualDecision(BaseModel):
    decision: Literal["expected", "reset"]


@router.post("/insights/unusual/{txn_id}")
def decide_unusual(txn_id: str, body: UnusualDecision, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not insights.explain_transaction(db, user.id, txn_id):
        raise NotFound("Transaction")
    db.add(ProfileOverride(user_id=user.id, path=f"insight/unusual/{txn_id}", prior_value=None,
                           corrected_value="expected" if body.decision == "expected" else None, reason=body.decision))
    audit(db, user.id, f"insight.unusual_{body.decision}", "transaction", txn_id)
    db.commit()
    return {"ok": True}


@router.get("/transactions/{txn_id}/explain")
def explain(txn_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = insights.explain_transaction(db, user.id, txn_id)
    if not out:
        raise NotFound("Transaction")
    return out


# --- cash-flow estimate ------------------------------------------------------

@router.get("/forecast")
def get_forecast(days: int = Query(default=60, ge=7, le=120), user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = forecast.build(db, user, days=days)
    out["expected_payments"] = [
        {"id": x.id, "label": x.label, "amount": x.amount, "direction": x.direction, "on_date": x.on_date.isoformat()}
        for x in db.query(ExpectedPayment).filter(ExpectedPayment.user_id == user.id).order_by(ExpectedPayment.on_date)
    ]
    return out


class ExclusionIn(BaseModel):
    key: str = Field(pattern=r"^(income|recurring:[\w-]{8,40}|emi:[\w-]{8,40}|card:[\w-]{8,40}|expected:[\w-]{8,40})$")
    excluded: bool


@router.post("/forecast/exclusions")
def set_exclusion(body: ExclusionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(ProfileOverride(user_id=user.id, path=f"forecast/exclude/{body.key}", prior_value=None, corrected_value=body.excluded))
    db.commit()
    return {"ok": True}


class OpeningIn(BaseModel):
    amount: float | None = Field(default=None, ge=-10_000_000, le=1_000_000_000)


@router.put("/forecast/opening-balance")
def set_opening(body: OpeningIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    value = {"amount": body.amount, "as_of": date.today().isoformat()} if body.amount is not None else None
    db.add(ProfileOverride(user_id=user.id, path="forecast/opening_balance", prior_value=None, corrected_value=value))
    db.commit()
    return forecast.opening_balance(db, user)


class ExpectedIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=100_000_000)
    direction: Literal["credit", "debit"]
    on_date: date


@router.post("/forecast/expected")
def add_expected(body: ExpectedIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.on_date < date.today():
        raise DomainError("DATE_IN_PAST", "Choose today or a later date.", field="on_date")
    x = ExpectedPayment(user_id=user.id, label=body.label.strip(), amount=round(body.amount, 2), direction=body.direction, on_date=body.on_date)
    db.add(x)
    db.commit()
    return {"id": x.id}


@router.delete("/forecast/expected/{item_id}")
def delete_expected(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    x = db.query(ExpectedPayment).filter(ExpectedPayment.id == item_id, ExpectedPayment.user_id == user.id).first()
    if not x:
        raise NotFound("Expected payment")
    db.delete(x)
    db.commit()
    return {"ok": True}
