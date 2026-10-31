"""Twilio Programmable Voice adapter for insurance consultation calls (RD §15.5, §17.2).

Creates an outbound call to the user; inline TwiML plays a short consented
introduction and dials the team-controlled consultant number. No recording.
Endpoint: POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Calls.json
(verify against current Twilio docs when credentials are added — see plan.md §7).
"""

from xml.sax.saxutils import escape

import httpx

from app.config import get_settings


class NotConfigured(Exception):
    pass


class CallError(Exception):
    pass


def twiml(intro: str, consultant: str) -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>"
        f"<Say language=\"en-IN\">{escape(intro)}</Say>"
        f"<Dial record=\"do-not-record\">{escape(consultant)}</Dial>"
        "</Response>"
    )


def create_call(to_e164: str, intro: str, status_callback: str | None) -> dict:
    s = get_settings()
    if not s.twilio_configured:
        raise NotConfigured("Twilio credentials are not configured")
    data = [("To", to_e164), ("From", s.twilio_from_number), ("Twiml", twiml(intro, s.consultant_phone_number))]
    if status_callback:
        data.append(("StatusCallback", status_callback))
        for ev in ("initiated", "ringing", "answered", "completed"):
            data.append(("StatusCallbackEvent", ev))
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Calls.json"
    try:
        r = httpx.post(url, data=data, auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=20)
    except httpx.HTTPError as exc:
        raise CallError(f"Network error contacting Twilio: {type(exc).__name__}") from exc
    if r.status_code >= 400:
        try:
            body = r.json()
            raise CallError(f"{body.get('code', r.status_code)}: {body.get('message', 'call failed')}")
        except ValueError:
            raise CallError(f"HTTP {r.status_code}")
    body = r.json()
    return {"sid": body.get("sid"), "status": body.get("status")}


def validate_signature(url: str, params: dict[str, str], signature: str | None) -> bool:
    """Validate X-Twilio-Signature with Twilio's official RequestValidator, as Twilio's security docs advise
    (it handles URL/port normalisation edge cases). `url` must be the exact public callback URL."""
    token = get_settings().twilio_auth_token
    if not token or not signature:
        return False
    from twilio.request_validator import RequestValidator

    return RequestValidator(token).validate(url, params, signature)


TWILIO_TO_STATUS = {
    "queued": "calling", "initiated": "calling", "ringing": "ringing", "in-progress": "in_progress",
    "answered": "in_progress", "completed": "completed", "busy": "failed", "failed": "failed",
    "no-answer": "no_answer", "canceled": "cancelled",
}
