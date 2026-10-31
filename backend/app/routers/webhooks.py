"""Inbound provider webhooks: WhatsApp gateway events and Twilio call status (RD §17, §26).

This module is the HTTP edge only. It authenticates the provider's signature,
de-duplicates redelivered events, and hands the facts to the service layer
(:mod:`app.services.channels`) where the business rules live.
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.errors import DomainError
from app.models import ConsultationRequest, Reminder
from app.services.channels import delivery, gateway, inbound, twilio_voice
from app.services.channels.idempotency import first_time

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("vitram.webhooks")


@router.post("/openwa")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    wa = gateway.whatsapp()
    if not wa.webhook_configured():
        raise DomainError("INTEGRATION_NOT_CONFIGURED", "OpenWA webhook secret is not configured.", status_code=503)
    raw = await request.body()
    if not wa.verify_signature(raw, request.headers.get("x-openwa-signature")):
        return PlainTextResponse("Invalid signature", status_code=401)
    try:
        payload = await request.json()
    except ValueError:
        return PlainTextResponse("Bad request", status_code=400)
    if not wa.session_matches(payload):
        # A validly signed webhook can still be wired to the wrong VITTRM deployment.
        # Acknowledge and drop it so the gateway does not retry forever.
        log.warning("Ignoring gateway event for a different session")
        return PlainTextResponse("", status_code=204)

    messages, statuses = wa.parse_webhook(payload)
    event_key = request.headers.get("x-openwa-idempotency-key") or payload.get("idempotencyKey")

    for st in statuses:
        key = event_key or (f"{st['message_id']}:{st['status']}" if st.get("message_id") else None)
        if not key or not first_time(db, "openwa_status", key):
            continue
        reminder = db.query(Reminder).filter(Reminder.provider_message_id == st["message_id"]).first()
        if reminder:
            delivery.apply_status(reminder, st["status"], st.get("error"))

    for msg in messages:
        key = event_key or msg.get("id")
        if not key or not first_time(db, "openwa_message", key):
            continue
        # One verified person per number: never answer into a group or an unresolved @lid identity.
        if msg["is_group"] or not msg["sender"]:
            continue
        reply = inbound.handle_inbound(db, msg)
        if reply:
            inbound.reply(msg["sender"], reply)
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
    if sid and status and first_time(db, "twilio", f"{sid}:{status}"):
        call = db.query(ConsultationRequest).filter(ConsultationRequest.twilio_call_sid == sid).first()
        if call and call.status != "cancelled":
            call.status = twilio_voice.TWILIO_TO_STATUS.get(status, call.status)
            if call.status in ("failed", "no_answer"):
                call.error = f"Twilio reported: {status}"
            audit(db, call.user_id, "consultation.status", "consultation", call.id, status=call.status)
    db.commit()
    return PlainTextResponse("", status_code=204)
