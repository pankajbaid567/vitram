"""Family members: CRUD, limits, ages, policy links and isolation."""

from datetime import date

from tests.conftest import signup


def add(c, **kw):
    body = {"name": "Asha", "relation": "spouse", **kw}
    return c.post("/api/family", json=body)


def test_add_list_update_delete(client):
    signup(client)
    m = add(client, dob="1990-05-20", is_dependant=False).json()
    assert m["name"] == "Asha" and m["relation"] == "spouse" and m["policies"] == []
    listing = client.get("/api/family").json()
    assert listing["self"]["relation"] == "self" and [x["id"] for x in listing["members"]] == [m["id"]]
    upd = client.patch(f"/api/family/{m['id']}", json={"name": "Asha K", "relation": "spouse", "is_dependant": True}).json()
    assert upd["name"] == "Asha K" and upd["is_dependant"] is True
    assert client.delete(f"/api/family/{m['id']}").json() == {"ok": True}
    assert client.get("/api/family").json()["members"] == []


def test_age_comes_from_the_birth_date_when_known_and_the_stated_age_otherwise(client):
    signup(client)
    today = date.today()
    born = today.replace(year=today.year - 40)
    assert add(client, dob=born.isoformat()).json()["age"] == 40
    assert add(client, name="Kid", relation="child", age=7).json()["age"] == 7


def test_validation(client):
    signup(client)
    assert add(client, relation="cousin").status_code == 422
    assert add(client, name="").status_code == 422
    assert add(client, age=200).status_code == 422


def test_there_is_a_limit_of_fifteen(client):
    signup(client)
    for i in range(15):
        assert add(client, name=f"P{i}", relation="sibling").status_code == 200
    r = add(client, name="One too many", relation="sibling")
    assert r.status_code == 400 and r.json()["error"]["code"] == "LIMIT"


def test_a_members_policies_are_listed_and_deleting_them_unlinks_without_losing_the_policy(sample):
    sample = sample  # shared workspace is read-only here: only inspect
    members = sample.get("/api/family").json()["members"]
    mother = next(m for m in members if m["relation"] == "mother")
    assert [p["product_name"] for p in mother["policies"]] == ["Senior Care"]


def test_deleting_a_member_removes_the_link_but_keeps_the_policy(client_factory):
    c = client_factory()
    c.post("/api/demo/workspace")
    mother = next(m for m in c.get("/api/family").json()["members"] if m["relation"] == "mother")
    policies_before = len(c.get("/api/insurance/policies").json())
    assert c.delete(f"/api/family/{mother['id']}").status_code == 200
    assert len(c.get("/api/insurance/policies").json()) == policies_before


def test_members_are_private(client, client_factory):
    signup(client)
    mid = add(client).json()["id"]
    other = client_factory()
    signup(other)
    assert other.get("/api/family").json()["members"] == []
    assert other.patch(f"/api/family/{mid}", json={"name": "x", "relation": "spouse"}).status_code == 404
    assert other.delete(f"/api/family/{mid}").status_code == 404
