"""OpenWA WhatsApp gateway adapter.

VITTRM talks only to the self-hosted OpenWA REST API. Outbound messages use
the configured session's send-text endpoint; inbound messages and delivery
receipts arrive through OpenWA's signed webhook envelope.
"""

import hashlib
import hmac
import html
import re
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.services.channels.gateway import InboundMessage, NotConfigured, SendError, StatusUpdate

__all__ = ["NotConfigured", "SendError", "OpenWAGateway", "send_text", "verify_signature", "parse_webhook"]


def _settings() -> tuple[str, str, str]:
    s = get_settings()
    if not s.openwa_configured:
        raise NotConfigured("OpenWA base URL, API key and session ID are not configured")
    return s.openwa_base_url.rstrip("/"), s.openwa_api_key, s.openwa_session_id


def _chat_id(to_e164: str) -> str:
    digits = re.sub(r"\D", "", to_e164)
    if not 8 <= len(digits) <= 15:
        raise SendError("Invalid WhatsApp destination", retryable=False)
    return f"{digits}@c.us"


def send_text(to_e164: str, body: str) -> str:
    base, api_key, session_id = _settings()
    endpoint = f"{base}/api/sessions/{quote(session_id, safe='')}/messages/send-text"
    # Tool output and imported document text can contain HTML character
    # references. WhatsApp is plain text, so decode them before sending rather
    # than exposing strings such as ``&#x20;`` to the recipient.
    text = html.unescape(html.unescape(body)).replace("\x00", "").strip()
    try:
        response = httpx.post(
            endpoint,
            json={"chatId": _chat_id(to_e164), "text": text[:4096], "linkPreview": False},
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=get_settings().openwa_timeout_seconds,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"Network error contacting OpenWA: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        try:
            data = response.json()
            detail = data.get("message") or data.get("error") or "request failed"
            if isinstance(detail, list):
                detail = "; ".join(str(x) for x in detail)
        except ValueError:
            detail = "request failed"
        retryable = response.status_code in (408, 409, 425, 429) or response.status_code >= 500
        raise SendError(f"OpenWA HTTP {response.status_code}: {detail}", retryable=retryable)
    try:
        message_id = response.json().get("messageId")
    except ValueError as exc:
        raise SendError("OpenWA returned an invalid response", retryable=False) from exc
    if not message_id:
        raise SendError("OpenWA response did not include a message ID", retryable=False)
    return str(message_id)


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Verify OpenWA's X-OpenWA-Signature over the exact request bytes."""
    secret = get_settings().openwa_webhook_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def parse_webhook(payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    """Return normalized (inbound messages, delivery status updates)."""
    event = payload.get("event")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
    if event == "message.received":
        sender = str(data.get("senderPhone") or data.get("from") or "")
        # A privacy @lid cannot safely be treated as a phone number. OpenWA can
        # populate senderPhone when RESOLVE_LID_TO_PHONE=true.
        if "@lid" in sender and not data.get("senderPhone"):
            sender = ""
        else:
            sender = sender.split("@", 1)[0]
        button = data.get("button") if isinstance(data.get("button"), dict) else {}
        messages.append({
            "id": data.get("id"),
            "sender": re.sub(r"\D", "", sender),
            "text": data.get("body") or button.get("text") or "",
            "is_group": bool(data.get("isGroup")) or data.get("kind") == "group",
        })
    elif event in ("message.ack", "message.failed"):
        statuses.append({
            "message_id": data.get("messageId") or data.get("id"),
            "status": "failed" if event == "message.failed" else data.get("status"),
            "error": data.get("error") or data.get("reason"),
        })
    return messages, statuses


class OpenWAGateway:
    """:class:`~app.services.channels.gateway.WhatsAppGateway` backed by a self-hosted OpenWA.

    Methods look up the module-level functions at call time so they stay patchable in tests.
    """

    name = "openwa"

    def configured(self) -> bool:
        return get_settings().openwa_configured

    def webhook_configured(self) -> bool:
        return get_settings().openwa_webhook_configured

    def send_text(self, to_e164: str, body: str) -> str:
        return send_text(to_e164, body)

    def verify_signature(self, raw_body: bytes, header: str | None) -> bool:
        return verify_signature(raw_body, header)

    def session_matches(self, payload: dict) -> bool:
        return payload.get("sessionId") == get_settings().openwa_session_id

    def parse_webhook(self, payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
        return parse_webhook(payload)
