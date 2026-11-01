"""Performance guardrails: the hot queries use their indexes, and big statements finish promptly.

Generous bounds: these catch an accidental O(n²) or a dropped index, not a few milliseconds.
"""

import random
import time
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import signup


def statement_csv(months: int, per_month: int = 45) -> bytes:
    rng = random.Random(7)
    rows, balance, day = [], 100000.0, date(2024, 1, 1)
    rows.append("BIG BANK (SAMPLE) - ACCOUNT STATEMENT")
    rows.append("Account,Savings 1234,Period,01/01/2024 to 31/12/2025")
    rows.append("")
    rows.append("Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance")
    merchants = ["SWIGGY", "ZOMATO", "AMAZON PAY", "UBER TRIP", "BIG BAZAAR", "AIRTEL BILL", "NETFLIX", "IRCTC", "POS CROMA"]
    for _ in range(months * per_month):
        day += timedelta(hours=rng.choice([6, 8, 12]))
        if rng.random() < 0.04:
            amt = round(rng.uniform(40000, 90000), 2)
            balance += amt
            rows.append(f"{day:%d/%m/%Y},ACME TECHNOLOGIES SALARY,,{amt:.2f},{balance:.2f}")
        else:
            amt = round(rng.uniform(80, 4000), 2)
            balance -= amt
            rows.append(f"{day:%d/%m/%Y},UPI/{rng.choice(merchants)}/{rng.randint(10**8, 10**9)},{amt:.2f},,{balance:.2f}")
    return "\n".join(rows).encode()


def test_a_two_year_statement_is_processed_in_seconds(client):
    signup(client)
    client.post("/api/consents", json={"purpose": "financial_documents"})
    data = statement_csv(months=24)          # ≈ 1,080 transactions
    start = time.perf_counter()
    d = client.post("/api/documents", data={"type": "bank_statement", "period_months": "12", "account_label": "Big"},
                    files={"file": ("big.csv", data, "text/csv")}).json()
    status = client.get(f"/api/documents/{d['id']}").json()
    elapsed = time.perf_counter() - start
    assert status["status"] == "needs_review", status
    assert status["transactions_found"] > 900
    assert elapsed < 20, f"processing took {elapsed:.1f}s"
    t0 = time.perf_counter()
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/transactions?limit=500").status_code == 200
    assert time.perf_counter() - t0 < 3


@pytest.mark.skipif(engine.dialect.name != "sqlite", reason="uses SQLite's EXPLAIN QUERY PLAN")
@pytest.mark.parametrize("sql,index", [
    ("SELECT * FROM transactions WHERE user_id = 'u' ORDER BY txn_date DESC LIMIT 100", "ix_transactions_user_date_id"),
    ("SELECT * FROM transactions WHERE user_id = 'u' AND (txn_date < '2026-01-01' OR (txn_date = '2026-01-01' AND id < 'x')) "
     "ORDER BY txn_date DESC, id DESC LIMIT 101", "ix_transactions_user_date_id"),
    ("SELECT * FROM document_facts WHERE document_id = 'd' AND key = 'last4'", "ix_document_facts_doc_key"),
    ("SELECT id FROM reminders WHERE status = 'scheduled' AND schedule_at <= '2030-01-01' ORDER BY schedule_at LIMIT 100", "ix_reminders_status_schedule"),
])
def test_hot_queries_use_their_indexes(client, sql, index):
    with engine.connect() as conn:
        plan = " ".join(str(r) for r in conn.execute(text("EXPLAIN QUERY PLAN " + sql)))
    assert index in plan, plan
