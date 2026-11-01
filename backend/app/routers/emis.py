"""EMI Intelligence (RD §14, S30–S32)."""

import calendar
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.concurrency import require_match
from app.errors import DomainError, NotFound
from app.models import Emi, ProfileOverride, RecurringGroup, User
from app.services import calculations, obligations, profile_engine, slices
from app.services.channels import scheduler
from app.services.finance import emi as emi_math
from app.services.finance import what_if
from app.fmt import inr

router = APIRouter(prefix="/emis", tags=["emis"])

EmiType = Literal["home_loan", "personal_loan", "vehicle_loan", "education_loan", "card_emi", "consumer_emi", "gold_loan", "loan", "other"]


class LateRule(BaseModel):
    flat_fee: float | None = Field(default=None, ge=0)
    penal_rate_pa: float | None = Field(default=None, ge=0, le=60)
    gst_applicable: bool = False


class PrepayRule(BaseModel):
    allowed: bool = True
    allowed_after_months: int | None = Field(default=None, ge=0)
    charge_pct: float | None = Field(default=None, ge=0, le=20)
    max_per_year_pct: float | None = Field(default=None, gt=0, le=100)
    gst_applicable: bool = False


class EmiIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    emi_type: EmiType = "personal_loan"
    lender: str | None = Field(default=None, max_length=80)
    principal: float | None = Field(default=None, gt=0)
    amount: float = Field(gt=0, le=10_000_000)
    due_day: int = Field(ge=1, le=31)
    remaining_count: int | None = Field(default=None, ge=1, le=480)
    rate: float | None = Field(default=None, ge=0, le=60)
    rate_type: Literal["fixed", "floating"] | None = None
    late_rule: LateRule | None = None
    prepayment_rule: PrepayRule | None = None

    @field_validator("title", "lender")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


def next_due(e: Emi, today: date | None = None) -> date:
    today = today or date.today()
    if e.first_due_date and e.first_due_date >= today:
        return e.first_due_date
    y, m = today.year, today.month
    last = calendar.monthrange(y, m)[1]
    d = date(y, m, min(e.due_day, last))
    if d < today:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        d = date(y, m, min(e.due_day, calendar.monthrange(y, m)[1]))
    return d


def outstanding(e: Emi) -> float | None:
    """Present value of remaining EMIs at the stated rate — only when rate and remaining count are known."""
    if e.rate is None or not e.remaining_count:
        return None
    r = e.rate / 1200
    if r == 0:
        return e.amount * e.remaining_count
    return e.amount * (1 - (1 + r) ** -e.remaining_count) / r


def emi_out(e: Emi, db: Session | None = None) -> dict:  # includes `version` for If-Match
    g = db.get(RecurringGroup, e.recurring_group_id) if (db is not None and e.recurring_group_id) else None
    bal = outstanding(e)
    missing = []
    if e.rate is None:
        missing.append("Interest rate")
    if not e.remaining_count:
        missing.append("Remaining EMIs")
    if not e.late_rule:
        missing.append("Late-payment rule")
    return {
        "id": e.id, "title": e.title, "emi_type": e.emi_type, "lender": e.lender, "principal": e.principal,
        "amount": e.amount, "due_day": e.due_day, "next_due": next_due(e).isoformat(), "remaining_count": e.remaining_count,
        "first_due_date": e.first_due_date.isoformat() if e.first_due_date else None,
        "rate": e.rate, "rate_type": e.rate_type, "late_rule": e.late_rule, "prepayment_rule": e.prepayment_rule,
        "source_type": e.source_type, "source_ref": e.source_ref, "source_document_id": e.source_document_id,
        "confirmed": e.confirmed, "version": e.version, "estimated_outstanding": round(bal, 2) if bal is not None else None,
        "missing_terms": missing,
        "detection": {"occurrences": g.occurrences, "first_date": g.first_date.isoformat(), "last_date": g.last_date.isoformat(),
                      "confidence": g.confidence} if g else None,
    }


def _get(db: Session, user: User, emi_id: str) -> Emi:
    e = db.query(Emi).filter(Emi.id == emi_id, Emi.user_id == user.id).first()
    if not e:
        raise NotFound("EMI")
    return e


@router.get("")
def list_emis(user: User = Depends(current_user), db: Session = Depends(get_db)):
    emis = db.query(Emi).filter(Emi.user_id == user.id).order_by(Emi.due_day).all()
    s = slices.loan_slice(db, user)
    confirmed_total = sum(e.amount for e in emis if e.confirmed)
    all_total = sum(e.amount for e in emis)
    return {
        "currency": "INR",
        "emis": [emi_out(e, db) for e in emis],
        "monthly_total": round(all_total, 2),
        "monthly_total_confirmed": round(confirmed_total, 2),
        "income": {"value": s["monthly_income"], "state": s["monthly_income_state"]},
        "obligation_share_pct": round(all_total / s["monthly_income"] * 100, 1) if s["monthly_income"] else None,
    }


@router.post("")
def add_emi(body: EmiIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump()
    e = Emi(user_id=user.id, source_type="manual", confirmed=True,
            **{k: v for k, v in data.items() if k not in ("late_rule", "prepayment_rule")},
            late_rule=data["late_rule"], prepayment_rule=data["prepayment_rule"])
    db.add(e)
    db.flush()
    audit(db, user.id, "emi.added", "emi", e.id)
    scheduler.schedule_for_user(db, user)
    profile_engine.build_profile(db, user)
    db.commit()
    return emi_out(e, db)


@router.patch("/{emi_id}")
def update_emi(emi_id: str, body: EmiIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get(db, user, emi_id)
    require_match(request, e.version)
    data = body.model_dump()
    for k, v in data.items():
        setattr(e, k, v)
    e.confirmed = True
    db.add(ProfileOverride(user_id=user.id, path=f"emi/{e.id}", corrected_value={k: v for k, v in data.items() if k not in ("late_rule", "prepayment_rule")}))
    if e.recurring_group_id:
        g = db.get(RecurringGroup, e.recurring_group_id)
        if g:
            g.state = "confirmed"
            db.add(ProfileOverride(user_id=user.id, path=profile_engine.recurring_path(g.direction, g.counterparty_key),
                                   corrected_value={"state": "confirmed", "kind": "emi"}))
    audit(db, user.id, "emi.updated", "emi", e.id)
    scheduler.schedule_for_user(db, user)
    profile_engine.build_profile(db, user)
    db.commit()
    return emi_out(e, db)


@router.post("/{emi_id}/confirm")
def confirm_emi(emi_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get(db, user, emi_id)
    e.confirmed = True
    if e.recurring_group_id:
        g = db.get(RecurringGroup, e.recurring_group_id)
        if g:
            g.state, g.user_kind = "confirmed", "emi"
            db.add(ProfileOverride(user_id=user.id, path=profile_engine.recurring_path(g.direction, g.counterparty_key),
                                   corrected_value={"state": "confirmed", "kind": "emi"}))
    audit(db, user.id, "emi.confirmed", "emi", e.id)
    scheduler.schedule_for_user(db, user)
    profile_engine.build_profile(db, user)
    db.commit()
    return emi_out(e, db)


@router.delete("/{emi_id}")
def delete_emi(emi_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removing a detected EMI marks its recurring group as 'not an EMI' so it isn't re-detected."""
    e = _get(db, user, emi_id)
    if e.recurring_group_id:
        g = db.get(RecurringGroup, e.recurring_group_id)
        if g:
            g.state = "rejected"
            db.add(ProfileOverride(user_id=user.id, path=profile_engine.recurring_path(g.direction, g.counterparty_key),
                                   corrected_value={"state": "rejected", "kind": None}))
    scheduler.cancel_for_object(db, user.id, "emi", e.id)
    db.delete(e)
    audit(db, user.id, "emi.deleted", "emi", emi_id)
    profile_engine.build_profile(db, user)
    db.commit()
    return {"ok": True}


@router.get("/calendar")
def calendar_view(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
                  view: Literal["month", "week"] = "month", day: date | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = date.today()
    if view == "week":
        anchor = day or today
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        y, m = start.year, start.month
    else:
        y, m = (int(month[:4]), int(month[5:])) if month else (today.year, today.month)
        if not 1 <= m <= 12:
            raise DomainError("INVALID_MONTH", "Choose a month from 01 to 12.", field="month")
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])
    items = obligations.between(db, user.id, start, end)
    return {"currency": "INR", "view": view, "month": f"{y:04d}-{m:02d}", "start": start.isoformat(), "end": end.isoformat(),
            "items": items, "total": round(sum(i["amount"] or 0 for i in items), 2),
            "unknown_amounts": sum(1 for i in items if i["amount"] is None)}


class WhatIfIn(BaseModel):
    kind: Literal["missed_payment", "late_payment", "prepayment", "rate_change"]
    days_late: int = Field(default=30, ge=1, le=365)
    prepay_amount: float | None = Field(default=None, gt=0)
    mode: Literal["reduce_tenure", "reduce_emi"] = "reduce_tenure"
    new_rate_pct: float | None = Field(default=None, ge=0, le=60)
    hold: Literal["emi", "tenure"] = "emi"
    late_rule_override: LateRule | None = None
    prepayment_rule_override: PrepayRule | None = None


@router.post("/{emi_id}/what-if")
def emi_what_if(emi_id: str, body: WhatIfIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get(db, user, emi_id)
    gst = get_settings().default_gst_on_fees_pct
    if body.kind in ("missed_payment", "late_payment"):
        rule = body.late_rule_override.model_dump() if body.late_rule_override else e.late_rule
        days = 30 if body.kind == "missed_payment" else body.days_late
        out = what_if.missed_payment(e.amount, rule, days, gst, label=body.kind)
        if body.kind == "late_payment" and out["computable"]:
            out["notes"].append(f"Paying {days} days late; the next EMI is still due on its usual date.")
    else:
        bal = outstanding(e)
        if bal is None:
            out = {"kind": body.kind, "computable": False, "baseline": None, "scenario": None,
                   "missing": [m for m in ("Interest rate", "Remaining EMIs") if (m == "Interest rate" and e.rate is None) or (m == "Remaining EMIs" and not e.remaining_count)],
                   "assumptions": [], "notes": ["Add the interest rate and remaining EMIs to model this."], "formula_version": what_if.FORMULA_VERSION,
                   "inputs": body.model_dump()}
        elif body.kind == "prepayment":
            if not body.prepay_amount:
                raise DomainError("VALUE_REQUIRED", "Enter the prepayment amount.", field="prepay_amount")
            rule = body.prepayment_rule_override.model_dump() if body.prepayment_rule_override else e.prepayment_rule
            # Model from today: treat remaining schedule as a fresh loan of `bal` over remaining_count, prepaying after 1 EMI.
            n = e.remaining_count
            if n < 2:
                raise DomainError("INVALID_INPUT", "Only one EMI remains; there's nothing to prepay.")
            if rule and rule.get("allowed_after_months"):
                rule = {**rule, "allowed_after_months": 0}
            out = what_if.prepayment(bal, e.rate, n, body.prepay_amount, 1, body.mode, rule, gst)
            out["assumptions"].insert(0, f"Outstanding estimated at {inr(bal)} from {n} remaining EMIs of {inr(e.amount)} at {e.rate:g}% p.a.")
            out["assumptions"].append("Prepayment is made right after your next EMI.")
            if e.prepayment_rule and e.prepayment_rule.get("allowed_after_months"):
                out["notes"].append(f"Your terms allow part-prepayment only after {e.prepayment_rule['allowed_after_months']} EMIs from the start of the loan.")
        else:
            if body.new_rate_pct is None:
                raise DomainError("VALUE_REQUIRED", "Enter the new interest rate.", field="new_rate_pct")
            out = what_if.rate_change(bal, e.rate, e.remaining_count, body.new_rate_pct, body.hold)
            if e.rate_type == "fixed":
                out["notes"].append("This EMI is recorded as fixed-rate; a rate change may not apply to it.")
    run_id = calculations.record(db, user.id, f"emi.{body.kind}", {"emi_id": e.id, **body.model_dump()},
                                 {k: v for k, v in out.items() if k != "inputs"}, out["formula_version"])
    audit(db, user.id, "calculation.run", "emi", e.id, kind=body.kind)
    db.commit()
    return {"currency": "INR", "precision": 2, "calculation_id": run_id, "emi": emi_out(e, db), "result": out}


class EmiOption(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    amount: float = Field(gt=0)
    rate: float = Field(ge=0, le=60)
    tenure_months: int = Field(ge=1, le=360)
    processing_fee: float | None = Field(default=None, ge=0)
    fee_gst_applicable: bool = True


class NewEmiIn(BaseModel):
    options: list[EmiOption] = Field(min_length=1, max_length=3)


@router.post("/explore")
def explore_new_emi(body: NewEmiIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Compare contemplated EMI options side by side with affordability (RD §14.4, HW 'comparisons, hidden charges')."""
    s = slices.emi_slice(db, user)
    gst = get_settings().default_gst_on_fees_pct
    rows = []
    for o in body.options:
        t = emi_math.totals(o.amount, o.rate, o.tenure_months)
        fee = o.processing_fee
        fee_total = None if fee is None else fee * (1 + gst / 100 if o.fee_gst_applicable else 1)
        aff = what_if.new_emi_affordability(s["monthly_income"], s["existing_emis"], t["monthly_emi"], s["avg_monthly_non_emi_spend"])
        rows.append({
            "label": o.label, "inputs": o.model_dump(), "monthly_emi": t["monthly_emi"], "total_interest": t["total_interest"],
            "processing_fee_with_gst": fee_total,
            "total_cost": t["total_interest"] + (fee_total or 0),
            "fee_known": fee is not None,
            "affordability": aff,
        })
    notes = []
    if any(not r["fee_known"] for r in rows):
        notes.append("Processing fee not entered for some options, so their total cost excludes it.")
    if any(o.rate == 0 for o in body.options):
        notes.append("'No-cost' EMIs often recover interest through a discount you don't get or a processing fee; enter the fee to compare fairly.")
    run_id = calculations.record(db, user.id, "emi.explore", body.model_dump(), {"count": len(rows)}, what_if.FORMULA_VERSION)
    db.commit()
    return {"currency": "INR", "calculation_id": run_id, "options": rows, "notes": notes, "profile_used": s}
