"""Integration self-check: `python -m app.doctor [--offline] [--json]`.

Run it after adding credentials. For every integration it says whether it is *configured* and, unless
``--offline``, whether the provider *accepts the credentials*: using only read-only calls (it never sends a
message, places a call or creates anything). Secrets are never printed: details carry status codes and the
provider's own error text, nothing else. Exit code 1 means at least one check failed (warnings do not).
"""

import argparse
import json
import smtplib
import sys
from dataclasses import asdict, dataclass

import httpx
from sqlalchemy import text

from app.config import Settings, get_settings
from app.security import redact

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
TIMEOUT = 8.0


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _get(url: str, **kw) -> httpx.Response:
    """The one HTTP seam (patched in tests); never follows redirects, so credentials can't be forwarded."""
    return httpx.get(url, timeout=TIMEOUT, follow_redirects=False, **kw)


def _safe(name: str, fn) -> Check:
    try:
        return fn()
    except Exception as exc:  # a broken probe must not hide the other checks
        return Check(name, FAIL, f"check crashed: {type(exc).__name__}")


def _http_status(r: httpx.Response) -> str:
    try:
        msg = (r.json().get("error") or {}).get("message") or r.json().get("message") or ""
    except Exception:  # noqa: BLE001
        msg = ""
    return f"HTTP {r.status_code}" + (f": {redact(str(msg))[:120]}" if msg else "")


# --- individual checks -------------------------------------------------------------------------------

def check_config(s: Settings) -> Check:
    problems, warnings = s.production_problems(), s.production_warnings()
    if problems:
        return Check("configuration", FAIL, "; ".join(problems))
    if warnings:
        return Check("configuration", WARN, "; ".join(warnings))
    return Check("configuration", OK, f"ENV={s.env}")


def check_database(s: Settings) -> Check:
    from app.db import engine
    from app.migrate import alembic_config, current_revision, head_revision
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    cur, head = current_revision(engine), head_revision(alembic_config(s.database_url))
    kind = "SQLite" if s.is_sqlite else "PostgreSQL"
    if cur != head:
        return Check("database", FAIL, f"{kind} reachable, but schema is at {cur} and the code needs {head}: run `python -m app.migrate upgrade`")
    return Check("database", OK, f"{kind}, schema at {head}")


def check_encryption_key(s: Settings) -> Check:
    if s.vitram_data_key:
        return Check("encryption key", OK, "VITRAM_DATA_KEY is set")
    return Check("encryption key", WARN if s.env != "production" else FAIL,
                 "using an auto-generated development key (files become unreadable if it is lost); set VITRAM_DATA_KEY")


def check_public_url(s: Settings) -> Check:
    if not s.public_api_url:
        return Check("public API URL", SKIP, "PUBLIC_API_URL not set (needed for WhatsApp and Twilio webhooks)")
    if not s.public_api_url.startswith("https://"):
        return Check("public API URL", WARN, f"{s.public_api_url} is not https; providers will refuse or you are on localhost/tunnel")
    return Check("public API URL", OK, f"webhooks go to {s.public_api_url}/api/webhooks/…")


def check_gemini(s: Settings, network: bool) -> Check:
    if not s.gemini_api_key:
        return Check("Gemini", SKIP, "GEMINI_API_KEY not set: assistant runs in Tool mode (optional)")
    if not s.gemini_model:
        return Check("Gemini", WARN, "key set but GEMINI_MODEL is empty")
    extras = f"live voice model {'set' if s.gemini_live_model else 'not set'}; AI extraction {'on' if s.ai_extraction else 'off'}"
    if not network:
        return Check("Gemini", OK, f"configured ({extras}); not probed")
    r = _get(f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}", headers={"x-goog-api-key": s.gemini_api_key})
    return Check("Gemini", OK if r.status_code == 200 else FAIL,
                 f"model {s.gemini_model!r} {'is available' if r.status_code == 200 else 'was rejected'} ({_http_status(r)}); {extras}")


def check_whatsapp(s: Settings, network: bool) -> Check:
    if s.whatsapp_provider == "meta":
        return _check_meta(s, network)
    return _check_openwa(s, network)


def _check_meta(s: Settings, network: bool) -> Check:
    missing = [n for n, v in (("WHATSAPP_TOKEN", s.whatsapp_token), ("WHATSAPP_PHONE_NUMBER_ID", s.whatsapp_phone_number_id),
                              ("WHATSAPP_REMINDER_TEMPLATE", s.whatsapp_reminder_template), ("WHATSAPP_APP_SECRET", s.whatsapp_app_secret),
                              ("WHATSAPP_VERIFY_TOKEN", s.whatsapp_verify_token)) if not v]
    if missing:
        return Check("WhatsApp (Meta Cloud API)", SKIP if len(missing) == 5 else FAIL, "missing " + ", ".join(missing))
    if not network:
        return Check("WhatsApp (Meta Cloud API)", OK, "configured; not probed. Confirm the template is APPROVED in Meta Business Suite")
    r = _get(f"https://graph.facebook.com/{s.whatsapp_graph_version or 'v21.0'}/{s.whatsapp_phone_number_id}",
             params={"fields": "verified_name,display_phone_number,quality_rating"}, headers={"Authorization": f"Bearer {s.whatsapp_token}"})
    if r.status_code != 200:
        return Check("WhatsApp (Meta Cloud API)", FAIL, f"token or phone-number id rejected ({_http_status(r)})")
    d = r.json()
    return Check("WhatsApp (Meta Cloud API)", OK, f"number {d.get('display_phone_number')} ({d.get('verified_name')}), quality {d.get('quality_rating')}. "
                 f"Confirm template {s.whatsapp_reminder_template!r} is APPROVED in Meta Business Suite")


def _check_openwa(s: Settings, network: bool) -> Check:
    name = "WhatsApp (OpenWA, unofficial)"
    if not (s.openwa_base_url and s.openwa_api_key and s.openwa_session_id):
        return Check(name, SKIP, "OPENWA_BASE_URL / OPENWA_API_KEY / OPENWA_SESSION_ID not all set (optional)")
    if not s.openwa_webhook_configured:
        return Check(name, FAIL, "OPENWA_WEBHOOK_SECRET must be at least 16 characters")
    if not network:
        return Check(name, OK, "configured; not probed. Use a dedicated test number only (ban risk)")
    base, headers = s.openwa_base_url.rstrip("/"), {"X-API-Key": s.openwa_api_key}
    r = _get(f"{base}/api/sessions/{s.openwa_session_id}", headers=headers)
    if r.status_code != 200:
        return Check(name, FAIL, f"session not reachable ({_http_status(r)})")
    status = str(r.json().get("status", "unknown")).lower()
    if status not in ("ready", "connected", "working", "authenticated"):
        return Check(name, WARN, f"session status is {status!r}: pair the number in the OpenWA dashboard")
    hooks = _get(f"{base}/api/sessions/{s.openwa_session_id}/webhooks", headers=headers)
    urls = [str(h.get("url", "")) for h in (hooks.json() if hooks.status_code == 200 and isinstance(hooks.json(), list) else [])]
    # OpenWA may run on the same machine (Docker → host.docker.internal) or reach a public URL: either is fine as long as it
    # points at this app's webhook route, so judge the route, not the host.
    ours = [u for u in urls if u.rstrip("/").endswith(("/api/webhooks/whatsapp", "/api/webhooks/openwa"))]
    if not ours:
        return Check(name, WARN, f"session {status}; no webhook points at /api/webhooks/whatsapp: register one with the shared secret")
    host = ours[0].split("//", 1)[-1].split("/", 1)[0]
    return Check(name, OK, f"session {status}; webhook registered → {host}")


def check_twilio(s: Settings, network: bool) -> list[Check]:
    out = []
    if not (s.twilio_account_sid and s.twilio_auth_token):
        return [Check("Twilio (Verify + Voice)", SKIP, "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set (optional)")]
    auth = (s.twilio_account_sid, s.twilio_auth_token)
    if not network:
        out.append(Check("Twilio account", OK, "configured; not probed"))
    else:
        r = _get(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}.json", auth=auth)
        out.append(Check("Twilio account", OK if r.status_code == 200 else FAIL,
                         f"credentials {'accepted' if r.status_code == 200 else 'rejected'} ({_http_status(r)})"
                         + (f", status {r.json().get('status')}, type {r.json().get('type')}" if r.status_code == 200 else "")))
    if not s.twilio_verify_service_sid:
        out.append(Check("Twilio Verify", WARN, "TWILIO_VERIFY_SERVICE_SID not set: users can't verify their phone, so WhatsApp stays off"))
    elif network:
        r = _get(f"https://verify.twilio.com/v2/Services/{s.twilio_verify_service_sid}", auth=auth)
        out.append(Check("Twilio Verify", OK if r.status_code == 200 else FAIL, f"service {'found' if r.status_code == 200 else 'not found'} ({_http_status(r)})"))
    else:
        out.append(Check("Twilio Verify", OK, "service sid set; not probed"))
    voice = [n for n, v in (("TWILIO_FROM_NUMBER", s.twilio_from_number), ("CONSULTANT_PHONE_NUMBER", s.consultant_phone_number), ("PUBLIC_API_URL", s.public_api_url)) if not v]
    out.append(Check("Twilio Voice (consultation calls)", WARN if voice else OK,
                     ("missing " + ", ".join(voice) + ": consultation requests will say no call was placed") if voice else "caller, consultant number and callback URL set"))
    return out


def check_smtp(s: Settings, network: bool) -> Check:
    if not (s.smtp_host and s.smtp_from):
        return Check("SMTP e-mail", SKIP, "SMTP_HOST / SMTP_FROM not set: verification and reset e-mails are unavailable (optional)")
    if not network:
        return Check("SMTP e-mail", OK, "configured; not probed")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT) as smtp:
        smtp.ehlo()
        if s.smtp_starttls:
            smtp.starttls()
            smtp.ehlo()
        user, pwd = s.smtp_username or s.smtp_user, s.smtp_password
        if user and pwd:
            smtp.login(user, pwd)
    return Check("SMTP e-mail", OK, f"{s.smtp_host}:{s.smtp_port} accepted the connection{' and login' if (s.smtp_username or s.smtp_user) and s.smtp_password else ''} (nothing sent)")


def check_ocr(_s: Settings) -> Check:
    from app.services.vision import provider_status
    st = provider_status()
    return Check("OCR (scans and photos)", OK if st["configured"] else SKIP, f"{st['provider']}: {st['note']}")


def check_reminder_loop() -> Check:
    from app.db import SessionLocal
    from app.services.channels import scheduler
    db = SessionLocal()
    try:
        age = scheduler.heartbeat_age(db)
    finally:
        db.close()
    if age is None:
        return Check("reminder loop", WARN, "has never run: start the API (RUN_SCHEDULER=true) or `python -m app.worker`")
    secs = int(age.total_seconds())
    return Check("reminder loop", OK if secs < 300 else WARN, f"last pass {secs}s ago" + ("" if secs < 300 else ": stalled? check the worker"))


# --- runner --------------------------------------------------------------------------------------

def run(network: bool = True, s: Settings | None = None) -> list[Check]:
    s = s or get_settings()
    database = _safe("database", lambda: check_database(s))
    checks = [
        _safe("configuration", lambda: check_config(s)),
        database,
        _safe("encryption key", lambda: check_encryption_key(s)),
        _safe("public API URL", lambda: check_public_url(s)),
        _safe("Gemini", lambda: check_gemini(s, network)),
        _safe("WhatsApp", lambda: check_whatsapp(s, network)),
        _safe("SMTP e-mail", lambda: check_smtp(s, network)),
        _safe("OCR", lambda: check_ocr(s)),
        _safe("reminder loop", check_reminder_loop) if database.status == OK else Check("reminder loop", SKIP, "database not ready"),
    ]
    try:
        checks[6:6] = check_twilio(s, network)
    except Exception as exc:  # noqa: BLE001
        checks[6:6] = [Check("Twilio", FAIL, f"check crashed: {type(exc).__name__}")]
    return _scrub(checks, s)


def _scrub(checks: list[Check], s: Settings) -> list[Check]:
    """Belt and braces: whatever a provider echoes back, no configured secret value can appear in the report."""
    secrets = [v for v in (s.gemini_api_key, s.whatsapp_token, s.whatsapp_app_secret, s.whatsapp_verify_token, s.openwa_api_key,
                           s.openwa_webhook_secret, s.twilio_auth_token, s.smtp_password, s.vitram_data_key) if v and len(v) >= 6]
    for c in checks:
        for secret in secrets:
            c.detail = c.detail.replace(secret, "***")
    return checks


SYMBOL = {OK: "✓", WARN: "!", FAIL: "✗", SKIP: "-"}


def render(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = [f" {SYMBOL[c.status]}  {c.name.ljust(width)}  {c.detail}" for c in checks]
    counts = {k: sum(c.status == k for c in checks) for k in (OK, WARN, FAIL, SKIP)}
    lines.append(f"\n {counts[OK]} ok · {counts[WARN]} warnings · {counts[FAIL]} failed · {counts[SKIP]} not configured")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.doctor", description=__doc__.split("\n\n")[0])
    ap.add_argument("--offline", action="store_true", help="check configuration only; make no network calls")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    checks = run(network=not args.offline)
    print(json.dumps([asdict(c) for c in checks], indent=2) if args.json else render(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
