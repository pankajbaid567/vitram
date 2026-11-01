"""Inbound WhatsApp messages as durable jobs, with replies sent through a transactional outbox.

The webhook only verifies the signature, records the event (unique key) and enqueues a job, all in **one transaction**, then answers
200 immediately, so the gateway never waits on our database work, the assistant, or its own send API. The job handles the message; any reply
is enqueued as a separate ``whatsapp_send`` job in the same transaction as the handling's database effects, so a reply exists if and only if
the effects were saved. Sending retries with back-off while the gateway is down, behind its circuit breaker.

Delivery is at-least-once: if a send succeeds but its acknowledgement is lost, the reply may go out twice. The inbound dedupe key and the
reply's own dedupe key keep that to the narrow crash window.
"""

import logging

from app.db import SessionLocal
from app.services import jobs
from app.services.channels import gateway, inbound

log = logging.getLogger("vitram.inbox")

INBOUND = "whatsapp_inbound"
SEND = "whatsapp_send"


def enqueue_inbound(db, msg: dict, event_key: str) -> None:
    """Add the job to the caller's transaction (the webhook commits it together with the event record)."""
    jobs.enqueue(db, INBOUND, {"msg": msg, "key": event_key}, dedupe_key=f"wa-in:{event_key}", max_attempts=5)


def _run_inbound(payload: dict) -> None:
    msg, key = payload["msg"], payload["key"]
    db = SessionLocal()
    try:
        reply = inbound.handle_inbound(db, msg)
        if reply:
            jobs.enqueue(db, SEND, {"to": msg["sender"], "body": reply}, dedupe_key=f"wa-reply:{key}", max_attempts=6)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run_send(payload: dict) -> None:
    wa = gateway.whatsapp()
    if not wa.configured():
        return
    try:
        wa.send_text("+" + payload["to"], payload["body"])
    except gateway.SendError as exc:
        if exc.retryable:
            raise                                     # the queue retries with back-off (and the circuit breaker fails fast meanwhile)
        log.warning("WhatsApp reply not sent: %s", exc)   # a rejected destination will not improve on retry


jobs.register(INBOUND, _run_inbound)
jobs.register(SEND, _run_send)
