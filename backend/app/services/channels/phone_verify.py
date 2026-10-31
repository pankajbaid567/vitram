"""Twilio Verify v2; phone numbers and one-time codes never enter logs."""

import httpx

from app.config import get_settings


class VerifyUnavailable(Exception):
    pass


def _request(path: str, data: dict[str, str]) -> dict:
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_verify_service_sid):
        raise VerifyUnavailable("Phone verification is not configured.")
    url = f"https://verify.twilio.com/v2/Services/{s.twilio_verify_service_sid}/{path}"
    try:
        response = httpx.post(url, data=data, auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=15)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise VerifyUnavailable("Phone verification is temporarily unavailable.") from exc


def start(phone_e164: str) -> bool:
    return _request("Verifications", {"To": phone_e164, "Channel": "sms"}).get("status") == "pending"


def check(phone_e164: str, code: str) -> bool:
    result = _request("VerificationCheck", {"To": phone_e164, "Code": code})
    return result.get("status") == "approved" and result.get("valid") is True
