"""Financial goals (M13): targets and hand-recorded contributions. No money moves, no returns are assumed."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import Goal, GoalContribution, User
from app.services import profile_engine

router = APIRouter(prefix="/goals", tags=["goals"])


def progress(goal: Goal, saved: float, today: date | None = None) -> dict:
    """Deterministic progress maths. `monthly_needed` spreads what's left evenly over the months to the target date."""
    today = today or date.today()
    remaining = max(round(goal.target_amount - saved, 2), 0.0)
    months_left = None
    monthly_needed = None
    if goal.target_date:
        months_left = max((goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month, 0)
        if remaining > 0:
            monthly_needed = round(remaining / months_left, 2) if months_left > 0 else remaining
    return {"saved": round(saved, 2), "remaining": remaining,
            "pct": min(round(saved / goal.target_amount * 100, 1), 100.0) if goal.target_amount else 0.0,
            "months_left": months_left, "monthly_needed": monthly_needed, "reached": saved >= goal.target_amount}


def goal_out(db: Session, g: Goal, rows: list[GoalContribution] | None = None) -> dict:
    """``rows`` (newest first) may be supplied by the list endpoint, which loads every goal's contributions in one query."""
    if rows is None:
        rows = db.query(GoalContribution).filter(GoalContribution.goal_id == g.id).order_by(GoalContribution.on_date.desc()).all()
    saved = sum(r.amount for r in rows)
    return {"id": g.id, "name": g.name, "target_amount": g.target_amount, "target_date": g.target_date.isoformat() if g.target_date else None,
            "status": g.status, "created_at": g.created_at.isoformat(), **progress(g, saved),
            "contributions": [{"id": r.id, "amount": r.amount, "on_date": r.on_date.isoformat(), "note": r.note} for r in rows[:50]]}


def _get(db: Session, user: User, goal_id: str) -> Goal:
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not g:
        raise NotFound("Goal")
    return g


@router.get("")
def list_goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.status != "archived").order_by(Goal.created_at).all()
    profile = profile_engine.get_profile(db, user)
    surplus = ((profile.get("cashflow_metrics") or {}).get("monthly_surplus") or {})
    by_goal: dict[str, list[GoalContribution]] = {g.id: [] for g in goals}
    if goals:
        for c in (db.query(GoalContribution).filter(GoalContribution.goal_id.in_(by_goal)).order_by(GoalContribution.on_date.desc())):
            by_goal[c.goal_id].append(c)
    return {"currency": "INR", "goals": [goal_out(db, g, by_goal[g.id]) for g in goals],
            # an estimate from the statement, shown next to "monthly needed" so the user can judge it themselves
            "monthly_surplus": {"value": surplus.get("value"), "state": surplus.get("state")},
            "note": "Progress counts only the contributions you record. VITRAM doesn't move money or assume any returns."}


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, le=1_000_000_000)
    target_date: date | None = None


@router.post("")
def create_goal(body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.target_date and body.target_date <= date.today():
        raise DomainError("DATE_IN_PAST", "Choose a target date in the future, or leave it empty.", field="target_date")
    g = Goal(user_id=user.id, name=body.name.strip(), target_amount=round(body.target_amount, 2), target_date=body.target_date)
    db.add(g)
    audit(db, user.id, "goal.created", "goal", g.id)
    db.commit()
    return goal_out(db, g)


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_amount: float | None = Field(default=None, gt=0, le=1_000_000_000)
    target_date: date | None = None
    clear_target_date: bool = False
    status: str | None = Field(default=None, pattern="^(active|achieved|archived)$")


@router.patch("/{goal_id}")
def update_goal(goal_id: str, body: GoalPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _get(db, user, goal_id)
    if body.name is not None:
        g.name = body.name.strip()
    if body.target_amount is not None:
        g.target_amount = round(body.target_amount, 2)
    if body.clear_target_date:
        g.target_date = None
    elif body.target_date is not None:
        g.target_date = body.target_date
    if body.status is not None:
        g.status = body.status
    db.commit()
    return goal_out(db, g)


@router.delete("/{goal_id}")
def delete_goal(goal_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _get(db, user, goal_id)
    db.query(GoalContribution).filter(GoalContribution.goal_id == g.id).delete()
    db.delete(g)
    audit(db, user.id, "goal.deleted", "goal", goal_id)
    db.commit()
    return {"ok": True}


class ContributionIn(BaseModel):
    amount: float = Field(ge=-1_000_000_000, le=1_000_000_000)
    on_date: date | None = None
    note: str | None = Field(default=None, max_length=120)


@router.post("/{goal_id}/contributions")
def add_contribution(goal_id: str, body: ContributionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _get(db, user, goal_id)
    if body.amount == 0:
        raise DomainError("AMOUNT_REQUIRED", "Enter an amount (use a minus sign for a withdrawal).", field="amount")
    on = body.on_date or date.today()
    if on > date.today():
        raise DomainError("DATE_IN_FUTURE", "Record contributions on or before today.", field="on_date")
    db.add(GoalContribution(goal_id=g.id, user_id=user.id, amount=round(body.amount, 2), on_date=on, note=(body.note or None)))
    db.commit()
    return goal_out(db, g)


@router.delete("/{goal_id}/contributions/{cid}")
def delete_contribution(goal_id: str, cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _get(db, user, goal_id)
    c = db.query(GoalContribution).filter(GoalContribution.id == cid, GoalContribution.goal_id == g.id).first()
    if not c:
        raise NotFound("Contribution")
    db.delete(c)
    db.commit()
    return goal_out(db, g)
