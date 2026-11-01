"""Failure behaviour: circuit breaker, bulkhead, retry budget, load shedding, and the gateway path under a dead dependency."""

import threading
import time

import httpx
import pytest

from app import main, resilience
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job
from app.services import jobs
from app.services.channels import openwa
from app.services.channels.gateway import SendError
from tests.conftest import signup


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_circuit_opens_after_threshold_then_probes_then_closes():
    clock = Clock()
    cb = resilience.CircuitBreaker("unit-a", failure_threshold=3, window=60, cooldown=30, clock=clock)
    for _ in range(3):
        cb.before()
        cb.failure()
    assert cb.state == resilience.OPEN
    with pytest.raises(resilience.CircuitOpen):
        cb.before()                                         # fails fast, the dependency is not called
    clock.t += 31
    assert cb.state == resilience.HALF_OPEN
    cb.before()                                             # the single probe
    with pytest.raises(resilience.CircuitOpen):
        cb.before()                                         # no second probe while one is in flight
    cb.success()
    assert cb.state == resilience.CLOSED
    cb.before()


def test_failed_probe_reopens_for_a_full_cooldown():
    clock = Clock()
    cb = resilience.CircuitBreaker("unit-b", failure_threshold=1, cooldown=30, clock=clock)
    cb.before()
    cb.failure()
    clock.t += 31
    cb.before()
    cb.failure()                                            # the probe failed
    assert cb.state == resilience.OPEN
    clock.t += 29
    assert cb.state == resilience.OPEN
    clock.t += 2
    assert cb.state == resilience.HALF_OPEN


def test_old_failures_age_out_of_the_window():
    clock = Clock()
    cb = resilience.CircuitBreaker("unit-c", failure_threshold=3, window=60, clock=clock)
    for _ in range(2):
        cb.before()
        cb.failure()
    clock.t += 61
    cb.before()
    cb.failure()                                            # only one failure inside the window
    assert cb.state == resilience.CLOSED


def test_bulkhead_refuses_beyond_capacity():
    b = resilience.Bulkhead("unit-d", 1)
    with b:
        with pytest.raises(resilience.Overloaded):
            with b:
                pass
    with b:                                                 # released after use
        pass


def test_retry_budget_caps_retries_to_a_fraction_of_traffic():
    clock = Clock()
    rb = resilience.RetryBudget(ratio=0.1, window=60, min_per_window=1, clock=clock)
    for _ in range(100):
        rb.record_call()
    allowed = sum(rb.allow_retry() for _ in range(50))
    assert allowed == 10                                    # 10% of 100 calls
    clock.t += 61
    assert rb.allow_retry() is True                         # the window moved on


def _dead_gateway(monkeypatch, calls):
    def boom(*a, **k):
        calls.append(1)
        raise httpx.ConnectError("gateway down")

    monkeypatch.setattr(openwa.httpx, "post", boom)
    s = get_settings()
    for k, v in (("openwa_base_url", "http://gw.invalid"), ("openwa_api_key", "k" * 40), ("openwa_session_id", "sid")):
        monkeypatch.setattr(s, k, v)


def test_dead_gateway_opens_the_circuit_and_stops_being_called(monkeypatch):
    resilience.reset_all()
    resilience.breaker("openwa", failure_threshold=3, cooldown=0.2)
    calls: list[int] = []
    _dead_gateway(monkeypatch, calls)
    gw = openwa.OpenWAGateway() if hasattr(openwa, "OpenWAGateway") else openwa.OpenWaGateway()
    for _ in range(3):
        with pytest.raises(SendError, match="Network error"):
            gw.send_text("+919876543210", "hi")
    assert len(calls) == 3
    with pytest.raises(SendError) as exc:
        gw.send_text("+919876543210", "hi")
    assert exc.value.retryable is True and "paused" in str(exc.value)
    assert len(calls) == 3                                  # failed fast: no network call while open

    time.sleep(0.25)                                        # cooldown over: one probe goes out
    monkeypatch.setattr(openwa.httpx, "post", lambda *a, **k: httpx.Response(200, json={"messageId": "m1"},
                                                                              request=httpx.Request("POST", "http://gw.invalid")))
    assert gw.send_text("+919876543210", "hi") == "m1"
    assert resilience.breaker("openwa").state == resilience.CLOSED
    resilience.reset_all()


def test_a_rejected_destination_does_not_count_against_the_gateway(monkeypatch):
    resilience.reset_all()
    resilience.breaker("openwa", failure_threshold=2, cooldown=60)
    calls: list[int] = []
    _dead_gateway(monkeypatch, calls)
    gw = openwa.OpenWAGateway() if hasattr(openwa, "OpenWAGateway") else openwa.OpenWaGateway()
    for _ in range(5):
        with pytest.raises(SendError, match="Invalid"):
            gw.send_text("12", "hi")
    assert resilience.breaker("openwa").state == resilience.CLOSED
    resilience.reset_all()


def test_load_shedding_refuses_new_work_but_keeps_health_endpoints(client, monkeypatch):
    signup(client)
    monkeypatch.setattr(get_settings(), "max_inflight_requests", 0)
    r = client.get("/api/dashboard")
    assert r.status_code == 503 and r.headers["Retry-After"] == "10" and r.json()["error"]["code"] == "BUSY"
    assert r.headers.get("X-Request-ID")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ready").status_code == 200


def test_uploads_are_refused_while_the_job_queue_is_backed_up(client, monkeypatch):
    signup(client)
    db = SessionLocal()
    db.query(Job).delete()
    for i in range(3):
        jobs.enqueue(db, "noop", {"i": i})
    db.commit()
    monkeypatch.setattr(get_settings(), "max_queued_jobs", 3)
    main._queue_depth_cache = (0.0, 0)
    r = client.post("/api/documents", data={"type": "bank_statement"}, files={"file": ("a.csv", b"x", "text/csv")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "BUSY"
    assert client.get("/api/goals").status_code == 200       # reads are unaffected
    db.query(Job).delete()
    db.commit()
    db.close()
    main._queue_depth_cache = (0.0, 0)


def test_bulkhead_prevents_a_slow_dependency_from_taking_every_thread():
    b = resilience.Bulkhead("unit-e", 2)
    gate, started, refused = threading.Event(), threading.Barrier(3), []

    def slow():
        try:
            with b:
                started.wait(timeout=5)
                gate.wait(timeout=5)
        except resilience.Overloaded:
            refused.append(1)

    holders = [threading.Thread(target=slow) for _ in range(2)]
    [t.start() for t in holders]
    started.wait(timeout=5)                                 # both slots are held
    with pytest.raises(resilience.Overloaded):
        with b:
            pass
    gate.set()
    [t.join() for t in holders]
    assert not refused
