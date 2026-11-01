"""Inbound WhatsApp: acknowledged means durably queued; replies go through a retrying outbox."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app import resilience
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job
from app.routers import webhooks
from app.services import jobs
from app.services.channels import openwa
from app.services.channels.gateway import SendError
from tests.test_whatsapp_providers import ADAPTERS, post, verified_opted_in_user

OPENWA = next(a for a in ADAPTERS if a.name == "openwa")


@pytest.fixture
def wa(monkeypatch):
    OPENWA.configure(get_settings(), monkeypatch)
    resilience.reset_all()
    db = SessionLocal()
    db.query(Job).delete()
    db.commit()
    db.close()
    sent = []
    OPENWA.sent = sent
    monkeypatch.setattr(openwa, "send_text", lambda to, body: sent.append((to, body)) or "mid")
    yield OPENWA
    resilience.reset_all()


def _jobs(kind=None):
    db = SessionLocal()
    try:
        q = db.query(Job)
        return q.filter(Job.kind == kind).all() if kind else q.all()
    finally:
        db.close()


def _make_runnable():
    db = SessionLocal()
    db.execute(update(Job).where(Job.status == "queued").values(run_after=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()
    db.close()


def test_the_webhook_is_acknowledged_once_the_message_is_durably_queued(client, wa, monkeypatch):
    sender = verified_opted_in_user(client, monkeypatch)
    real_run = jobs.run_available
    monkeypatch.setattr(webhooks.jobs, "run_available", lambda *a, **k: 0)      # no fast path: only the durable record exists
    msg = wa.inbound(sender, "STOP", f"in-{uuid.uuid4().hex[:6]}")
    assert post(client, wa, msg, extra_headers={"x-openwa-idempotency-key": uuid.uuid4().hex}).status_code == 200
    queued = _jobs("whatsapp_inbound")
    assert len(queued) == 1 and queued[0].status == "queued"
    assert "whatsapp_reminders" in client.get("/api/auth/me").json()["consents"]     # not handled yet
    assert wa.sent == []

    assert real_run() >= 2                                                           # inbound job, then the reply it enqueued
    assert "whatsapp_reminders" not in client.get("/api/auth/me").json()["consents"]
    assert len(wa.sent) == 1 and "won't get" in wa.sent[0][1]


def test_a_redelivered_event_creates_one_job(client, wa, monkeypatch):
    sender = verified_opted_in_user(client, monkeypatch)
    monkeypatch.setattr(webhooks.jobs, "run_available", lambda *a, **k: 0)
    msg = wa.inbound(sender, "STOP", f"in-{uuid.uuid4().hex[:6]}")
    headers = {"x-openwa-idempotency-key": uuid.uuid4().hex}
    for _ in range(3):
        assert post(client, wa, msg, extra_headers=headers).status_code == 200
    assert len(_jobs("whatsapp_inbound")) == 1


def test_a_down_gateway_delays_the_reply_but_never_the_acknowledgement_or_the_effect(client, wa, monkeypatch):
    sender = verified_opted_in_user(client, monkeypatch)

    def down(to, body):
        raise SendError("OpenWA HTTP 503", retryable=True)

    monkeypatch.setattr(openwa, "send_text", down)
    msg = wa.inbound(sender, "STOP", f"in-{uuid.uuid4().hex[:6]}")
    assert post(client, wa, msg, extra_headers={"x-openwa-idempotency-key": uuid.uuid4().hex}).status_code == 200
    assert "whatsapp_reminders" not in client.get("/api/auth/me").json()["consents"]   # the effect did not wait for the gateway
    sends = _jobs("whatsapp_send")
    assert len(sends) == 1 and sends[0].status == "queued" and sends[0].attempts == 1 and "503" in sends[0].last_error

    sent = []
    monkeypatch.setattr(openwa, "send_text", lambda to, body: sent.append((to, body)) or "mid")
    _make_runnable()                                                                # back-off elapsed, gateway healthy again
    jobs.run_available()
    assert len(sent) == 1 and _jobs("whatsapp_send")[0].status == "done"
    jobs.run_available()
    assert len(sent) == 1                                                           # exactly once after recovery


def test_a_rejected_destination_is_not_retried_forever(client, wa, monkeypatch):
    sender = verified_opted_in_user(client, monkeypatch)

    def rejected(to, body):
        raise SendError("Invalid WhatsApp destination", retryable=False)

    monkeypatch.setattr(openwa, "send_text", rejected)
    msg = wa.inbound(sender, "STOP", f"in-{uuid.uuid4().hex[:6]}")
    assert post(client, wa, msg, extra_headers={"x-openwa-idempotency-key": uuid.uuid4().hex}).status_code == 200
    assert [j.status for j in _jobs("whatsapp_send")] == ["done"]                   # logged and dropped, not retried
