"""Reminder scheduling and dispatch (RD §14.3, §25).

In-app reminders always work. WhatsApp reminders are sent only after explicit
opt-in and only when OpenWA is configured; otherwise the
reminder is marked `not_configured` and the in-app notification remains.
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app import ratelimit
from app.db import SessionLocal
from app.deps import has_consent
from app.models import Emi, Notification, Reminder, ReminderPreference, User, UserCard, UserPolicy, WorkerHeartbeat
from app.security import decrypt_str
from app.services import obligations
from app.services.channels import gateway
from app.fmt import inr

log = logging.getLogger("vitram.reminders")
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ATTEMPTS = 3
POLICY_LEAD_DAYS = [30, 7]
CLAIM_TTL = timedelta(minutes=5)  # a worker that dies mid-send releases its claim after this long
BATCH_SIZE = 100


def prefs_for(db: Session, user_id: str) -> ReminderPreference:
    p = db.get(ReminderPreference, user_id)
    if p is None:
        p = ReminderPreference(user_id=user_id, days_before=[3], on_due_date=True, send_hour=9, whatsapp_enabled=False,
                               include=["emi", "card", "policy"])
        db.add(p)
        db.flush()
    return p


def whatsapp_block_reason(db: Session, user: User, prefs: ReminderPreference) -> str | None:
    """Why this user can't be messaged on WhatsApp right now, or None when they can.

    Every precondition is re-checked at send time: consent can be withdrawn (including
    by replying STOP) after a reminder was queued.
    """
    if not prefs.whatsapp_enabled:
        return "WhatsApp reminders are turned off."
    if not user.phone_enc:
        return "There is no mobile number on your account."
    if not user.phone_verified_at:
        return "Your mobile number isn't verified yet."
    if not has_consent(db, user.id, "whatsapp_reminders"):
        return "WhatsApp reminders aren't allowed on your account."
    return None


def whatsapp_allowed(db: Session, user: User, prefs: ReminderPreference) -> bool:
    return whatsapp_block_reason(db, user, prefs) is None


def describe_dispatch(r: Reminder, block_reason: str | None) -> str:
    """User-facing, truthful account of what just happened to a reminder.

    Never says "sent on WhatsApp" unless the gateway accepted the message.
    """
    if r.channel == "in_app":
        if block_reason is None:
            return "Sent as an in-app notification."
        return f"Sent as an in-app notification only. {block_reason}"
    if r.status == "not_configured":
        return "WhatsApp isn't connected in this environment, so nothing was sent on WhatsApp. The in-app notification was created."
    if r.status == "failed":
        return f"WhatsApp rejected the message: {r.last_error}. The in-app notification was created."
    if r.status == "scheduled":
        return f"WhatsApp didn't respond ({r.last_error}); VITRAM will retry. The in-app notification was created."
    return "Sent on WhatsApp. Delivery status will update when WhatsApp confirms it."


def reminder_text(item: dict, days_left: int) -> tuple[str, list[str]]:
    """Minimal preview content: obligation name, date, amount (RD §14.3). No account numbers."""
    d = date.fromisoformat(item["date"])
    when = "today" if days_left == 0 else f"on {d:%d %b}"
    amount = f"{inr(item['amount'])}" if item.get("amount") else "the amount due"
    text = f"VITRAM reminder: {item['title']} of {amount} is due {when}."
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
    """Deliver one reminder. Always leaves it in a definite state and releases its claim."""
    try:
        return _dispatch(db, r)
    finally:
        r.claimed_at = None


def _dispatch(db: Session, r: Reminder) -> Reminder:
    item = _item_for(db, r)
    if item is None:
        r.status = "cancelled"
        return r
    days_left = (r.due_date - date.today()).days
    text, params = reminder_text(item, max(days_left, 0))
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
    if user is None or whatsapp_block_reason(db, user, prefs_for(db, r.user_id)):
        r.channel, r.status, r.sent_at = "in_app", "sent", datetime.now(timezone.utc)
        r.last_error = None
        return r
    wa = gateway.whatsapp()
    if not wa.configured():
        r.status = "not_configured"
        r.last_error = "WhatsApp gateway is not configured"
        return r
    r.attempts += 1
    try:
        mid = wa.send_reminder(decrypt_str(user.phone_enc), text, params)
        r.status, r.provider_message_id, r.sent_at, r.last_error = "sent", mid, datetime.now(timezone.utc), None
    except gateway.SendError as exc:
        r.last_error = str(exc)[:300]
        if exc.retryable and r.attempts < MAX_ATTEMPTS:
            r.status = "scheduled"  # back in the queue, after a growing delay
            r.schedule_at = datetime.now(timezone.utc) + timedelta(minutes=5 * r.attempts)
        else:
            r.status = "failed"
    return r


def claim_due(db: Session, now: datetime | None = None, limit: int = BATCH_SIZE) -> list[Reminder]:
    """Atomically claim due reminders so that concurrent workers never send the same one twice.

    Each candidate is claimed with a single conditional ``UPDATE`` whose ``WHERE`` repeats the
    eligibility test; the database serialises competing updates, so exactly one worker sees
    ``rowcount == 1`` per reminder. The claim is committed *before* anything is sent. A claim
    older than ``CLAIM_TTL`` belongs to a crashed worker and may be taken over.
    """
    now = now or datetime.now(timezone.utc)
    stale = now - CLAIM_TTL
    eligible = or_(Reminder.status == "scheduled", (Reminder.status == "sending") & (Reminder.claimed_at < stale))
    ids = [row[0] for row in db.query(Reminder.id).filter(eligible, Reminder.schedule_at <= now)
           .order_by(Reminder.schedule_at).limit(limit)]
    claimed: list[str] = []
    for rid in ids:
        won = db.execute(update(Reminder).where(Reminder.id == rid, eligible)
                         .values(status="sending", claimed_at=now)).rowcount
        if won == 1:
            claimed.append(rid)
    db.commit()
    return [db.get(Reminder, rid) for rid in claimed]


def dispatch_due(db: Session) -> int:
    claimed = claim_due(db)
    for r in claimed:
        try:
            dispatch(db, r)
            db.commit()
        except Exception:  # noqa: BLE001 - one bad reminder must not block the batch
            db.rollback()
            log.exception("reminder %s failed to dispatch", r.id)
            r.status, r.claimed_at = "scheduled", None  # retried on the next tick
            db.commit()
    return len(claimed)


async def reminder_loop(interval: int = 60) -> None:
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception:  # noqa: BLE001
            log.exception("reminder dispatch failed")
        await asyncio.sleep(interval)


def beat(db: Session, name: str = "reminders") -> None:
    """Record that this loop completed a pass (read by `/api/ready` and `app.doctor`)."""
    row = db.get(WorkerHeartbeat, name)
    if row is None:
        db.add(WorkerHeartbeat(name=name, beat_at=datetime.now(timezone.utc)))
    else:
        row.beat_at = datetime.now(timezone.utc)
    db.commit()


def heartbeat_age(db: Session, name: str = "reminders") -> timedelta | None:
    row = db.get(WorkerHeartbeat, name)
    if row is None:
        return None
    at = row.beat_at if row.beat_at.tzinfo else row.beat_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - at


def _tick() -> None:
    db = SessionLocal()
    try:
        dispatch_due(db)
        beat(db)
        ratelimit.purge_expired()
    finally:
        db.close()
