"""Safety regressions for the completion work."""

from datetime import date, datetime, timezone

from app.config import get_settings
from app.db import SessionLocal
from app.models import Emi, Reminder
from app.services.channels import scheduler
from app.services.saathi.orchestrator import fidelity_flags
from tests.conftest import signup


def test_phone_verify_uses_verify_v2_contract_without_exposing_code(monkeypatch):
    from app.services.channels import phone_verify
    settings = get_settings()
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "secret")
    monkeypatch.setattr(settings, "twilio_verify_service_sid", "VAtest")
    requests = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "pending" if len(requests) == 1 else "approved", "valid": True}

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return Reply()

    monkeypatch.setattr(phone_verify.httpx, "post", fake_post)
    assert phone_verify.start("+919123456781")
    assert phone_verify.check("+919123456781", "123456")
    assert requests[0][0].endswith("/Verifications")
    assert requests[0][1]["data"] == {"To": "+919123456781", "Channel": "sms"}
    assert requests[1][0].endswith("/VerificationCheck")
    assert requests[1][1]["data"] == {"To": "+919123456781", "Code": "123456"}


def test_phone_verification_gates_reminders_and_resets_on_change(client, monkeypatch):
    signup(client)
    client.patch("/api/onboarding/about", json={"phone": "9123456782"})
    client.post("/api/consents", json={"purpose": "whatsapp_reminders"})
    client.put("/api/reminders/preferences", json={"days_before": [3], "on_due_date": True,
                                                    "send_hour": 9, "whatsapp_enabled": True})
    emi = client.post("/api/emis", json={"title": "Car EMI", "amount": 1000, "due_day": 10}).json()
    before = client.post("/api/reminders/send-now", json={"object_type": "emi", "object_id": emi["id"]}).json()
    assert before["channel"] == "in_app"

    from app.services.channels import phone_verify
    monkeypatch.setattr(phone_verify, "start", lambda _phone: True)
    monkeypatch.setattr(phone_verify, "check", lambda _phone, _code: True)
    assert client.post("/api/onboarding/phone/verification").json()["status"] == "pending"
    assert client.post("/api/onboarding/phone/verification/check", json={"code": "123456"}).json()["status"] == "verified"
    assert client.get("/api/auth/me").json()["phone_verified"] is True
    client.patch("/api/onboarding/about", json={"phone": "9123456783"})
    assert client.get("/api/auth/me").json()["phone_verified"] is False


def test_queued_whatsapp_cannot_send_after_consent_revoked(client, monkeypatch):
    user_id = signup(client)["id"]
    assert client.patch("/api/onboarding/about", json={"phone": "9123456781"}).status_code == 200
    assert client.post("/api/consents", json={"purpose": "whatsapp_reminders"}).status_code == 200
    db = SessionLocal()
    emi = Emi(user_id=user_id, title="Test EMI", amount=1000, due_day=date.today().day, confirmed=True)
    db.add(emi)
    db.flush()
    queued = Reminder(user_id=user_id, object_type="emi", object_id=emi.id, channel="whatsapp",
                      schedule_at=datetime.now(timezone.utc), due_date=date.today(), template_key="due_today",
                      status="scheduled")
    db.add(queued)
    db.commit()
    queued_id = queued.id
    db.close()

    settings = get_settings()
    monkeypatch.setattr(settings, "openwa_base_url", "http://openwa.test")
    monkeypatch.setattr(settings, "openwa_api_key", "test")
    monkeypatch.setattr(settings, "openwa_session_id", "session-1")
    monkeypatch.setattr(scheduler.openwa, "send_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sent after opt-out")))
    assert client.delete("/api/consents/whatsapp_reminders").status_code == 200

    db = SessionLocal()
    reminder = db.get(Reminder, queued_id)
    assert reminder.channel == "in_app"
    # Also cover a stale queue row left by a concurrent worker or old release.
    reminder.channel = "whatsapp"
    scheduler.dispatch(db, reminder)
    db.commit()
    assert reminder.channel == "in_app" and reminder.status == "sent"
    db.close()


def test_live_tool_rejects_different_conversation_context(sample):
    conv_id = sample.post("/api/ai/chat", json={"message": "show my profile", "context_type": "dashboard"}).json()["conversation_id"]
    r = sample.post("/api/ai/tools/profile_get_slice", json={
        "conversation_id": conv_id, "context_type": "insurance", "args": {},
    })
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONTEXT_MISMATCH"


def test_model_money_claims_match_to_displayed_precision():
    source = [{"monthly_emi": 10746.97}]
    assert fidelity_flags("EMI is ₹10,747", source) == []
    assert fidelity_flags("EMI is ₹10,746", source) == ["unverified_amount:10746"]
    assert fidelity_flags("EMI is ₹10,746.98", source) == ["unverified_amount:10746.98"]
