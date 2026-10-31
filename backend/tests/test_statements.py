"""RD §27.1/27.2 — statement parsing, categorisation, dedup, recurring grouping, override precedence."""

from datetime import date

from app.services.statements import recurring as rec
from app.services.statements.categorizer import categorize, counterparty, display_label
from app.services.statements.parser import parse_amount, parse_csv, parse_pdf, parse_statement
from tests.conftest import FIXTURES, signup


def test_parse_amount_indian_formats():
    assert parse_amount("1,12,450.00") == 112450.0
    assert parse_amount("₹2,500") == 2500.0
    assert parse_amount("500.00 Dr") == -500.0
    assert parse_amount("") is None
    assert parse_amount("abc") is None


def test_csv_fixture_parses_all_rows():
    parsed = parse_csv((FIXTURES / "sample_statement_6m.csv").read_bytes())
    assert len(parsed.rows) == 260
    assert parsed.period == (date(2026, 3, 1), date(2026, 8, 31))
    salary = [r for r in parsed.rows if "SALARY" in r.description]
    assert len(salary) == 6 and all(r.direction == "credit" for r in salary)
    credits = sum(r.amount for r in parsed.rows if r.direction == "credit")
    debits = sum(r.amount for r in parsed.rows if r.direction == "debit")
    # closing balance − opening balance == credits − debits
    last_balance = parsed.rows[-1].balance
    assert round(84000 + credits - debits, 2) == round(last_balance, 2)


def test_pdf_fixture_direction_from_balance():
    parsed = parse_pdf((FIXTURES / "sample_statement_mar_apr.pdf").read_bytes())
    csv_rows = [r for r in parse_csv((FIXTURES / "sample_statement_6m.csv").read_bytes()).rows if r.txn_date < date(2026, 5, 1)]
    assert len(parsed.rows) == len(csv_rows)
    assert [r.direction for r in parsed.rows] == [r.direction for r in csv_rows]
    assert all(r.source_ref.startswith("page ") for r in parsed.rows)


def test_unsupported_and_encrypted():
    import io

    from pypdf import PdfReader, PdfWriter

    try:
        parse_statement(b"%PDF-1.4 garbage", "application/pdf")
    except Exception as exc:
        assert getattr(exc, "code", None) in ("UNREADABLE_PDF", "NO_TEXT_LAYER")
    w = PdfWriter()
    w.append(PdfReader(str(FIXTURES / "sample_statement_mar_apr.pdf")))
    w.encrypt("secret")
    buf = io.BytesIO()
    w.write(buf)
    try:
        parse_statement(buf.getvalue(), "application/pdf")
        raise AssertionError("expected failure")
    except Exception as exc:
        assert exc.code == "PASSWORD_PROTECTED"


def test_categorizer_rules():
    assert categorize("UPI/DR/1/SWIGGY/YESB/swiggy@ybl/Order", "debit")[0] == "food_delivery"
    assert categorize("NEFT-ACME TECH-SALARY SEP", "credit")[0] == "salary"
    assert categorize("NACH-DR-KONKAN FINANCE LTD-EMI", "debit")[0] == "emi"
    assert categorize("NACH-DR-WESTERN GHATS LIFE-PREMIUM", "debit")[0] == "insurance"
    assert categorize("NACH-DR-GROWW MUTUAL FUND SIP", "debit")[0] == "investments"
    assert categorize("CC PAYMENT HORIZON BANK", "debit")[0] == "card_payment"
    assert categorize("SOMETHING UNKNOWN", "debit")[0] == "other"
    assert counterparty("NEFT-ACME LTD-SALARY MAR 2026") == counterparty("NEFT-ACME LTD-SALARY APR 2026")
    assert display_label("UPI/DR/123/RAJESH KUMAR/AXIS/r@okaxis/rent") == "Rajesh Kumar"


def _t(i, d, amt, cat="emi", cp="konkan finance", direction="debit"):
    return rec.TxnLite(str(i), d, amt, direction, cat, cp, cp.title())


def test_recurring_detection_and_frequent_merchant_excluded():
    emis = [_t(i, date(2026, m, 3), 11240) for i, m in enumerate(range(3, 9))]
    swiggy = [_t(100 + i, date(2026, 3 + i // 8, 1 + (i % 8) * 3), 400 + i, "food_delivery", "swiggy") for i in range(48)]
    groups = rec.detect(emis + swiggy)
    assert [g.kind for g in groups] == ["emi"]
    assert groups[0].typical_amount == 11240 and groups[0].day_of_month == 3


def test_multiple_salary_like_credits_need_confirmation():
    a = [_t(i, date(2026, m, 1), 90000, "salary", "acme salary", "credit") for i, m in enumerate(range(3, 9))]
    b = [_t(50 + i, date(2026, m, 10), 60000, "salary", "side gig salary", "credit") for i, m in enumerate(range(3, 9))]
    cands = rec.salary_candidates(rec.detect(a + b), avg_monthly_credit=150000)
    assert len(cands) == 2


# --- through the API -----------------------------------------------------


def _upload_statement(c, path, account_id=None, months=6):
    data = {"type": "bank_statement", "period_months": str(months)}
    if account_id:
        data["bank_account_id"] = account_id
    else:
        data["account_label"] = "Salary account"
    return c.post("/api/documents", data=data, files={"file": (path.name, path.read_bytes(), "text/csv")})


def test_upload_requires_consent(client):
    signup(client)
    r = _upload_statement(client, FIXTURES / "sample_statement_6m.csv")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_statement_flow_dedup_and_overrides(client):
    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    r = _upload_statement(client, FIXTURES / "sample_statement_6m.csv")
    assert r.status_code == 200, r.text
    doc = client.get(f"/api/documents/{r.json()['id']}").json()
    assert doc["status"] in ("needs_review", "ready") and doc["transactions_found"] == 260

    # duplicate file → warned, not re-imported
    dup = _upload_statement(client, FIXTURES / "sample_statement_6m.csv", doc["bank_account_id"])
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_DOCUMENT"

    # overlapping statement (PDF of Mar–Apr) → rows already present are skipped
    pdf = FIXTURES / "sample_statement_mar_apr.pdf"
    r2 = client.post("/api/documents", data={"type": "bank_statement", "period_months": "3", "bank_account_id": doc["bank_account_id"]},
                     files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
    d2 = client.get(f"/api/documents/{r2.json()['id']}").json()
    assert any("already in VITRAM" in w for w in d2["warnings"]), d2
    assert client.get("/api/transactions?limit=1").json()["total"] == 260

    review = client.get("/api/profile/review").json()
    salary = next(g for g in review["recurring"] if g["kind"] == "salary")
    assert salary["needs_confirmation"]
    income = client.get("/api/profile").json()["profile"]["income_summary"]["monthly_estimate"]
    assert income["state"] == "extracted" and income["value"] == 118200

    # confirm salary → confirmed state
    client.post(f"/api/profile/recurring/{salary['id']}", json={"action": "confirm"})
    income = client.get("/api/profile").json()["profile"]["income_summary"]["monthly_estimate"]
    assert income["state"] == "confirmed"

    # user override wins over the statement
    client.patch("/api/profile/overrides", json={"path": "income/monthly_estimate", "value": 115000})
    income = client.get("/api/profile").json()["profile"]["income_summary"]["monthly_estimate"]
    assert income["value"] == 115000 and income["state"] == "confirmed"

    # recategorise one transaction; correction survives a profile rebuild
    t = client.get("/api/transactions?category=other&limit=1").json()["items"][0]
    client.patch(f"/api/transactions/{t['id']}", json={"category": "ecommerce"})
    client.get("/api/profile?rebuild=true")
    t2 = [x for x in client.get("/api/transactions?category=ecommerce&limit=500").json()["items"] if x["id"] == t["id"]][0]
    assert t2["category_source"] == "user"

    # detected EMI appears unconfirmed
    emis = client.get("/api/emis").json()["emis"]
    assert any(e["source_type"] == "bank_detection" and not e["confirmed"] for e in emis)


def test_cross_user_access_is_denied(client_factory):
    a, b = client_factory(), client_factory()
    signup(a)
    signup(b)
    a.post("/api/consents", json={"purpose": "financial_documents"})
    r = _upload_statement(a, FIXTURES / "sample_statement_6m.csv")
    doc_id = r.json()["id"]
    assert b.get(f"/api/documents/{doc_id}").status_code == 404
    assert b.get(f"/api/documents/{doc_id}/file").status_code == 404
    assert b.delete(f"/api/documents/{doc_id}").status_code == 404
    assert b.get("/api/transactions").json()["total"] == 0


def test_delete_document_removes_derived_data(client):
    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    doc = _upload_statement(client, FIXTURES / "sample_statement_6m.csv").json()
    assert client.get("/api/transactions").json()["total"] == 260
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/profile").json()["profile"]["income_summary"]["monthly_estimate"]["state"] == "missing"
