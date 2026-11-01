import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="vitram-test-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp / 'test.db'}"
os.environ["DATA_DIR"] = str(_tmp)
os.environ["APP_ORIGIN"] = "http://testserver"
# No background loops inside the test process: tests drive the job queue and the reminder dispatcher explicitly, and a polling loop
# would race them (it could claim a job a test is about to claim itself).
os.environ["RUN_SCHEDULER"] = "false"
os.environ["THROTTLE_ENABLED"] = "false"     # rate-limit tests switch it on explicitly (tests/test_throttle.py)
os.environ["REDIS_URL"] = ""
# Explicit empty values override the repository-root .env so tests never use
# developer credentials or make live vendor requests by accident.
for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_LIVE_MODEL", "OPENWA_BASE_URL",
          "OPENWA_API_KEY", "OPENWA_SESSION_ID", "OPENWA_WEBHOOK_SECRET",
          "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
          "TWILIO_FROM_NUMBER", "TWILIO_VERIFY_SERVICE_SID", "CONSULTANT_PHONE_NUMBER", "PUBLIC_API_URL",
          "WHATSAPP_PROVIDER", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_APP_SECRET", "WHATSAPP_VERIFY_TOKEN",
          "WHATSAPP_REMINDER_TEMPLATE", "WHATSAPP_TEMPLATE_LANGUAGE", "WHATSAPP_GRAPH_VERSION"):
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


@pytest.fixture(autouse=True)
def _host_independent_ocr(monkeypatch, request):
    """Tests must behave the same on macOS and Linux CI.

    Pretend on-device OCR exists and default it to "a blank page: no text found"; tests that care install their own
    fake via ``monkeypatch.setattr(pipeline, "read_document", ...)``. The one test that exercises the real
    Apple Vision helper opts out with ``@pytest.mark.real_ocr`` (and is skipped where Swift is unavailable).
    """
    if request.node.get_closest_marker("real_ocr"):
        return
    from app.services import pipeline
    from app.services.vision import VisionError, providers

    monkeypatch.setattr(providers, "_macos_available", lambda: True)

    def blank_page(data, mime, max_pages=None):
        if providers.active_provider() == "none":  # a test that turned OCR off must see it off
            raise VisionError("OCR_NOT_CONFIGURED", "Reading scans and photos isn't set up on this server.")
        raise VisionError("NO_TEXT_FOUND", "No readable text was found. Retake the photo in good light, flat and in focus.")

    monkeypatch.setattr(pipeline, "read_document", blank_page)
