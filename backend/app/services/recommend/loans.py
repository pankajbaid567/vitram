"""Loan recommendation (RD §12.4, §21.1–21.2).

1. Hard eligibility filters only where the data is known.
2. Unknown eligibility is marked unknown — never assumed pass/fail.
3. Transparent fit features + configurable weights.
4. Reason codes and "why this may fit" text are generated from feature
   values and product facts; the LLM never changes scores or eligibility.
"""

from app.services.finance.loan_cost import loan_cost_breakdown
from app.fmt import inr

FORMULA_VERSION = "recommend.loans.v1"

WEIGHTS = {"cost": 0.35, "affordability": 0.35, "flexibility": 0.15, "certainty": 0.10, "warnings": 0.05}

DEFAULT_TENURE = {"personal": 36, "home": 240, "vehicle": 60, "education": 84, "gold": 12}

PURPOSE_LABELS = {
    "home": "buying a home", "vehicle": "a vehicle", "education": "education", "medical": "medical expenses",
    "wedding": "a wedding", "travel": "travel", "home_renovation": "home renovation",
    "debt_consolidation": "consolidating debt", "personal": "a personal need", "other": "your stated need",
}


def _fmt(x: float) -> str:
    return f"{inr(x)}"


def evaluate(product: dict, intent: dict, profile: dict, gst_pct: float) -> dict:
    elig = product.get("eligibility", {})
    rep = product.get("repayment", {})
    pricing = product.get("pricing", {})
    amount = intent["amount"]
    excluded: list[str] = []
    unknown: list[str] = []
    matched: list[str] = []

    if intent["purpose"] not in product.get("purposes", []):
        excluded.append("PURPOSE_MISMATCH")
    if amount < rep.get("amount_min", 0) or amount > rep.get("amount_max", float("inf")):
        excluded.append("AMOUNT_OUT_OF_RANGE")
    emp = profile.get("employment_type")
    allowed_emp = elig.get("employment", [])
    if emp and allowed_emp and "any" not in allowed_emp:
        (matched if emp in allowed_emp else excluded).append("EMPLOYMENT_MATCH" if emp in allowed_emp else "EMPLOYMENT_MISMATCH")
    age = profile.get("age")
    if age is None:
        unknown.append("AGE_UNKNOWN")
    elif not elig.get("age_min", 0) <= age <= elig.get("age_max", 200):
        excluded.append("AGE_OUT_OF_RANGE")
    else:
        matched.append("AGE_MATCH")
    income = profile.get("monthly_income")
    floor = elig.get("min_monthly_income")
    if floor:
        if income is None:
            unknown.append("INCOME_UNKNOWN")
        elif income < floor:
            excluded.append("INCOME_BELOW_FLOOR")
        else:
            matched.append("INCOME_MEETS_FLOOR")
    if elig.get("credit_score_min"):
        unknown.append("CREDIT_SCORE_REQUIREMENT_UNKNOWN")

    coll = intent.get("collateral") or {}
    need = elig.get("collateral", "none")
    if need == "required":
        types = elig.get("collateral_types", [])
        if coll.get("available") is False:
            excluded.append("COLLATERAL_REQUIRED")
        elif coll.get("available") is None:
            unknown.append("COLLATERAL_UNKNOWN")
        elif coll.get("type") and types and coll["type"] not in types:
            excluded.append("COLLATERAL_TYPE_MISMATCH")
        else:
            matched.append("COLLATERAL_MATCH")
            ltv = elig.get("max_ltv_pct")
            if ltv and coll.get("value"):
                if amount > coll["value"] * ltv / 100:
                    excluded.append("AMOUNT_EXCEEDS_LTV")
            elif ltv:
                unknown.append("COLLATERAL_VALUE_UNKNOWN")
    elif need == "none":
        matched.append("NO_COLLATERAL_NEEDED")
    elif need == "optional" and coll.get("available"):
        matched.append("COLLATERAL_OPTIONAL_MAY_LOWER_RATE")

    # tenure
    tmin, tmax = rep.get("tenure_min", 1), rep.get("tenure_max", 360)
    req_t = intent.get("tenure_months")
    notes = []
    if req_t:
        tenure = min(max(req_t, tmin), tmax)
        if tenure != req_t:
            notes.append(f"Your preferred tenure of {req_t} months isn't offered; shown at {tenure} months.")
    else:
        tenure = min(max(DEFAULT_TENURE.get(product["category"], 36), tmin), tmax)
        notes.append(f"No tenure chosen; shown at {tenure} months. You can change it.")

    rate = pricing.get("indicative_rate")
    cost = loan_cost_breakdown(amount, rate, tenure, product.get("charges"), product.get("contingent"), gst_pct)
    cost["assumptions"].insert(0, f"Indicative rate {rate:g}% p.a. from the sample catalogue (range {pricing.get('rate_min'):g}–{pricing.get('rate_max'):g}%). "
                                  "The actual rate depends on the lender's assessment.")
    emi = cost["monthly_emi"]

    # affordability
    comfort = intent.get("emi_comfort")
    surplus = profile.get("monthly_surplus")
    existing = profile.get("existing_emis") or 0
    afford = None
    if comfort:
        afford = min(comfort / emi, 1.5) / 1.5
        matched.append("EMI_WITHIN_COMFORT" if emi <= comfort else "EMI_ABOVE_COMFORT")
    elif surplus is not None and surplus > 0:
        afford = max(min((surplus - emi) / surplus + 0.5, 1), 0)
        matched.append("EMI_WITHIN_SURPLUS" if emi <= surplus else "EMI_ABOVE_SURPLUS")
    else:
        unknown.append("AFFORDABILITY_UNKNOWN")
    obligation_share = (existing + emi) / income * 100 if income else None

    # flexibility
    rules = {c["key"]: c.get("rule") for c in product.get("contingent", [])}
    pp = rules.get("part_prepayment")
    if pp and pp.get("allowed") is not False:
        flex = 1.0 - min((pp.get("charge_pct") or 0) / 5, 1) * 0.5
        matched.append("PREPAYMENT_ALLOWED")
    elif pp and pp.get("allowed") is False:
        flex = 0.0
        matched.append("NO_PART_PREPAYMENT")
    else:
        flex = 0.3
    if pricing.get("interest_type") == "floating":
        matched.append("FLOATING_RATE")

    warnings = product.get("clauses", [])
    if any(c["key"] == "credit_insurance" and c.get("mandatory", True) for c in product.get("charges", [])):
        matched.append("BUNDLED_INSURANCE")

    return {
        "product": product,
        "eligible": not excluded,
        "excluded_reasons": excluded,
        "unknown_conditions": unknown,
        "matched": matched,
        "tenure_months": tenure,
        "cost": cost,
        "affordability_score": afford,
        "flexibility_score": flex,
        "obligation_share_pct": obligation_share,
        "warnings": warnings,
        "notes": notes,
    }


def _why(e: dict, intent: dict, profile: dict, cheapest_id: str | None) -> list[str]:
    p, c = e["product"], e["cost"]
    out = []
    purpose = PURPOSE_LABELS.get(intent["purpose"], "your need")
    out.append(f"Offered for {purpose}, and your amount of {_fmt(intent['amount'])} is within its range.")
    if "EMI_WITHIN_COMFORT" in e["matched"]:
        out.append(f"EMI of {_fmt(c['monthly_emi'])} is within the {_fmt(intent['emi_comfort'])} a month you said you're comfortable with.")
    elif "EMI_WITHIN_SURPLUS" in e["matched"]:
        out.append(f"EMI of {_fmt(c['monthly_emi'])} fits within your estimated monthly surplus of {_fmt(profile['monthly_surplus'])}.")
    if p["id"] == cheapest_id:
        out.append(f"Lowest scheduled total cost among these options ({_fmt(c['total_cost_of_credit'])} over the loan).")
    if "NO_COLLATERAL_NEEDED" in e["matched"]:
        out.append("No collateral needed.")
    if "COLLATERAL_MATCH" in e["matched"]:
        out.append("Accepts the collateral you said you can offer.")
    if "PREPAYMENT_ALLOWED" in e["matched"] and intent.get("prepayment_important"):
        out.append("Allows part-prepayment, which you said matters to you.")
    return out


def _cautions(e: dict, intent: dict) -> list[str]:
    out = []
    c = e["cost"]
    m = e["matched"]
    if "EMI_ABOVE_COMFORT" in m:
        out.append(f"EMI of {_fmt(c['monthly_emi'])} is above your comfort of {_fmt(intent['emi_comfort'])}. A longer tenure would lower it.")
    if "EMI_ABOVE_SURPLUS" in m:
        out.append(f"EMI of {_fmt(c['monthly_emi'])} is more than your estimated monthly surplus.")
    if "NO_PART_PREPAYMENT" in m:
        out.append("Part-prepayment isn't allowed.")
    if "BUNDLED_INSURANCE" in m:
        out.append("A bundled loan insurance cover is mandatory and adds to the cost.")
    if "FLOATING_RATE" in m:
        out.append("Floating rate: EMI or tenure can change when the benchmark changes.")
    labels = {
        "CREDIT_SCORE_REQUIREMENT_UNKNOWN": "Has a credit-score requirement VITRAM can't check.",
        "INCOME_UNKNOWN": "Has an income requirement; confirm your income to check it.",
        "AGE_UNKNOWN": "Age limits apply; add your date of birth to check.",
        "COLLATERAL_UNKNOWN": "Needs collateral; tell us whether you can offer it.",
        "COLLATERAL_VALUE_UNKNOWN": "Loan is limited to a share of the collateral's value; add its approximate value to check.",
    }
    out += [labels[u] for u in e["unknown_conditions"] if u in labels]
    return out


EXCLUDE_TEXT = {
    "PURPOSE_MISMATCH": "Not offered for this purpose",
    "AMOUNT_OUT_OF_RANGE": "Amount outside the product's range",
    "EMPLOYMENT_MISMATCH": "Employment type not accepted",
    "AGE_OUT_OF_RANGE": "Outside the age limits",
    "INCOME_BELOW_FLOOR": "Below the minimum income",
    "COLLATERAL_REQUIRED": "Needs collateral you said you can't offer",
    "COLLATERAL_TYPE_MISMATCH": "Needs a different type of collateral",
    "AMOUNT_EXCEEDS_LTV": "Amount is more than the share of collateral value the lender finances",
}


def recommend(products: list[dict], metas: dict[str, dict], intent: dict, profile: dict, gst_pct: float) -> dict:
    evals = [evaluate(p, intent, profile, gst_pct) for p in products]
    ok = [e for e in evals if e["eligible"]]
    excluded = [e for e in evals if not e["eligible"]]
    cheapest = min(ok, key=lambda e: e["cost"]["total_cost_of_credit"], default=None)
    if ok:
        costs = [e["cost"]["total_cost_of_credit"] for e in ok]
        lo, hi = min(costs), max(costs)
        for e in ok:
            cost_score = 1.0 if hi == lo else 1 - (e["cost"]["total_cost_of_credit"] - lo) / (hi - lo)
            aff = e["affordability_score"] if e["affordability_score"] is not None else 0.5
            flex_w = WEIGHTS["flexibility"] * (1.5 if intent.get("prepayment_important") else 1)
            certainty = 1 - min(len(e["unknown_conditions"]) / 3, 1)
            warn = 1 - min(sum(1 for w in e["warnings"] if w["severity"] in ("cost_impact", "important")) / 3, 1)
            e["score"] = round(
                WEIGHTS["cost"] * cost_score + WEIGHTS["affordability"] * aff + flex_w * e["flexibility_score"]
                + WEIGHTS["certainty"] * certainty + WEIGHTS["warnings"] * warn, 4
            )
            e["why"] = _why(e, intent, profile, cheapest["product"]["id"] if cheapest else None)
            e["cautions"] = _cautions(e, intent)
    ok.sort(key=lambda e: -e["score"])

    missing = []
    if profile.get("monthly_income") is None:
        missing.append({"key": "monthly_income", "message": "Confirm your monthly income so income limits and affordability can be checked."})
    if profile.get("age") is None:
        missing.append({"key": "age", "message": "Add your date of birth so age limits can be checked."})
    if not intent.get("emi_comfort") and profile.get("monthly_surplus") is None:
        missing.append({"key": "emi_comfort", "message": "Tell us a comfortable monthly EMI, or upload a bank statement."})

    def pack(e):
        p = e["product"]
        return {
            "product_id": p["id"], "lender": p["lender"], "product_name": p["product_name"], "category": p["category"],
            "secured": p["secured"], "interest_type": p["pricing"].get("interest_type"),
            "rate_range": [p["pricing"].get("rate_min"), p["pricing"].get("rate_max")],
            "indicative_rate": p["pricing"].get("indicative_rate"),
            "tenure_months": e["tenure_months"], "cost": e["cost"], "score": e.get("score"),
            "reason_codes": e["matched"], "unknown_conditions": e["unknown_conditions"],
            "excluded_reasons": e["excluded_reasons"], "why": e.get("why", []), "cautions": e.get("cautions", []),
            "warnings": e["warnings"], "notes": e["notes"], "obligation_share_pct": e["obligation_share_pct"],
            "catalogue": metas[p["id"]],
        }

    return {
        "intent": intent,
        "profile_used": profile,
        "results": [pack(e) for e in ok],
        "excluded": [{"product_id": e["product"]["id"], "lender": e["product"]["lender"], "product_name": e["product"]["product_name"],
                      "reasons": [EXCLUDE_TEXT.get(r, r) for r in e["excluded_reasons"]]} for e in excluded
                     if "PURPOSE_MISMATCH" not in e["excluded_reasons"]],
        "missing_data": missing,
        "weights": WEIGHTS,
        "formula_version": FORMULA_VERSION,
    }
