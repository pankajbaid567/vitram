"""Password change (M12): current password required, other sessions end, this one stays."""

from tests.conftest import ORIGIN


def _signup(c, email):
    r = c.post("/api/auth/signup", json={"name": "P", "email": email, "password": "correct-horse-1", "accept_terms": True})
    assert r.status_code == 200, r.text


def test_change_password_revokes_other_sessions(client_factory):
    a, b = client_factory(), client_factory()
    _signup(a, "pw1@example.com")
    assert b.post("/api/auth/login", json={"email": "pw1@example.com", "password": "correct-horse-1"}).status_code == 200

    r = a.post("/api/auth/password", json={"current_password": "correct-horse-1", "new_password": "battery-staple-2"})
    assert r.status_code == 200 and r.json()["other_sessions_ended"] == 1
    assert a.get("/api/auth/me").status_code == 200  # this session stays
    assert b.get("/api/auth/me").status_code == 401  # the other one ended

    c = client_factory()
    assert c.post("/api/auth/login", json={"email": "pw1@example.com", "password": "correct-horse-1"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "pw1@example.com", "password": "battery-staple-2"}).status_code == 200


def test_change_password_rejects_wrong_current_and_short_new(client_factory):
    a = client_factory()
    _signup(a, "pw2@example.com")
    r = a.post("/api/auth/password", json={"current_password": "nope-nope-1", "new_password": "battery-staple-2"})
    assert r.status_code == 400 and r.json()["error"]["field"] == "current_password"
    r = a.post("/api/auth/password", json={"current_password": "correct-horse-1", "new_password": "short"})
    assert r.status_code == 422
    r = a.post("/api/auth/password", json={"current_password": "correct-horse-1", "new_password": "correct-horse-1"})
    assert r.status_code == 400 and r.json()["error"]["field"] == "new_password"


def test_change_password_requires_session_and_origin(client_factory):
    c = client_factory()
    assert c.post("/api/auth/password", json={"current_password": "x" * 8, "new_password": "y" * 8}).status_code == 401
    assert ORIGIN  # CSRF origin header is set by the factory
