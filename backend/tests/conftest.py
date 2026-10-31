import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="vitram-test-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp / 'test.db'}"
os.environ["DATA_DIR"] = str(_tmp)
os.environ["APP_ORIGIN"] = "http://testserver"
# Explicit empty values override the repository-root .env so tests never use
# developer credentials or make live vendor requests by accident.
for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_LIVE_MODEL", "OPENWA_BASE_URL",
          "OPENWA_API_KEY", "OPENWA_SESSION_ID", "OPENWA_WEBHOOK_SECRET",
          "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
          "TWILIO_FROM_NUMBER", "TWILIO_VERIFY_SERVICE_SID", "CONSULTANT_PHONE_NUMBER", "PUBLIC_API_URL"):
    os.environ[k] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(scope="session")
def client_factory():
    with TestClient(app) as base:  # runs lifespan (init DB, catalogues)
        def make():
            c = TestClient(app)
            c.headers.update(ORIGIN)
            return c
        yield make
        del base


@pytest.fixture
def client(client_factory):
    return client_factory()


def signup(c, email=None, name="Test User"):
    import uuid
    email = email or f"t{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/auth/signup", json={"name": name, "email": email, "password": "correct-horse-1", "accept_terms": True})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def user_client(client):
    signup(client)
    return client


@pytest.fixture(scope="session")
def sample(client_factory):
    c = client_factory()
    r = c.post("/api/demo/workspace")
    assert r.status_code == 200, r.text
    return c
