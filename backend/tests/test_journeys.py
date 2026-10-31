"""RD §31 acceptance criteria — loans, cards, EMIs, insurance/emergency, channels."""

import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timezone

from app.config import get_settings
from app.services.channels import openwa, twilio_voice
from tests.conftest import signup


# --- Loans (RD §31.2) --------------------------------------------------------

def test_loan_recommend_reasons_and_real_cost(sample):
    r = sample.post("/api/loans/recommend", json={"purpose": "personal", "amount": 300000, "tenure_months": 36,
                                                  "collateral": {"available": False}}).json()
    assert r["results"], r
    top = r["results"][0]
    assert top["reason_codes"] and top["why"]
    assert top["catalogue"]["is_mock"] is True and top["catalogue"]["last_updated"]
    cost = top["cost"]
    # scheduled cost excludes contingent charges
    assert cost["scheduled_total_outflow"] == cost["monthly_emi"] * 36 + cost["upfront_charges_total"]
    assert cost["contingent_charges"]
    # gold loan (needs gold collateral) excluded when user has no collateral
    assert not any(x["product_id"] == "narmada-gold-quick" for x in r["results"])
    assert any("collateral" in " ".join(e["reasons"]).lower() for e in r["excluded"])
    assert r["profile_used"]["monthly_income"] == 118200


def test_unknown_eligibility_is_not_assumed(client):
    signup(client)  # no DOB, no income
    r = client.post("/api/loans/recommend", json={"purpose": "personal", "amount": 200000}).json()
    assert r["results"]
    assert all("AGE_UNKNOWN" in x["unknown_conditions"] for x in r["results"])
    assert {m["key"] for m in r["missing_data"]} >= {"monthly_income", "age"}


def test_loan_compare_and_what_if(sample):
    cmp = sample.post("/api/loans/compare", json={"product_ids": ["aravali-personal-flex", "vindhya-instant-personal"],
                                                  "intent": {"purpose": "personal", "amount": 300000, "tenure_months": 36}}).json()
    assert len(cmp["products"]) == 2
    v = next(p for p in cmp["products"] if p["product_id"] == "vindhya-instant-personal")
    assert v["flexibility"]["part_prepayment"]["allowed"] is False
    wi = sample.post("/api/loans/calculate", json={"kind": "prepayment", "product_id": "aravali-personal-flex", "principal": 300000,
                                                   "tenure_months": 36, "prepay_amount": 50000, "after_month": 12}).json()["result"]
    assert wi["computable"] and wi["scenario"]["interest_saved"] > 0 and wi["formula_version"]
    blocked = sample.post("/api/loans/calculate", json={"kind": "prepayment", "product_id": "vindhya-instant-personal", "principal": 300000,
                                                        "tenure_months": 36, "prepay_amount": 50000, "after_month": 12}).json()["result"]
    assert blocked["computable"] is False
    # home loan late fee flat amount unknown → penal interest only, flagged
    late = sample.post("/api/loans/calculate", json={"kind": "missed_payment", "product_id": "satpura-home-advantage", "principal": 3000000,
                                                     "tenure_months": 240}).json()["result"]
    assert late["computable"] and any("Flat late fee" in m for m in late["missing"])


def test_loan_calc_requires_terms(user_client):
    r = user_client.post("/api/loans/calculate", json={"kind": "cost", "principal": 100000, "tenure_months": 12})
    assert r.status_code == 422


# --- Cards (RD §31.3) --------------------------------------------------------

def test_best_card_for_flight(sample):
    r = sample.post("/api/cards/best-for-spend", json={"amount": 30000, "category": "travel"}).json()
    assert r["ranked"][0]["card_name"] == "Horizon Voyager"
    top = r["ranked"][0]
    # 8,000 travel spend this cycle already used 800 of 5,000 accelerated miles; 3,000 more fit under the cap
    assert top["reward_units"] == 3000 and top["value_inr"] == 1500
    assert [u["card_name"] for u in r["unranked"]] == ["Coastal Shopper"]
    cb = next(x for x in r["ranked"] if x["card_name"] == "Deccan Cashback")
    assert cb["value_inr"] == 300  # 1% base


def test_card_number_is_rejected(user_client):
    r = user_client.post("/api/cards", json={"nickname": "4111 1111 1111 1111"})
    assert r.status_code == 422


def test_card_insights(sample):
    ins = sample.get("/api/cards/insights/categories").json()["insights"]
    food = next(i for i in ins if i["category"] == "food_delivery")
    assert food["best_card"] == "Deccan Cashback"


def test_card_exploration_separates_calculation_ready_and_market_reference(sample):
    result = sample.get("/api/cards/explore").json()
    assert len(result["products"]) >= 50
    assert all(card["eligibility"] == "unknown" for card in result["products"])
    assert any(card["reference_only"] and not card["catalogue"]["is_mock"] for card in result["products"])
    assert any(not card["reference_only"] and card["catalogue"]["is_mock"] for card in result["products"])
    assert any(card["matched_spend_categories"] for card in result["products"])


# --- EMIs (RD §31.3) ----------------------------------------------------------

def test_emi_manual_calendar_and_missing_late_rule(user_client):
    e = user_client.post("/api/emis", json={"title": "Bike loan", "amount": 4200, "due_day": 10, "remaining_count": 18, "rate": 11}).json()
    assert e["confirmed"] and "Late-payment rule" in e["missing_terms"]
    cal = user_client.get("/api/emis/calendar").json()
    assert any(i["object_id"] == e["id"] for i in cal["items"])
    r = user_client.post(f"/api/emis/{e['id']}/what-if", json={"kind": "missed_payment"}).json()["result"]
    assert r["computable"] is False and r["missing"]  # never fabricated
    r = user_client.post(f"/api/emis/{e['id']}/what-if", json={"kind": "missed_payment",
                                                               "late_rule_override": {"flat_fee": 500, "penal_rate_pa": 24, "gst_applicable": True}}).json()["result"]
    assert r["computable"] and r["scenario"]["extra_cost"] > 500
    p = user_client.post(f"/api/emis/{e['id']}/what-if", json={"kind": "prepayment", "prepay_amount": 20000}).json()["result"]
    assert p["computable"] and p["scenario"]["interest_saved"] > 0


def test_emi_week_calendar_crosses_month_boundary(user_client):
    response = user_client.get("/api/emis/calendar?view=week&day=2026-10-01")
    assert response.status_code == 200
    calendar = response.json()
    assert calendar["view"] == "week"
    assert calendar["start"] == "2026-09-28"
    assert calendar["end"] == "2026-10-04"
    assert user_client.get("/api/emis/calendar?month=2026-13").status_code == 400


def test_detected_emi_confirm_and_reminder_honesty(sample):
    emis = sample.get("/api/emis").json()["emis"]
    det = next(e for e in emis if e["source_type"] == "bank_detection")
    assert not det["confirmed"] and det["detection"]["occurrences"] == 6
    assert sample.post(f"/api/emis/{det['id']}/confirm").json()["confirmed"]
    r = sample.post("/api/reminders/send-now", json={"object_type": "emi", "object_id": det["id"]}).json()
    assert r["channel"] == "in_app" and r["status"] == "sent" and "explanation" in r
    notes = sample.get("/api/notifications").json()["items"]
    assert any("VITTRM reminder" in n["title"] for n in notes)


def test_whatsapp_reminder_not_configured_is_honest(client, monkeypatch):
    signup(client)
    client.patch("/api/onboarding/about", json={"phone": "98765 43210"})
    from app.services.channels import phone_verify
    monkeypatch.setattr(phone_verify, "start", lambda _phone: True)
    monkeypatch.setattr(phone_verify, "check", lambda _phone, _code: True)
    assert client.post("/api/onboarding/phone/verification").status_code == 200
    assert client.post("/api/onboarding/phone/verification/check", json={"code": "123456"}).status_code == 200
    client.post("/api/consents", json={"purpose": "whatsapp_reminders"})
    assert client.put("/api/reminders/preferences", json={"days_before": [3], "on_due_date": True, "send_hour": 9,
                                                          "whatsapp_enabled": True}).status_code == 200
    e = client.post("/api/emis", json={"title": "Loan", "amount": 5000, "due_day": 5}).json()
    r = client.post("/api/reminders/send-now", json={"object_type": "emi", "object_id": e["id"]}).json()
    assert r["channel"] == "whatsapp" and r["status"] == "not_configured"
    assert "isn't connected" in r["explanation"]


def test_new_emi_explore(sample):
    r = sample.post("/api/emis/explore", json={"options": [
        {"label": "No-cost EMI", "amount": 60000, "rate": 0, "tenure_months": 6, "processing_fee": 199},
        {"label": "Card EMI", "amount": 60000, "rate": 15, "tenure_months": 6}]}).json()
    assert len(r["options"]) == 2 and r["notes"]
    assert r["options"][0]["affordability"]["computable"]


# --- Insurance & emergency (RD §31.4) -----------------------------------------

def _members(c):
    f = c.get("/api/family").json()
    return {m["relation"]: m for m in f["members"]}


def test_emergency_requires_member_and_filters(sample):
    r = sample.post("/api/insurance/emergency", json={"event": "hospitalisation"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "MEMBER_REQUIRED"
    mother = _members(sample)["mother"]
    r = sample.post("/api/insurance/emergency", json={"event": "hospitalisation", "member_key": mother["id"]}).json()
    names = [p["policy"]["product_name"] for p in r["policies"]]
    assert names == ["Senior Care"]  # only her policies
    p = r["policies"][0]
    assert p["status"] == "may_apply"
    assert p["coverage"]["copay"]["value"] == 20 and p["coverage"]["copay"]["citation"]["page"] == 1
    assert "Discharge summary and final bill" in p["claim"]["documents"]["value"]
    assert any(w["status"] and w["status"]["running"] for w in p["waiting_periods"])
    assert "can't guarantee" in r["disclaimer"]
    me = sample.post("/api/insurance/emergency", json={"event": "hospitalisation", "member_key": "self"}).json()
    statuses = {p["policy"]["product_name"]: p["status"] for p in me["policies"]}
    assert statuses == {"Family Health Shield": "may_apply", "Term Secure": "not_applicable"}


def test_insurance_recommend_and_compare(sample):
    fam = _members(sample)
    r = sample.post("/api/insurance/recommend", json={"type": "health", "member_keys": [fam["mother"]["id"]]}).json()
    ids = [x["product_id"] for x in r["results"]]
    assert "sahyadri-senior-care" in ids and "sahyadri-family-shield" not in ids  # age 61 outside floater (max 65)? relation check
    assert all(x["catalogue"]["is_mock"] for x in r["results"])
    assert any("ADDS_TO_EXISTING_COVER" in x["reason_codes"] for x in r["results"])
    pols = sample.get("/api/insurance/policies").json()
    senior = next(p for p in pols if p["product_name"] == "Senior Care")
    c = sample.post("/api/insurance/compare", json={"product_ids": ["godavari-parents-plus"], "policy_ids": [senior["id"]],
                                                    "member_keys": [fam["mother"]["id"]]}).json()
    assert [col["kind"] for col in c["columns"]] == ["catalogue", "existing"]


def test_market_insurance_catalogue_has_reference_products(sample):
    products = sample.get("/api/insurance/catalogue").json()["products"]
    assert len(products) >= 30
    refs = [p for p in products if p.get("reference_only")]
    assert len(refs) >= 30
    assert all(p["official_url"].startswith("https://") and not p["catalogue"]["is_mock"] for p in refs)


def test_consultation_not_configured_never_claims_call(sample):
    prev = sample.post("/api/consultations/preview", json={"topic": "Is my mother's policy enough?"}).json()
    assert "Topic:" in prev["context_summary"] and prev["calling_configured"] is False
    r = sample.post("/api/consultations", json={"topic": "Is my mother's policy enough?", "consent": True, "phone": "9876543210",
                                                "use_phone_on_file": False})
    body = r.json()
    assert body["status"] == "not_configured" and "no call was placed" in body["status_text"]
    assert sample.post("/api/consultations", json={"topic": "x x x", "consent": False, "phone": "9876543210",
                                                   "use_phone_on_file": False}).status_code == 400


# --- Channels: signature checks (RD §17, §26) ---------------------------------

def test_openwa_signature_and_session_scope(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "openwa_webhook_secret", "a-secure-test-secret")
    monkeypatch.setattr(s, "openwa_session_id", "session-1")
    body = json.dumps({"event": "session.status", "sessionId": "session-1", "data": {"status": "ready"}}).encode()
    bad = client.post("/api/webhooks/openwa", content=body, headers={"x-openwa-signature": "sha256=deadbeef", "content-type": "application/json"})
    assert bad.status_code == 401
    sig = "sha256=" + hmac.new(b"a-secure-test-secret", body, hashlib.sha256).hexdigest()
    ok = client.post("/api/webhooks/openwa", content=body, headers={"x-openwa-signature": sig, "content-type": "application/json"})
    assert ok.status_code == 200
    other = json.dumps({"event": "session.status", "sessionId": "other", "data": {"status": "ready"}}).encode()
    other_sig = "sha256=" + hmac.new(b"a-secure-test-secret", other, hashlib.sha256).hexdigest()
    assert client.post("/api/webhooks/openwa", content=other,
                       headers={"x-openwa-signature": other_sig, "content-type": "application/json"}).status_code == 204


def test_whatsapp_inbound_emergency_and_stop(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "openwa_webhook_secret", "a-secure-test-secret")
    monkeypatch.setattr(s, "openwa_session_id", "session-1")
    signup(client)
    client.patch("/api/onboarding/about", json={"phone": "9123456780"})
    from app.services.channels import phone_verify
    monkeypatch.setattr(phone_verify, "start", lambda _phone: True)
    monkeypatch.setattr(phone_verify, "check", lambda _phone, _code: True)
    client.post("/api/onboarding/phone/verification")
    client.post("/api/onboarding/phone/verification/check", json={"code": "123456"})
    client.post("/api/consents", json={"purpose": "whatsapp_reminders"})
    from app.db import SessionLocal
    from app.routers.webhooks import handle_inbound
    db = SessionLocal()
    reply = handle_inbound(db, {"id": "m1", "from": "919123456780", "text": "I am in hospital, what do I do?"})
    assert "policy" in reply.lower() and "/insurance/emergency" in reply
    stop = handle_inbound(db, {"id": "m2", "from": "919123456780", "text": "STOP"})
    db.commit()
    assert "won't get" in stop
    unknown = handle_inbound(db, {"id": "m3", "from": "919000000000", "text": "hi"})
    assert unknown is None
    db.close()
    assert "whatsapp_reminders" not in client.get("/api/auth/me").json()["consents"]


def test_twilio_signature(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "twilio_auth_token", "token123")
    url = "https://api.example.com/api/webhooks/twilio"
    params = {"CallSid": "CA1", "CallStatus": "completed"}
    payload = url + "".join(k + params[k] for k in sorted(params))
    sig = base64.b64encode(hmac.new(b"token123", payload.encode(), hashlib.sha1).digest()).decode()
    assert twilio_voice.validate_signature(url, params, sig)
    assert not twilio_voice.validate_signature(url, params, "nope")
    assert "<Dial record=\"do-not-record\">" in twilio_voice.twiml("hi", "+911234567890")


def test_openwa_parse():
    msgs, sts = openwa.parse_webhook({"event": "message.received", "data": {
        "id": "msg.1", "from": "9199@c.us", "type": "text", "body": "hello", "kind": "individual",
    }})
    assert msgs[0]["text"] == "hello" and msgs[0]["from"] == "9199"
    msgs, sts = openwa.parse_webhook({"event": "message.ack", "data": {
        "messageId": "msg.0", "status": "delivered",
    }})
    assert not msgs and sts[0] == {"id": "msg.0", "status": "delivered", "error": None}


def test_openwa_send_text_contract(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "openwa_base_url", "http://openwa.test")
    monkeypatch.setattr(s, "openwa_api_key", "secret-key")
    monkeypatch.setattr(s, "openwa_session_id", "session-1")
    seen = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"messageId": "msg.1", "timestamp": 1}

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(openwa.httpx, "post", fake_post)
    assert openwa.send_text("+91 91234 56780", "hello;&#x20;&amp;#x20;world") == "msg.1"
    assert seen["url"].endswith("/api/sessions/session-1/messages/send-text")
    assert seen["headers"]["X-API-Key"] == "secret-key"
    assert seen["json"] == {"chatId": "919123456780@c.us", "text": "hello;  world", "linkPreview": False}


def test_openwa_ack_updates_reminder_once(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import Reminder, WebhookEvent

    user_id = signup(client)["id"]
    db = SessionLocal()
    reminder = Reminder(user_id=user_id, object_type="emi", object_id="test-object", channel="whatsapp",
                        schedule_at=datetime.now(timezone.utc), due_date=date.today(), template_key="test",
                        status="sent", provider_message_id="msg.ack")
    db.add(reminder)
    db.commit()
    reminder_id = reminder.id
    db.close()

    settings = get_settings()
    secret = "a-secure-test-secret"
    monkeypatch.setattr(settings, "openwa_webhook_secret", secret)
    monkeypatch.setattr(settings, "openwa_session_id", "session-1")
    event = {"event": "message.ack", "sessionId": "session-1", "idempotencyKey": "ack-1",
             "data": {"messageId": "msg.ack", "status": "delivered"}}
    raw = json.dumps(event).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"content-type": "application/json", "x-openwa-signature": signature,
               "x-openwa-idempotency-key": "ack-1"}
    assert client.post("/api/webhooks/openwa", content=raw, headers=headers).status_code == 200
    assert client.post("/api/webhooks/openwa", content=raw, headers=headers).status_code == 200

    db = SessionLocal()
    assert db.get(Reminder, reminder_id).status == "delivered"
    assert db.query(WebhookEvent).filter(WebhookEvent.provider == "openwa_status",
                                         WebhookEvent.external_id == "ack-1").count() == 1
    db.close()


def test_csrf_origin_check(client_factory):
    c = client_factory()
    c.headers["Origin"] = "https://evil.example"
    r = c.post("/api/auth/signup", json={"name": "x", "email": "e@x.com", "password": "12345678", "accept_terms": True})
    assert r.status_code == 403
