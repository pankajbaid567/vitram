"""Server-side cache: correct invalidation matters more than the hit rate, so most of these tests are about staleness."""

import os

import pytest

from app import cache
from app.config import get_settings
from tests.conftest import signup
from tests.querycount import count_queries

REDIS = os.environ.get("TEST_REDIS_URL", "")


@pytest.fixture(autouse=True)
def _fresh():
    cache.reset()
    yield
    cache.reset()


def test_second_dashboard_read_is_served_from_cache_with_far_fewer_queries(client):
    signup(client)
    client.get("/api/dashboard")                              # first build also writes the financial profile, which bumps the version
    client.get("/api/dashboard")                              # builds again under the settled version and stores it
    with count_queries() as warm:
        r = client.get("/api/dashboard")
    cache.reset()
    with count_queries() as cold:
        client.get("/api/dashboard")
    assert r.status_code == 200
    assert len(warm) <= 3 and len(cold) >= 10, (len(warm), len(cold))   # session + user lookups only vs the full build


def test_a_change_to_the_users_data_invalidates_immediately(client):
    signup(client)
    before = client.get("/api/dashboard").json()
    assert client.get("/api/dashboard").json() == before        # cached
    e = client.post("/api/emis", json={"title": "Bike", "amount": 4200, "due_day": 10, "remaining_count": 18, "rate": 11})
    assert e.status_code == 200
    after = client.get("/api/dashboard").json()
    assert after != before, "the dashboard must reflect the new EMI right away"


def test_changing_the_users_own_row_invalidates(client):
    me = signup(client)
    assert client.get("/api/dashboard").json()["user"]["name"] == me["name"]
    client.patch("/api/onboarding/about", json={"name": "Renamed Person"})
    assert client.get("/api/dashboard").json()["user"]["name"] == "Renamed Person"


def test_users_never_see_each_others_cached_dashboard(client_factory):
    a, b = client_factory(), client_factory()
    signup(a, name="Alice A")
    signup(b, name="Bob B")
    assert a.get("/api/dashboard").json()["user"]["name"] == "Alice A"
    assert b.get("/api/dashboard").json()["user"]["name"] == "Bob B"
    assert a.get("/api/dashboard").json()["user"]["name"] == "Alice A"


def test_rolled_back_changes_do_not_invalidate(client):
    from app.db import SessionLocal
    from app.models import User

    me = signup(client)
    client.get("/api/dashboard")
    db = SessionLocal()
    uid = db.query(User).filter(User.email == me["email"]).one().id
    v0 = cache.store().version(uid)
    u = db.get(User, uid)
    u.name = "never committed"
    db.flush()
    db.rollback()
    db.close()
    assert cache.store().version(uid) == v0


def test_entries_expire_after_the_ttl_backstop():
    clock = [100.0]
    st = cache.MemoryStore(clock=lambda: clock[0])
    st.set("k", "v", ttl=30)
    assert st.get("k") == "v"
    clock[0] += 31
    assert st.get("k") is None


def test_cache_can_be_switched_off(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_enabled", False)
    signup(client)
    client.get("/api/dashboard")
    with count_queries() as q:
        client.get("/api/dashboard")
    assert len(q) >= 10


def test_a_broken_redis_is_a_cache_miss_not_an_error(client, monkeypatch):
    pytest.importorskip("redis")
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")
    cache.reset()
    signup(client)
    assert client.get("/api/dashboard").status_code == 200


@pytest.mark.parametrize("path", ["/api/loans/catalogue", "/api/cards/catalogue", "/api/insurance/catalogue"])
def test_catalogues_use_etags_and_answer_304(client, path):
    signup(client)
    first = client.get(path)
    assert first.status_code == 200 and "max-age" in first.headers["cache-control"] and first.headers["etag"]
    again = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    changed = client.get(path, headers={"If-None-Match": '"something-else"'})
    assert changed.status_code == 200 and changed.json() == first.json()


def test_user_specific_responses_stay_uncacheable(client):
    signup(client)
    assert client.get("/api/dashboard").headers["cache-control"] == "no-store"


@pytest.mark.skipif(not REDIS, reason="set TEST_REDIS_URL to run against a real Redis (Upstash works)")
def test_redis_store_versions_and_values_are_shared_between_instances():
    a = cache.RedisStore(REDIS, prefix="vitram:test:cache:")
    b = cache.RedisStore(REDIS, prefix="vitram:test:cache:")
    a._r.connection_pool.connection_kwargs["socket_timeout"] = 10
    b._r.connection_pool.connection_kwargs["socket_timeout"] = 10
    v = a.version("u-test")
    a.set("x", "1", ttl=30)
    assert b.get("x") == "1"
    b.bump("u-test")
    assert a.version("u-test") == v + 1


def test_writing_audit_logs_does_not_throw_away_cached_pages(client):
    me = signup(client)
    client.get("/api/dashboard")
    client.get("/api/dashboard")
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    uid = db.query(User).filter(User.email == me["email"]).one().id
    v0 = cache.store().version(uid)
    client.post("/api/loans/recommend", json={"purpose": "personal", "amount": 300000})   # records a calculation_runs row
    assert cache.store().version(uid) == v0
    db.close()
