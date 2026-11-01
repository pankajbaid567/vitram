"""Family layer (RD §6.2, S03, S51)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.concurrency import require_match
from app.errors import DomainError, NotFound
from app.models import FamilyMember, PolicyMember, User, UserPolicy
from app.services import profile_engine

router = APIRouter(prefix="/family", tags=["family"])

Relation = Literal["spouse", "child", "father", "mother", "father_in_law", "mother_in_law", "sibling", "other_dependant"]


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    relation: Relation
    dob: date | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    is_dependant: bool = False


def _age(m: FamilyMember) -> int | None:
    if m.dob:
        t = date.today()
        return t.year - m.dob.year - ((t.month, t.day) < (m.dob.month, m.dob.day))
    return m.age


def member_out(m: FamilyMember, db: Session, policies: list[UserPolicy] | None = None) -> dict:
    """``policies`` may be supplied by a list endpoint that already loaded everyone's policies in one query (no N+1)."""
    if policies is None:
        policies = (
            db.query(UserPolicy)
            .join(PolicyMember, PolicyMember.policy_id == UserPolicy.id)
            .filter(PolicyMember.family_member_id == m.id)
            .all()
        )
    return {
        "id": m.id, "name": m.name, "relation": m.relation, "dob": m.dob.isoformat() if m.dob else None,
        "age": _age(m), "is_dependant": m.is_dependant, "version": m.version,
        "policies": [{"id": p.id, "insurer": p.insurer, "product_name": p.product_name, "type": p.type} for p in policies],
    }


@router.get("")
def list_members(user: User = Depends(current_user), db: Session = Depends(get_db)):
    self_policies = (
        db.query(UserPolicy).join(PolicyMember, PolicyMember.policy_id == UserPolicy.id)
        .filter(UserPolicy.user_id == user.id, PolicyMember.family_member_id.is_(None)).all()
    )
    members = db.query(FamilyMember).filter(FamilyMember.user_id == user.id).order_by(FamilyMember.created_at).all()
    by_member: dict[str, list[UserPolicy]] = {m.id: [] for m in members}
    for member_id, policy in (db.query(PolicyMember.family_member_id, UserPolicy)
                              .join(UserPolicy, PolicyMember.policy_id == UserPolicy.id)
                              .filter(UserPolicy.user_id == user.id, PolicyMember.family_member_id.isnot(None))):
        by_member.setdefault(member_id, []).append(policy)
    return {
        "self": {"id": "self", "name": user.name, "relation": "self",
                 "policies": [{"id": p.id, "insurer": p.insurer, "product_name": p.product_name, "type": p.type} for p in self_policies]},
        "members": [member_out(m, db, by_member[m.id]) for m in members],
    }


def _get(db: Session, user: User, member_id: str) -> FamilyMember:
    m = db.query(FamilyMember).filter(FamilyMember.id == member_id, FamilyMember.user_id == user.id).first()
    if not m:
        raise NotFound("Family member")
    return m


@router.post("")
def add_member(body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.query(FamilyMember).filter(FamilyMember.user_id == user.id).count() >= 15:
        raise DomainError("LIMIT", "You can add up to 15 family members.")
    m = FamilyMember(user_id=user.id, **body.model_dump())
    db.add(m)
    db.flush()
    audit(db, user.id, "family.added", "family_member", m.id)
    profile_engine.build_profile(db, user)
    db.commit()
    return member_out(m, db)


@router.patch("/{member_id}")
def update_member(member_id: str, body: MemberIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _get(db, user, member_id)
    require_match(request, m.version)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    profile_engine.build_profile(db, user)
    db.commit()
    return member_out(m, db)


@router.delete("/{member_id}")
def delete_member(member_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _get(db, user, member_id)
    db.query(PolicyMember).filter(PolicyMember.family_member_id == m.id).delete()
    db.delete(m)
    audit(db, user.id, "family.deleted", "family_member", member_id)
    profile_engine.build_profile(db, user)
    db.commit()
    return {"ok": True}
