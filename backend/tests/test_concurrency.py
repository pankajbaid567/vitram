"""Optimistic concurrency: no lost updates on editable records."""

import threading

import pytest

from app.db import SessionLocal
from app.models import Goal
from tests.conftest import signup


def _goal(c, name="Laptop"):
    return c.post("/api/goals", json={"name": name, "target_amount": 90000}).json()


def test_records_carry_a_version_that_increases_on_each_change(client):
    signup(client)
    g = _goal(client)
    assert g["version"] == 1
    g2 = client.patch(f"/api/goals/{g['id']}", json={"name": "Laptop 2"}).json()
    assert g2["version"] == 2


def test_if_match_with_the_current_version_succeeds(client):
    signup(client)
    g = _goal(client)
    r = client.patch(f"/api/goals/{g['id']}", json={"name": "New"}, headers={"If-Match": f'"{g["version"]}"'})
    assert r.status_code == 200 and r.json()["name"] == "New"


def test_stale_if_match_is_refused_with_the_current_version_and_nothing_is_written(client):
    signup(client)
    g = _goal(client)
    client.patch(f"/api/goals/{g['id']}", json={"name": "Edited elsewhere"})           # version 1 -> 2
    r = client.patch(f"/api/goals/{g['id']}", json={"name": "My stale edit"}, headers={"If-Match": '"1"'})
    assert r.status_code == 412
    err = r.json()["error"]
    assert err["code"] == "STALE_VERSION" and err["details"]["current_version"] == 2
    assert client.get("/api/goals").json()["goals"][0]["name"] == "Edited elsewhere"


def test_omitting_if_match_keeps_last_write_wins(client):
    signup(client)
    g = _goal(client)
    assert client.patch(f"/api/goals/{g['id']}", json={"name": "A"}).status_code == 200
    assert client.patch(f"/api/goals/{g['id']}", json={"name": "B"}).status_code == 200


@pytest.mark.parametrize("path,body,make", [
    ("/api/family", {"name": "Asha", "relation": "spouse"}, lambda c, b: c.post("/api/family", json=b).json()),
    ("/api/emis", {"title": "Bike", "amount": 4200, "due_day": 10, "remaining_count": 18, "rate": 11}, lambda c, b: c.post("/api/emis", json=b).json()),
])
def test_other_editable_records_enforce_if_match(client, path, body, make):
    signup(client)
    rec = make(client, body)
    assert rec["version"] == 1
    assert client.patch(f"{path}/{rec['id']}", json={**body, "name" if "name" in body else "title": "Changed"}).status_code == 200
    stale = client.patch(f"{path}/{rec['id']}", json=body, headers={"If-Match": '"1"'})
    assert stale.status_code == 412


def test_database_refuses_a_write_from_a_stale_copy(client):
    """Layer two: even without the header, two sessions that loaded the same row cannot both write it."""
    from sqlalchemy.orm.exc import StaleDataError

    signup(client)
    g = _goal(client)
    a, b = SessionLocal(), SessionLocal()
    try:
        ga, gb = a.get(Goal, g["id"]), b.get(Goal, g["id"])
        ga.name = "from A"
        a.commit()
        gb.name = "from B"
        with pytest.raises(StaleDataError):
            b.commit()
    finally:
        a.close()
        b.close()


def test_simultaneous_patches_never_both_win_silently(client):
    """Ten simultaneous edits using the same If-Match: exactly one wins, the rest get 412 or 409."""
    signup(client)
    g = _goal(client)
    codes = []

    def edit(i):
        codes.append(client.patch(f"/api/goals/{g['id']}", json={"name": f"edit {i}"}, headers={"If-Match": '"1"'}).status_code)

    threads = [threading.Thread(target=edit, args=(i,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(200) == 1, codes
    assert set(codes) <= {200, 409, 412}
    assert client.get("/api/goals").json()["goals"][0]["version"] == 2
