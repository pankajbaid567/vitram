"""RD §27.2 — policy / loan extraction with page references, prompt injection, conflicts, grounded search."""

from app.services.extractors.insurance import extract_policy
from app.services.extractors.loan import extract_loan
from app.services.pdf_text import extract_pages
from tests.conftest import FIXTURES, signup


def _facts(path, fn):
    ex = fn(extract_pages((FIXTURES / path).read_bytes()))
    return ex, {f.key: f for f in ex.facts}


def test_health_policy_extraction_with_pages():
    ex, f = _facts("sample_policy_family_health.pdf", extract_policy)
    assert f["sum_insured"].value == 1_000_000 and f["sum_insured"].page == 1
    assert f["premium"].value == 18_900
    assert f["copay"].value == 0
    assert f["ped_waiting_period"].value == "36 months"
    assert f["policy_type"].value == "health"
    assert f["policy_number"].value.startswith("••••")  # masked (RD §10.1)
    assert "SGI/FHS/2026/00481234" not in (f["policy_number"].snippet or "")
    assert any("Maternity" in x for x in f["exclusions"].value) and f["exclusions"].page == 2
    assert f["claim_documents"].page == 3 and "Discharge summary" in f["claim_documents"].value
    assert f["claim_intimation"].value == "24 hours"
    assert [m["relation"] for m in f["insured_members"].value] == ["self", "spouse"]
    assert f["start_date"].value == "2026-01-15" and f["end_date"].value == "2027-01-14"


def test_scanned_policy_marks_ocr_facts_for_review(client, monkeypatch):
    import io
    from pypdf import PdfWriter
    from app.services import pipeline
    from tests.test_vision import fake_ocr

    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=600)
    writer.write(pdf)
    raw = pdf.getvalue()
    first = client.post("/api/documents", data={"type": "insurance_policy"},
                        files={"file": ("scan.pdf", raw, "application/pdf")}).json()
    assert client.get(f"/api/documents/{first['id']}").json()["error_code"] == "NO_TEXT_FOUND"

    text = extract_pages((FIXTURES / "sample_policy_family_health.pdf").read_bytes())[0]
    monkeypatch.setattr(pipeline, "read_document", fake_ocr({1: text}))
    second = client.post("/api/documents", data={"type": "insurance_policy"},
                         files={"file": ("scan.pdf", raw, "application/pdf")}).json()
    processed = client.get(f"/api/documents/{second['id']}").json()
    assert processed["extraction_method"] == "ocr_macos"
    assert processed["status"] == "needs_review"
    facts = client.get(f"/api/documents/{second['id']}/facts").json()["facts"]
    assert facts and all(f["confidence"] < 0.8 for f in facts)
    assert any("scan or photo" in w for w in processed["warnings"])


def test_card_document_extracts_reviewable_facts_and_rejects_full_pan(client):
    import io
    from reportlab.pdfgen import canvas

    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})

    def pdf(lines):
        buf = io.BytesIO()
        page = canvas.Canvas(buf)
        for index, line in enumerate(lines):
            page.drawString(50, 750 - index * 25, line)
        page.save()
        return buf.getvalue()

    unsafe = pdf(["Card number 4111 1111 1111 1111", "Total amount due Rs 12,500.00"])
    denied = client.post("/api/documents", data={"type": "card_document"},
                         files={"file": ("card.pdf", unsafe, "application/pdf")})
    assert denied.status_code == 400 and denied.json()["error"]["code"] == "CARD_CREDENTIAL_FOUND"

    safe = pdf(["Card ending 4821", "Payment due date: 25/10/2026", "Total amount due Rs 12,500.00",
                "Reward points balance: 1,250", "20/09/2026 PURCHASE BOOK SHOP Rs 1,250.00"])
    uploaded = client.post("/api/documents", data={"type": "card_document"},
                           files={"file": ("card.pdf", safe, "application/pdf")}).json()
    processed = client.get(f"/api/documents/{uploaded['id']}").json()
    assert processed["status"] == "needs_review"
    facts = client.get(f"/api/documents/{uploaded['id']}/facts").json()["facts"]
    values = {f["key"]: f["value"] for f in facts}
    assert values["last4"] == "4821"
    assert values["due_date"] == "2026-10-25"
    assert values["outstanding"] == 12500
    assert values["points_balance"] == 1250
    assert values["purchase_1"] == {"date": "2026-09-20", "merchant": "BOOK SHOP", "amount_inr": 1250}
    assert all(f["citation"]["page"] == 1 for f in facts)
    assert "4111 1111 1111 1111" not in str(facts)
    spend = next(f for f in facts if f["key"] == "purchase_1")
    assert spend["state"] == "extracted" and spend["confidence"] <= 0.55
    confirmed = client.patch(f"/api/documents/{uploaded['id']}/facts/{spend['id']}", json={"confirm_only": True})
    assert confirmed.status_code == 200 and confirmed.json()["user_verified"] is True


def test_reviewed_card_document_import_is_explicit_scoped_and_reversible(client, client_factory):
    import io
    from reportlab.pdfgen import canvas

    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    for index, line in enumerate(("Card ending 4821", "Payment due date: 25/10/2026",
                                  "Total amount due Rs 12,500.00", "Reward points balance: 1,250")):
        pdf.drawString(50, 750 - index * 25, line)
    pdf.save()
    doc = client.post("/api/documents", data={"type": "card_document"},
                      files={"file": ("redacted-card.pdf", buf.getvalue(), "application/pdf")}).json()
    card = client.post("/api/cards", json={"nickname": "My card", "last4": "4821"}).json()
    path = f"/api/cards/{card['id']}/import-document"
    body = {"document_id": doc["id"]}
    assert client.post(path, json=body).json()["error"]["code"] == "CARD_FACTS_UNREVIEWED"

    facts = client.get(f"/api/documents/{doc['id']}/facts").json()["facts"]
    for fact in facts:
        client.patch(f"/api/documents/{doc['id']}/facts/{fact['id']}", json={"confirm_only": True})
    other = client_factory()
    signup(other)
    assert other.post(path, json=body).status_code == 404
    assert other.post(f"/api/cards/{other.post('/api/cards', json={'nickname': 'Other', 'last4': '4821'}).json()['id']}/import-document",
                      json=body).status_code == 404

    imported = client.post(path, json=body)
    assert imported.status_code == 200
    assert set(imported.json()["imported_fields"]) == {"outstanding", "due_date", "points_balance"}
    linked = imported.json()["card"]
    assert linked["source_document_id"] == doc["id"]
    assert linked["outstanding"] == 12500 and linked["due_date"] == "2026-10-25"
    assert linked["points"]["balance"] == 1250

    mismatch = client.post("/api/cards", json={"nickname": "Different card", "last4": "9999"}).json()
    assert client.post(f"/api/cards/{mismatch['id']}/import-document", json=body).json()["error"]["code"] == "CARD_LAST4_MISMATCH"
    occupied = client.post("/api/cards", json={"nickname": "Existing balance", "last4": "4821", "outstanding": 700}).json()
    occupied_path = f"/api/cards/{occupied['id']}/import-document"
    assert client.post(occupied_path, json=body).status_code == 409
    assert client.post(occupied_path, json={**body, "replace_existing": True}).status_code == 200
    manual = client.patch(f"/api/cards/{card['id']}", json={"nickname": "My card", "last4": "4821",
                                                            "outstanding": 100, "due_date": "2026-11-01"})
    assert manual.status_code == 200 and manual.json()["source_document_id"] is None

    # Re-reading invalidates the old reviewed snapshot instead of retaining
    # values whose page facts are about to change.
    assert client.post(f"/api/documents/{doc['id']}/reprocess").status_code == 200
    cards = {c["id"]: c for c in client.get("/api/cards").json()["cards"]}
    assert cards[card["id"]]["outstanding"] == 100 and cards[card["id"]]["due_date"] == "2026-11-01"
    assert cards[occupied["id"]]["source_document_id"] is None
    assert cards[occupied["id"]]["outstanding"] is None and cards[occupied["id"]]["due_date"] is None
    assert cards[occupied["id"]]["points"] is None

    refreshed = client.get(f"/api/documents/{doc['id']}/facts").json()["facts"]
    for fact in refreshed:
        if fact["key"] in ("last4", "outstanding"):
            client.patch(f"/api/documents/{doc['id']}/facts/{fact['id']}", json={"confirm_only": True})
    assert client.post(occupied_path, json=body).status_code == 200
    partial = client.post("/api/cards", json={"nickname": "Manual due date", "last4": "4821",
                                             "due_date": "2026-12-01"}).json()
    assert client.post(f"/api/cards/{partial['id']}/import-document",
                       json={**body, "replace_existing": True}).status_code == 200
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    after_delete = {c["id"]: c for c in client.get("/api/cards").json()["cards"]}
    assert after_delete[occupied["id"]]["outstanding"] is None
    assert after_delete[card["id"]]["outstanding"] == 100
    assert after_delete[partial["id"]]["outstanding"] is None
    assert after_delete[partial["id"]]["due_date"] == "2026-12-01"


def test_prompt_injection_is_only_content():
    ex, f = _facts("sample_policy_family_health.pdf", extract_policy)
    # The injected sentence never becomes a structured fact value…
    for fact in ex.facts:
        if fact.key not in ("conditions",):
            assert "ignore all previous instructions" not in str(fact.value).lower()
    # …and when it's retrievable text, it's just quoted data (checked in the Saathi tests).


def test_senior_policy_copay_and_waiting():
    _, f = _facts("sample_policy_senior_care.pdf", extract_policy)
    assert f["copay"].value == 20
    assert f["ped_waiting_period"].value == "24 months"
    assert f["insured_members"].value[0]["relation"] == "mother"


def test_loan_kfs_extraction():
    ex, f = _facts("sample_loan_kfs.pdf", extract_loan)
    t = f["_terms"].value
    assert t["principal"] == 400_000 and t["annual_rate_pct"] == 14.25 and t["tenure_months"] == 36
    assert t["rate_type"] == "fixed" and t["stated_emi"] == 13_720 and t["due_day"] == 5
    fees = {c["key"]: c for c in t["charges"]}
    assert fees["processing_fee"]["basis"] == "percent_of_principal" and fees["processing_fee"]["value"] == 2.5
    assert fees["processing_fee"]["min"] == 2999 and fees["processing_fee"]["gst_applicable"]
    assert fees["stamp_duty"]["gst_applicable"] is False
    late = next(c for c in t["contingent"] if c["key"] == "late_payment")["rule"]
    assert late == {"penal_rate_pa": 24.0, "flat_fee": 600.0, "gst_applicable": True}
    pp = t["prepayment_rule"]
    assert pp["allowed_after_months"] == 6 and pp["charge_pct"] == 2 and pp["max_per_year_pct"] == 25
    sev = {c["title"]: c["severity"] for c in t["clauses"]}
    assert sev["Loan insurance is a condition"] == "important"
    assert all(c["source"]["page"] for c in t["clauses"])


def test_sample_workspace_policy_and_loan_views(sample):
    ov = sample.get("/api/insurance/overview").json()
    assert ov["policy_count"] == 3
    fam = {m["name"]: m for m in ov["family_coverage"]}
    assert fam["Kamala Sample"]["health_cover"] == 500_000
    pol_id = next(p["id"] for g in ov["policies_by_type"] for p in g["policies"] if p["product_name"] == "Senior Care")
    detail = sample.get(f"/api/insurance/policies/{pol_id}").json()
    assert detail["waiting_status"] and detail["waiting_status"][0]["citation"]["page"]
    docs = sample.get("/api/documents").json()
    loan_doc = next(d for d in docs if d["type"] == "loan_document")
    a = sample.get(f"/api/loans/documents/{loan_doc['id']}").json()
    assert a["cost"]["emi_check"]["matches"]
    assert a["cost"]["annualized_cost_pct"] > 14.25
    assert a["cost"]["stated_apr_pct"] == 17.9


def test_grounded_search_and_not_found(sample):
    docs = sample.get("/api/documents").json()
    fam = next(d for d in docs if d["display_name"] == "sample_policy_family_health.pdf")
    r = sample.post(f"/api/documents/{fam['id']}/search", json={"query": "is maternity covered?"}).json()
    assert r["found"] and any(x["citation"]["page"] == 2 for x in r["results"])
    r2 = sample.post(f"/api/documents/{fam['id']}/search", json={"query": "zzqx unrelated gibberish"}).json()
    assert r2["found"] is False


def test_fact_correction_is_user_verified(sample):
    pols = sample.get("/api/insurance/policies").json()
    term = next(p for p in pols if p["type"] == "term_life")
    facts = sample.get(f"/api/documents/{term['document_id']}/facts").json()["facts"]
    prem = next(f for f in facts if f["key"] == "premium")
    r = sample.patch(f"/api/documents/{term['document_id']}/facts/{prem['id']}", json={"value": "1,200"})
    assert r.status_code == 200 and r.json()["value"] == 1200 and r.json()["state"] == "confirmed"
    pols = sample.get("/api/insurance/policies").json()
    assert next(p for p in pols if p["id"] == term["id"])["premium"]["amount"] == 1200


def test_conflicting_policy_versions_are_flagged(client):
    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    import io

    from reportlab.pdfgen import canvas

    def make(sum_insured):
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 800
        for line in ["Insurer: Test Insurer (sample)", "Plan Name: Test Plan", "Policy Number: TST/123456789",
                     f"Sum Insured: Rs. {sum_insured}", "Hospitalisation cover", "Premium: Rs. 10,000"]:
            c.drawString(50, y, line)
            y -= 14
        c.save()
        return buf.getvalue()

    for si in ("5,00,000", "7,00,000"):
        r = client.post("/api/documents", data={"type": "insurance_policy"}, files={"file": (f"p{si}.pdf", make(si), "application/pdf")})
        assert r.status_code == 200
    pols = client.get("/api/insurance/policies").json()
    assert len(pols) == 2  # both versions kept
    detail = client.get(f"/api/insurance/policies/{pols[0]['id']}").json()
    assert any(c["key"] == "sum_insured" for c in detail["conflicts"])


def test_injection_line_excluded_and_flagged():
    ex, f = _facts("sample_policy_family_health.pdf", extract_policy)
    assert not any("ai assistants" in c.lower() for c in f["conditions"].value)
    assert any("addressed to AI assistants" in w for w in ex.warnings)
    assert all("SAMPLE DOCUMENT FOR VITRAM" not in x for x in f["exclusions"].value)  # running header stripped


def test_calendar_respects_first_due_date(sample):
    emis = sample.get("/api/emis").json()["emis"]
    doc_emi = next(e for e in emis if e["source_type"] == "document")
    assert doc_emi["first_due_date"] == "2026-10-05"
    from datetime import date
    first = date.fromisoformat(doc_emi["first_due_date"])
    before = first.replace(day=1)
    prev = (before.replace(month=before.month - 1) if before.month > 1 else before.replace(year=before.year - 1, month=12))
    cal = sample.get(f"/api/emis/calendar?month={prev:%Y-%m}").json()
    assert not any(i["object_id"] == doc_emi["id"] for i in cal["items"])
