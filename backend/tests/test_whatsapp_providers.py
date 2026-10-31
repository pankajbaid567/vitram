"""One behavioural contract, two providers: the same webhook scenarios must hold for OpenWA and Meta."""

import hashlib
import hmac
import json
import random
import uuid
from datetime import date, datetime, timezone

import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.models import Reminder
from app.services.channels import meta_cloud, openwa, phone_verify
from tests.conftest import signup

OPENWA_SECRET = "openwa-secret-0123456789"
META_SECRET = "meta-app-secret"


class Adapter:
    """How to talk to one provider's webhook, so the scenarios below stay provider-neutral."""

    def __init__(self, name, path, module, secret):
        self.name, self.path, self.module, self.secret = name, path, module, secret

    def configure(self, s, monkeypatch):
        if self.name == "openwa":
            for k, v in {"whatsapp_provider": "openwa", "openwa_base_url": "http://openwa.test", "openwa_api_key": "k",
                         "openwa_session_id": "session-1", "openwa_webhook_secret": OPENWA_SECRET}.items():
                monkeypatch.setattr(s, k, v)
        else:
            for k, v in {"whatsapp_provider": "meta", "whatsapp_token": "t", "whatsapp_phone_number_id": "1055",
                         "whatsapp_app_secret": META_SECRET, "whatsapp_verify_token": "v",
                         "whatsapp_reminder_template": "tmpl"}.items():
                monkeypatch.setattr(s, k, v)

    def sign(self, raw: bytes, secret=None) -> dict:
        key = (secret or self.secret).encode()
        digest = "sha256=" + hmac.new(key, raw, hashlib.sha256).hexdigest()
        return {"x-openwa-signature" if self.name == "openwa" else "x-hub-signature-256": digest, "content-type": "application/json"}

    def inbound(self, sender: str, text: str, msg_id: str) -> dict:
        if self.name == "openwa":
            return {"event": "message.received", "sessionId": "session-1",
                    "data": {"id": msg_id, "senderPhone": sender, "body": text, "type": "chat", "isGroup": False}}
        return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "1055"}, "messages": [{"from": sender, "id": msg_id, "type": "text", "text": {"body": text}}]}}]}]}

    def status(self, provider_id: str, status: str) -> dict:
        if self.name == "openwa":
            return {"event": "message.ack", "sessionId": "session-1", "data": {"messageId": provider_id, "status": status}}
        return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "1055"}, "statuses": [{"id": provider_id, "status": status}]}}]}]}


ADAPTERS = [Adapter("openwa", "/api/webhooks/whatsapp", openwa, OPENWA_SECRET), Adapter("meta", "/api/webhooks/whatsapp", meta_cloud, META_SECRET)]


@pytest.fixture(params=ADAPTERS, ids=lambda a: a.name)
def wa(request, monkeypatch):
    a = request.param
    a.configure(get_settings(), monkeypatch)
    sent = []
    monkeypatch.setattr(a.module, "send_text", lambda to, body: sent.append((to, body)) or "mid")
    a.sent = sent
    return a


def post(client, a: Adapter, payload: dict, secret=None, extra_headers=None):
    raw = json.dumps(payload).encode()
    headers = {**a.sign(raw, secret), **(extra_headers or {})}
    return client.post(a.path, content=raw, headers=headers)


def verified_opted_in_user(client, monkeypatch):
    signup(client)
    phone = "9" + "".join(random.choice("0123456789") for _ in range(9))
    client.patch("/api/onboarding/about", json={"phone": phone})
    monkeypatch.setattr(phone_verify, "start", lambda _p: True)
    monkeypatch.setattr(phone_verify, "check", lambda _p, _c: True)
    client.post("/api/onboarding/phone/verification")
    client.post("/api/onboarding/phone/verification/check", json={"code": "123456"})
    client.post("/api/consents", json={"purpose": "whatsapp_reminders"})
    return "91" + phone


def test_signature_is_required_and_checked_over_the_raw_bytes(client, wa):
    body = wa.inbound("919000000001", "hi", "m-sig")
    assert post(client, wa, body, secret="wrong-secret-wrong-secret").status_code == 401
    assert client.post(wa.path, content=json.dumps(body).encode(), headers={"content-type": "application/json"}).status_code == 401
    assert post(client, wa, body).status_code == 200


def test_webhook_for_another_number_or_session_is_dropped(client, wa):
    other = wa.inbound("919000000001", "hi", "m-other")
    if wa.name == "openwa":
        other["sessionId"] = "someone-elses"
    else:
        other["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "9999"
    assert post(client, wa, other).status_code == 204


def test_stop_revokes_consent_once_and_a_replay_is_ignored(client, wa, monkeypatch):
    sender = verified_opted_in_user(client, monkeypatch)
    msg = wa.inbound(sender, "STOP", f"in-{uuid.uuid4().hex[:6]}")
    headers = {"x-openwa-idempotency-key": f"k-{uuid.uuid4().hex[:6]}"} if wa.name == "openwa" else None
    assert post(client, wa, msg, extra_headers=headers).status_code == 200
    assert len(wa.sent) == 1 and "won't get" in wa.sent[0][1]
    assert "whatsapp_reminders" not in client.get("/api/auth/me").json()["consents"]
    assert post(client, wa, msg, extra_headers=headers).status_code == 200   # provider redelivers the same event
    assert len(wa.sent) == 1, "a replayed webhook must not be processed twice"


def test_unknown_sender_gets_no_reply(client, wa):
    assert post(client, wa, wa.inbound("919111111111", "hello", f"in-{uuid.uuid4().hex[:6]}")).status_code == 200
    assert wa.sent == []


def test_delivery_receipts_only_move_forward(client, wa):
    uid = signup(client)["id"]
    pid = f"prov-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        r = Reminder(user_id=uid, object_type="emi", object_id="x", channel="whatsapp", status="sent", provider_message_id=pid,
                     schedule_at=datetime.now(timezone.utc), due_date=date.today(), template_key="due_today")
        db.add(r)
        db.commit()
        rid = r.id
    finally:
        db.close()

    def current():
        d = SessionLocal()
        try:
            return d.get(Reminder, rid).status
        finally:
            d.close()

    keys = lambda: ({"x-openwa-idempotency-key": uuid.uuid4().hex} if wa.name == "openwa" else None)  # noqa: E731
    for incoming, expected in [("delivered", "delivered"), ("read", "read"), ("delivered", "read"), ("failed", "failed")]:
        post(client, wa, wa.status(pid, incoming), extra_headers=keys())
        assert current() == expected, (incoming, expected)
