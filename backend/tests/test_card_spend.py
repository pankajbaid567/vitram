"""Card statement purchases → reward estimate: only confirmed rows count, per category, reversibly."""

import io

import pytest
from reportlab.pdfgen import canvas

from tests.conftest import signup

LINES = [
    "Card ending 4821", "Payment due date: 25/10/2026", "Total amount due Rs 12,500.00",
    "20/09/2026 PURCHASE SWIGGY Rs 1,000.00",
    "21/09/2026 PURCHASE ZOMATO Rs 500.00",
    "22/09/2026 PURCHASE MAKEMYTRIP Rs 8,000.00",
    "23/09/2026 PURCHASE BOOK SHOP Rs 250.00",
]


def pdf(lines):
    buf = io.BytesIO()
    page = canvas.Canvas(buf)
    for i, line in enumerate(lines):
        page.drawString(50, 750 - i * 25, line)
    page.save()
    return buf.getvalue()


@pytest.fixture
def stmt(client):
    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    doc = client.post("/api/documents", data={"type": "card_document"}, files={"file": ("c.pdf", pdf(LINES), "application/pdf")}).json()
    facts = {f["key"]: f for f in client.get(f"/api/documents/{doc['id']}/facts").json()["facts"]}
    card = client.post("/api/cards", json={"catalogue_id": "horizon-voyager", "nickname": "Voyager", "last4": "4821"}).json()
    return client, doc["id"], facts, card["id"]


def confirm(client, doc_id, fact):
    assert client.patch(f"/api/documents/{doc_id}/facts/{fact['id']}", json={"confirm_only": True}).status_code == 200


def test_nothing_counts_until_the_card_ending_is_confirmed(stmt):
    c, doc, facts, card = stmt
    r = c.get(f"/api/cards/{card}/spend-reconciliation", params={"document_id": doc})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CARD_FACTS_UNREVIEWED"


def test_unconfirmed_and_rejected_rows_never_count(stmt):
    c, doc, facts, card = stmt
    confirm(c, doc, facts["last4"])
    confirm(c, doc, facts["purchase_1"])                                          # Swiggy: confirmed
    c.post(f"/api/documents/{doc}/facts/{facts['purchase_2']['id']}/reject")      # Zomato: rejected
    # purchase_3 (MakeMyTrip) and purchase_4 stay unconfirmed
    p = c.get(f"/api/cards/{card}/spend-reconciliation", params={"document_id": doc}).json()
    assert p["currency"] == "INR"
    assert [r["merchant"] for r in p["counted_rows"]] == ["SWIGGY"]
    assert p["by_category"] == {"food_delivery": 1000.0} and p["total"] == 1000.0
    assert p["unconfirmed_rows"] == 2 and p["rejected_rows"] == 1
    assert c.get("/api/cards").json()["cards"][0]["imported_spend"] is None, "a preview changes nothing"


def test_applying_groups_by_category_keeps_manual_spend_and_is_reversible(stmt):
    c, doc, facts, card = stmt
    for key in ("last4", "purchase_1", "purchase_2", "purchase_3"):
        confirm(c, doc, facts[key])
    # the user had typed some travel spend by hand
    c.patch(f"/api/cards/{card}", json={"catalogue_id": "horizon-voyager", "nickname": "Voyager", "last4": "4821", "cycle_spend": {"travel": 2000}})
    out = c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc}).json()
    assert out["imported_spend"]["by_category"] == {"food_delivery": 1500.0, "travel": 8000.0} and out["imported_spend"]["rows"] == 3
    shown = out["card"]
    assert shown["cycle_spend"] == {"travel": 2000.0}, "manual entries are untouched"
    assert shown["effective_cycle_spend"] == {"travel": 10000.0, "food_delivery": 1500.0}

    undone = c.delete(f"/api/cards/{card}/spend-reconciliation").json()
    assert undone["removed"] is True and undone["card"]["effective_cycle_spend"] == {"travel": 2000.0}
    assert c.delete(f"/api/cards/{card}/spend-reconciliation").json()["removed"] is False


def test_reconciled_spend_changes_the_reward_estimate_through_caps(stmt):
    c, doc, facts, card = stmt
    before = c.post("/api/cards/best-for-spend", json={"amount": 48000, "category": "travel"}).json()
    for key in ("last4", "purchase_3"):
        confirm(c, doc, facts[key])
    c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc})
    after = c.post("/api/cards/best-for-spend", json={"amount": 48000, "category": "travel"}).json()
    voy = lambda r: next(x for x in r["ranked"] + r["unranked"] if x["card_id"] == card)  # noqa: E731
    # Voyager: 10 miles per ₹100 on travel, capped at 5,000 accelerated miles a month.
    assert voy(before)["reward_units"] == 4800.0                                  # ₹48,000 fits under the cap
    assert voy(after)["reward_units"] < 4800.0, "₹8,000 already spent this cycle uses up 800 of the 5,000-mile cap"


def test_wrong_card_and_foreign_documents_are_refused(stmt, client_factory):
    c, doc, facts, card = stmt
    confirm(c, doc, facts["last4"])
    other = c.post("/api/cards", json={"catalogue_id": "horizon-voyager", "nickname": "Other", "last4": "9999"}).json()["id"]
    r = c.get(f"/api/cards/{other}/spend-reconciliation", params={"document_id": doc})
    assert r.status_code == 400 and r.json()["error"]["code"] == "CARD_LAST4_MISMATCH"
    stranger = client_factory()
    signup(stranger)
    assert stranger.get(f"/api/cards/{card}/spend-reconciliation", params={"document_id": doc}).status_code == 404


def test_deleting_the_statement_withdraws_its_spend(stmt):
    c, doc, facts, card = stmt
    for key in ("last4", "purchase_1"):
        confirm(c, doc, facts[key])
    c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc})
    assert c.get("/api/cards").json()["cards"][0]["imported_spend"]
    assert c.delete(f"/api/documents/{doc}").status_code == 200
    assert c.get("/api/cards").json()["cards"][0]["imported_spend"] is None


def test_a_second_statement_needs_explicit_replacement(stmt):
    c, doc, facts, card = stmt
    for key in ("last4", "purchase_1"):
        confirm(c, doc, facts[key])
    c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc})
    doc2 = c.post("/api/documents", data={"type": "card_document"},
                  files={"file": ("c2.pdf", pdf(LINES[:3] + ["24/09/2026 PURCHASE SWIGGY Rs 700.00"]), "application/pdf")}).json()["id"]
    f2 = {f["key"]: f for f in c.get(f"/api/documents/{doc2}/facts").json()["facts"]}
    for key in ("last4", "purchase_1"):
        confirm(c, doc2, f2[key])
    blocked = c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc2})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "SPEND_IMPORT_CONFLICT"
    ok = c.post(f"/api/cards/{card}/spend-reconciliation", json={"document_id": doc2, "replace_existing": True})
    assert ok.status_code == 200 and ok.json()["imported_spend"]["total"] == 700.0
