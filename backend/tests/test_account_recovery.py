"""Account email links: single-use, expiring, and session-revoking."""

from app.config import get_settings
from app.services import mailer
from tests.conftest import signup


def test_email_verification_and_password_reset(client, monkeypatch):
    user = signup(client)
    sent: list[str] = []
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "vitram@test")
    monkeypatch.setattr(mailer, "send", lambda _to, _subject, body: sent.append(body))

    assert client.post("/api/auth/email-verification/request").json()["status"] == "sent"
    verify = sent.pop().split("token=")[1].strip()
    assert client.post("/api/auth/email-verification/confirm", json={"token": verify}).json()["status"] == "verified"
    assert client.post("/api/auth/email-verification/confirm", json={"token": verify}).status_code == 400
    assert client.get("/api/auth/me").json()["email_verified"] is True

    assert client.post("/api/auth/password-reset/request", json={"email": "unknown@example.com"}).json()["sent"] is True
    assert client.post("/api/auth/password-reset/request", json={"email": user["email"]}).json()["sent"] is True
    reset = sent.pop().split("token=")[1].split()[0]
    assert client.post("/api/auth/password-reset/confirm", json={"token": reset, "new_password": "new-secret-2"}).json()["ok"] is True
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/password-reset/confirm", json={"token": reset, "new_password": "another-secret-3"}).status_code == 400
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "correct-horse-1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "new-secret-2"}).status_code == 200


def test_password_reset_request_without_smtp_is_non_enumerating(client):
    user = signup(client)
    known = client.post("/api/auth/password-reset/request", json={"email": user["email"]}).json()
    unknown = client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"}).json()
    assert known == unknown
