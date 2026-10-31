"""Minimal profile slices per journey (RD §5 "privacy by purpose", §11.1, §27.3 context isolation).

Each journey receives only the fields it needs. Insurance never receives
transactions; loans never receive family details; and so on.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Emi, FamilyMember, User, UserPolicy
from app.services import profile_engine


def _age(dob: date | None) -> int | None:
    if not dob:
        return None
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def loan_slice(db: Session, user: User) -> dict:
    p = profile_engine.get_profile(db, user)
    inc = (p.get("income_summary") or {}).get("monthly_estimate") or {}
    cf = p.get("cashflow_metrics") or {}
    surplus = (cf.get("monthly_surplus") or {}).get("value")
    emis = db.query(Emi).filter(Emi.user_id == user.id).all()
    return {
        "age": _age(user.dob),
        "employment_type": user.employment_type,
        "monthly_income": inc.get("value"),
        "monthly_income_state": inc.get("state"),
        "monthly_income_source": inc.get("source"),
        "monthly_surplus": surplus,
        "existing_emis": round(sum(e.amount for e in emis), 2),
        "existing_emis_confirmed": all(e.confirmed for e in emis) if emis else True,
    }


def emi_slice(db: Session, user: User) -> dict:
    s = loan_slice(db, user)
    p = profile_engine.get_profile(db, user)
    cf = p.get("cashflow_metrics") or {}
    outflow = (cf.get("avg_monthly_outflow") or {}).get("value")
    s["avg_monthly_non_emi_spend"] = round(outflow - s["existing_emis"], 2) if outflow is not None else None
    return s


def insurance_members(db: Session, user: User, keys: list[str] | None = None) -> list[dict]:
    """Only name/relation/age of selected people — no banking data (RD §27.3)."""
    out = [{"key": "self", "name": user.name.split(" ")[0] if user.name else "You", "relation": "self", "age": _age(user.dob)}]
    for m in db.query(FamilyMember).filter(FamilyMember.user_id == user.id).all():
        out.append({"key": m.id, "name": m.name, "relation": m.relation, "age": _age(m.dob) if m.dob else m.age})
    if keys is not None:
        out = [m for m in out if m["key"] in keys]
    return out


def policies_for(db: Session, user: User) -> list[dict]:
    rows = db.query(UserPolicy).filter(UserPolicy.user_id == user.id, UserPolicy.status != "failed").all()
    return [{
        "id": p.id, "product_name": p.product_name, "insurer": p.insurer, "type": p.type,
        "sum_insured": (p.coverage or {}).get("sum_insured"),
        "member_keys": [m.family_member_id or "self" for m in p.members],
        "end_date": p.end_date.isoformat() if p.end_date else None,
    } for p in rows]
