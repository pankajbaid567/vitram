"""Cash-flow estimate (M13) — deterministic, from confirmed data only.

Inputs, each included only when the user has confirmed or entered it:
  income        — monthly income the user confirmed (or typed in), on the salary day of a confirmed salary pattern
  recurring     — confirmed recurring debits (rent, bills, subscriptions…), excluding EMIs and card bills (counted below)
  EMIs          — confirmed EMIs on their due day, respecting first due date and instalments left
  card bills    — outstanding amounts the user entered, on the card's due date
  expected      — one-off amounts the user added
The starting balance is one the user entered, else the last balance printed on their statement (with its date).
Nothing is guessed: missing inputs are listed instead of filled in. It is an estimate, not a promise.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Emi, ExpectedPayment, ProfileOverride, RecurringGroup, Transaction, User, UserCard
from app.services import profile_engine

SKIP_RECURRING_KINDS = {"emi", "card_bill", "salary", "income_other", "transfer", "investment"}
LOW_BALANCE_BUFFER = 5000.0  # rupees; below this we call out "tight"


def _on_day(y: int, m: int, day: int) -> date:
    return date(y, m, min(max(day, 1), calendar.monthrange(y, m)[1]))


def _monthly_dates(day: int, start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while True:
        d = _on_day(y, m, day)
        if d > end:
            return out
        if d >= start:
            out.append(d)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _nice(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.day} {x.strftime('%b %Y')}"


def _latest_override(db: Session, user_id: str, path: str):
    r = (db.query(ProfileOverride).filter(ProfileOverride.user_id == user_id, ProfileOverride.path == path)
         .order_by(ProfileOverride.created_at.desc()).first())
    return r.corrected_value if r else None


def exclusions(db: Session, user_id: str) -> set[str]:
    rows = (db.query(ProfileOverride).filter(ProfileOverride.user_id == user_id, ProfileOverride.path.like("forecast/exclude/%"))
            .order_by(ProfileOverride.created_at).all())
    state: dict[str, bool] = {}
    for r in rows:
        state[r.path.removeprefix("forecast/exclude/")] = bool(r.corrected_value)
    return {k for k, v in state.items() if v}


def opening_balance(db: Session, user: User) -> dict:
    entered = _latest_override(db, user.id, "forecast/opening_balance")
    if isinstance(entered, dict) and entered.get("amount") is not None:
        return {"amount": float(entered["amount"]), "as_of": entered.get("as_of"), "source": "you entered"}
    t = (db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.balance.isnot(None))
         .order_by(Transaction.txn_date.desc()).first())
    if t:
        return {"amount": float(t.balance), "as_of": t.txn_date.isoformat(), "source": "last balance on your statement"}
    return {"amount": None, "as_of": None, "source": None}


def build(db: Session, user: User, days: int = 60, today: date | None = None) -> dict:
    today = today or date.today()
    end = today + timedelta(days=days)
    excluded = exclusions(db, user.id)
    events: list[dict] = []
    assumptions: list[str] = []
    missing: list[str] = []

    def add(key: str, d: date, amount: float, direction: str, label: str, source: str):
        events.append({"key": key, "date": d.isoformat(), "amount": round(amount, 2), "direction": direction, "label": label,
                       "source": source, "excluded": key.split("@")[0] in excluded})

    # income: confirmed or user-entered only
    profile = profile_engine.get_profile(db, user)
    inc = (profile.get("income_summary") or {}).get("monthly_estimate") or {}
    income = None
    if inc.get("value") is not None and inc.get("state") == "confirmed":
        income, income_src = float(inc["value"]), "income you confirmed"
    elif user.salary_manual:
        income, income_src = float(user.salary_manual), "salary you entered"
    salary_group = db.query(RecurringGroup).filter(RecurringGroup.user_id == user.id, RecurringGroup.direction == "credit",
                                                   RecurringGroup.state == "confirmed").order_by(RecurringGroup.typical_amount.desc()).first()
    if income is not None:
        day = salary_group.day_of_month if salary_group and salary_group.day_of_month else None
        if day is None:
            day = 1
            assumptions.append("Income is placed on the 1st of each month because no confirmed salary date was found.")
        for d in _monthly_dates(day, today, end):
            add(f"income@{d}", d, income, "credit", "Monthly income", income_src)
    else:
        missing.append("Confirmed monthly income — confirm it in Review, or enter your salary in your profile.")

    # confirmed recurring debits
    groups = db.query(RecurringGroup).filter(RecurringGroup.user_id == user.id, RecurringGroup.direction == "debit",
                                             RecurringGroup.state == "confirmed").all()
    for g in groups:
        kind = g.user_kind or g.kind
        if kind in SKIP_RECURRING_KINDS or not g.day_of_month:
            continue
        for d in _monthly_dates(g.day_of_month, today, end):
            add(f"recurring:{g.id}@{d}", d, g.typical_amount, "debit", g.label, "recurring payment you confirmed")
    unconfirmed = db.query(RecurringGroup).filter(RecurringGroup.user_id == user.id, RecurringGroup.direction == "debit",
                                                  RecurringGroup.state == "extracted").count()
    if unconfirmed:
        missing.append(f"{unconfirmed} detected recurring payment{'s' if unconfirmed > 1 else ''} not confirmed yet — they're left out.")

    # confirmed EMIs
    for e in db.query(Emi).filter(Emi.user_id == user.id, Emi.confirmed.is_(True)).all():
        start = max(today, e.first_due_date) if e.first_due_date else today
        dates = _monthly_dates(e.due_day, start, end)
        if e.remaining_count is not None:
            dates = dates[: max(e.remaining_count, 0)]
        for d in dates:
            add(f"emi:{e.id}@{d}", d, e.amount, "debit", e.title, "EMI you confirmed")
    pending_emis = db.query(Emi).filter(Emi.user_id == user.id, Emi.confirmed.is_(False)).count()
    if pending_emis:
        missing.append(f"{pending_emis} EMI{'s' if pending_emis > 1 else ''} waiting for confirmation — left out.")

    # card bills the user entered
    for c in db.query(UserCard).filter(UserCard.user_id == user.id).all():
        if c.due_date and c.outstanding and today <= c.due_date <= end:
            add(f"card:{c.id}@{c.due_date}", c.due_date, c.outstanding, "debit", f"{c.nickname} bill", "outstanding you entered")

    # one-off expected payments
    for x in db.query(ExpectedPayment).filter(ExpectedPayment.user_id == user.id).all():
        if today <= x.on_date <= end:
            add(f"expected:{x.id}@{x.on_date}", x.on_date, x.amount, x.direction, x.label, "you added")

    events.sort(key=lambda e: (e["date"], 0 if e["direction"] == "credit" else 1))
    opening = opening_balance(db, user)
    if opening["amount"] is None:
        missing.append("Your current balance — add it so the estimate can show what's left.")
    elif opening["source"] != "you entered" and opening["as_of"] and (today - date.fromisoformat(opening["as_of"])).days > 7:
        assumptions.append(f"Starts from the last balance on your statement ({_nice(opening['as_of'])}); anything paid or received since then isn't included.")

    running = opening["amount"] or 0.0
    lowest = {"amount": running, "date": today.isoformat()}
    tight_days: list[str] = []
    total_in = total_out = 0.0
    for ev in events:
        if ev["excluded"]:
            ev["balance_after"] = round(running, 2)
            continue
        if ev["direction"] == "credit":
            running += ev["amount"]
            total_in += ev["amount"]
        else:
            running -= ev["amount"]
            total_out += ev["amount"]
        ev["balance_after"] = round(running, 2)
        if running < lowest["amount"]:
            lowest = {"amount": round(running, 2), "date": ev["date"]}
        if opening["amount"] is not None and running < LOW_BALANCE_BUFFER and ev["date"] not in tight_days:
            tight_days.append(ev["date"])

    pressure = None
    if opening["amount"] is not None:
        if lowest["amount"] < 0:
            pressure = {"level": "shortfall", "date": lowest["date"],
                        "message": f"On these numbers the balance could go below zero around {_nice(lowest['date'])}."}
        elif lowest["amount"] < LOW_BALANCE_BUFFER:
            pressure = {"level": "tight", "date": lowest["date"],
                        "message": f"The balance could get close to zero around {_nice(lowest['date'])}."}
    assumptions.append("Only confirmed or entered amounts are used; day-to-day spending like food and shopping isn't included.")
    return {
        "currency": "INR", "from": today.isoformat(), "to": end.isoformat(), "days": days,
        "opening_balance": opening, "events": events,
        "totals": {"in": round(total_in, 2), "out": round(total_out, 2), "net": round(total_in - total_out, 2)},
        "closing_balance": round(running, 2) if opening["amount"] is not None else None,
        "lowest": lowest if opening["amount"] is not None else None, "tight_days": tight_days[:10], "pressure": pressure,
        "assumptions": assumptions, "missing": missing,
        "note": "This is an estimate from the data shown, not a guarantee.",
    }
