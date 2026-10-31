"""Financial Profile Engine (RD §9).

Builds the structured FinancialProfile (RD §9.3) from normalised transactions,
recurring groups, onboarding data, family, cards, EMIs and policies. Every
material value is a *fact* carrying its state (RD §9.4):
  extracted | confirmed | conflicted | missing
User corrections are stored as overrides and applied last, so they win over
machine guesses unless a new statement clearly disagrees (→ conflicted).
"""

import hashlib
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    BankAccount,
    Document,
    DocumentFact,
    Emi,
    FamilyMember,
    FinancialProfile,
    ProfileOverride,
    RecurringGroup,
    Transaction,
    User,
    UserCard,
    UserPolicy,
)
from app.services.statements import recurring as rec
from app.services.statements.categorizer import CATEGORIES, categorize, counterparty, detect_channel, display_label
from app.services.statements.parser import ParsedStatement
from app.fmt import inr

CONFLICT_THRESHOLD = 0.25
FIXED_KINDS = {"emi", "rent", "premium", "subscription", "utility"}


def fact(value, state: str, source: str, confidence: float | None = None, refs: list | None = None, **extra) -> dict:
    out = {"value": value, "state": state, "source": source}
    if confidence is not None:
        out["confidence"] = confidence
    if refs:
        out["refs"] = refs
    out.update(extra)
    return out


def _age(dob: date | None) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# --- ingestion ------------------------------------------------------------


def _fingerprint(account_id: str, row, occurrence: int) -> str:
    base = f"{account_id}|{row.txn_date.isoformat()}|{row.amount:.2f}|{row.direction}|{' '.join(row.description.lower().split())}|{occurrence}"
    return hashlib.sha256(base.encode()).hexdigest()


def ingest_statement(db: Session, doc: Document, parsed: ParsedStatement) -> dict:
    """Insert parsed rows as transactions, skipping ones already present from an
    overlapping statement (RD §26). User category corrections survive re-ingest."""
    account_id = doc.bank_account_id
    existing = {
        fp: (cat, src)
        for fp, cat, src in db.query(Transaction.fingerprint, Transaction.category, Transaction.category_source)
        .filter(Transaction.bank_account_id == account_id)
        .all()
    }
    corrections = {
        o.path[4:]: o.corrected_value
        for o in db.query(ProfileOverride).filter(ProfileOverride.user_id == doc.owner_user_id, ProfileOverride.path.like("txn/%"))
    }
    seen: Counter = Counter()
    inserted, skipped = 0, 0
    for row in parsed.rows:
        key = (row.txn_date, row.amount, row.direction, row.description.lower())
        seen[key] += 1
        fp = _fingerprint(account_id, row, seen[key])
        if fp in existing:
            skipped += 1
            continue
        category, merchant, conf = categorize(row.description, row.direction)
        fix = corrections.get(fp) or {}
        if fix.get("direction"):
            row.direction = fix["direction"]
            row.confidence = 0.95
        category_source = "rule"
        if fix.get("category"):
            category, category_source, conf = fix["category"], "user", 0.95
        db.add(
            Transaction(
                user_id=doc.owner_user_id,
                bank_account_id=account_id,
                source_document_id=doc.id,
                txn_date=row.txn_date,
                amount=row.amount,
                direction=row.direction,
                description=row.description[:500],
                merchant=merchant,
                channel=detect_channel(row.description),
                category=category,
                category_source=category_source,
                balance=row.balance,
                fingerprint=fp,
                source_ref=row.source_ref,
                confidence=min(row.confidence, 0.95 if conf >= 0.5 else 0.7),
            )
        )
        existing[fp] = (category, "rule")
        inserted += 1
    db.flush()
    return {"inserted": inserted, "skipped_overlap": skipped}


def _override_map(db: Session, user_id: str) -> dict[str, ProfileOverride]:
    rows = (
        db.query(ProfileOverride)
        .filter(ProfileOverride.user_id == user_id)
        .order_by(ProfileOverride.created_at)
        .all()
    )
    return {o.path: o for o in rows}  # latest wins


def recurring_path(direction: str, cp: str) -> str:
    return f"recurring/{direction}/{cp}"


def rebuild_recurring(db: Session, user_id: str) -> None:
    txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    lite = [
        rec.TxnLite(t.id, t.txn_date, t.amount, t.direction, t.category, counterparty(t.description), display_label(t.description, t.merchant))
        for t in txns
    ]
    detected = rec.detect(lite)
    overrides = _override_map(db, user_id)
    existing = {(g.counterparty_key, g.direction): g for g in db.query(RecurringGroup).filter(RecurringGroup.user_id == user_id)}
    by_id = {t.id: t for t in txns}
    for t in txns:
        t.recurring_group_id = None
    kept = set()
    for d in detected:
        g = existing.get((d.counterparty_key, d.direction))
        if g is None:
            g = RecurringGroup(user_id=user_id, counterparty_key=d.counterparty_key, direction=d.direction)
            db.add(g)
        g.kind, g.label, g.typical_amount = d.kind, d.label, d.typical_amount
        g.day_of_month, g.occurrences, g.confidence = d.day_of_month, d.occurrences, d.confidence
        g.first_date, g.last_date = d.first_date, d.last_date
        ov = overrides.get(recurring_path(d.direction, d.counterparty_key))
        if ov and isinstance(ov.corrected_value, dict):
            g.state = ov.corrected_value.get("state", "confirmed")
            g.user_kind = ov.corrected_value.get("kind")
        db.flush()
        for tid in d.txn_ids:
            by_id[tid].recurring_group_id = g.id
        kept.add(g.id)
    for g in existing.values():
        if g.id not in kept and g.state != "confirmed":
            db.delete(g)
    db.flush()
    _sync_detected_emis(db, user_id)


def _sync_detected_emis(db: Session, user_id: str) -> None:
    """Detected EMI groups become unconfirmed EMI records (RD §14.1)."""
    groups = db.query(RecurringGroup).filter(RecurringGroup.user_id == user_id).all()
    emis = {e.recurring_group_id: e for e in db.query(Emi).filter(Emi.user_id == user_id, Emi.recurring_group_id.isnot(None))}
    for g in groups:
        kind = g.user_kind or g.kind
        e = emis.get(g.id)
        if kind != "emi" or g.state == "rejected":
            if e is not None and e.source_type == "bank_detection" and not e.confirmed:
                db.delete(e)
            continue
        if e is None:
            db.add(
                Emi(
                    user_id=user_id,
                    title=f"{g.label} EMI" if "emi" not in g.label.lower() else g.label,
                    emi_type="loan",
                    lender=g.label,
                    amount=g.typical_amount,
                    due_day=g.day_of_month or g.last_date.day,
                    source_type="bank_detection",
                    source_ref=f"{g.occurrences} matching debits, {g.first_date:%b %Y}–{g.last_date:%b %Y}",
                    recurring_group_id=g.id,
                    confirmed=g.state == "confirmed",
                )
            )
        elif not e.confirmed:
            e.amount = g.typical_amount
            e.due_day = g.day_of_month or e.due_day
            e.confirmed = g.state == "confirmed"
    db.flush()


# --- profile build --------------------------------------------------------


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def build_profile(db: Session, user: User) -> dict:
    uid = user.id
    txns = db.query(Transaction).filter(Transaction.user_id == uid).order_by(Transaction.txn_date).all()
    groups = db.query(RecurringGroup).filter(RecurringGroup.user_id == uid).all()
    overrides = _override_map(db, uid)
    family = db.query(FamilyMember).filter(FamilyMember.user_id == uid).all()
    accounts = db.query(BankAccount).filter(BankAccount.user_id == uid).all()
    docs = db.query(Document).filter(Document.owner_user_id == uid).all()
    cards = db.query(UserCard).filter(UserCard.user_id == uid).all()
    emis = db.query(Emi).filter(Emi.user_id == uid).all()
    policies = db.query(UserPolicy).filter(UserPolicy.user_id == uid, UserPolicy.status != "failed").all()
    doc_names = {d.id: d.display_name for d in docs}

    profile: dict = {
        "identity_summary": {"name": user.name, "age": _age(user.dob), "city": user.city},
        "employment_summary": {
            "employment_type": user.employment_type,
            "employer": user.employer,
            "designation": user.designation,
            "salary_manual": fact(user.salary_manual, "confirmed", "You entered this") if user.salary_manual else None,
        },
        "family_summary": [
            {"id": m.id, "name": m.name, "relation": m.relation, "age": m.age or _age(m.dob)} for m in family
        ],
    }

    # --- accounts / coverage
    acct_rows = []
    for a in accounts:
        a_txns = [t for t in txns if t.bank_account_id == a.id]
        acct_rows.append(
            {
                "id": a.id, "label": a.label, "bank_name": a.bank_name, "masked_ref": a.masked_account_ref,
                "is_primary": a.is_primary, "transactions": len(a_txns),
                "period_start": a_txns[0].txn_date.isoformat() if a_txns else None,
                "period_end": a_txns[-1].txn_date.isoformat() if a_txns else None,
            }
        )
    profile["bank_accounts"] = acct_rows

    if not txns:
        profile.update(_empty_money_sections())
    else:
        profile.update(_money_sections(user, txns, groups, overrides, doc_names))

    # --- obligations
    profile["obligations"] = {
        "emis": [
            {
                "id": e.id, "title": e.title, "lender": e.lender, "amount": e.amount, "due_day": e.due_day,
                "state": "confirmed" if e.confirmed else "extracted", "source_type": e.source_type,
                "remaining_count": e.remaining_count,
            }
            for e in emis
        ],
        "credit_card_bills": [
            {
                "id": c.id, "card": c.nickname, "last4": c.last4, "outstanding": c.outstanding,
                "due_date": c.due_date.isoformat() if c.due_date else None,
            }
            for c in cards
        ],
        "insurance_premiums": [
            {
                "policy_id": p.id, "insurer": p.insurer, "product": p.product_name,
                "premium": (p.premium or {}).get("amount"), "frequency": (p.premium or {}).get("frequency"),
                "renewal_date": p.end_date.isoformat() if p.end_date else None,
            }
            for p in policies
        ],
    }
    confirmed_emi_total = sum(e.amount for e in emis if e.confirmed)
    detected_emi_total = sum(e.amount for e in emis if not e.confirmed)
    profile["obligations"]["monthly_emi_total"] = fact(
        confirmed_emi_total + detected_emi_total,
        "confirmed" if emis and not detected_emi_total else ("extracted" if emis else "missing"),
        "Confirmed EMIs" if not detected_emi_total else "Includes EMIs detected from your statement that you haven't confirmed",
    )

    profile["existing_credit_products"] = [
        {"type": "credit_card", "id": c.id, "name": c.nickname, "last4": c.last4} for c in cards
    ] + [{"type": "emi", "id": e.id, "name": e.title} for e in emis if e.confirmed]
    profile["existing_insurance"] = [
        {"id": p.id, "insurer": p.insurer, "product": p.product_name, "type": p.type,
         "members": [m.family_member_id or "self" for m in p.members]}
        for p in policies
    ]
    profile["user_goals"] = []
    profile["source_links"] = [
        {"document_id": d.id, "type": d.type, "name": d.display_name, "status": d.processing_status}
        for d in docs
    ]
    profile["review_state"] = review_summary(db, uid, groups, txns, profile)
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()

    row = db.get(FinancialProfile, uid)
    if row is None:
        row = FinancialProfile(user_id=uid, profile=profile, version=1)
        db.add(row)
    else:
        row.profile = profile
        row.version += 1
        row.generated_at = datetime.now(timezone.utc)
    row.quality_flags = profile["review_state"]["flags"]
    db.flush()
    return profile


def _empty_money_sections() -> dict:
    missing = fact(None, "missing", "Upload a bank statement to estimate this")
    return {
        "income_summary": {"monthly_estimate": missing, "salary_candidates": [], "other_recurring_credits": [],
                           "irregular_credits_total": None, "consistency": None},
        "expense_summary": {"category_totals": [], "merchant_totals": [], "recurring_spends": []},
        "cashflow_metrics": {"months_covered": 0, "avg_monthly_inflow": missing, "avg_monthly_outflow": missing,
                             "fixed_monthly": missing, "variable_monthly": missing, "monthly_surplus": missing,
                             "volatility": None, "monthly_series": []},
        "behaviour": [],
        "high_value_events": [],
    }


def _money_sections(user: User, txns: list[Transaction], groups: list[RecurringGroup],
                    overrides: dict[str, ProfileOverride], doc_names: dict[str, str]) -> dict:
    first, last = txns[0].txn_date, txns[-1].txn_date
    months = max((last - first).days + 1, 1) / 30.44
    months = max(months, 1.0)
    credits = [t for t in txns if t.direction == "credit"]
    debits = [t for t in txns if t.direction == "debit"]
    inflow_total = sum(t.amount for t in credits)
    outflow_total = sum(t.amount for t in debits)
    src = f"{len(txns)} transactions, {first:%d %b %Y} – {last:%d %b %Y}"

    # --- income
    income_groups = [g for g in groups if g.direction == "credit" and g.state != "rejected"]
    candidates = rec.salary_candidates(
        [rec.DetectedGroup(g.counterparty_key, g.direction, g.user_kind or g.kind, g.label, g.typical_amount,
                           g.day_of_month, g.occurrences, g.first_date, g.last_date, g.confidence, [])
         for g in income_groups],
        inflow_total / months,
    )
    cand_rows = []
    for c in candidates:
        g = next(x for x in income_groups if x.counterparty_key == c.counterparty_key)
        cand_rows.append({
            "group_id": g.id, "label": g.label, "typical_amount": g.typical_amount, "day_of_month": g.day_of_month,
            "occurrences": g.occurrences, "state": g.state, "is_salary": (g.user_kind or g.kind) == "salary",
            "confidence": g.confidence,
        })
    confirmed_salary = [g for g in income_groups if g.state == "confirmed" and (g.user_kind or g.kind) == "salary"]
    salary_like = [c for c in cand_rows if c["is_salary"]]
    statement_income = None
    if confirmed_salary:
        statement_income = sum(g.typical_amount for g in confirmed_salary)
        income_fact = fact(statement_income, "confirmed", "Salary credits you confirmed", 0.95)
    elif len(salary_like) == 1:
        statement_income = salary_like[0]["typical_amount"]
        income_fact = fact(statement_income, "extracted", f"Recurring credit '{salary_like[0]['label']}' looks like salary",
                           salary_like[0]["confidence"])
    elif len(cand_rows) >= 1:
        income_fact = fact(None, "missing", "Several recurring credits could be salary — confirm which ones",
                           needs_review=True)
    else:
        income_fact = fact(None, "missing", "No regular salary-like credit found")
    if user.salary_manual:
        if statement_income and abs(statement_income - user.salary_manual) / user.salary_manual > CONFLICT_THRESHOLD:
            income_fact = fact(user.salary_manual, "conflicted", "You entered this; your statement suggests a different amount",
                               statement_value=statement_income)
        else:
            income_fact = fact(user.salary_manual, "confirmed", "You entered this", statement_value=statement_income)
    ov = overrides.get("income/monthly_estimate")
    if ov is not None and ov.corrected_value is not None:
        corrected = float(ov.corrected_value)
        if statement_income and corrected and abs(statement_income - corrected) / corrected > CONFLICT_THRESHOLD \
                and ov.created_at.date() < last:
            income_fact = fact(corrected, "conflicted", "Your correction differs from the latest statement",
                               statement_value=statement_income)
        else:
            income_fact = fact(corrected, "confirmed", "You corrected this", statement_value=statement_income)

    salary_amounts = []
    for g in confirmed_salary or [g for g in income_groups if (g.user_kind or g.kind) == "salary"]:
        salary_amounts += [t.amount for t in credits if t.recurring_group_id == g.id]
    consistency = None
    if len(salary_amounts) >= 2:
        cv = statistics.pstdev(salary_amounts) / statistics.mean(salary_amounts)
        consistency = {"coefficient_of_variation": round(cv, 3),
                       "label": "Steady" if cv < 0.05 else ("Mostly steady" if cv < 0.15 else "Varies month to month")}

    recurring_credit_ids = {g.id for g in income_groups}
    irregular = sum(t.amount for t in credits if t.recurring_group_id not in recurring_credit_ids)
    other_recurring = [
        {"group_id": g.id, "label": g.label, "typical_amount": g.typical_amount, "state": g.state}
        for g in income_groups if (g.user_kind or g.kind) != "salary" and g.id not in {c["group_id"] for c in cand_rows}
    ]

    # --- categories
    cat_tot: dict[str, float] = defaultdict(float)
    cat_cnt: Counter = Counter()
    for t in debits:
        cat_tot[t.category] += t.amount
        cat_cnt[t.category] += 1
    category_totals = sorted(
        (
            {"category": c, "label": CATEGORIES.get(c, c.title()), "total": round(v, 2),
             "monthly_avg": round(v / months, 2), "count": cat_cnt[c], "share_pct": round(v / outflow_total * 100, 1) if outflow_total else 0}
            for c, v in cat_tot.items()
        ),
        key=lambda r: -r["total"],
    )

    # --- merchants
    m_tot: dict[str, float] = defaultdict(float)
    m_cnt: Counter = Counter()
    m_cat: dict[str, str] = {}
    for t in debits:
        if t.merchant:
            m_tot[t.merchant] += t.amount
            m_cnt[t.merchant] += 1
            m_cat[t.merchant] = t.category
    merchant_totals = sorted(
        (
            {"merchant": m, "category": m_cat[m], "total": round(v, 2), "count": m_cnt[m],
             "per_month": round(m_cnt[m] / months, 1), "monthly_spend": round(v / months, 2)}
            for m, v in m_tot.items()
        ),
        key=lambda r: -r["total"],
    )[:15]

    recurring_spends = [
        {"group_id": g.id, "label": g.label, "kind": g.user_kind or g.kind, "typical_amount": g.typical_amount,
         "day_of_month": g.day_of_month, "occurrences": g.occurrences, "state": g.state, "confidence": g.confidence}
        for g in groups if g.direction == "debit" and g.state != "rejected"
    ]

    # --- cash flow
    fixed = sum(g.typical_amount for g in groups
                if g.direction == "debit" and g.state != "rejected" and (g.user_kind or g.kind) in FIXED_KINDS)
    avg_in, avg_out = inflow_total / months, outflow_total / months
    series: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0})
    for t in txns:
        series[_month_key(t.txn_date)]["inflow" if t.direction == "credit" else "outflow"] += t.amount
    monthly_series = [{"month": k, "inflow": round(v["inflow"], 2), "outflow": round(v["outflow"], 2)} for k, v in sorted(series.items())]
    full_months = monthly_series[1:-1] if len(monthly_series) > 2 else monthly_series
    volatility = None
    if len(full_months) >= 2 and avg_in:
        nets = [m["inflow"] - m["outflow"] for m in full_months]
        volatility = round(statistics.pstdev(nets) / avg_in, 3)
    has_uncertain = any(t.confidence < 0.6 for t in txns)
    est_state = "extracted"

    # --- behaviour (neutral language, RD §9.2)
    behaviour = []
    for m in merchant_totals[:6]:
        if m["category"] in {"food_delivery", "ecommerce", "entertainment", "groceries", "travel"} and m["per_month"] >= 2:
            behaviour.append({
                "kind": "frequent_merchant", "merchant": m["merchant"], "category": m["category"],
                "text": f"About {m['per_month']:g} payments a month to {m['merchant']}, averaging {inr(m['monthly_spend'])} a month.",
            })
    cat_month: dict[tuple[str, str], float] = defaultdict(float)
    for t in debits:
        cat_month[(t.category, _month_key(t.txn_date))] += t.amount
    for c in category_totals[:8]:
        if c["category"] in {"transfers", "emi", "card_payment", "rent", "investments"}:
            continue
        per = {mk: v for (cc, mk), v in cat_month.items() if cc == c["category"]}
        if len(per) >= 3:
            avg = sum(per.values()) / len(per)
            peak_month, peak = max(per.items(), key=lambda kv: kv[1])
            if peak > 1.5 * avg and peak - avg > 2000:
                behaviour.append({
                    "kind": "category_spike", "category": c["category"], "month": peak_month,
                    "text": f"{c['label']} was higher in {datetime.strptime(peak_month, '%Y-%m'):%B %Y} "
                            f"({inr(peak)}) than your usual {inr(avg)} a month.",
                })
    subs = [g for g in groups if (g.user_kind or g.kind) == "subscription" and g.state != "rejected"]
    if subs:
        behaviour.append({
            "kind": "subscriptions", "text": f"{len(subs)} recurring subscriptions totalling about "
                                             f"{inr(sum(g.typical_amount for g in subs))} a month.",
        })

    # --- high-value events
    hv = []
    for direction, pool in (("debit", debits), ("credit", credits)):
        if not pool:
            continue
        med = statistics.median(t.amount for t in pool)
        for t in pool:
            if t.amount >= 25_000 and t.amount >= 3 * med and t.recurring_group_id is None:
                hv.append({
                    "transaction_id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "direction": direction,
                    "description": t.merchant or t.description[:80], "category": t.category,
                    "source": {"document_id": t.source_document_id, "document_name": doc_names.get(t.source_document_id),
                               "ref": t.source_ref},
                })
    hv.sort(key=lambda r: -r["amount"])

    return {
        "income_summary": {
            "monthly_estimate": income_fact,
            "salary_candidates": cand_rows,
            "other_recurring_credits": other_recurring,
            "irregular_credits_total": round(irregular, 2),
            "consistency": consistency,
        },
        "expense_summary": {
            "category_totals": category_totals,
            "merchant_totals": merchant_totals,
            "recurring_spends": recurring_spends,
        },
        "cashflow_metrics": {
            "months_covered": round(months, 1),
            "period_start": first.isoformat(),
            "period_end": last.isoformat(),
            "avg_monthly_inflow": fact(round(avg_in, 2), est_state, src),
            "avg_monthly_outflow": fact(round(avg_out, 2), est_state, src),
            "fixed_monthly": fact(round(fixed, 2), est_state, "Recurring EMIs, rent, premiums, subscriptions and utilities"),
            "variable_monthly": fact(round(max(avg_out - fixed, 0), 2), est_state, "Average outflow minus fixed items"),
            "monthly_surplus": fact(round(avg_in - avg_out, 2), est_state, "Average inflow minus average outflow"),
            "volatility": volatility,
            "has_uncertain_transactions": has_uncertain,
            "monthly_series": monthly_series,
        },
        "behaviour": behaviour,
        "high_value_events": hv[:10],
    }


def review_summary(db: Session, uid: str, groups: list[RecurringGroup], txns: list[Transaction], profile: dict) -> dict:
    pending_groups = [g for g in groups if g.state == "extracted" and (g.user_kind or g.kind) in rec.NEEDS_CONFIRMATION]
    low_conf = [t for t in txns if t.confidence < 0.6 and t.category_source != "user"]
    fact_q = db.query(DocumentFact).filter(DocumentFact.user_id == uid)
    conflicted = fact_q.filter(DocumentFact.state == "conflicted").count()
    low_facts = fact_q.filter(DocumentFact.state == "extracted", DocumentFact.confidence < 0.6).count()
    income = (profile.get("income_summary") or {}).get("monthly_estimate") or {}
    income_needs = 1 if income.get("needs_review") or income.get("state") == "conflicted" else 0
    total = len(pending_groups) + len(low_conf) + conflicted + income_needs
    flags = []
    if not txns:
        flags.append("no_statement")
    if income_needs:
        flags.append("income_needs_confirmation")
    if low_conf:
        flags.append("uncertain_transactions")
    if conflicted:
        flags.append("conflicted_facts")
    return {
        "items_needing_review": total,
        "recurring_to_confirm": len(pending_groups),
        "uncertain_transactions": len(low_conf),
        "conflicted_facts": conflicted,
        "low_confidence_document_facts": low_facts,
        "income_needs_confirmation": bool(income_needs),
        "flags": flags,
    }


def get_profile(db: Session, user: User, rebuild: bool = False) -> dict:
    row = db.get(FinancialProfile, user.id)
    if row is None or rebuild:
        profile = build_profile(db, user)
        db.commit()
        return profile
    return row.profile
