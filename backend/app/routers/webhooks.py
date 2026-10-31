"""Inbound webhooks: OpenWA WhatsApp events and Twilio call status (RD §17, §26).

Both are authenticated by provider signatures and processed idempotently.
"""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import has_consent
from app.errors import DomainError
from app.models import Consent, ConsultationRequest, Conversation, Message, Reminder, ReminderPreference, User, WebhookEvent
from app.security import phone_lookup_hash
from app.services.channels import openwa, twilio_voice

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("vitram.webhooks")

EMERGENCY = re.compile(r"emergency|hospital|admit|bharti|accident|claim|icu|ilaaj|cashless", re.I)
STOP = re.compile(r"^\s*(stop|unsubscribe|band karo|stop all)\s*$", re.I)


def _first_time(db: Session, provider: str, external_id: str) -> bool:
    try:
        with db.begin_nested():
            db.add(WebhookEvent(provider=provider, external_id=external_id))
        return True
    except IntegrityError:
        return False


def _reply(to: str, text: str) -> None:
    if not get_settings().openwa_configured:
        return
    try:
        openwa.send_text("+" + to, text)
    except openwa.SendError as exc:
        log.warning("WhatsApp reply failed: %s", exc)


def handle_inbound(db: Session, msg: dict) -> str | None:
    """Route one inbound message. Returns the reply text (also sent when configured)."""
    s = get_settings()
    sender = msg.get("from") or ""
    users = db.query(User).filter(User.phone_lookup == phone_lookup_hash("+" + sender.lstrip("+"))).limit(2).all() if sender else []
    user = users[0] if len(users) == 1 else None
    text = (msg.get("text") or "").strip()
    link = s.app_origin.rstrip("/")
    if user is None or not user.phone_verified_at or not has_consent(db, user.id, "whatsapp_reminders"):
        # Do not contact people merely because the connected WhatsApp account
        # has an unread or historical inbound message from them. VITTRM only
        # replies after the sender has linked and verified this exact number
        # and explicitly enabled WhatsApp messages.
        log.info("Ignoring WhatsApp message from an unlinked or opted-out number")
        return None
    if STOP.match(text):
        now = datetime.now(timezone.utc)
        for c in db.query(Consent).filter(Consent.user_id == user.id, Consent.purpose == "whatsapp_reminders", Consent.revoked_at.is_(None)):
            c.revoked_at = now
        pref = db.get(ReminderPreference, user.id)
        if pref:
            pref.whatsapp_enabled = False
        for reminder in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.channel == "whatsapp",
                                                  Reminder.status == "scheduled"):
            reminder.channel = "in_app"
        audit(db, user.id, "consent.revoked", "consent", "whatsapp_reminders", via="whatsapp")
        return "You won't get VITTRM messages on WhatsApp any more. You can turn them back on in the app."
    from app.services.saathi import context as C
    from app.services.saathi import orchestrator
    ctx_type = "emergency" if EMERGENCY.search(text) else "dashboard"
    ctx = C.resolve(db, user, ctx_type, None, None)
    conv = (db.query(Conversation).filter(Conversation.user_id == user.id, Conversation.channel == "whatsapp",
                                          Conversation.context_type == ctx_type).order_by(Conversation.started_at.desc()).first())
    if conv is None:
        conv = Conversation(user_id=user.id, context_type=ctx_type, channel="whatsapp")
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content=text, modality="text"))
    result = orchestrator.tool_mode(db, user, conv, text, ctx)
    body = result["text"]
    route = "/insurance/emergency" if ctx_type == "emergency" else "/"
    for c in result["cards"]:
        if c.get("type") == "navigation":
            route = c["route"]
    reply = f"{body}\n\nDetails in VITTRM: {link}{route}"
    db.add(Message(conversation_id=conv.id, role="assistant", content=reply, mode="tool", cards=result["cards"],
                   citations=result["citations"], tool_calls=result["tool_calls"]))
    audit(db, user.id, "whatsapp.inbound", "conversation", conv.id, context=ctx_type)
    return reply


@router.post("/openwa")
async def openwa_inbound(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.openwa_webhook_configured:
        raise DomainError("INTEGRATION_NOT_CONFIGURED", "OpenWA webhook secret is not configured.", status_code=503)
    raw = await request.body()
    if not openwa.verify_signature(raw, request.headers.get("x-openwa-signature")):
        return PlainTextResponse("Invalid signature", status_code=401)
    try:
        payload = await request.json()
    except ValueError:
        return PlainTextResponse("Bad request", status_code=400)
    if payload.get("sessionId") != s.openwa_session_id:
        # A validly signed webhook can still be wired to the wrong VITTRM
        # deployment. Acknowledge and drop it so OpenWA does not retry forever.
        log.warning("Ignoring OpenWA event for a different session")
        return PlainTextResponse("", status_code=204)
    messages, statuses = openwa.parse_webhook(payload)
    event_key = request.headers.get("x-openwa-idempotency-key") or payload.get("idempotencyKey")
    for st in statuses:
        key = event_key or (f"{st['id']}:{st.get('status')}" if st.get("id") else None)
        if not key or not _first_time(db, "openwa_status", key):
            continue
        r = db.query(Reminder).filter(Reminder.provider_message_id == st["id"]).first()
        if r and st.get("status") in ("sent", "delivered", "read", "failed"):
            order = ["sent", "delivered", "read"]
            if st["status"] == "failed":
                r.status, r.last_error = "failed", st.get("error")
            elif r.status not in order or order.index(st["status"]) >= order.index(r.status):
                r.status = st["status"]
    for m in messages:
        key = event_key or m.get("id")
        if not key or not _first_time(db, "openwa_message", key):
            continue
        # VITTRM links WhatsApp to one verified person. Never post account
        # details or automated replies into a group conversation.
        if m.get("is_group") or not m.get("from"):
            continue
        reply = handle_inbound(db, m)
        if reply:
            _reply(m["from"], reply)
    db.commit()
    return {"ok": True}


@router.post("/twilio")
async def twilio_status(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.twilio_auth_token:
        raise DomainError("INTEGRATION_NOT_CONFIGURED", "Twilio not configured.", status_code=503)
    form = dict((await request.form()).items())
    url = (s.public_api_url.rstrip("/") + request.url.path) if s.public_api_url else str(request.url)
    if not twilio_voice.validate_signature(url, {k: str(v) for k, v in form.items()}, request.headers.get("x-twilio-signature")):
        return PlainTextResponse("Invalid signature", status_code=401)
    sid, status = form.get("CallSid"), form.get("CallStatus")
    if sid and status and _first_time(db, "twilio", f"{sid}:{status}"):
        c = db.query(ConsultationRequest).filter(ConsultationRequest.twilio_call_sid == sid).first()
        if c and c.status != "cancelled":
            c.status = twilio_voice.TWILIO_TO_STATUS.get(status, c.status)
            if c.status in ("failed", "no_answer"):
                c.error = f"Twilio reported: {status}"
            audit(db, c.user_id, "consultation.status", "consultation", c.id, status=c.status)
    db.commit()
    return PlainTextResponse("", status_code=204)
