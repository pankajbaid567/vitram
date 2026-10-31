"""Recurring obligation / income detection (RD §9.2, §14.1, §26).

A group is recurring when the same counterparty appears in at least two
distinct months with similar amounts on a roughly monthly cadence. Detected
groups are *extracted* facts — salary, EMI and card-bill groups always go to
review for confirmation.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

CATEGORY_TO_KIND = {
    "salary": "salary",
    "emi": "emi",
    "card_payment": "card_bill",
    "rent": "rent",
    "insurance": "premium",
    "subscriptions": "subscription",
    "utilities": "utility",
    "investments": "investment",
    "transfers": "transfer",
}

NEEDS_CONFIRMATION = {"salary", "income_other", "emi", "card_bill", "premium", "rent"}
DISCRETIONARY = {"food_delivery", "groceries", "ecommerce", "travel", "entertainment", "fuel", "cash", "healthcare"}
OBLIGATION_CATEGORIES = {"salary", "emi", "card_payment", "rent", "insurance", "subscriptions", "utilities", "investments"}


@dataclass
class TxnLite:
    id: str
    txn_date: date
    amount: float
    direction: str
    category: str
    counterparty: str
    label: str


@dataclass
class DetectedGroup:
    counterparty_key: str
    direction: str
    kind: str
    label: str
    typical_amount: float
    day_of_month: int | None
    occurrences: int
    first_date: date
    last_date: date
    confidence: float
    txn_ids: list[str]


def _months(d: date) -> int:
    return d.year * 12 + d.month


def detect(txns: list[TxnLite]) -> list[DetectedGroup]:
    buckets: dict[tuple[str, str], list[TxnLite]] = defaultdict(list)
    for t in txns:
        if t.counterparty in {"", "unknown"}:
            continue
        buckets[(t.counterparty, t.direction)].append(t)

    groups: list[DetectedGroup] = []
    for (cp, direction), items in buckets.items():
        items.sort(key=lambda t: t.txn_date)
        # Many payments a month to the same merchant is frequent spending, not a recurring obligation.
        all_months = {_months(t.txn_date) for t in items}
        top_cat = max({t.category for t in items}, key=lambda c: sum(1 for t in items if t.category == c))
        if len(items) / len(all_months) > 1.6 and top_cat not in OBLIGATION_CATEGORIES:
            continue
        if direction == "debit" and top_cat in DISCRETIONARY:
            continue
        # Try the whole bucket, then an amount-consistent core (median ± 20 %).
        median = statistics.median(t.amount for t in items)
        core = [t for t in items if abs(t.amount - median) <= max(0.2 * median, 1)]
        by_month: dict[int, list[TxnLite]] = defaultdict(list)
        for t in core:
            by_month[_months(t.txn_date)].append(t)
        if len(by_month) < 2:
            continue
        # Use at most one representative per month (closest to median).
        reps = [min(v, key=lambda t: abs(t.amount - median)) for _, v in sorted(by_month.items())]
        gaps = [(b.txn_date - a.txn_date).days for a, b in zip(reps, reps[1:])]
        monthly_gaps = [g for g in gaps if 20 <= g <= 40]
        if not gaps or len(monthly_gaps) < max(1, int(len(gaps) * 0.6)):
            continue
        month_span = _months(reps[-1].txn_date) - _months(reps[0].txn_date) + 1
        coverage = len(reps) / month_span
        amounts = [t.amount for t in reps]
        spread = (max(amounts) - min(amounts)) / median if median else 1
        confidence = round(min(0.95, 0.45 + 0.3 * coverage + 0.2 * (1 - min(spread, 1)) + 0.05 * min(len(reps), 6) / 6), 2)
        cats = [t.category for t in reps]
        top_cat = max(set(cats), key=cats.count)
        kind = CATEGORY_TO_KIND.get(top_cat)
        if kind is None:
            kind = "income_other" if direction == "credit" else "other"
        days = [t.txn_date.day for t in reps]
        groups.append(
            DetectedGroup(
                counterparty_key=cp,
                direction=direction,
                kind=kind,
                label=reps[-1].label,
                # Latest three occurrences reflect revisions (e.g. a salary increment).
                typical_amount=round(statistics.median(amounts[-3:]), 2),
                day_of_month=max(set(days), key=days.count) if len(set(days)) < len(days) else round(statistics.median(days)),
                occurrences=len(reps),
                first_date=reps[0].txn_date,
                last_date=reps[-1].txn_date,
                confidence=confidence,
                txn_ids=[t.id for t in core],
            )
        )
    return groups


def salary_candidates(groups: list[DetectedGroup], avg_monthly_credit: float) -> list[DetectedGroup]:
    """Recurring credits that could be salary: labelled salary, or large and regular (RD §26)."""
    out = []
    for g in groups:
        if g.direction != "credit":
            continue
        if g.kind == "salary" or (g.typical_amount >= 0.3 * avg_monthly_credit and g.occurrences >= 2):
            out.append(g)
    return sorted(out, key=lambda g: -g.typical_amount)
