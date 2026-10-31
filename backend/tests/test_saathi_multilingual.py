"""Vitt Saathi Tool mode in Hindi and Hinglish (RD §11.2): same tools, same numbers, reply in the user's language."""

import re

from app.fmt import inr
from app.services.saathi import i18n
from app.services.saathi import router_offline as ro

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def chat(c, text, ctx="dashboard", cid=None, obj=None, member=None):
    r = c.post("/api/ai/chat", json={"message": text, "context_type": ctx, "conversation_id": cid,
                                     "context_object_id": obj, "member_key": member})
    assert r.status_code == 200, r.text
    return r.json()


def test_language_detection():
    assert i18n.detect("मुझे कार के लिए 5 लाख का लोन चाहिए") == "hi"
    assert i18n.detect("mujhe car ke liye 5 lakh ka loan chahiye") == "hinglish"
    assert i18n.detect("I need a car loan of 5 lakh") == "en"
    assert i18n.detect("3 lakh") is None  # ambiguous → falls back to conversation / profile language
    assert i18n.normalize("५ लाख") == "5 लाख"


def test_hindi_slot_parsing():
    assert ro.parse_amount("मुझे ५ लाख चाहिए".translate(str.maketrans("०१२३४५६७८९", "0123456789"))) == 500_000
    assert ro.parse_amount("2 करोड़ का घर") == 20_000_000
    assert ro.parse_tenure("3 साल के लिए") == 36
    assert ro.parse_purpose("गाड़ी के लिए लोन") == "vehicle"
    assert ro.parse_relation("माँ अस्पताल में भर्ती हैं") == "mother"
    assert ro.parse_collateral("कुछ गिरवी नहीं रख सकता") == "none"
    assert ro.detect_intent("असली लागत कितनी है?") == "loan_cost"


def test_hindi_loan_reply_uses_tool_numbers(sample):
    m = chat(sample, "मुझे 3 साल के लिए 3 लाख का पर्सनल लोन चाहिए")["message"]
    assert m["lang"] == "hi" and DEVANAGARI.search(m["content"])
    card = next(c for c in m["cards"] if c["type"] == "loan_options")
    assert inr(card["results"][0]["cost"]["monthly_emi"]) in m["content"]  # same deterministic number


def test_hinglish_card_reply(sample):
    m = chat(sample, "₹30,000 ki flight ke liye kaunsa card use karun?")["message"]
    assert m["lang"] == "hinglish"
    assert "Horizon Voyager" in m["content"] and "₹1,500" in m["content"] and "sabse zyada" in m["content"]


def test_hindi_emergency_grounded_and_no_guarantee(sample):
    fam = sample.get("/api/family").json()["members"]
    mother = next(x for x in fam if x["relation"] == "mother")
    m = chat(sample, "माँ अस्पताल में भर्ती हैं, कौन सी पॉलिसी काम आएगी?", ctx="emergency", member=mother["id"])["message"]
    assert "Senior Care" in m["content"] and "मंज़ूरी का वादा नहीं" in m["content"]
    assert m["citations"]


def test_hinglish_missing_terms_never_fabricated(sample):
    emis = sample.get("/api/emis").json()["emis"]
    det = next(e for e in emis if e["source_type"] == "bank_detection")
    m = chat(sample, "agar meri agli EMI miss ho gayi toh kya hoga?", ctx="emi", obj=det["id"])["message"]
    assert m["lang"] == "hinglish" and "andaaze se penalty nahi" in m["content"]


def test_language_does_not_bypass_tool_isolation(sample):
    # A Hindi card question on the insurance page must not run the card tool
    m = chat(sample, "₹5000 के स्विगी ऑर्डर के लिए कौन सा कार्ड?", ctx="insurance")["message"]
    assert not any(c["type"] == "card_ranking" for c in m["cards"])
    assert any(c["type"] == "navigation" for c in m["cards"])
    assert DEVANAGARI.search(m["content"])


def test_ambiguous_follow_up_keeps_conversation_language(sample):
    r1 = chat(sample, "mujhe loan chahiye")
    assert r1["message"]["lang"] == "hinglish"
    r2 = chat(sample, "personal, 3 lakh", cid=r1["conversation_id"])
    assert r2["message"]["lang"] == "hinglish"
