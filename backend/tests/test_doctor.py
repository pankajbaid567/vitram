"""`python -m app.doctor`: configuration and read-only provider probes, with no secrets in the report."""

import json
import smtplib

import pytest

from app import doctor
from app.config import Settings


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {}

    def json(self):
        return self._body


def settings(**kw):
    base = {"env": "development", "app_origin": "http://localhost:5173", "database_url": "sqlite:///:memory:"}
    return Settings(**{**base, **kw})


def by_name(checks):
    return {c.name: c for c in checks}


@pytest.fixture
def no_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("--offline must not make network calls")
    monkeypatch.setattr(doctor, "_get", forbidden)
    monkeypatch.setattr(smtplib, "SMTP", forbidden)


def test_offline_with_nothing_configured_skips_integrations_and_makes_no_calls(no_network):
    checks = by_name(doctor.run(network=False, s=settings()))
    assert checks["configuration"].status == doctor.OK
    for name in ("Gemini", "WhatsApp (OpenWA, unofficial)", "Twilio (Verify + Voice)", "SMTP e-mail"):
        assert checks[name].status == doctor.SKIP, name


def test_offline_reports_configured_but_unprobed(no_network):
    s = settings(gemini_api_key="g-key-123456", gemini_model="m", smtp_host="smtp.test", smtp_from="a@b.c")
    checks = by_name(doctor.run(network=False, s=s))
    assert checks["Gemini"].status == doctor.OK and "not probed" in checks["Gemini"].detail
    assert checks["SMTP e-mail"].status == doctor.OK and "not probed" in checks["SMTP e-mail"].detail


# --- Meta ---------------------------------------------------------------------------------------

META = dict(whatsapp_provider="meta", whatsapp_token="EAAG-token-abcdef", whatsapp_phone_number_id="1055", whatsapp_app_secret="app-secret-xyz",
            whatsapp_verify_token="verify-token-123", whatsapp_reminder_template="tmpl")


def test_meta_probe_success_names_the_number_and_reminds_about_template_approval(monkeypatch):
    seen = {}

    def fake(url, **kw):
        seen["url"], seen["auth"] = url, kw["headers"]["Authorization"]
        return Resp(200, {"display_phone_number": "+91 98765 43210", "verified_name": "VITRAM", "quality_rating": "GREEN"})
    monkeypatch.setattr(doctor, "_get", fake)
    c = by_name(doctor.run(s=settings(**META)))["WhatsApp (Meta Cloud API)"]
    assert c.status == doctor.OK and "GREEN" in c.detail and "APPROVED" in c.detail
    assert seen["url"].endswith("/1055") and "EAAG-token-abcdef" in seen["auth"], "the probe really used the token"


def test_meta_probe_failure_never_leaks_the_token_even_if_the_provider_echoes_it(monkeypatch):
    monkeypatch.setattr(doctor, "_get", lambda *a, **k: Resp(401, {"error": {"message": "Invalid OAuth access token EAAG-token-abcdef"}}))
    checks = doctor.run(s=settings(**META))
    c = by_name(checks)["WhatsApp (Meta Cloud API)"]
    assert c.status == doctor.FAIL and "401" in c.detail
    assert "EAAG-token-abcdef" not in doctor.render(checks) and "EAAG-token-abcdef" not in json.dumps([vars(x) for x in checks])


def test_meta_reports_exactly_what_is_missing():
    c = by_name(doctor.run(network=False, s=settings(whatsapp_provider="meta", whatsapp_token="t" * 10)))["WhatsApp (Meta Cloud API)"]
    assert c.status == doctor.FAIL and "WHATSAPP_PHONE_NUMBER_ID" in c.detail and "WHATSAPP_REMINDER_TEMPLATE" in c.detail


# --- OpenWA -------------------------------------------------------------------------------------

OPENWA = dict(openwa_base_url="http://openwa.test", openwa_api_key="owa-key-abcdef", openwa_session_id="s1",
              openwa_webhook_secret="x" * 20, public_api_url="https://api.example.com")


def test_openwa_ready_session_with_registered_webhook(monkeypatch):
    def fake(url, **kw):
        assert kw["headers"]["X-API-Key"] == "owa-key-abcdef"
        return Resp(200, [{"url": "https://api.example.com/api/webhooks/whatsapp"}]) if url.endswith("/webhooks") else Resp(200, {"status": "ready"})
    monkeypatch.setattr(doctor, "_get", fake)
    c = by_name(doctor.run(s=settings(**OPENWA)))["WhatsApp (OpenWA, unofficial)"]
    assert c.status == doctor.OK and "webhook registered" in c.detail


def test_openwa_webhook_may_point_at_the_local_machine_not_only_a_public_url(monkeypatch):
    """OpenWA in Docker reaches this app at host.docker.internal; that is registered and fine."""
    def fake(url, **kw):
        return Resp(200, [{"url": "http://host.docker.internal:8765/api/webhooks/whatsapp"}]) if url.endswith("/webhooks") else Resp(200, {"status": "ready"})
    monkeypatch.setattr(doctor, "_get", fake)
    c = by_name(doctor.run(s=settings(**{**OPENWA, "public_api_url": "https://stale-tunnel.example"})))["WhatsApp (OpenWA, unofficial)"]
    assert c.status == doctor.OK and "host.docker.internal:8765" in c.detail


def test_openwa_unpaired_session_and_missing_webhook_are_warnings(monkeypatch):
    monkeypatch.setattr(doctor, "_get", lambda url, **kw: Resp(200, {"status": "qr_ready"}))
    c = by_name(doctor.run(s=settings(**OPENWA)))["WhatsApp (OpenWA, unofficial)"]
    assert c.status == doctor.WARN and "pair" in c.detail
    monkeypatch.setattr(doctor, "_get", lambda url, **kw: Resp(200, []) if url.endswith("/webhooks") else Resp(200, {"status": "ready"}))
    c = by_name(doctor.run(s=settings(**OPENWA)))["WhatsApp (OpenWA, unofficial)"]
    assert c.status == doctor.WARN and "no webhook points at" in c.detail


# --- Twilio / Gemini / SMTP -----------------------------------------------------------------------------

def test_twilio_probes_account_and_verify_service(monkeypatch):
    def fake(url, **kw):
        assert kw["auth"] == ("ACtest", "tw-token-123456")
        return Resp(200, {"status": "active", "type": "Trial"}) if "api.twilio.com" in url else Resp(404, {"message": "not found"})
    monkeypatch.setattr(doctor, "_get", fake)
    s = settings(twilio_account_sid="ACtest", twilio_auth_token="tw-token-123456", twilio_verify_service_sid="VAbad")
    checks = by_name(doctor.run(s=s))
    assert checks["Twilio account"].status == doctor.OK and "Trial" in checks["Twilio account"].detail
    assert checks["Twilio Verify"].status == doctor.FAIL
    assert checks["Twilio Voice (consultation calls)"].status == doctor.WARN


def test_gemini_probe_checks_the_configured_model(monkeypatch):
    monkeypatch.setattr(doctor, "_get", lambda url, **kw: Resp(200, {}) if url.endswith("/models/good") else Resp(404, {"error": {"message": "model not found"}}))
    assert by_name(doctor.run(s=settings(gemini_api_key="g-key-123456", gemini_model="good")))["Gemini"].status == doctor.OK
    assert by_name(doctor.run(s=settings(gemini_api_key="g-key-123456", gemini_model="bad")))["Gemini"].status == doctor.FAIL


def test_smtp_connects_and_logs_in_but_never_sends(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout): calls.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): calls.append("ehlo")
        def starttls(self): calls.append("starttls")
        def login(self, u, p): calls.append(("login", u))
        def sendmail(self, *a, **k): raise AssertionError("the doctor must never send mail")
        send_message = sendmail
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    c = by_name(doctor.run(s=settings(smtp_host="smtp.test", smtp_from="a@b.c", smtp_username="u", smtp_password="pw-secret-1")))["SMTP e-mail"]
    assert c.status == doctor.OK and ("login", "u") in calls and "starttls" in calls and "nothing sent" in c.detail


def test_a_crashing_probe_becomes_a_failure_not_a_traceback(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("dns exploded")
    monkeypatch.setattr(doctor, "_get", boom)
    c = by_name(doctor.run(s=settings(gemini_api_key="g-key-123456", gemini_model="m")))["Gemini"]
    assert c.status == doctor.FAIL and "ConnectionError" in c.detail and "dns exploded" not in c.detail


# --- reporting -----------------------------------------------------------------------------------------

def test_exit_code_and_json_output(client, monkeypatch, capsys, no_network):   # `client` boots the app, which migrates the test DB
    assert doctor.main(["--offline", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"name", "status", "detail"} <= set(data[0])
    monkeypatch.setattr(doctor, "check_database", lambda s: doctor.Check("database", doctor.FAIL, "down"))
    assert doctor.main(["--offline"]) == 1


def test_production_misconfiguration_fails_the_configuration_check(no_network):
    c = by_name(doctor.run(network=False, s=settings(env="production", vitram_data_key=None, app_origin="http://prod.example.com")))
    assert c["configuration"].status == doctor.FAIL and c["encryption key"].status == doctor.FAIL


def test_an_unmigrated_database_fails_cleanly_and_does_not_crash_dependent_checks(no_network, monkeypatch):
    monkeypatch.setattr(doctor, "check_database", lambda s: doctor.Check("database", doctor.FAIL, "schema at None"))
    checks = by_name(doctor.run(network=False, s=settings()))
    assert checks["database"].status == doctor.FAIL
    assert checks["reminder loop"].status == doctor.SKIP and "database not ready" in checks["reminder loop"].detail
