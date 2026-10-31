"""Insurance consultation calls: honest states, consent, the verified-phone gate, retries and signed callbacks.

Twilio is never contacted: HTTP is mocked and callbacks are signed with the real validator algorithm.
"""

import random

import httpx
import pytest
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.services.channels import phone_verify, twilio_voice
from tests.conftest import signup

TOKEN = "twilio-auth-token-for-tests"
CALLBACK = "https://api.example.com"


@pytest.fixture
def twilio(monkeypatch):
    s = get_settings()
    for k, v in {"twilio_account_sid": "ACtest", "twilio_auth_token": TOKEN, "twilio_from_number": "+15005550006",
                 "consultant_phone_number": "+919800000001", "public_api_url": CALLBACK}.items():
        monkeypatch.setattr(s, k, v)
    return s


class Resp:
    def __init__(self, status=201, body=None, raises=False):
        self.status_code, self._body, self._raises = status, body if body is not None else {}, raises

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._body


def mock_twilio(monkeypatch, response):
    calls = []

    def fake_post(url, data=None, auth=None, timeout=None):
        calls.append({"url": url, "data": data, "auth": auth})
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(twilio_voice.httpx, "post", fake_post)
    return calls


def verified_user(client, monkeypatch):
    signup(client)
    phone = "9" + "".join(random.choice("0123456789") for _ in range(9))
    client.patch("/api/onboarding/about", json={"phone": phone})
    monkeypatch.setattr(phone_verify, "start", lambda _p: True)
    monkeypatch.setattr(phone_verify, "check", lambda _p, _c: True)
    client.post("/api/onboarding/phone/verification")
    client.post("/api/onboarding/phone/verification/check", json={"code": "123456"})
    return phone


BODY = {"topic": "Is my family floater enough for a parent?", "consent": True, "use_phone_on_file": True}


# --- the Twilio request ------------------------------------------------------------------------------

def test_the_outbound_call_is_a_no_recording_bridge_to_the_consultant(twilio, monkeypatch):
    calls = mock_twilio(monkeypatch, Resp(201, {"sid": "CA123", "status": "queued"}))
    out = twilio_voice.create_call("+919876543210", "Hello & welcome <b>", f"{CALLBACK}/api/webhooks/twilio")
    assert out == {"sid": "CA123", "status": "queued"}
    c = calls[0]
    assert c["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Calls.json" and c["auth"] == ("ACtest", TOKEN)
    data = dict(c["data"])
    assert data["To"] == "+919876543210" and data["From"] == "+15005550006"
    assert 'record="do-not-record"' in data["Twiml"] and "+919800000001" in data["Twiml"]
    assert "&amp;" in data["Twiml"] and "<b>" not in data["Twiml"], "the intro is escaped, so user text can't inject TwiML"
    assert {v for k, v in c["data"] if k == "StatusCallbackEvent"} == {"initiated", "ringing", "answered", "completed"}


def test_without_credentials_nothing_is_attempted(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", None)
    with pytest.raises(twilio_voice.NotConfigured):
        twilio_voice.create_call("+919876543210", "hi", None)


@pytest.mark.parametrize("response,expect", [
    (Resp(400, {"code": 21215, "message": "Geo-permissions not enabled"}), "21215: Geo-permissions not enabled"),
    (Resp(500, raises=True), "HTTP 500"),
    (httpx.ConnectTimeout("slow"), "Network error contacting Twilio: ConnectTimeout"),
])
def test_failures_become_readable_errors(twilio, monkeypatch, response, expect):
    mock_twilio(monkeypatch, response)
    with pytest.raises(twilio_voice.CallError, match=expect):
        twilio_voice.create_call("+919876543210", "hi", None)


# --- the request flow ------------------------------------------------------------------------------------

def test_without_twilio_the_request_is_saved_and_says_no_call_was_placed(client):
    signup(client)
    client.patch("/api/onboarding/about", json={"phone": "9" + "".join(random.choice("0123456789") for _ in range(9))})
    out = client.post("/api/consultations", json=BODY).json()
    assert out["status"] == "not_configured" and "no call was placed" in out["status_text"] and out["twilio_call_sid"] is None
    assert "consultation_calls" in client.get("/api/auth/me").json()["consents"], "the consent that was given is recorded"


def test_consent_is_required_and_the_summary_has_no_banking_data(client):
    signup(client)
    assert client.post("/api/consultations", json={**BODY, "consent": False}).status_code == 400
    prev = client.post("/api/consultations/preview", json={"topic": "Review my cover"}).json()["context_summary"]
    assert prev.startswith("Topic: Review my cover") and "salary" not in prev.lower() and "transaction" not in prev.lower()


def test_a_call_needs_a_verified_number_when_calling_is_live(client, twilio, monkeypatch):
    mock_twilio(monkeypatch, Resp(201, {"sid": "CA1", "status": "queued"}))
    signup(client)
    client.patch("/api/onboarding/about", json={"phone": "9" + "".join(random.choice("0123456789") for _ in range(9))})
    r = client.post("/api/consultations", json=BODY)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PHONE_NOT_VERIFIED"


def test_a_verified_user_gets_a_call_and_cannot_dial_a_different_number(client, twilio, monkeypatch):
    calls = mock_twilio(monkeypatch, Resp(201, {"sid": "CAabc", "status": "queued"}))
    verified_user(client, monkeypatch)
    out = client.post("/api/consultations", json=BODY).json()
    assert out["status"] == "calling" and out["twilio_call_sid"] == "CAabc" and len(calls) == 1
    other = client.post("/api/consultations", json={**BODY, "use_phone_on_file": False, "phone": "9123456789"})
    assert other.status_code == 403 and len(calls) == 1, "an unverified destination must never reach Twilio"


def test_a_failed_call_is_saved_with_its_error_and_can_be_retried(client, twilio, monkeypatch):
    mock_twilio(monkeypatch, Resp(400, {"code": 21211, "message": "Invalid 'To' number"}))
    verified_user(client, monkeypatch)
    created = client.post("/api/consultations", json=BODY).json()
    assert created["status"] == "failed" and "21211" in created["error"]
    mock_twilio(monkeypatch, Resp(201, {"sid": "CAretry", "status": "ringing"}))
    again = client.post(f"/api/consultations/{created['id']}/retry").json()
    assert again["status"] == "ringing" and again["error"] is None and again["twilio_call_sid"] == "CAretry"
    assert client.post(f"/api/consultations/{created['id']}/retry").status_code == 400, "no second call while one is ringing"


def test_cancel_and_the_request_list(client, twilio, monkeypatch):
    mock_twilio(monkeypatch, Resp(201, {"sid": "CAx", "status": "queued"}))
    verified_user(client, monkeypatch)
    cid = client.post("/api/consultations", json=BODY).json()["id"]
    assert client.post(f"/api/consultations/{cid}/cancel").json()["status"] == "cancelled"
    listing = client.get("/api/consultations").json()
    assert listing["calling_configured"] is True and [i["id"] for i in listing["items"]] == [cid]
    assert client.get(f"/api/consultations/{cid}").json()["status_text"] == "Cancelled"


# --- signed status callbacks --------------------------------------------------------------------------------

def callback(client, sid, status, token=TOKEN, send_sig=True):
    params = {"CallSid": sid, "CallStatus": status}
    url = f"{CALLBACK}/api/webhooks/twilio"
    headers = {"X-Twilio-Signature": RequestValidator(token).compute_signature(url, params)} if send_sig else {}
    return client.post("/api/webhooks/twilio", data=params, headers=headers)


def test_signed_callbacks_move_the_request_and_replays_are_ignored(client, twilio, monkeypatch):
    mock_twilio(monkeypatch, Resp(201, {"sid": "CAcb1", "status": "queued"}))
    verified_user(client, monkeypatch)
    cid = client.post("/api/consultations", json=BODY).json()["id"]
    for status, expected in (("ringing", "ringing"), ("in-progress", "in_progress"), ("completed", "completed")):
        assert callback(client, "CAcb1", status).status_code == 204
        assert client.get(f"/api/consultations/{cid}").json()["status"] == expected
    assert callback(client, "CAcb1", "ringing").status_code == 204          # an old event, delivered again
    assert client.get(f"/api/consultations/{cid}").json()["status"] == "completed"


def test_unsigned_or_wrongly_signed_callbacks_are_refused(client, twilio):
    assert callback(client, "CAx", "completed", send_sig=False).status_code == 401
    assert callback(client, "CAx", "completed", token="not-the-token").status_code == 401


def test_a_failed_callback_records_why_and_cancelled_requests_stay_cancelled(client, twilio, monkeypatch):
    mock_twilio(monkeypatch, Resp(201, {"sid": "CAcb2", "status": "queued"}))
    verified_user(client, monkeypatch)
    cid = client.post("/api/consultations", json=BODY).json()["id"]
    callback(client, "CAcb2", "no-answer")
    got = client.get(f"/api/consultations/{cid}").json()
    assert got["status"] == "no_answer" and "no-answer" in got["error"]
    client.post(f"/api/consultations/{cid}/cancel")
    callback(client, "CAcb2", "completed")
    assert client.get(f"/api/consultations/{cid}").json()["status"] == "cancelled"
