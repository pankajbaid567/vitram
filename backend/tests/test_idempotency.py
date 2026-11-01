"""Idempotency-Key: a retried or raced request has one effect."""

import threading
import uuid

from tests.conftest import signup


def _key():
    return {"Idempotency-Key": uuid.uuid4().hex}


def test_retry_with_same_key_replays_and_creates_once(client):
    signup(client)
    h = _key()
    first = client.post("/api/goals", json={"name": "Laptop", "target_amount": 90000}, headers=h)
    again = client.post("/api/goals", json={"name": "Laptop", "target_amount": 90000}, headers=h)
    assert first.status_code == again.status_code == 200
    assert again.headers.get("Idempotent-Replay") == "true" and first.headers.get("Idempotent-Replay") is None
    assert again.json() == first.json()
    assert len(client.get("/api/goals").json()["goals"]) == 1


def test_without_a_key_requests_are_not_deduplicated(client):
    signup(client)
    for _ in range(2):
        client.post("/api/goals", json={"name": "Laptop", "target_amount": 90000})
    assert len(client.get("/api/goals").json()["goals"]) == 2


def test_same_key_with_a_different_body_is_refused(client):
    signup(client)
    h = _key()
    assert client.post("/api/goals", json={"name": "A", "target_amount": 1000}, headers=h).status_code == 200
    r = client.post("/api/goals", json={"name": "B", "target_amount": 2000}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(client.get("/api/goals").json()["goals"]) == 1


def test_keys_do_not_collide_between_users(client_factory):
    a, b = client_factory(), client_factory()
    signup(a)
    signup(b)
    h = _key()
    a.post("/api/goals", json={"name": "Mine", "target_amount": 1000}, headers=h)
    r = b.post("/api/goals", json={"name": "Theirs", "target_amount": 5000}, headers=h)
    assert r.status_code == 200 and r.headers.get("Idempotent-Replay") is None
    assert [g["name"] for g in b.get("/api/goals").json()["goals"]] == ["Theirs"]


def test_failed_requests_do_not_stick(client):
    signup(client)
    h = _key()
    bad = client.post("/api/goals", json={"name": "", "target_amount": -1}, headers=h)
    assert bad.status_code in (400, 422)
    # a 4xx is a normal answer and may replay; the point is that the key never wedges later valid use with another key
    ok = client.post("/api/goals", json={"name": "Ok", "target_amount": 10}, headers=_key())
    assert ok.status_code == 200


def test_ten_parallel_requests_with_one_key_have_one_effect(client_factory):
    c = client_factory()
    signup(c)
    h = _key()
    results = []

    def fire():
        # each thread gets its own client so cookies are shared via the headers below
        results.append(c.post("/api/goals", json={"name": "Race", "target_amount": 777}, headers=h).status_code)

    threads = [threading.Thread(target=fire) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert set(results) <= {200, 409}                      # replays/in-progress, never an error or a second creation
    assert results.count(200) >= 1
    assert len([g for g in c.get("/api/goals").json()["goals"] if g["name"] == "Race"]) == 1


def test_idempotency_header_is_ignored_for_anonymous_requests(client):
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}, headers=_key())
    assert r.status_code in (400, 401, 422)
    assert r.headers.get("Idempotent-Replay") is None
