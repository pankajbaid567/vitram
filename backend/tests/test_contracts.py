"""Response contracts (spec Q1, S7): currency, precision, provenance, catalogue labels, calculation snapshots.

If a route drops one of these guarantees, a test here fails.
"""

import pytest

from app.db import SessionLocal
from app.models import CalculationRun

INTENT = {"purpose": "personal", "amount": 300000, "tenure_months": 36}


@pytest.fixture(scope="module")
def ctx(sample):
    c = sample
    emi = c.get("/api/emis").json()["emis"][0]["id"]
    docs = c.get("/api/documents").json()
    members = c.get("/api/family").json()["members"]
    rec = c.post("/api/loans/recommend", json=INTENT).json()
    return {"c": c, "emi": emi, "docs": docs, "mother": next(m["id"] for m in members if m["relation"] == "mother"),
            "products": [r["product_id"] for r in rec["results"][:2]],
            "policy": c.get("/api/insurance/policies").json()[0]["id"]}


# --- every money-bearing response is explicitly in rupees -----------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/dashboard", None), ("get", "/api/cards", None), ("get", "/api/emis", None), ("get", "/api/emis/calendar", None),
    ("get", "/api/insurance/overview", None), ("get", "/api/forecast", None), ("get", "/api/insights/spending", None),
    ("get", "/api/profile", None), ("get", "/api/loans/catalogue", None), ("get", "/api/cards/catalogue", None),
    ("get", "/api/insurance/catalogue", None),
    ("post", "/api/loans/recommend", INTENT),
    ("post", "/api/cards/best-for-spend", {"amount": 5000, "category": "travel"}),
])
def test_money_responses_declare_inr(ctx, method, path, body):
    r = getattr(ctx["c"], method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 200, (path, r.text[:200])
    assert r.json()["currency"] == "INR", path


# --- calculators: precision, formula version, and a snapshot that can be cited -----------------

def calculators(ctx):
    p = ctx["products"][0]
    return [
        ("loan.recommend", "post", "/api/loans/recommend", INTENT),
        ("loan.compare", "post", "/api/loans/compare", {"product_ids": ctx["products"], "intent": INTENT}),
        ("loan.cost", "post", "/api/loans/calculate", {"kind": "cost", "product_id": p, "principal": 300000, "tenure_months": 36}),
        ("loan.prepayment", "post", "/api/loans/calculate", {"kind": "prepayment", "product_id": p, "principal": 300000, "tenure_months": 36, "prepay_amount": 50000, "after_month": 12}),
        ("loan.missed_payment", "post", "/api/loans/calculate", {"kind": "missed_payment", "product_id": p, "principal": 300000, "tenure_months": 36, "days_late": 10}),
        ("loan.tenure_change", "post", "/api/loans/calculate", {"kind": "tenure_change", "product_id": p, "principal": 300000, "tenure_months": 36, "new_tenure_months": 48}),
        ("loan.rate_change", "post", "/api/loans/calculate", {"kind": "rate_change", "product_id": p, "principal": 300000, "tenure_months": 36, "new_rate_pct": 13}),
        ("loan.affordability", "post", "/api/loans/calculate", {"kind": "affordability", "product_id": p, "principal": 300000, "tenure_months": 36}),
        ("cards.best_for_spend", "post", "/api/cards/best-for-spend", {"amount": 8000, "category": "travel"}),
        ("emi.missed_payment", "post", f"/api/emis/{ctx['emi']}/what-if", {"kind": "missed_payment", "days_late": 10}),
        ("emi.prepayment", "post", f"/api/emis/{ctx['emi']}/what-if", {"kind": "prepayment", "prepay_amount": 10000}),
        ("emi.explore", "post", "/api/emis/explore", {"options": [{"label": "A", "amount": 40000, "tenure_months": 12, "rate": 14}]}),
    ]


def test_every_calculator_leaves_a_citable_snapshot(ctx):
    c = ctx["c"]
    for kind, method, path, body in calculators(ctx):
        r = getattr(c, method)(path, json=body)
        assert r.status_code == 200, (kind, r.text[:200])
        out = r.json()
        assert out["currency"] == "INR", kind
        rid = out.get("calculation_id")
        assert rid, f"{kind} must return the id of its calculation snapshot"
        db = SessionLocal()
        try:
            run = db.get(CalculationRun, rid)
            assert run is not None and run.kind == kind
            assert run.inputs and run.outputs and run.formula_version, kind
        finally:
            db.close()


def test_what_if_results_state_their_assumptions_and_version(ctx):
    c, p = ctx["c"], ctx["products"][0]
    out = c.post("/api/loans/calculate", json={"kind": "prepayment", "product_id": p, "principal": 300000, "tenure_months": 36,
                                               "prepay_amount": 50000, "after_month": 12}).json()
    assert out["precision"] == 2
    res = out["result"]
    assert res["formula_version"] and res["computable"] is True and "assumptions" in res and "missing" in res


# --- catalogue-backed answers are labelled as sample data -----------------------------------------

def test_loan_options_carry_catalogue_provenance(ctx):
    for opt in ctx["c"].post("/api/loans/recommend", json=INTENT).json()["results"]:
        cat = opt["catalogue"]
        assert cat["is_mock"] is True and cat["last_updated"] and cat["source"], opt["product_id"]


def test_card_catalogue_rows_are_labelled(ctx):
    for card in ctx["c"].get("/api/cards").json()["cards"]:
        assert card["catalogue"]["is_mock"] is True and card["catalogue"]["last_updated"]


def labelled(entry):
    """Priced catalogue data is fictional (`is_mock`); real-institution entries must be reference-only: a name and an
    official link with a verification date, and no invented numbers."""
    meta = entry["catalogue"]
    assert meta["last_updated"] and meta["source"], entry["id"]
    if meta["is_mock"]:
        return "mock"
    assert entry.get("reference_only") is True and entry.get("official_url") and entry.get("verified_at"), entry["id"]
    return "reference"


def test_insurance_catalogue_is_either_labelled_sample_data_or_reference_only(ctx):
    products = ctx["c"].get("/api/insurance/catalogue").json()["products"]
    kinds = {labelled(p) for p in products}
    assert kinds == {"mock", "reference"}   # both kinds exist, and each is honest about what it is


def test_card_catalogue_is_either_labelled_sample_data_or_reference_only(ctx):
    products = ctx["c"].get("/api/cards/catalogue").json()["products"]
    assert {labelled(p) for p in products} == {"mock", "reference"}
    for p in products:
        if p["reference_only"]:
            assert p["annual_fee"] is None and p["reward_unit"] is None, "reference entries must not carry invented numbers"


# --- material facts open their source -----------------------------------------------------------------

def test_extracted_facts_carry_a_source(ctx):
    c = ctx["c"]
    for d in ctx["docs"]:
        if d["type"] == "bank_statement":
            continue
        facts = c.get(f"/api/documents/{d['id']}/facts").json()["facts"]
        assert facts, d["display_name"]
        for f in facts:
            cite = f["citation"]
            assert cite["document_id"] == d["id"] and cite["page"] and cite["snippet"], (d["display_name"], f["key"])
            assert f["state"] in ("extracted", "confirmed", "conflicted", "missing")


def test_emergency_coverage_values_are_cited(ctx):
    out = ctx["c"].post("/api/insurance/emergency", json={"member_key": ctx["mother"], "event": "hospitalisation"}).json()
    assert out["currency"] == "INR" and out["policies"]
    for entry in out["policies"]:
        for name in ("sum_insured", "copay", "room_rent"):
            item = entry["coverage"].get(name)
            if item and item.get("value") is not None:
                assert item["citation"]["page"], name
