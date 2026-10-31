"""Insurance recommendation and emergency applicability (RD §15.3–15.4, §16, §21.3).

Recommendations are profile-based fit assessments against a labelled sample
catalogue. Emergency applicability is a documented-coverage shortlist — never
a claim decision (RD §33.1: no guarantee of claim approval).
"""

from datetime import date
from app.fmt import inr

FORMULA_VERSION = "recommend.insurance.v1"

RELATION_GROUPS = {
    "self": "self", "spouse": "spouse", "child": "child", "son": "child", "daughter": "child",
    "father": "father", "mother": "mother", "parent": "parent", "father_in_law": "parent", "mother_in_law": "parent",
}


def _age_band_match(band: str, age: int) -> bool:
    lo, hi = (int(x) for x in band.split("-"))
    return lo <= age <= hi


def _relation_ok(allowed: list[str], rel: str) -> bool:
    g = RELATION_GROUPS.get(rel, rel)
    return g in allowed or (g in ("father", "mother") and "parent" in allowed)


def indicative_premium(product: dict, members: list[dict], sum_insured: float | None) -> dict:
    rows = (product.get("premium") or {}).get("indicative", [])
    ages = [m["age"] for m in members if m.get("age") is not None]
    if not rows:
        return {"amount": None, "reason": "No indicative premium in the sample data."}
    if len(ages) < len(members):
        return {"amount": None, "reason": "Add ages for everyone to be covered to see an indicative premium."}
    eldest = max(ages) if ages else None
    candidates = [r for r in rows if (sum_insured is None or r["sum_insured"] == sum_insured)
                  and (eldest is None or _age_band_match(r["age_band"], eldest))
                  and r.get("members", 1) == len(members)]
    if not candidates and sum_insured is None:
        candidates = [r for r in rows if eldest is not None and _age_band_match(r["age_band"], eldest)
                      and r.get("members", 1) == len(members)]
    if not candidates:
        return {"amount": None, "reason": "No indicative premium in the sample data for this age, cover and number of people."}
    r = min(candidates, key=lambda r: r["sum_insured"])
    amount = r.get("annual") or r.get("single")
    return {"amount": amount, "frequency": "annual" if r.get("annual") else "single trip", "sum_insured": r["sum_insured"],
            "basis": {k: v for k, v in r.items() if k not in ("annual", "single")}, "binding": False}


def existing_cover(policies: list[dict], member_keys: list[str], ptype: str) -> dict:
    per = {}
    for key in member_keys:
        covers = [p for p in policies if p["type"] == ptype and key in p["member_keys"]]
        per[key] = {"policies": [{"id": p["id"], "name": p["product_name"], "sum_insured": p.get("sum_insured")} for p in covers],
                    "sum_insured_total": sum(p.get("sum_insured") or 0 for p in covers) if covers else 0}
    return per


def recommend(products: list[dict], metas: dict, intent: dict, members: list[dict], policies: list[dict]) -> dict:
    """members = [{"key": "self"|member_id, "name", "relation", "age"}]"""
    ptype = intent["type"]
    target = intent.get("sum_insured")
    budget = intent.get("budget_annual")
    cover = existing_cover(policies, [m["key"] for m in members], ptype)
    results, excluded = [], []
    for p in products:
        if p["type"] != ptype:
            continue
        # Market-reference entries make the catalogue searchable, but are not
        # scored until eligibility, restrictions and premium inputs are verified.
        if p.get("reference_only"):
            continue
        elig = p.get("eligibility", {})
        reasons, unknown, codes = [], [], []
        for m in members:
            if not _relation_ok(elig.get("members", []), m["relation"]):
                reasons.append(f"Doesn't cover a {m['relation']}")
            if m.get("age") is None:
                unknown.append(f"Age of {m['name']} unknown")
            elif not elig.get("age_min", 0) <= m["age"] <= elig.get("age_max", 200):
                reasons.append(f"{m['name']} is outside the age limits ({elig.get('age_min')}–{elig.get('age_max')})")
        if len(members) > elig.get("max_members", 99):
            reasons.append(f"Covers at most {elig['max_members']} people")
        if target and target not in p.get("coverage", {}).get("sum_insured_options", []):
            opts = p.get("coverage", {}).get("sum_insured_options", [])
            if not opts or target > max(opts):
                reasons.append(f"Doesn't offer cover of {inr(target)}")
        if reasons:
            excluded.append({"product_id": p["id"], "insurer": p["insurer"], "product_name": p["product_name"], "reasons": reasons})
            continue
        prem = indicative_premium(p, members, target)
        r = p.get("restrictions", {})
        why, cautions = [], []
        names = ", ".join(m["name"] for m in members)
        why.append(f"Can cover {names} based on the ages and relationships you've added.")
        uncovered = [m for m in members if cover[m["key"]]["sum_insured_total"] == 0]
        if ptype in ("health", "term_life"):
            if uncovered:
                codes.append("NO_EXISTING_COVER_FOR_MEMBER")
                why.append(f"Your uploaded policies show no {ptype.replace('_', ' ')} cover for {', '.join(m['name'] for m in uncovered)}.")
            else:
                codes.append("ADDS_TO_EXISTING_COVER")
                tot = sum(cover[m['key']]['sum_insured_total'] for m in members)
                why.append(f"Would add to existing cover of {inr(tot)} from your uploaded policies.")
        if budget and prem.get("amount"):
            if prem["amount"] <= budget:
                codes.append("WITHIN_BUDGET")
                why.append(f"Indicative premium of {inr(prem['amount'])} is within your budget of {inr(budget)}.")
            else:
                codes.append("ABOVE_BUDGET")
                cautions.append(f"Indicative premium of {inr(prem['amount'])} is above your budget of {inr(budget)}.")
        if r.get("copay_pct"):
            cautions.append(f"You pay {r['copay_pct']:g}% of every claim (co-payment).")
        if r.get("ped_waiting_months"):
            cautions.append(f"Pre-existing conditions are covered only after {r['ped_waiting_months']} months.")
        if r.get("deductible"):
            cautions.append(f"Deductible of {inr(r['deductible'])} per claim.")
        for note in r.get("notes", []):
            cautions.append(note)
        score = 0.0
        score += 1 if "NO_EXISTING_COVER_FOR_MEMBER" in codes else 0.6
        score += 0.6 if "WITHIN_BUDGET" in codes else (0 if "ABOVE_BUDGET" in codes else 0.3)
        score -= (r.get("copay_pct") or 0) / 50
        score -= (r.get("ped_waiting_months") or 0) / 120
        score -= 0.1 * len(unknown)
        results.append({
            "product_id": p["id"], "insurer": p["insurer"], "product_name": p["product_name"], "type": p["type"],
            "variant": p.get("variant"), "coverage": p.get("coverage"), "restrictions": r, "claims": p.get("claims"),
            "indicative_premium": prem, "reason_codes": codes, "unknown_conditions": unknown, "why": why,
            "cautions": cautions, "score": round(score, 3), "catalogue": metas[p["id"]],
        })
    results.sort(key=lambda x: -x["score"])
    missing = []
    if any(m.get("age") is None for m in members):
        missing.append({"key": "ages", "message": "Add date of birth or age for everyone to be covered."})
    return {"intent": intent, "members": members, "existing_cover": cover, "results": results, "excluded": excluded,
            "missing_data": missing, "formula_version": FORMULA_VERSION}


EVENT_TYPES = {
    "hospitalisation": {"label": "Hospitalisation", "types": ["health"]},
    "accident": {"label": "Accident / injury", "types": ["health", "term_life"]},
    "day_care": {"label": "Day-care procedure", "types": ["health"]},
    "death": {"label": "Death of the insured", "types": ["term_life", "traditional_life"]},
    "travel_medical": {"label": "Medical emergency while travelling", "types": ["travel", "health"]},
}


def ped_status(start: date | None, months: int | None, today: date | None = None) -> dict | None:
    if not start or not months:
        return None
    today = today or date.today()
    y, m = divmod(start.month - 1 + months, 12)
    ends = date(start.year + y, m + 1, min(start.day, 28))
    return {"months": months, "ends_on": ends.isoformat(), "running": today < ends}
