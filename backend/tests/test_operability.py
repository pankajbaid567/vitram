"""Request ids, the global 500 handler, structured logs and fail-fast production configuration."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.observability import JsonFormatter, RequestIdFilter, new_request_id, request_id_var


# --- request ids ------------------------------------------------------------------------------

def test_every_response_carries_a_request_id(client):
    r = client.get("/api/health")
    assert len(r.headers["x-request-id"]) >= 8


def test_a_well_formed_inbound_id_is_reused_and_garbage_is_replaced(client):
    assert client.get("/api/health", headers={"X-Request-ID": "trace-abc-12345"}).headers["x-request-id"] == "trace-abc-12345"
    for bad in ("short", "has spaces in it!!", "x" * 200, "<script>alert(1)</script>"):
        rid = client.get("/api/health", headers={"X-Request-ID": bad}).headers["x-request-id"]
        assert rid != bad and len(rid) == 32


def test_blocked_requests_also_get_an_id(client):
    r = client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.headers["x-request-id"]


def test_log_records_carry_the_request_id_and_json_is_valid(caplog):
    token = request_id_var.set("req-0123456789")
    try:
        rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        RequestIdFilter().filter(rec)
        line = json.loads(JsonFormatter().format(rec))
    finally:
        request_id_var.reset(token)
    assert line["request_id"] == "req-0123456789" and line["message"] == "hello world" and line["level"] == "INFO"


def test_new_request_id_is_unique():
    assert new_request_id() != new_request_id()


# --- unexpected errors -------------------------------------------------------------------------

def test_unexpected_errors_return_the_stable_shape_without_internals(caplog):
    def boom():
        raise RuntimeError("secret internal detail: db password hunter2")

    app.add_api_route("/api/_test_boom", boom)
    try:
        with TestClient(app, raise_server_exceptions=False) as c, caplog.at_level(logging.ERROR):
            r = c.get("/api/_test_boom", headers={"X-Request-ID": "trace-boom-0001"})
    finally:
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/api/_test_boom"]
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR" and err["request_id"] == "trace-boom-0001" and r.headers["x-request-id"] == "trace-boom-0001"
    assert "hunter2" not in r.text and "RuntimeError" not in r.text, "internals must not reach the client"
    assert any("unhandled error" in rec.getMessage() for rec in caplog.records), "…but they are logged for operators"


# --- production fail-fast -----------------------------------------------------------------------

def prod(**kw):
    base = {"env": "production", "vitram_data_key": "k" * 44, "app_origin": "https://app.example.com"}
    return Settings(**{**base, **kw})


def test_a_correct_production_config_has_no_problems():
    assert prod().production_problems() == []
    prod().assert_production_ready()


@pytest.mark.parametrize("kw,needle", [
    ({"vitram_data_key": None}, "VITRAM_DATA_KEY"),
    ({"app_origin": "http://app.example.com"}, "https://"),
    ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE"),
])
def test_unsafe_production_configs_refuse_to_start(kw, needle):
    s = prod(**kw)
    assert any(needle in p for p in s.production_problems())
    with pytest.raises(RuntimeError, match=needle):
        s.assert_production_ready()


def test_localhost_is_allowed_without_tls_so_compose_demos_work():
    assert prod(app_origin="http://localhost:8080", session_cookie_secure=False).production_problems() == []


def test_development_never_blocks_and_openwa_in_production_is_only_a_warning():
    assert Settings(env="development", vitram_data_key=None, app_origin="http://x").production_problems() == []
    s = prod(whatsapp_provider="openwa")
    assert s.production_problems() == [] and any("unofficial" in w for w in s.production_warnings())


def test_tests_run_in_development_mode():
    assert get_settings().env != "production"


# --- readiness and the worker heartbeat -----------------------------------------------------------

def test_ready_reports_database_migrations_and_reminder_loop(client):
    r = client.get("/api/ready")
    body = r.json()
    assert r.status_code == 200 and body["ready"] is True
    assert body["checks"]["database"] == "ok" and body["checks"]["migrations"] == "ok"
    assert body["checks"]["reminder_loop"]["state"] in ("ok", "never_ran", "stale")


def test_a_tick_records_a_heartbeat_that_readiness_sees(client):
    from app.services.channels import scheduler
    scheduler._tick()
    body = client.get("/api/ready").json()
    assert body["checks"]["reminder_loop"]["state"] == "ok" and body["checks"]["reminder_loop"]["last_beat_seconds_ago"] < 5


def test_readiness_is_503_when_the_database_is_unreachable(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.routers import ops

    class Down:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("password=hunter2 host=db.internal"))
    monkeypatch.setattr(ops, "engine", Down())
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json()["ready"] is False
    assert "unreachable" in r.json()["checks"]["database"] and "hunter2" not in r.text


def test_schema_behind_the_code_is_not_ready(client, monkeypatch):
    from app.routers import ops
    monkeypatch.setattr(ops, "head_revision", lambda _cfg: "9999")
    r = client.get("/api/ready")
    assert r.status_code == 503 and "behind" in r.json()["checks"]["migrations"]


def test_the_scheduler_flag_defaults_on_and_the_worker_module_imports():
    from app import worker
    assert get_settings().run_scheduler is True and callable(worker.main)


@pytest.mark.parametrize("given,expected", [
    ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:///x.db", "sqlite:///x.db"),
])
def test_platform_database_urls_are_normalised(given, expected):
    assert Settings(database_url=given).database_url == expected
