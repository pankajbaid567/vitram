"""Inbound WhatsApp messages: STOP opt-out and Vitt Saathi replies.

Business rules live here, not in the webhook router: the router only authenticates,
de-duplicates and routes. VITRAM answers only the *verified, opted-in* owner of a
number, never someone who merely appears in the connected account's chat history.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.deps import has_consent
from app.models import Consent, Conversation, Message, Reminder, ReminderPreference, User
from app.security import phone_lookup_hash
from app.services.channels import gateway
from app.services.channels.gateway import InboundMessage

log = logging.getLogger("vitram.inbound")

EMERGENCY = re.compile(r"emergency|hospital|admit|bharti|accident|claim|icu|ilaaj|cashless", re.I)
STOP = re.compile(r"^\s*(stop|unsubscribe|band karo|stop all)\s*$", re.I)
STOP_REPLY = "You won't get VITRAM messages on WhatsApp any more. You can turn them back on in the app."


def _resolve_user(db: Session, sender: str) -> User | None:
    """The single account that owns this number, or None when unknown/ambiguous."""
    if not sender:
        return None
    users = db.query(User).filter(User.phone_lookup == phone_lookup_hash("+" + sender.lstrip("+"))).limit(2).all()
    return users[0] if len(users) == 1 else None


def _opt_out(db: Session, user: User) -> str:
    """STOP: revoke consent, disable WhatsApp, and downgrade queued WhatsApp reminders to in-app."""
    now = datetime.now(timezone.utc)
    for c in db.query(Consent).filter(Consent.user_id == user.id, Consent.purpose == "whatsapp_reminders",
                                      Consent.revoked_at.is_(None)):
        c.revoked_at = now
    pref = db.get(ReminderPreference, user.id)
    if pref:
        pref.whatsapp_enabled = False
    for reminder in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.channel == "whatsapp",
                                              Reminder.status == "scheduled"):
        reminder.channel = "in_app"
    audit(db, user.id, "consent.revoked", "consent", "whatsapp_reminders", via="whatsapp")
    return STOP_REPLY


def _answer(db: Session, user: User, text: str) -> str:
    from app.services.saathi import context as C
    from app.services.saathi import orchestrator

    ctx_type = "emergency" if EMERGENCY.search(text) else "dashboard"
    ctx = C.resolve(db, user, ctx_type, None, None)
    conv = (db.query(Conversation).filter(Conversation.user_id == user.id, Conversation.channel == "whatsapp",
                                          Conversation.context_type == ctx_type)
            .order_by(Conversation.started_at.desc()).first())
    if conv is None:
        conv = Conversation(user_id=user.id, context_type=ctx_type, channel="whatsapp")
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content=text, modality="text"))
    result = orchestrator.tool_mode(db, user, conv, text, ctx)
    route = "/insurance/emergency" if ctx_type == "emergency" else "/"
    for card in result["cards"]:
        if card.get("type") == "navigation":
            route = card["route"]
    reply = f"{result['text']}\n\nDetails in VITRAM: {get_settings().app_origin.rstrip('/')}{route}"
    db.add(Message(conversation_id=conv.id, role="assistant", content=reply, mode="tool", cards=result["cards"],
                   citations=result["citations"], tool_calls=result["tool_calls"]))
    audit(db, user.id, "whatsapp.inbound", "conversation", conv.id, context=ctx_type)
    return reply


def handle_inbound(db: Session, msg: InboundMessage) -> str | None:
    """Route one inbound message. Returns the reply text, or None when we must stay silent."""
    user = _resolve_user(db, msg.get("sender") or "")
    if user is None or not user.phone_verified_at or not has_consent(db, user.id, "whatsapp_reminders"):
        log.info("Ignoring WhatsApp message from an unlinked or opted-out number")
        return None
    text = (msg.get("text") or "").strip()
    return _opt_out(db, user) if STOP.match(text) else _answer(db, user, text)


def reply(to_digits: str, text: str) -> None:
    """Best-effort reply through the gateway; a failure must never lose the webhook."""
    wa = gateway.whatsapp()
    if not wa.configured():
        return
    try:
        wa.send_text("+" + to_digits, text)
    except gateway.SendError as exc:
        log.warning("WhatsApp reply failed: %s", exc)
