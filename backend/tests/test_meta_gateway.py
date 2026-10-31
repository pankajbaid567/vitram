"""Meta WhatsApp Cloud API adapter: request shapes, signatures, handshake, parsing, error mapping.

All HTTP is mocked; nothing here talks to Meta.
"""

import hashlib
import hmac

import pytest

from app.config import get_settings
from app.services.channels import gateway, meta_cloud
from app.services.channels.gateway import SendError

SECRET = "app-secret-for-tests"


@pytest.fixture
def meta(monkeypatch):
    s = get_settings()
    for k, v in {"whatsapp_provider": "meta", "whatsapp_token": "EAAG-secret-token-123", "whatsapp_phone_number_id": "1055",
                 "whatsapp_app_secret": SECRET, "whatsapp_verify_token": "handshake-token",
                 "whatsapp_reminder_template": "vitram_reminder", "whatsapp_template_language": "en"}.items():
        monkeypatch.setattr(s, k, v)
    return s


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def capture(monkeypatch, response):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=None):  # noqa: A002
        calls.append({"url": url, "json": json, "headers": headers, "follow_redirects": follow_redirects})
        return response
    monkeypatch.setattr(meta_cloud.httpx, "post", fake_post)
    return calls


OK = FakeResponse(200, {"messages": [{"id": "wamid.ABC"}]})


# --- selection / configuration ------------------------------------------------------

def test_provider_is_selected_by_setting(meta, monkeypatch):
    assert gateway.whatsapp().name == "meta"
    monkeypatch.setattr(meta, "whatsapp_provider", "openwa")
    assert gateway.whatsapp().name == "openwa"
    monkeypatch.setattr(meta, "whatsapp_provider", "carrier-pigeon")
    with pytest.raises(gateway.NotConfigured):
        gateway.whatsapp()


def test_configuration_flags(meta, monkeypatch):
    assert meta.meta_configured and meta.meta_webhook_configured and meta.whatsapp_configured
    monkeypatch.setattr(meta, "whatsapp_reminder_template", None)
    assert not meta.meta_configured and not meta.whatsapp_configured  # can't send reminders without an approved template
    monkeypatch.setattr(meta, "whatsapp_app_secret", None)
    assert not meta.meta_webhook_configured


# --- sending --------------------------------------------------------------------------

def test_reminder_is_a_template_message_with_three_variables(meta, monkeypatch):
    monkeypatch.setattr(meta, "whatsapp_graph_version", "")  # empty setting falls back to the default version
    calls = capture(monkeypatch, OK)
    mid = gateway.whatsapp().send_reminder("+91 98765 43210", "ignored rendered text", ["Bike EMI", "₹4,000", "05 Nov 2026"])
    assert mid == "wamid.ABC"
    c = calls[0]
    assert c["url"] == "https://graph.facebook.com/v21.0/1055/messages"
    assert c["headers"]["Authorization"] == "Bearer EAAG-secret-token-123" and c["follow_redirects"] is False
    body = c["json"]
    assert body["messaging_product"] == "whatsapp" and body["to"] == "919876543210" and body["type"] == "template"
    t = body["template"]
    assert t["name"] == "vitram_reminder" and t["language"] == {"code": "en"}
    assert [p["text"] for p in t["components"][0]["parameters"]] == ["Bike EMI", "₹4,000", "05 Nov 2026"]


def test_template_variables_are_sanitised(meta, monkeypatch):
    calls = capture(monkeypatch, OK)
    gateway.whatsapp().send_reminder("+919876543210", "", ["Line one\nline   two\t&amp;#x20;", "", "d"])
    texts = [p["text"] for p in calls[0]["json"]["template"]["components"][0]["parameters"]]
    assert "\n" not in texts[0] and "  " not in texts[0] and texts[1] == "-"  # empty variables are rejected by Meta


def test_reply_is_free_text(meta, monkeypatch):
    calls = capture(monkeypatch, OK)
    gateway.whatsapp().send_text("+919876543210", "Senior Care may apply.")
    body = calls[0]["json"]
    assert body["type"] == "text" and body["text"] == {"body": "Senior Care may apply.", "preview_url": False}


@pytest.mark.parametrize("status,body,retryable", [
    (429, {"error": {"code": 130429, "message": "Rate limit hit"}}, True),
    (503, {}, True),
    (400, {"error": {"code": 131056, "message": "pair rate limit"}}, True),
    (400, {"error": {"code": 131047, "message": "Re-engagement message: outside the 24 h window"}}, False),
    (401, {"error": {"code": 190, "message": "Invalid OAuth access token"}}, False),
    (400, {"error": {"code": 132000, "message": "Template params mismatch"}}, False),
])
def test_error_mapping(meta, monkeypatch, status, body, retryable):
    capture(monkeypatch, FakeResponse(status, body))
    with pytest.raises(SendError) as exc:
        gateway.whatsapp().send_text("+919876543210", "hi")
    assert exc.value.retryable is retryable
    assert "EAAG-secret-token-123" not in str(exc.value)  # the token never appears in errors


def test_unparseable_or_idless_success_is_final(meta, monkeypatch):
    capture(monkeypatch, FakeResponse(200, ValueError("not json")))
    with pytest.raises(SendError) as exc:
        gateway.whatsapp().send_text("+919876543210", "hi")
    assert exc.value.retryable is False


def test_network_errors_are_retryable_and_bad_numbers_are_not(meta, monkeypatch):
    def boom(*a, **k):
        raise meta_cloud.httpx.ConnectTimeout("x")
    monkeypatch.setattr(meta_cloud.httpx, "post", boom)
    with pytest.raises(SendError) as exc:
        gateway.whatsapp().send_text("+919876543210", "hi")
    assert exc.value.retryable
    with pytest.raises(SendError) as exc2:
        gateway.whatsapp().send_text("123", "hi")
    assert exc2.value.retryable is False


# --- webhook: handshake, signature, parsing ---------------------------------------------

def sign(raw: bytes, secret=SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def test_signature(meta):
    wa = gateway.whatsapp()
    raw = b'{"object":"whatsapp_business_account"}'
    assert wa.verify_signature(raw, sign(raw))
    assert not wa.verify_signature(raw, sign(raw, "other-secret"))
    assert not wa.verify_signature(raw + b" ", sign(raw))  # any byte change breaks it
    assert not wa.verify_signature(raw, None) and not wa.verify_signature(raw, "deadbeef")


def test_subscription_handshake(meta, client):
    ok = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "handshake-token", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403
    assert client.get("/api/webhooks/whatsapp", params={"hub.mode": "unsubscribe", "hub.verify_token": "handshake-token", "hub.challenge": "1"}).status_code == 403


def envelope(*, messages=(), statuses=(), phone_number_id="1055"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"display_phone_number": "x", "phone_number_id": phone_number_id},
        "messages": list(messages), "statuses": list(statuses)}}]}]}


def test_parse_messages_and_statuses(meta):
    wa = gateway.whatsapp()
    payload = envelope(
        messages=[{"from": "919876543210", "id": "wamid.IN1", "type": "text", "text": {"body": "STOP"}},
                  {"from": "919876543210", "id": "wamid.IN2", "type": "button", "button": {"text": "Yes"}},
                  {"from": "919876543210", "id": "wamid.IN3", "type": "interactive", "interactive": {"button_reply": {"title": "Details"}}},
                  {"from": "919876543210", "id": "wamid.IN4", "type": "image"}],
        statuses=[{"id": "wamid.OUT1", "status": "delivered"},
                  {"id": "wamid.OUT2", "status": "failed", "errors": [{"code": 131026, "title": "Message undeliverable"}]}])
    msgs, sts = wa.parse_webhook(payload)
    assert [m["text"] for m in msgs] == ["STOP", "Yes", "Details", ""] and msgs[0]["sender"] == "919876543210"
    assert sts[0] == {"message_id": "wamid.OUT1", "status": "delivered", "error": None}
    assert sts[1]["status"] == "failed" and "131026" in sts[1]["error"]
    assert wa.session_matches(payload)
    assert not wa.session_matches(envelope(phone_number_id="9999"))
    assert not wa.session_matches({"object": "page"})  # not a WhatsApp event
    assert wa.parse_webhook({"object": "page"}) == ([], [])


def test_provider_setting_is_normalised_and_validated():
    from pydantic import ValidationError

    from app.config import Settings
    assert Settings(whatsapp_provider="").whatsapp_provider == "openwa"      # blank line in .env
    assert Settings(whatsapp_provider=" META ").whatsapp_provider == "meta"
    with pytest.raises(ValidationError):
        Settings(whatsapp_provider="metta")
