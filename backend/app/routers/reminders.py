"""Reminder settings and history (RD §14.3, §25, S33)."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import current_user, has_consent
from app.errors import DomainError, NotFound
from app.models import Emi, Reminder, User, UserCard, UserPolicy
from app.services import obligations
from app.services.channels import scheduler

router = APIRouter(prefix="/reminders", tags=["reminders"])

STATUS_TEXT = {
    "scheduled": "Scheduled", "sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed",
    "not_configured": "Not sent — WhatsApp isn't connected", "cancelled": "Cancelled",
}


def reminder_out(r: Reminder) -> dict:
    return {
        "id": r.id, "object_type": r.object_type, "object_id": r.object_id, "channel": r.channel,
        "schedule_at": r.schedule_at.isoformat(), "due_date": r.due_date.isoformat(), "template_key": r.template_key,
        "status": r.status, "status_text": STATUS_TEXT.get(r.status, r.status), "attempts": r.attempts,
        "last_error": r.last_error, "sent_at": r.sent_at.isoformat() if r.sent_at else None,
    }


def _prefs_out(db: Session, user: User) -> dict:
    p = scheduler.prefs_for(db, user.id)
    s = get_settings()
    return {
        "days_before": p.days_before, "on_due_date": p.on_due_date, "send_hour": p.send_hour,
        "whatsapp_enabled": p.whatsapp_enabled, "include": p.include,
        "phone_masked": user.phone_masked, "phone_verified": bool(user.phone_verified_at),
        "whatsapp_consent": bool(has_consent(db, user.id, "whatsapp_reminders")),
        "whatsapp_configured": s.openwa_configured,
        "policy_lead_days": scheduler.POLICY_LEAD_DAYS,
    }


@router.get("")
def list_reminders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    scheduler.schedule_for_user(db, user)
    db.commit()
    rows = db.query(Reminder).filter(Reminder.user_id == user.id).order_by(Reminder.schedule_at.desc()).limit(100).all()
    upcoming = sorted([r for r in rows if r.status == "scheduled"], key=lambda r: r.schedule_at)
    history = [r for r in rows if r.status != "scheduled"]
    prefs = scheduler.prefs_for(db, user.id)
    muted = set(prefs.muted or [])
    today = date.today()
    items, seen = [], set()
    for it in obligations.between(db, user.id, today, today + timedelta(days=60)):
        k = f"{it['kind']}:{it['object_id']}"
        if k in seen:
            continue
        seen.add(k)
        items.append({"key": k, "kind": it["kind"], "object_id": it["object_id"], "title": it.get("title"), "next_date": it["date"],
                      "confirmed": it.get("confirmed", True), "muted": k in muted, "included": it["kind"] in prefs.include})
    return {"preferences": _prefs_out(db, user), "upcoming": [reminder_out(r) for r in upcoming],
            "history": [reminder_out(r) for r in history], "items": items}


class MuteIn(BaseModel):
    muted: bool


@router.put("/items/{kind}/{object_id}")
def set_item_muted(kind: Literal["emi", "card", "policy"], object_id: str, body: MuteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Switch reminders off (or back on) for one EMI, card or policy."""
    model = {"emi": Emi, "card": UserCard, "policy": UserPolicy}[kind]
    if not db.query(model).filter(model.id == object_id, model.user_id == user.id).first():
        raise NotFound("Item")
    p = scheduler.prefs_for(db, user.id)
    key = f"{kind}:{object_id}"
    muted = [m for m in (p.muted or []) if m != key] + ([key] if body.muted else [])
    p.muted = muted
    if body.muted:
        scheduler.cancel_for_object(db, user.id, kind, object_id)
    else:
        for r in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.object_type == kind, Reminder.object_id == object_id,
                                           Reminder.status == "cancelled", Reminder.schedule_at > datetime.now(timezone.utc)):
            db.delete(r)
        db.flush()
        scheduler.schedule_for_user(db, user)
    audit(db, user.id, "reminders.item_muted" if body.muted else "reminders.item_unmuted", kind, object_id)
    db.commit()
    return {"ok": True, "key": key, "muted": body.muted}


@router.delete("/{reminder_id}")
def cancel_one(reminder_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cancel a single upcoming reminder. It stays cancelled; other dates for the same item are unaffected."""
    r = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == user.id).first()
    if not r:
        raise NotFound("Reminder")
    if r.status == "scheduled":
        r.status = "cancelled"
    audit(db, user.id, "reminders.cancelled", "reminder", r.id)
    db.commit()
    return reminder_out(r)


class PrefsIn(BaseModel):
    days_before: list[int] = Field(min_length=0, max_length=4)
    on_due_date: bool = True
    send_hour: int = Field(ge=6, le=21)
    whatsapp_enabled: bool = False
    include: list[Literal["emi", "card", "policy"]] = Field(default_factory=lambda: ["emi", "card", "policy"])


@router.put("/preferences")
def update_prefs(body: PrefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if any(d < 1 or d > 15 for d in body.days_before):
        raise DomainError("INVALID_DAYS", "Choose between 1 and 15 days before the due date.", field="days_before")
    if body.whatsapp_enabled:
        if not user.phone_enc:
            raise DomainError("PHONE_REQUIRED", "Add your mobile number to get WhatsApp reminders.", field="phone")
        if not has_consent(db, user.id, "whatsapp_reminders"):
            raise DomainError("CONSENT_REQUIRED", "Allow WhatsApp reminders first.", field="whatsapp_reminders", status_code=403)
    p = scheduler.prefs_for(db, user.id)
    p.days_before, p.on_due_date, p.send_hour = sorted(set(body.days_before)), body.on_due_date, body.send_hour
    p.whatsapp_enabled, p.include = body.whatsapp_enabled, body.include
    # Re-plan future reminders with the new cadence/channel.
    for r in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.status == "scheduled"):
        db.delete(r)
    db.flush()
    scheduler.schedule_for_user(db, user)
    audit(db, user.id, "reminders.preferences_updated")
    db.commit()
    return _prefs_out(db, user)


class SendNowIn(BaseModel):
    object_type: Literal["emi", "card", "policy"]
    object_id: str


@router.post("/send-now")
def send_now(body: SendNowIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Send one reminder immediately (demo of the reminder flow, RD §30 step 40)."""
    model = {"emi": Emi, "card": UserCard, "policy": UserPolicy}[body.object_type]
    obj = db.query(model).filter(model.id == body.object_id, model.user_id == user.id).first()
    if not obj:
        raise NotFound("Item")
    if body.object_type == "emi":
        from app.routers.emis import next_due
        due = next_due(obj)
    elif body.object_type == "card":
        due = obj.due_date or date.today()
    else:
        due = obj.end_date or date.today()
    prefs = scheduler.prefs_for(db, user.id)
    block_reason = scheduler.whatsapp_block_reason(db, user, prefs)
    channel = "in_app" if block_reason else "whatsapp"
    r = Reminder(user_id=user.id, object_type=body.object_type, object_id=body.object_id, channel=channel,
                 schedule_at=datetime.now(timezone.utc), due_date=due, template_key=f"manual_{datetime.now(timezone.utc):%H%M%S}")
    db.add(r)
    db.flush()
    scheduler.dispatch(db, r)
    audit(db, user.id, "reminder.sent_now", body.object_type, body.object_id, channel=channel, status=r.status)
    db.commit()
    return {**reminder_out(r), "explanation": scheduler.describe_dispatch(r, block_reason)}
