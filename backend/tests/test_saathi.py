"""RD §27.3 — Vitt Saathi evaluation in Tool mode: grounding, numeric fidelity, context isolation, unknown handling."""

import re

from app.services.saathi.orchestrator import fidelity_flags, inr
from app.services.saathi import router_offline as ro
from app.services.saathi import tools as T


def chat(c, text, ctx="dashboard", cid=None, obj=None, member=None):
    r = c.post("/api/ai/chat", json={"message": text, "context_type": ctx, "conversation_id": cid,
                                     "context_object_id": obj, "member_key": member})
    assert r.status_code == 200, r.text
    return r.json()


def test_status_reports_tool_mode(sample):
    s = sample.get("/api/ai/status").json()
    assert s["chat_mode"] == "tool" and s["voice_available"] is False and s["chat_note"]


def test_slot_parsers():
    assert ro.parse_amount("need 5 lakh for a car") == 500_000
    assert ro.parse_amount("₹30,000 flight") == 30_000
    assert ro.parse_amount("1.2 crore home") == 12_000_000
    assert ro.parse_tenure("for 3 saal") == 36
    assert ro.parse_purpose("mujhe gaadi ke liye loan chahiye") == "vehicle"
    assert ro.parse_collateral("kuch girvi nahi rakh sakta") == "none"
    assert ro.parse_relation("maa hospital mein hai") == "mother"
    assert inr(1234567.4) == "₹12,34,567"


def test_loan_conversation_asks_then_answers_with_tool_numbers(sample):
    r1 = chat(sample, "I need a loan")
    assert "What is the loan for" in r1["message"]["content"]
    cid = r1["conversation_id"]
    r2 = chat(sample, "personal need, 3 lakh for 3 years", cid=cid)
    m = r2["message"]
    assert m["mode"] == "tool"
    card = next(c for c in m["cards"] if c["type"] == "loan_options")
    emi = card["results"][0]["cost"]["monthly_emi"]
    assert inr(emi) in m["content"]  # narrative number == tool number
    assert "sample catalogue" in m["content"]
    r3 = chat(sample, "what's the real cost?", cid=cid)
    assert any(c["type"] == "loan_cost" for c in r3["message"]["cards"])
    r4 = chat(sample, "compare the top two", cid=cid)
    assert any(c["type"] == "loan_comparison" for c in r4["message"]["cards"])


def test_card_question_from_dashboard(sample):
    m = chat(sample, "Which card should I use for a ₹30,000 flight?")["message"]
    assert "Horizon Voyager" in m["content"] and "₹1,500" in m["content"]


def test_common_questions_use_instant_curated_answers(sample):
    m = chat(sample, "What is credit utilisation?", ctx="card")["message"]
    assert m["mode"] == "tool"
    assert "share of your total card limit" in m["content"]
    assert not m["cards"] and not m["citations"]

    m = chat(sample, "What is a waiting period?", ctx="insurance")["message"]
    assert "pre-existing-disease" in m["content"] and m["mode"] == "tool"

    m = chat(sample, "Credit utilisation kya hai?", ctx="card")["message"]
    assert "matlab" in m["content"] and m["lang"] == "hinglish"


def test_named_market_product_answer_does_not_invent_terms(sample):
    m = chat(sample, "Tell me about ATLAS Credit Card", ctx="card")["message"]
    assert "Axis Bank" in m["content"] and "market-reference" in m["content"]
    assert "official product page" in m["content"]


def test_faq_directory_is_available(sample):
    body = sample.get("/api/ai/faqs?category=insurance").json()
    assert body["count"] >= 10
    assert all(x["category"] == "insurance" for x in body["faqs"])


def test_reward_balance_suggestion_lists_cards(sample):
    m = chat(sample, "Show my reward balances", ctx="card")["message"]
    assert "3 cards" in m["content"]
    assert any(c["type"] == "card_list" for c in m["cards"])


def test_emergency_asks_for_person_then_grounded(sample):
    m = chat(sample, "Emergency, someone is in hospital", ctx="emergency")["message"]
    assert "Who is this for" in m["content"]
    fam = sample.get("/api/family").json()["members"]
    mother = next(x for x in fam if x["relation"] == "mother")
    m = chat(sample, "Which policy covers this?", ctx="emergency", member=mother["id"])["message"]
    assert "Senior Care" in m["content"] and "can't promise approval" in m["content"]
    assert m["citations"] and all(c["document_type"] == "insurance_policy" for c in m["citations"])


def test_policy_question_grounded_or_not_found(sample):
    pols = sample.get("/api/insurance/policies").json()
    fam_pol = next(p for p in pols if p["product_name"] == "Family Health Shield")
    m = chat(sample, "Is maternity excluded?", ctx="insurance", obj=fam_pol["id"])["message"]
    assert "page 2" in m["content"] and m["citations"]
    m = chat(sample, "does it cover space travel waiting clause zzqx", ctx="insurance", obj=fam_pol["id"])["message"]
    # Either a sourced quote or an explicit not-found — never an invented clause
    assert m["citations"] or "couldn't find" in m["content"]


def test_prompt_injection_text_is_not_followed(sample):
    pols = sample.get("/api/insurance/policies").json()
    fam_pol = next(p for p in pols if p["product_name"] == "Family Health Shield")
    m = chat(sample, "what does the note to AI assistants clause say", ctx="insurance", obj=fam_pol["id"])["message"]
    # It may be quoted as document text, but Saathi never asserts claims will be approved
    assert not re.search(r"(?<!“)every claim will be approved(?!.*”)", m["content"].split("“")[0])


def test_context_isolation():
    # Insurance context has no access to transaction-level tools; loan context can't touch policies
    assert "loans_search" not in T.CONTEXT_TOOLS["insurance"]
    assert "insurance_find_applicable_existing" not in T.CONTEXT_TOOLS["loan"]
    assert "documents_search" not in T.CONTEXT_TOOLS["card"]


def test_insurance_slice_has_no_banking_data(sample):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    user = db.query(User).filter(User.is_sample.is_(True)).first()
    res = T.run(db, user, "profile_get_slice", {}, {"type": "insurance"})
    text = str(res.data).lower()
    assert "transaction" not in text and "salary" not in text and "surplus" not in text and "income" not in text
    db.close()


def test_cross_module_request_offers_navigation(sample):
    m = chat(sample, "Which card should I use for 5000 on Swiggy?", ctx="insurance")["message"]
    assert any(c["type"] == "navigation" for c in m["cards"])


def test_numeric_fidelity_guard():
    assert fidelity_flags("EMI is ₹10,747", [{"monthly_emi": 10746.97}]) == []
    assert fidelity_flags("EMI is ₹9,999", [{"monthly_emi": 10746.97}]) == ["unverified_amount:9999"]


def test_emi_what_if_via_chat_never_fabricates(sample):
    emis = sample.get("/api/emis").json()["emis"]
    det = next(e for e in emis if e["source_type"] == "bank_detection")
    m = chat(sample, "What if I miss my next EMI?", ctx="emi", obj=det["id"])["message"]
    assert "can't calculate this precisely" in m["content"]


def test_voice_token_not_configured(sample):
    r = sample.post("/api/ai/session-token", json={"context_type": "dashboard"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "INTEGRATION_NOT_CONFIGURED"
