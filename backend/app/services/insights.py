"""Spending insights (M13): trends, possible subscriptions, unusual transactions, explain-this-transaction.

Everything here is deterministic arithmetic over the user's own transactions. Subscriptions and unusual
transactions are *possible matches* the user confirms or dismisses; nothing is called fraud, and the
wording stays neutral (no judgement about how people spend).
"""

from __future__ import annotations

import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.fmt import inr
from app.models import Document, ProfileOverride, RecurringGroup, Transaction
from app.services.statements.categorizer import CATEGORIES

TREND_CATEGORIES = {"food_delivery", "groceries", "ecommerce", "travel", "fuel", "entertainment", "utilities", "subscriptions",
                    "healthcare", "education", "cash"}
EXPECTED_LARGE = {"rent", "emi", "card_payment", "investments", "transfers", "insurance", "salary", "income_other"}
SUBSCRIPTION_HINTS = ("netflix", "spotify", "prime", "hotstar", "youtube", "apple", "google", "zee5", "sonyliv", "jiocinema",
                      "audible", "kindle", "linkedin", "microsoft", "adobe", "icloud", "swiggy one", "zomato gold", "gym", "cult")
TREND_MIN_CHANGE_PCT, TREND_MIN_CHANGE_INR = 20.0, 1000.0
LOOKBACK_DAYS = 90


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def full_months(txns: list[Transaction]) -> list[str]:
    """Calendar months fully covered by the statements (first/last month dropped when only partly covered)."""
    if not txns:
        return []
    first, last = min(t.txn_date for t in txns), max(t.txn_date for t in txns)
    keys = sorted({_month_key(t.txn_date) for t in txns})
    if first.day > 3 and keys:
        keys = keys[1:]
    if keys and last.day < calendar.monthrange(last.year, last.month)[1] - 3 and keys[-1] == _month_key(last):
        keys = keys[:-1]
    return keys


def _overrides(db: Session, user_id: str, prefix: str) -> dict[str, object]:
    rows = db.query(ProfileOverride).filter(ProfileOverride.user_id == user_id, ProfileOverride.path.like(f"{prefix}%")) \
             .order_by(ProfileOverride.created_at).all()
    out: dict[str, object] = {}
    for r in rows:  # latest decision wins
        out[r.path[len(prefix):]] = r.corrected_value
    return out


def category_trends(txns: list[Transaction]) -> tuple[list[dict], str | None]:
    months = full_months(txns)
    if len(months) < 3:
        return [], None
    latest, prior = months[-1], months[:-1]
    per: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in txns:
        if t.direction == "debit" and t.category in TREND_CATEGORIES:
            per[t.category][_month_key(t.txn_date)] += t.amount
    out = []
    for cat, by_month in per.items():
        now = round(by_month.get(latest, 0.0), 2)
        avg = round(sum(by_month.get(m, 0.0) for m in prior) / len(prior), 2)
        diff = round(now - avg, 2)
        if avg <= 0 or abs(diff) < TREND_MIN_CHANGE_INR or abs(diff) / avg * 100 < TREND_MIN_CHANGE_PCT:
            continue
        out.append({"category": cat, "label": CATEGORIES.get(cat, cat), "month": latest, "amount": now, "average": avg,
                    "change": diff, "change_pct": round(diff / avg * 100, 1),
                    "series": [{"month": m, "amount": round(by_month.get(m, 0.0), 2)} for m in months]})
    return sorted(out, key=lambda x: -abs(x["change"])), latest


def subscriptions(db: Session, user_id: str) -> list[dict]:
    groups = db.query(RecurringGroup).filter(RecurringGroup.user_id == user_id, RecurringGroup.direction == "debit").all()
    out = []
    for g in groups:
        name = f"{g.label} {g.counterparty_key}".lower()
        hinted = any(h in name for h in SUBSCRIPTION_HINTS)
        if not (g.kind == "subscription" or g.user_kind == "subscription" or (hinted and g.typical_amount < 5000)):
            continue
        if g.user_kind == "not_subscription":
            continue
        out.append({"group_id": g.id, "label": g.label, "typical_amount": round(g.typical_amount, 2), "day_of_month": g.day_of_month,
                    "occurrences": g.occurrences, "last_date": g.last_date.isoformat(),
                    "yearly_estimate": round(g.typical_amount * 12, 2),
                    "status": "confirmed" if g.user_kind == "subscription" else "possible",
                    "why": "Charged every month" + (" by a known subscription service" if hinted else "")})
    return sorted(out, key=lambda s: -s["typical_amount"])


def unusual(db: Session, user_id: str, txns: list[Transaction]) -> list[dict]:
    if not txns:
        return []
    dismissed = _overrides(db, user_id, "insight/unusual/")
    latest = max(t.txn_date for t in txns)
    since = latest - timedelta(days=LOOKBACK_DAYS)
    debits = [t for t in txns if t.direction == "debit"]
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    by_cat: dict[str, list[Transaction]] = defaultdict(list)
    for t in debits:
        if t.merchant:
            by_merchant[t.merchant.lower()].append(t)
        by_cat[t.category].append(t)
    flagged: dict[str, dict] = {}

    def flag(t: Transaction, reason: str, kind: str):
        if t.id in dismissed:
            return
        f = flagged.setdefault(t.id, {"id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "description": t.description,
                                      "merchant": t.merchant, "category": CATEGORIES.get(t.category, t.category), "reasons": [], "kinds": []})
        f["reasons"].append(reason)
        f["kinds"].append(kind)

    for t in debits:
        if t.txn_date < since or t.category in EXPECTED_LARGE:
            continue
        hist = [x.amount for x in by_merchant.get((t.merchant or "").lower(), []) if x.id != t.id] if t.merchant else []
        if len(hist) >= 3:
            med = statistics.median(hist)
            if t.amount > 2.5 * med and t.amount - med >= 1000:
                flag(t, f"About {t.amount / med:.1f}× your usual {inr(med)} at {t.merchant}", "merchant_spike")
        cat_hist = [x.amount for x in by_cat.get(t.category, []) if x.id != t.id]
        if len(cat_hist) >= 5 and t.id not in flagged:
            med = statistics.median(cat_hist)
            if t.amount > 3 * med and t.amount >= 5000:
                flag(t, f"Much larger than your usual {CATEGORIES.get(t.category, t.category).lower()} payment of about {inr(med)}", "category_spike")
        if t.merchant and len(by_merchant[t.merchant.lower()]) == 1 and t.amount >= 15000:
            flag(t, f"First payment to {t.merchant}, and a large one", "new_payee")
        if t.merchant:
            twin = next((x for x in by_merchant[t.merchant.lower()] if x.id != t.id and abs(x.amount - t.amount) < 0.01
                         and abs((x.txn_date - t.txn_date).days) <= 1), None)
            if twin:
                flag(t, f"Same amount charged by {t.merchant} twice within a day — possibly a duplicate", "possible_duplicate")
    return sorted(flagged.values(), key=lambda f: f["date"], reverse=True)


def spending_insights(db: Session, user_id: str) -> dict:
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    trends, latest = category_trends(txns)
    subs = subscriptions(db, user_id)
    odd = unusual(db, user_id, txns)
    months = full_months(txns)
    opportunities = []
    live_subs = [s for s in subs if s["status"] in ("possible", "confirmed")]
    if live_subs:
        monthly = round(sum(s["typical_amount"] for s in live_subs), 2)
        opportunities.append({"kind": "subscriptions", "title": f"Subscriptions come to about {inr(monthly)} a month",
                              "body": f"That's about {inr(monthly * 12)} a year across {len(live_subs)} services. Worth checking you still use each one.",
                              "amount": monthly})
    ups = [t for t in trends if t["change"] > 0]
    if ups:
        u = ups[0]
        opportunities.append({"kind": "trend", "title": f"Spending on {u['label'].lower()} was higher than usual in {_month_label(u['month'])}",
                              "body": f"{inr(u['amount'])}, compared with your average of {inr(u['average'])}. If that wasn't planned, it's a place to look first.",
                              "amount": u["change"]})
    return {
        "currency": "INR", "months_covered": months, "latest_full_month": latest,
        "trends": trends, "subscriptions": subs, "unusual": odd, "opportunities": opportunities[:3],
        "notes": [
            "Subscriptions and unusual transactions are possible matches from patterns in your statement. Confirm or dismiss each one.",
            "An unusual payment isn't necessarily a problem. If you don't recognise one, contact your bank.",
            "Trends compare full calendar months only; partly covered months are left out.",
        ],
    }


def _month_label(key: str) -> str:
    y, m = key.split("-")
    return f"{calendar.month_name[int(m)]} {y}"


def explain_transaction(db: Session, user_id: str, txn_id: str) -> dict | None:
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == user_id).first()
    if not t:
        return None
    doc = db.get(Document, t.source_document_id)
    lines = []
    cat_label = CATEGORIES.get(t.category, t.category)
    lines.append(f"Categorised as {cat_label} " + ("because you set it." if t.category_source == "user"
                                                  else "from the payee name and payment details in your statement."))
    same = []
    if t.merchant:
        same = db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.merchant == t.merchant,
                                            Transaction.direction == t.direction, Transaction.id != t.id).all()
        if same:
            avg = sum(x.amount for x in same) / len(same)
            first = min(x.txn_date for x in same + [t])
            lines.append(f"{len(same) + 1} payments to {t.merchant} since {first.day} {first.strftime('%b %Y')}, about {inr(avg)} each on average.")
        else:
            lines.append(f"This is the only payment to {t.merchant} in your statements.")
    group = db.get(RecurringGroup, t.recurring_group_id) if t.recurring_group_id else None
    if group:
        state = {"confirmed": "you confirmed", "rejected": "you marked as not recurring"}.get(group.state, "VITRAM detected")
        lines.append(f"Part of a monthly pattern ({group.label}, around day {group.day_of_month or '—'}) that {state}.")
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    odd = next((u for u in unusual(db, user_id, txns) if u["id"] == t.id), None)
    receipts = [d for d in db.query(Document).filter(Document.owner_user_id == user_id, Document.type == "receipt").all()
                if (d.meta or {}).get("linked_transaction_id") == t.id]
    return {
        "transaction": {"id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "direction": t.direction,
                        "description": t.description, "merchant": t.merchant, "channel": t.channel, "category": cat_label,
                        "category_source": t.category_source, "confidence": t.confidence},
        "explanation": lines,
        "unusual": odd["reasons"] if odd else [],
        "recurring": {"id": group.id, "label": group.label, "state": group.state} if group else None,
        "source": {"document_id": t.source_document_id, "document_name": doc.display_name if doc else None, "ref": t.source_ref},
        "receipts": [{"document_id": d.id, "name": d.display_name, **((d.meta or {}).get("receipt") or {})} for d in receipts],
    }
