"""Metrics endpoint, readiness queue signals and tracing."""

from app import metrics
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job
from app.services import jobs
from tests.conftest import signup


def test_metrics_endpoint_is_off_without_a_token(client):
    assert get_settings().metrics_token == ""
    assert client.get("/api/metrics").status_code == 404


def test_metrics_endpoint_needs_the_bearer_token(client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret-token-for-tests")
    get_settings.cache_clear()
    try:
        assert client.get("/api/metrics").status_code == 401
        assert client.get("/api/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        client.get("/api/health")
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope"})
        r = client.get("/api/metrics", headers={"Authorization": "Bearer s3cret-token-for-tests"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
        body = r.text
        assert 'vitram_http_requests_total{method="GET",route="/api/health",status="2xx"}' in body
        assert "vitram_http_request_duration_seconds_bucket" in body
        assert "vitram_jobs_oldest_queued_age_seconds" in body and 'vitram_jobs{status="queued"}' in body
        for secret in ("x@example.com", "nope"):
            assert secret not in body                       # labels are templates and status classes, never user data
    finally:
        get_settings.cache_clear()


def test_route_labels_use_templates_not_ids(client):
    me = signup(client)
    g = client.post("/api/goals", json={"name": "Laptop", "target_amount": 1000}).json()
    client.get(f"/api/goals/{g['id']}")
    text = metrics.render()[0].decode()
    assert g["id"] not in text and me["email"] not in text


def test_readiness_reports_queue_depth_and_staleness(client):
    db = SessionLocal()
    db.query(Job).delete()
    db.commit()
    body = client.get("/api/ready").json()
    assert body["checks"]["jobs"] == {"state": "ok", "queued": 0, "dead": 0, "oldest_queued_age_seconds": None}
    from datetime import datetime, timedelta, timezone

    jobs.enqueue(db, "noop", {}, run_after=datetime.now(timezone.utc) - timedelta(hours=1))
    db.commit()
    body = client.get("/api/ready").json()
    assert body["checks"]["jobs"]["state"] == "stale" and body["checks"]["jobs"]["queued"] == 1
    assert body["ready"] is True                            # a stalled worker is an alert, not a reason to stop serving
    db.query(Job).delete()
    db.commit()
    db.close()


def test_job_outcomes_are_counted(client):
    db = SessionLocal()
    db.query(Job).delete()
    jobs.register("metric_ok", lambda p: None)
    jobs.enqueue(db, "metric_ok", {})
    db.commit()
    before = _sample("vitram_jobs_finished_total", kind="metric_ok", outcome="done")
    assert jobs.run_next("w") is True
    assert _sample("vitram_jobs_finished_total", kind="metric_ok", outcome="done") == before + 1
    db.close()


def _sample(name, **labels):
    for fam in metrics.registry.collect():
        for s in fam.samples:
            if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                return s.value
    return 0


def test_tracing_emits_server_sql_and_request_id_spans():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import tracing

    exporter = InMemorySpanExporter()
    traced = FastAPI()

    @traced.get("/ping")
    def ping():
        from sqlalchemy import text

        from app.db import engine

        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"ok": True}

    assert tracing.setup(traced, exporter=exporter) is True
    with TestClient(traced) as c:
        assert c.get("/ping").status_code == 200
    names = [s.name for s in exporter.get_finished_spans()]
    assert any("GET" in n and "ping" in n for n in names), names
    sql = [sp for sp in exporter.get_finished_spans() if sp.name.startswith("SQL ")]
    assert sql and sql[0].attributes["db.statement"] == "SELECT 1"
    assert all("db.parameters" not in sp.attributes for sp in sql)
