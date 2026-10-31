"""Smart calendar data (RD §14.3): EMIs + card dues + premium renewals in a date window."""

import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Emi, UserCard, UserPolicy


def _due_in_month(year: int, month: int, day: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def between(db: Session, user_id: str, start: date, end: date) -> list[dict]:
    items: list[dict] = []
    for e in db.query(Emi).filter(Emi.user_id == user_id).all():
        y, m = start.year, start.month
        while True:
            d = _due_in_month(y, m, e.due_day)
            if d > end:
                break
            if d >= start and (e.first_due_date is None or d >= e.first_due_date):
                items.append({
                    "kind": "emi", "object_id": e.id, "title": e.title, "date": d.isoformat(), "amount": e.amount,
                    "confirmed": e.confirmed, "source_type": e.source_type, "link": f"/emis/{e.id}",
                })
            m += 1
            if m > 12:
                y, m = y + 1, 1
    for c in db.query(UserCard).filter(UserCard.user_id == user_id, UserCard.due_date.isnot(None)).all():
        if start <= c.due_date <= end:
            items.append({
                "kind": "card", "object_id": c.id, "title": f"{c.nickname} bill", "date": c.due_date.isoformat(),
                "amount": c.outstanding, "confirmed": True, "source_type": "manual", "link": f"/cards/{c.id}",
            })
    for p in db.query(UserPolicy).filter(UserPolicy.user_id == user_id, UserPolicy.end_date.isnot(None)).all():
        if start <= p.end_date <= end:
            items.append({
                "kind": "policy", "object_id": p.id, "title": f"{p.product_name or 'Policy'} renewal",
                "date": p.end_date.isoformat(), "amount": (p.premium or {}).get("amount"), "confirmed": p.status == "active",
                "source_type": "document", "link": f"/insurance/policies/{p.id}",
            })
    items.sort(key=lambda i: (i["date"], i["kind"]))
    return items


def upcoming(db: Session, user_id: str, days: int = 30) -> list[dict]:
    today = date.today()
    return between(db, user_id, today, today + timedelta(days=days))
