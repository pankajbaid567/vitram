"""Token-bucket throttling: budgets per action, isolation between users, daily AI cap, fail-open, and shared state through Redis."""

import os
import threading
import uuid

import pytest

from app import throttle
from app.config import get_settings
from tests.conftest import signup

REDIS = os.environ.get("TEST_REDIS_URL", "")


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def _fresh():
    throttle.reset()
    yield
    throttle.reset()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "throttle_enabled", True)


def test_classify_picks_a_budget_by_what_the_request_does():
    c = throttle.classify
    assert c("GET", "/api/dashboard") == "read"
    assert c("POST", "/api/goals") == "write"
    assert c("POST", "/api/documents") == "upload"
    assert c("POST", "/api/cards/abc/import-document") == "upload"
    assert c("POST", "/api/ai/chat") == "ai"
    for exempt in ("/api/health", "/api/ready", "/api/metrics", "/api/webhooks/whatsapp"):
        assert c("POST", exempt) is None


def test_bucket_allows_a_burst_then_refills_at_the_sustained_rate():
    clock = Clock()
    b = throttle.MemoryBuckets(clock=clock)
    p = throttle.Policy("t", capacity=3, refill_per_sec=1.0)
    assert [b.take("k", p).allowed for _ in range(3)] == [True, True, True]
    refused = b.take("k", p)
    assert not refused.allowed and refused.retry_after == 1 and refused.remaining == 0
    clock.t += 1
    assert b.take("k", p).allowed                                 # one token came back
    assert not b.take("k", p).allowed
    clock.t += 100
    assert [b.take("k", p).allowed for _ in range(3)] == [True, True, True]   # capped at the burst size, not 100 tokens


def test_users_have_separate_buckets():
    b = throttle.MemoryBuckets(clock=Clock())
    p = throttle.Policy("t", capacity=1, refill_per_sec=0.01)
    assert b.take("u:a", p).allowed and not b.take("u:a", p).allowed
    assert b.take("u:b", p).allowed


def test_identity_prefers_the_session_over_the_ip():
    a = throttle.identity("tok", "1.2.3.4", "9.9.9.9")
    assert a.startswith("u:") and "tok" not in a                  # hashed, never the raw session token
    assert throttle.identity(None, "1.2.3.4", "9.9.9.9") == "ip:1.2.3.4"
    assert throttle.identity(None, None, "9.9.9.9") == "ip:9.9.9.9"


def test_api_answers_429_with_retry_after_once_the_budget_is_spent(client, on, monkeypatch):
    monkeypatch.setitem(throttle.POLICIES, "write", throttle.Policy("write", 3, 0.001))
    signup(client)                                                # spends write tokens too
    codes = [client.post("/api/goals", json={"name": f"g{i}", "target_amount": 100}).status_code for i in range(6)]
    assert 429 in codes and codes[0] in (200, 429)
    r = client.post("/api/goals", json={"name": "x", "target_amount": 100})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) >= 1 and r.headers["RateLimit-Remaining"] == "0" and r.headers.get("X-Request-ID")
    assert client.get("/api/goals").status_code == 200            # reads have their own budget


def test_one_noisy_user_does_not_affect_another(client_factory, on, monkeypatch):
    monkeypatch.setitem(throttle.POLICIES, "write", throttle.Policy("write", 4, 0.001))
    a, b = client_factory(), client_factory()
    signup(a)
    signup(b)
    for _ in range(10):
        a.post("/api/goals", json={"name": "spam", "target_amount": 1})
    assert a.post("/api/goals", json={"name": "spam", "target_amount": 1}).status_code == 429
    assert b.post("/api/goals", json={"name": "fine", "target_amount": 1}).status_code == 200


def test_health_and_readiness_are_never_throttled(client, on, monkeypatch):
    monkeypatch.setitem(throttle.POLICIES, "read", throttle.Policy("read", 1, 0.001))
    assert all(client.get("/api/health").status_code == 200 for _ in range(10))
    assert all(client.get("/api/ready").status_code == 200 for _ in range(10))


def test_daily_assistant_cap(on, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_daily_cap", 3)
    results = [throttle.check("POST", "/api/ai/chat", "tok-day", None, None) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert results[3].reason == "daily"
    assert throttle.check("POST", "/api/ai/chat", "other-user", None, None).allowed


def test_a_broken_redis_fails_open(client, on, monkeypatch):
    pytest.importorskip("redis")
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")      # nothing listens here
    throttle.reset()
    signup(client)
    assert client.get("/api/goals").status_code == 200            # the request is served, not refused
    assert throttle.check("GET", "/api/goals", "tok", None, None) is None


@pytest.mark.skipif(not REDIS, reason="set TEST_REDIS_URL to run against a real Redis (Upstash works)")
def test_redis_buckets_are_atomic_and_shared(monkeypatch):
    be = throttle.RedisBuckets(REDIS, prefix=f"vitram:test:{uuid.uuid4().hex}:", timeout=10)   # generous: the laptop is far from the region
    p = throttle.Policy("t", capacity=5, refill_per_sec=0.001)
    results = []
    threads = [threading.Thread(target=lambda: results.append(be.take("shared", p).allowed)) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 5 and results.count(False) == 15      # exactly the burst, across 20 racing callers
    second = throttle.RedisBuckets(REDIS, prefix=be.prefix, timeout=10)              # another "API instance" sees the same state
    refused = second.take("shared", p)
    assert not refused.allowed and refused.retry_after >= 1
    assert be.day_count("u", 2) and be.day_count("u", 2) and not be.day_count("u", 2)
