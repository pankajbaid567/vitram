"""Query budgets.

* N+1 guard: every read must issue the same number of SQL statements for a user with 1 of each item as for a user with 12.
* Ceiling: a read may not creep above its recorded budget (raise it deliberately, with a reason, never by accident).
"""

import pytest

from app.db import SessionLocal
from app.models import PolicyMember, User, UserPolicy
from tests.conftest import signup
from tests.querycount import count_queries

READS = [
    "/api/dashboard", "/api/documents", "/api/emis", "/api/emis/calendar", "/api/insurance/overview", "/api/insurance/policies",
    "/api/cards", "/api/family", "/api/goals", "/api/notifications",
]

# Statement ceilings measured on the sample workspace; see docs/PERFORMANCE.md.
BUDGET = {
    "/api/dashboard": 17, "/api/documents": 4, "/api/emis": 6, "/api/emis/calendar": 6, "/api/insurance/overview": 6,
    "/api/insurance/policies": 5, "/api/cards": 6, "/api/family": 9, "/api/goals": 4, "/api/notifications": 3,
}


def _counts(c) -> dict[str, int]:
    out = {}
    for path in READS:
        with count_queries() as q:
            r = c.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        out[path] = len(q)
    return out


def _grow(c, email: str, n: int) -> None:
    db = SessionLocal()
    try:
        uid = db.query(User).filter(User.email == email).one().id
        for i in range(n):
            fid = c.post("/api/family", json={"name": f"Member {i}", "relation": "sibling"}).json()["id"]
            assert c.post("/api/emis", json={"title": f"Loan {i}", "amount": 1000 + i, "due_day": 5, "remaining_count": 6}).status_code == 200
            assert c.post("/api/cards", json={"catalogue_id": "horizon-voyager", "nickname": f"Card {i}", "last4": f"{1000 + i}"}).status_code == 200
            assert c.post("/api/goals", json={"name": f"Goal {i}", "target_amount": 50000}).status_code == 200
            pol = UserPolicy(user_id=uid, insurer="Ins", product_name=f"Plan {i}", type="health", status="ready")
            pol.members = [PolicyMember(family_member_id=fid), PolicyMember(family_member_id=None)]
            db.add(pol)
        db.commit()
    finally:
        db.close()


def test_reads_do_not_issue_more_queries_as_data_grows(client):
    me = signup(client)
    _grow(client, me["email"], 1)
    small = _counts(client)
    _grow(client, me["email"], 11)
    big = _counts(client)
    grew = {p: (small[p], big[p]) for p in READS if big[p] > small[p]}
    assert not grew, f"N+1: query count grows with data (1 -> 12 items): {grew}"


@pytest.mark.parametrize("path", READS)
def test_read_stays_within_its_query_budget(sample, path):
    with count_queries() as q:
        r = sample.get(path)
    assert r.status_code == 200
    assert len(q) <= BUDGET[path], f"{path} issued {len(q)} queries (budget {BUDGET[path]}):\n" + "\n".join(s[:110] for s in q)


def test_transactions_keyset_pagination_walks_every_row_once(sample):
    seen, cursor, pages = [], None, 0
    while True:
        url = "/api/transactions?limit=60" + (f"&cursor={cursor}" if cursor else "")
        body = sample.get(url).json()
        if cursor is None:
            total = body["total"]
        else:
            assert body["total"] is None            # counting is only done on the first page
        seen += [t["id"] for t in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages > 1 and len(seen) == total == len(set(seen))
    dates = [t["date"] for t in sample.get("/api/transactions?limit=500").json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_transactions_cursor_rejects_garbage(sample):
    r = sample.get("/api/transactions?cursor=not-a-cursor")
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_CURSOR"


def test_transactions_page_cost_does_not_grow_with_depth(sample):
    first = sample.get("/api/transactions?limit=50").json()
    with count_queries() as shallow:
        sample.get("/api/transactions?limit=50&cursor=" + first["next_cursor"])
    deep_cursor = first
    for _ in range(3):
        deep_cursor = sample.get("/api/transactions?limit=50&cursor=" + deep_cursor["next_cursor"]).json()
    with count_queries() as deep:
        sample.get("/api/transactions?limit=50&cursor=" + deep_cursor["next_cursor"])
    assert len(deep) == len(shallow)
