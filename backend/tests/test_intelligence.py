"""M13 — statement intelligence, cash-flow estimate, goals, reminders per item, password reset, card benefits."""

from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from app.config import get_settings
from app.models import Goal
from app.routers.goals import progress
from app.services import mailer, pipeline
from tests.conftest import signup
from tests.test_vision import fake_ocr, png_bytes, upload


def consent(c):
    assert c.post("/api/consents", json={"purpose": "financial_documents"}).status_code == 200


def statement_csv() -> bytes:
    rows, bal = [], 20000.0

    def add(d, desc, debit=0.0, credit=0.0):
        nonlocal bal
        bal += credit - debit
        rows.append(f"{d},{desc},{debit or ''},{credit or ''},{bal:.2f}")

    for m in (5, 6, 7, 8):
        add(f"01/{m:02d}/2026", "SALARY ACME CORP", credit=90000)
        add(f"03/{m:02d}/2026", "RENT TRANSFER TO LANDLORD", debit=25000)
        add(f"05/{m:02d}/2026", "NETFLIX.COM SUBSCRIPTION", debit=649)
        for day, amt in ((8, 380), (12, 420), (18, 410), (24, 390)):
            add(f"{day:02d}/{m:02d}/2026", "UPI SWIGGY ORDER", debit=amt)
    add("26/08/2026", "UPI SWIGGY ORDER PARTY", debit=3500)
    add("20/08/2026", "AMAZON PAY INDIA", debit=1299)
    add("20/08/2026", "AMAZON PAY INDIA", debit=1299)
    add("31/08/2026", "UPI GROCER", debit=100)
    return ("Date,Narration,Debit,Credit,Balance\n" + "\n".join(rows)).encode()


@pytest.fixture
def csv_user(client):
    signup(client)
    consent(client)
    r = client.post("/api/documents", data={"type": "bank_statement", "period_months": "3", "account_label": "Salary"},
                    files={"file": ("stmt.csv", statement_csv(), "text/csv")})
    assert r.status_code == 200, r.text
    return client


# --- spending insights ---------------------------------------------------------------

def test_insights_trends_subscriptions_and_unusual(csv_user):
    ins = csv_user.get("/api/insights/spending").json()
    assert ins["months_covered"] == ["2026-05", "2026-06", "2026-07", "2026-08"]
    food = next(t for t in ins["trends"] if t["category"] == "food_delivery")
    assert food["amount"] == 5100.0 and food["average"] == 1600.0 and food["change"] == 3500.0
    netflix = next(s for s in ins["subscriptions"] if "netflix" in s["label"].lower())
    assert netflix["status"] == "possible" and netflix["yearly_estimate"] == 649 * 12
    kinds = {k for u in ins["unusual"] for k in u["kinds"]}
    assert {"merchant_spike", "possible_duplicate"} <= kinds
    text = " ".join(r for u in ins["unusual"] for r in u["reasons"]).lower()
    assert "fraud" not in text  # neutral language, never an accusation
    assert any("subscriptions" in o["kind"] for o in ins["opportunities"])


def test_subscription_and_unusual_decisions(csv_user):
    ins = csv_user.get("/api/insights/spending").json()
    sub = ins["subscriptions"][0]
    assert csv_user.post(f"/api/insights/subscriptions/{sub['group_id']}", json={"decision": "confirm"}).json()["user_kind"] == "subscription"
    assert next(s for s in csv_user.get("/api/insights/spending").json()["subscriptions"] if s["group_id"] == sub["group_id"])["status"] == "confirmed"
    csv_user.post(f"/api/insights/subscriptions/{sub['group_id']}", json={"decision": "dismiss"})
    assert all(s["group_id"] != sub["group_id"] for s in csv_user.get("/api/insights/spending").json()["subscriptions"])
    odd = ins["unusual"][0]
    csv_user.post(f"/api/insights/unusual/{odd['id']}", json={"decision": "expected"})
    assert all(u["id"] != odd["id"] for u in csv_user.get("/api/insights/spending").json()["unusual"])


def test_explain_transaction_and_isolation(csv_user, client_factory):
    ins = csv_user.get("/api/insights/spending").json()
    spike = next(u for u in ins["unusual"] if "merchant_spike" in u["kinds"])
    ex = csv_user.get(f"/api/transactions/{spike['id']}/explain").json()
    assert ex["transaction"]["amount"] == 3500 and ex["unusual"]
    assert ex["source"]["document_name"] == "stmt.csv"
    assert any("payments to" in line for line in ex["explanation"])
    other = client_factory()
    signup(other)
    assert other.get(f"/api/transactions/{spike['id']}/explain").status_code == 404
    assert other.post(f"/api/insights/unusual/{spike['id']}", json={"decision": "expected"}).status_code == 404


def test_scanned_statement_photo(client, monkeypatch):
    signup(client)
    consent(client)
    text = "Opening Balance 10,000.00\n02/08/2026 UPI SWIGGY 450.00 9,550.00\n05/08/2026 SALARY ACME 50,000.00 59,550.00"
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: text}))
    r = upload(client, png_bytes((320, 480), "#f5f5f5"), "statement.png", "bank_statement", period_months="3", account_label="Main")
    d = client.get(f"/api/documents/{r.json()['id']}").json()
    assert d["read_from_scan"] and d["transactions_found"] == 2
    assert any("read from a scan" in w for w in d["warnings"])
    txns = client.get("/api/transactions").json()["items"]
    assert all(t["confidence"] < 0.85 for t in txns)  # scanned rows are less certain than digital ones


# --- cash-flow estimate -------------------------------------------------------------

@freeze_time("2026-09-10 12:00:00")  # mid-month: salary (the 1st) is well after the ₹30,000 payment below
def test_forecast_uses_only_confirmed_or_entered_data(user_client):
    c = user_client
    empty = c.get("/api/forecast?days=40").json()
    assert empty["events"] == [] and empty["closing_balance"] is None
    assert any("income" in m.lower() for m in empty["missing"]) and any("balance" in m.lower() for m in empty["missing"])

    c.patch("/api/onboarding/about", json={"salary_manual": 50000})
    emi = c.post("/api/emis", json={"title": "Bike loan", "amount": 10000, "due_day": 10}).json()
    when = date.today() + timedelta(days=5)
    c.post("/api/forecast/expected", json={"label": "School fees", "amount": 30000, "direction": "debit", "on_date": when.isoformat()})
    c.put("/api/forecast/opening-balance", json={"amount": 5000})
    f = c.get("/api/forecast?days=40").json()
    assert f["opening_balance"] == {"amount": 5000.0, "as_of": date.today().isoformat(), "source": "you entered"}
    kinds = {e["source"] for e in f["events"]}
    assert {"salary you entered", "EMI you confirmed", "you added"} <= kinds
    assert f["closing_balance"] == pytest.approx(5000 + f["totals"]["in"] - f["totals"]["out"])
    assert any("1st of each month" in a for a in f["assumptions"])
    assert f["pressure"] and f["pressure"]["level"] in ("tight", "shortfall")  # ₹30,000 fee against ₹5,000 before salary

    before = f["totals"]["out"]
    c.post("/api/forecast/exclusions", json={"key": f"emi:{emi['id']}", "excluded": True})
    g = c.get("/api/forecast?days=40").json()
    emi_events = [e for e in g["events"] if e["key"].startswith(f"emi:{emi['id']}")]
    assert emi_events and all(e["excluded"] for e in emi_events)
    assert g["totals"]["out"] == pytest.approx(before - 10000 * len(emi_events))


def test_forecast_rejects_bad_input(user_client):
    assert user_client.post("/api/forecast/exclusions", json={"key": "../../x", "excluded": True}).status_code == 422
    past = (date.today() - timedelta(days=1)).isoformat()
    assert user_client.post("/api/forecast/expected", json={"label": "x", "amount": 5, "direction": "debit", "on_date": past}).status_code == 400


# --- goals -------------------------------------------------------------------------

def test_goal_progress_maths():
    g = Goal(name="Laptop", target_amount=90000, target_date=date(2027, 3, 15))
    p = progress(g, 30000, today=date(2026, 9, 23))
    assert p["remaining"] == 60000 and p["months_left"] == 6 and p["monthly_needed"] == 10000 and p["pct"] == 33.3
    assert progress(g, 95000, today=date(2026, 9, 23))["reached"] is True


def test_goals_api(user_client):
    c = user_client
    target = (date.today() + timedelta(days=200)).isoformat()
    g = c.post("/api/goals", json={"name": "Emergency fund", "target_amount": 100000, "target_date": target}).json()
    g = c.post(f"/api/goals/{g['id']}/contributions", json={"amount": 25000, "note": "Bonus"}).json()
    assert g["saved"] == 25000 and g["remaining"] == 75000 and g["monthly_needed"] > 0
    g = c.post(f"/api/goals/{g['id']}/contributions", json={"amount": -5000}).json()
    assert g["saved"] == 20000
    assert c.post(f"/api/goals/{g['id']}/contributions", json={"amount": 0}).status_code == 400
    lst = c.get("/api/goals").json()
    assert len(lst["goals"]) == 1 and "doesn't move money" in lst["note"]
    assert c.delete(f"/api/goals/{g['id']}").json()["ok"]


# --- reminders per item ---------------------------------------------------------------

def test_reminders_can_be_muted_per_item(sample):
    data = sample.get("/api/reminders").json()
    item = next(i for i in data["items"] if i["kind"] == "card")
    assert sample.put(f"/api/reminders/items/card/{item['object_id']}", json={"muted": True}).json()["muted"]
    after = sample.get("/api/reminders").json()
    assert all(r["object_id"] != item["object_id"] for r in after["upcoming"])
    assert next(i for i in after["items"] if i["key"] == item["key"])["muted"]
    sample.put(f"/api/reminders/items/card/{item['object_id']}", json={"muted": False})
    again = sample.get("/api/reminders").json()
    assert any(r["object_id"] == item["object_id"] for r in again["upcoming"])
    one = next(r for r in again["upcoming"] if r["object_id"] == item["object_id"])
    assert sample.delete(f"/api/reminders/{one['id']}").json()["status"] == "cancelled"
    assert all(r["id"] != one["id"] for r in sample.get("/api/reminders").json()["upcoming"])  # stays cancelled


# --- password reset -------------------------------------------------------------------

def test_password_reset_is_honest_when_email_is_off(client):
    assert client.get("/api/auth/password-reset/status").json() == {"email_configured": False}
    r = client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"}).json()
    assert r["sent"] is False and r["email_configured"] is False


def test_password_reset_flow_with_email(client_factory, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.test")
    monkeypatch.setattr(s, "smtp_from", "vitram@test")
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, body: sent.append((to, body)))
    a = client_factory()
    signup(a, email="reset1@example.com")
    unknown = a.post("/api/auth/password-reset/request", json={"email": "ghost@example.com"}).json()
    known = a.post("/api/auth/password-reset/request", json={"email": "reset1@example.com"}).json()
    assert unknown["message"] == known["message"] and len(sent) == 1  # no account enumeration
    token = sent[0][1].split("token=")[1].split()[0]
    b = client_factory()
    assert b.post("/api/auth/password-reset/confirm", json={"token": token, "new_password": "new-secret-9"}).json()["ok"]
    assert a.get("/api/auth/me").status_code == 401  # all sessions ended
    assert b.post("/api/auth/login", json={"email": "reset1@example.com", "password": "new-secret-9"}).status_code == 200
    again = b.post("/api/auth/password-reset/confirm", json={"token": token, "new_password": "another-1"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "RESET_LINK_INVALID"


# --- card benefits ---------------------------------------------------------------------

def test_card_user_benefits_are_separate_and_safe(user_client):
    c = user_client
    card = c.post("/api/cards", json={"nickname": "Office card", "last4": "1234", "user_benefits": ["Airport lounge 4×/year", " "]}).json()
    assert card["user_benefits"] == ["Airport lounge 4×/year"]
    bad = c.post("/api/cards", json={"nickname": "X", "user_benefits": ["my card 4111 1111 1111 1111"]})
    assert bad.status_code == 422
