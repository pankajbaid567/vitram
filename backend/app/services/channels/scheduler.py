"""Reminder scheduling and dispatch (RD §14.3, §25).

In-app reminders always work. WhatsApp reminders are sent only after explicit
opt-in and only when OpenWA is configured; otherwise the
reminder is marked `not_configured` and the in-app notification remains.
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.deps import has_consent
from app.models import Emi, Notification, Reminder, ReminderPreference, User, UserCard, UserPolicy
from app.security import decrypt_str
from app.services import obligations
from app.services.channels import openwa
from app.fmt import inr

log = logging.getLogger("vitram.reminders")
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ATTEMPTS = 3
POLICY_LEAD_DAYS = [30, 7]


def prefs_for(db: Session, user_id: str) -> ReminderPreference:
    p = db.get(ReminderPreference, user_id)
    if p is None:
        p = ReminderPreference(user_id=user_id, days_before=[3], on_due_date=True, send_hour=9, whatsapp_enabled=False,
                               include=["emi", "card", "policy"])
        db.add(p)
        db.flush()
    return p


def whatsapp_allowed(db: Session, user: User, prefs: ReminderPreference) -> bool:
    return bool(prefs.whatsapp_enabled and user.phone_enc and user.phone_verified_at
                and has_consent(db, user.id, "whatsapp_reminders"))


def reminder_text(item: dict, days_left: int) -> tuple[str, list[str]]:
    """Minimal preview content: obligation name, date, amount (RD §14.3). No account numbers."""
    d = date.fromisoformat(item["date"])
    when = "today" if days_left == 0 else f"on {d:%d %b}"
    amount = f"{inr(item['amount'])}" if item.get("amount") else "the amount due"
    text = f"VITTRM reminder: {item['title']} of {amount} is due {when}."
    return text, [item["title"], amount, f"{d:%d %b %Y}"]


def schedule_for_user(db: Session, user: User, horizon_days: int = 35) -> int:
    prefs = prefs_for(db, user.id)
    channel = "whatsapp" if whatsapp_allowed(db, user, prefs) else "in_app"
    today = date.today()
    items = obligations.between(db, user.id, today, today + timedelta(days=horizon_days))
    created = 0
    for item in items:
        if item["kind"] not in prefs.include or not item.get("confirmed", True):
            continue
        if f"{item['kind']}:{item['object_id']}" in (prefs.muted or []):
            continue  # the user switched reminders off for this item
        due = date.fromisoformat(item["date"])
        offsets = POLICY_LEAD_DAYS if item["kind"] == "policy" else list(prefs.days_before)
        if prefs.on_due_date and item["kind"] != "policy":
            offsets = offsets + [0]
        for off in sorted(set(offsets)):
            send_day = due - timedelta(days=off)
            at = datetime.combine(send_day, time(prefs.send_hour), IST).astimezone(timezone.utc)
            if at < datetime.now(timezone.utc) - timedelta(hours=12):
                continue
            key = "due_today" if off == 0 else f"due_in_{off}"
            exists = db.query(Reminder).filter(
                Reminder.user_id == user.id, Reminder.object_type == item["kind"], Reminder.object_id == item["object_id"],
                Reminder.due_date == due, Reminder.template_key == key,
            ).first()
            if exists:
                if exists.status == "scheduled":
                    exists.channel = channel
                continue
            db.add(Reminder(user_id=user.id, object_type=item["kind"], object_id=item["object_id"], channel=channel,
                            schedule_at=at, due_date=due, template_key=key, status="scheduled"))
            created += 1
    db.flush()
    return created


def cancel_for_object(db: Session, user_id: str, object_type: str, object_id: str) -> None:
    for r in db.query(Reminder).filter(Reminder.user_id == user_id, Reminder.object_type == object_type,
                                       Reminder.object_id == object_id, Reminder.status == "scheduled"):
        r.status = "cancelled"


def _item_for(db: Session, r: Reminder) -> dict | None:
    if r.object_type == "emi":
        e = db.get(Emi, r.object_id)
        return e and {"title": e.title, "amount": e.amount, "date": r.due_date.isoformat(), "link": f"/emis/{e.id}"}
    if r.object_type == "card":
        c = db.get(UserCard, r.object_id)
        return c and {"title": f"{c.nickname} bill", "amount": c.outstanding, "date": r.due_date.isoformat(), "link": f"/cards/{c.id}"}
    if r.object_type == "policy":
        p = db.get(UserPolicy, r.object_id)
        return p and {"title": f"{p.product_name or 'Policy'} renewal", "amount": (p.premium or {}).get("amount"),
                      "date": r.due_date.isoformat(), "link": f"/insurance/policies/{p.id}"}
    return None


def dispatch(db: Session, r: Reminder) -> Reminder:
    item = _item_for(db, r)
    if item is None:
        r.status = "cancelled"
        return r
    days_left = (r.due_date - date.today()).days
    text, _ = reminder_text(item, max(days_left, 0))
    # In-app copy is always kept (RD §26: keep in-app reminder on WhatsApp failure).
    dedupe = f"rem:{r.object_type}:{r.object_id}:{r.due_date}:{r.template_key}"
    if not db.query(Notification).filter(Notification.user_id == r.user_id, Notification.dedupe_key == dedupe).first():
        db.add(Notification(user_id=r.user_id, kind="reminder", title=text, link=item["link"], dedupe_key=dedupe))
    if r.channel != "whatsapp":
        r.status, r.sent_at = "sent", datetime.now(timezone.utc)
        return r
    user = db.get(User, r.user_id)
    # A reminder may have been queued before consent was withdrawn (including
    # STOP on WhatsApp). Authorisation must be checked at the point of send.
    if user is None or not whatsapp_allowed(db, user, prefs_for(db, r.user_id)):
        r.channel, r.status, r.sent_at = "in_app", "sent", datetime.now(timezone.utc)
        r.last_error = None
        return r
    s = get_settings()
    if not s.openwa_configured:
        r.status = "not_configured"
        r.last_error = "OpenWA connection is not configured"
        return r
    r.attempts += 1
    try:
        mid = openwa.send_text(decrypt_str(user.phone_enc), text)
        r.status, r.provider_message_id, r.sent_at, r.last_error = "sent", mid, datetime.now(timezone.utc), None
    except openwa.SendError as exc:
        r.last_error = str(exc)[:300]
        if exc.retryable and r.attempts < MAX_ATTEMPTS:
            r.schedule_at = datetime.now(timezone.utc) + timedelta(minutes=5 * r.attempts)
        else:
            r.status = "failed"
    return r


def dispatch_due(db: Session) -> int:
    now = datetime.now(timezone.utc)
    due = db.query(Reminder).filter(Reminder.status == "scheduled", Reminder.schedule_at <= now).limit(100).all()
    for r in due:
        dispatch(db, r)
    db.commit()
    return len(due)


async def reminder_loop(interval: int = 60) -> None:
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception:  # noqa: BLE001
            log.exception("reminder dispatch failed")
        await asyncio.sleep(interval)


def _tick() -> None:
    db = SessionLocal()
    try:
        dispatch_due(db)
    finally:
        db.close()
