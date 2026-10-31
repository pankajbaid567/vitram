"""Reminder delivery: status ladder, concurrent claims, truthful messaging, gateway port."""

import random
from datetime import date, datetime, timedelta, timezone

import pytest

from app.db import SessionLocal
from app.models import Reminder
from app.services.channels import delivery, gateway, openwa, scheduler
from tests.conftest import signup


# --- delivery status ladder (pure) -------------------------------------------------

@pytest.mark.parametrize("current,incoming,expected", [
    ("scheduled", "delivered", "delivered"),   # first receipt can skip "sent"
    ("sent", "delivered", "delivered"),
    ("delivered", "read", "read"),
    ("read", "delivered", "read"),             # late, out-of-order receipt never regresses
    ("read", "sent", "read"),
    ("delivered", "delivered", "delivered"),   # redelivery is a no-op
    ("read", "failed", "failed"),              # failure is terminal and always recorded
    ("sent", "bogus", "sent"),                 # unknown statuses are ignored
    ("sent", None, "sent"),
])
def test_status_ladder(current, incoming, expected):
    assert delivery.next_status(current, incoming) == expected


def test_apply_status_reports_change_and_records_error():
    r = Reminder(status="sent")
    assert delivery.apply_status(r, "delivered") is True
    assert delivery.apply_status(r, "delivered") is False
    assert delivery.apply_status(r, "failed", "number not on WhatsApp") is True
    assert r.status == "failed" and r.last_error == "number not on WhatsApp"


# --- atomic claim: no double sends across workers ---------------------------------------

def _queue(db, user_id, n=3, status="scheduled", claimed_at=None):
    rows = [Reminder(user_id=user_id, object_type="emi", object_id=f"e{i}", channel="in_app",
                     schedule_at=datetime.now(timezone.utc) - timedelta(minutes=1), due_date=date.today(),
                     template_key=f"due_in_{i}", status=status, claimed_at=claimed_at) for i in range(n)]
    db.add_all(rows)
    db.commit()
    return {r.id for r in rows}


def test_two_workers_never_claim_the_same_reminder(client):
    uid = signup(client)["id"]
    a, b = SessionLocal(), SessionLocal()
    try:
        mine = _queue(a, uid, n=5)
        won_a = {r.id for r in scheduler.claim_due(a)} & mine
        won_b = {r.id for r in scheduler.claim_due(b)} & mine
        assert won_a == mine, "the first worker takes everything that was due"
        assert won_b == set(), "the second worker finds nothing left to claim"
        assert all(a.get(Reminder, i).status == "sending" for i in mine)
    finally:
        a.close(); b.close()


def test_a_crashed_workers_claim_expires(client):
    uid = signup(client)["id"]
    db = SessionLocal()
    try:
        long_ago = datetime.now(timezone.utc) - scheduler.CLAIM_TTL - timedelta(minutes=1)
        stale = _queue(db, uid, n=1, status="sending", claimed_at=long_ago)
        fresh = _queue(db, uid, n=1, status="sending", claimed_at=datetime.now(timezone.utc))
        got = {r.id for r in scheduler.claim_due(db)}
        assert stale <= got and not (fresh & got)
    finally:
        db.close()


def test_dispatch_releases_the_claim_and_requeues_retryable_failures(client, monkeypatch):
    uid = signup(client)["id"]
    db = SessionLocal()
    try:
        monkeypatch.setattr(scheduler, "_item_for", lambda *_: {"title": "Loan EMI", "amount": 1000, "date": date.today().isoformat(), "link": "/emis"})
        r = Reminder(user_id=uid, object_type="emi", object_id="x", channel="whatsapp", status="sending",
                     claimed_at=datetime.now(timezone.utc), schedule_at=datetime.now(timezone.utc),
                     due_date=date.today(), template_key="due_today")
        db.add(r)
        db.commit()

        class Down:
            def configured(self): return True
            def send_text(self, *_): raise gateway.SendError("engine down", retryable=True)

        monkeypatch.setattr(scheduler, "whatsapp_block_reason", lambda *a: None)
        monkeypatch.setattr(scheduler, "decrypt_str", lambda _: "+919999999999")
        monkeypatch.setattr(scheduler.gateway, "whatsapp", lambda: Down())
        scheduler.dispatch(db, r)
        assert r.status == "scheduled" and r.claimed_at is None and r.attempts == 1
        assert r.schedule_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    finally:
        db.close()


# --- truthful messages (regression: "Sent on WhatsApp" when nothing was sent) ---------------

def _sample_with_phone(client_factory):
    c = client_factory()
    c.post("/api/demo/workspace")
    phone = "9" + "".join(random.choice("0123456789") for _ in range(9))
    assert c.patch("/api/onboarding/about", json={"phone": phone}).status_code == 200
    assert c.post("/api/consents", json={"purpose": "whatsapp_reminders"}).status_code == 200
    prefs = {"days_before": [3], "on_due_date": True, "send_hour": 9, "whatsapp_enabled": True, "include": ["emi", "card", "policy"]}
    assert c.put("/api/reminders/preferences", json=prefs).status_code == 200
    return c, c.get("/api/emis").json()["emis"][0]["id"]


def test_send_now_never_claims_whatsapp_when_phone_is_unverified(client_factory):
    c, emi = _sample_with_phone(client_factory)
    out = c.post("/api/reminders/send-now", json={"object_type": "emi", "object_id": emi}).json()
    assert out["channel"] == "in_app"
    assert "Sent on WhatsApp" not in out["explanation"]
    assert "isn't verified" in out["explanation"]


@pytest.mark.parametrize("status,error,expected", [
    ("sent", None, "Sent on WhatsApp"),
    ("failed", "blocked", "rejected"),
    ("scheduled", "timeout", "will retry"),
    ("not_configured", None, "isn't connected"),
])
def test_describe_dispatch_whatsapp_outcomes(status, error, expected):
    r = Reminder(channel="whatsapp", status=status, last_error=error)
    assert expected in scheduler.describe_dispatch(r, None)


def test_describe_dispatch_in_app_names_the_reason():
    r = Reminder(channel="in_app", status="sent")
    assert "turned off" in scheduler.describe_dispatch(r, "WhatsApp reminders are turned off.")
    assert "WhatsApp" not in scheduler.describe_dispatch(r, None).replace("in-app", "")


# --- gateway port ----------------------------------------------------------------

def test_openwa_is_the_default_gateway_and_satisfies_the_port():
    wa = gateway.whatsapp()
    assert isinstance(wa, openwa.OpenWAGateway) and wa.name == "openwa"
    for member in ("configured", "webhook_configured", "send_text", "verify_signature", "session_matches", "parse_webhook"):
        assert callable(getattr(wa, member))
