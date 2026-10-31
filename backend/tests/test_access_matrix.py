"""Access control, exhaustively: every route is authenticated, and no route lets one user touch another's objects.

The route list is read from the app itself, so a newly added endpoint is covered automatically; it either
requires a session and 404s on someone else's object, or it must be added to PUBLIC with a reason.
"""

import re

import pytest

from app.main import app
from app.public_routes import PUBLIC
from tests.conftest import signup

def api_routes():
    """Every documented operation, from the app's own OpenAPI schema (the routers are mounted lazily)."""
    paths = app.openapi()["paths"]
    return sorted((m.upper(), p) for p, ops in paths.items() for m in ops if m in ("get", "post", "put", "patch", "delete") and p.startswith("/api"))


ROUTES = api_routes()


def test_the_route_table_is_not_empty():
    assert len(ROUTES) > 100


@pytest.mark.parametrize("method,path", [r for r in ROUTES if r not in PUBLIC], ids=lambda x: str(x))
def test_every_non_public_route_rejects_anonymous_callers(client_factory, method, path):
    anon = client_factory()
    url = re.sub(r"\{[^}]+\}", "x", path)
    r = anon.request(method, url, json={} if method in ("POST", "PUT", "PATCH") else None)
    assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a session"


def test_every_public_route_is_a_real_route():
    assert set(PUBLIC) <= set(ROUTES), set(PUBLIC) - set(ROUTES)


# --- one user must not reach another's objects ----------------------------------------------------

def ids_for(owner) -> dict[str, str]:
    """A real id for every kind of path parameter, taken from the owner's own data."""
    get = lambda p: owner.get(p).json()  # noqa: E731
    docs = get("/api/documents")
    doc = next(d for d in docs if d["type"] == "loan_document")
    facts = get(f"/api/documents/{doc['id']}/facts")["facts"]
    cards, emis, pols = get("/api/cards")["cards"], get("/api/emis")["emis"], get("/api/insurance/policies")
    owner.post("/api/goals", json={"name": "Laptop", "target_amount": 90000, "target_date": "2030-01-01"})
    goal = get("/api/goals")["goals"][0]["id"] if isinstance(get("/api/goals"), dict) else get("/api/goals")[0]["id"]
    owner.post("/api/accounts", json={"label": "Other", "bank_name": "B"})
    acct = next(a["id"] for a in get("/api/accounts"))
    txn = get("/api/transactions?limit=1")["items"][0]["id"]
    rem = owner.post("/api/reminders/send-now", json={"object_type": "emi", "object_id": emis[0]["id"]}).json()["id"]
    notif = get("/api/notifications")["items"][0]["id"]
    family = get("/api/family")["members"][0]["id"]
    return {"doc_id": doc["id"], "fact_id": facts[0]["id"], "card_id": cards[0]["id"], "emi_id": emis[0]["id"], "pid": pols[0]["id"],
            "member_id": family, "account_id": acct, "goal_id": goal, "txn_id": txn, "reminder_id": rem, "nid": notif,
            "cid": "x", "item_id": "x", "group_id": "x", "kind": "emi", "object_id": emis[0]["id"], "product_id": "nilgiri-salaried-personal",
            "purpose": "terms", "name": "sample_loan_kfs.pdf"}


@pytest.fixture(scope="module")
def two_users(client_factory):
    owner = client_factory()
    owner.post("/api/demo/workspace")
    owner_ids = ids_for(owner)
    intruder = client_factory()
    signup(intruder)
    return owner_ids, intruder


# Parameters that name catalogue entries or shared enums rather than someone's data.
SHARED_PARAMS = {"product_id", "purpose", "name", "kind", "cid", "item_id", "group_id"}


@pytest.mark.parametrize("method,path", [r for r in ROUTES if r not in PUBLIC and "{" in r[1]], ids=lambda x: str(x))
def test_another_users_objects_are_unreachable(two_users, method, path):
    owner_ids, intruder = two_users
    params = re.findall(r"\{([^}]+)\}", path)
    if all(p in SHARED_PARAMS for p in params):
        pytest.skip("addresses shared catalogue data, not a user's object")
    url = path
    for p in params:
        url = url.replace("{" + p + "}", owner_ids.get(p, "x"))
    body = {} if method in ("POST", "PUT", "PATCH") else None
    # Required query parameters (e.g. ?document_id=…) point at the owner's objects too, so validation can't mask the check.
    spec = app.openapi()["paths"][path][method.lower()]
    query = {q["name"]: owner_ids["doc_id"] if q["name"] == "document_id" else owner_ids.get(q["name"], "x")
             for q in spec.get("parameters", []) if q["in"] == "query" and q.get("required")}
    r = intruder.request(method, url, json=body, params=query)
    assert not (200 <= r.status_code < 300), f"{method} {url} succeeded for a different user ({r.status_code})"
    if method == "GET":
        assert r.status_code == 404, f"GET {url} answered {r.status_code}; expected 404"
    leaked = [v for k, v in owner_ids.items() if k not in SHARED_PARAMS and len(v) > 20 and v in r.text and v not in url]
    assert not leaked, "the response echoes another user's identifiers"
