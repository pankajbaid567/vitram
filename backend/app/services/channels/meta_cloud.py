"""Meta WhatsApp Cloud API adapter (the official channel; RD §17.1).

* Business-initiated reminders are **template** messages: free text is rejected by Meta outside the
  24-hour customer-service window. The template (``WHATSAPP_REMINDER_TEMPLATE``) must be approved
  and have three body variables: ``{{1}}`` item, ``{{2}}`` amount, ``{{3}}`` date.
* Replies to a user's message are free text (we are inside the window).
* Inbound webhooks are signed with the app secret (``X-Hub-Signature-256`` = HMAC-SHA256 of the raw body)
  and subscribed once with a ``GET`` handshake echoing ``hub.challenge``.
"""

import hashlib
import hmac
import html
import re

import httpx

from app.config import get_settings
from app.services.channels.gateway import InboundMessage, NotConfigured, SendError, StatusUpdate

GRAPH = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v21.0"  # an empty WHATSAPP_GRAPH_VERSION in .env must not produce a broken URL

# Meta error codes worth retrying (throttling / transient). Everything else (bad token, template
# mismatch, recipient not reachable, outside the window) will fail again, so it is final.
RETRYABLE_CODES = {1, 2, 4, 17, 341, 80007, 130429, 131016, 131056, 133004}


def _settings():
    s = get_settings()
    if not s.meta_configured:
        raise NotConfigured("WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_REMINDER_TEMPLATE are not configured")
    return s


def _to(to_e164: str) -> str:
    digits = re.sub(r"\D", "", to_e164)
    if not 8 <= len(digits) <= 15:
        raise SendError("Invalid WhatsApp destination", retryable=False)
    return digits


def _clean(text: str, limit: int) -> str:
    return html.unescape(html.unescape(text)).replace("\x00", "").strip()[:limit]


def _variable(text: str) -> str:
    """Template variables may not contain newlines, tabs or 4+ consecutive spaces; max 1024 chars."""
    return re.sub(r"\s+", " ", _clean(text, 1024)) or "-"


def _post(payload: dict) -> str:
    s = _settings()
    url = f"{GRAPH}/{s.whatsapp_graph_version or DEFAULT_GRAPH_VERSION}/{s.whatsapp_phone_number_id}/messages"
    try:
        r = httpx.post(url, json={"messaging_product": "whatsapp", **payload},
                       headers={"Authorization": f"Bearer {s.whatsapp_token}"},
                       timeout=s.whatsapp_timeout_seconds, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise SendError(f"Network error contacting Meta: {type(exc).__name__}") from exc
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400:
        err = body.get("error") if isinstance(body, dict) else None
        err = err if isinstance(err, dict) else {}
        code = err.get("code")
        detail = err.get("message") or "request failed"
        retryable = r.status_code in (408, 429) or r.status_code >= 500 or code in RETRYABLE_CODES
        raise SendError(f"Meta HTTP {r.status_code} (code {code}): {detail}", retryable=retryable)
    messages = body.get("messages") if isinstance(body, dict) else None
    mid = messages[0].get("id") if isinstance(messages, list) and messages else None
    if not mid:
        raise SendError("Meta response did not include a message id", retryable=False)
    return str(mid)


def send_text(to_e164: str, body: str) -> str:
    return _post({"to": _to(to_e164), "type": "text", "text": {"body": _clean(body, 4096), "preview_url": False}})


def send_reminder(to_e164: str, text: str, params: list[str]) -> str:  # noqa: ARG001 - text is for providers without templates
    s = _settings()
    return _post({
        "to": _to(to_e164), "type": "template",
        "template": {
            "name": s.whatsapp_reminder_template,
            "language": {"code": s.whatsapp_template_language or "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": _variable(p)} for p in params[:3]]}],
        },
    })


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def verify_subscription(query: dict) -> str | None:
    s = get_settings()
    token = query.get("hub.verify_token") or ""
    if query.get("hub.mode") == "subscribe" and s.whatsapp_verify_token and hmac.compare_digest(token, s.whatsapp_verify_token):
        return str(query.get("hub.challenge") or "")
    return None


def _values(payload: dict):
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") == "messages" and isinstance(change.get("value"), dict):
                yield change["value"]


def session_matches(payload: dict) -> bool:
    wanted = get_settings().whatsapp_phone_number_id
    seen = [str((v.get("metadata") or {}).get("phone_number_id") or "") for v in _values(payload)]
    return bool(seen) and all(x == wanted for x in seen)


def _message_text(m: dict) -> str:
    kind = m.get("type")
    if kind == "text":
        return (m.get("text") or {}).get("body") or ""
    if kind == "button":
        return (m.get("button") or {}).get("text") or ""
    if kind == "interactive":
        i = m.get("interactive") or {}
        return ((i.get("button_reply") or i.get("list_reply") or {}).get("title")) or ""
    return ""


def parse_webhook(payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
    for value in _values(payload):
        for m in value.get("messages") or []:
            messages.append({"id": m.get("id"), "sender": re.sub(r"\D", "", str(m.get("from") or "")),
                             "text": _message_text(m), "is_group": bool(m.get("group_id"))})
        for st in value.get("statuses") or []:
            errors = st.get("errors") or []
            error = "; ".join(f"{e.get('code')}: {e.get('title') or e.get('message')}" for e in errors if isinstance(e, dict)) or None
            statuses.append({"message_id": st.get("id"), "status": st.get("status"), "error": error})
    return messages, statuses


class MetaCloudGateway:
    """:class:`~app.services.channels.gateway.WhatsAppGateway` for Meta's WhatsApp Cloud API."""

    name = "meta"
    signature_header = "x-hub-signature-256"
    idempotency_header = None  # Meta sends none; message and status ids are the natural keys

    def configured(self) -> bool:
        return get_settings().meta_configured

    def webhook_configured(self) -> bool:
        return get_settings().meta_webhook_configured

    def send_text(self, to_e164: str, body: str) -> str:
        return send_text(to_e164, body)

    def send_reminder(self, to_e164: str, text: str, params: list[str]) -> str:
        return send_reminder(to_e164, text, params)

    def verify_signature(self, raw_body: bytes, header: str | None) -> bool:
        return verify_signature(raw_body, header)

    def verify_subscription(self, query: dict) -> str | None:
        return verify_subscription(query)

    def session_matches(self, payload: dict) -> bool:
        return session_matches(payload)

    def parse_webhook(self, payload: dict) -> tuple[list[InboundMessage], list[StatusUpdate]]:
        return parse_webhook(payload)
