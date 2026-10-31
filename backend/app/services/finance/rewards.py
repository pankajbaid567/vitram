"""Card reward maths for "Which card should I use?" (RD §13.2, §21.4, §22.3).

Different reward currencies are never treated as equivalent unless the card
programme data provides a valuation rule (RD §13.3). Caps, exclusions,
minimum transaction amounts and milestones are applied only when present in
the card rules; otherwise the estimate is labelled incomplete.
"""

from app.fmt import group, inr

FORMULA_VERSION = "rewards.v1"


def _match_rule(rules: dict, category: str | None, merchant: str | None) -> dict | None:
    merchant_l = (merchant or "").lower()
    for rule in rules.get("category_rules", []):
        if merchant_l and any(m.lower() in merchant_l for m in rule.get("merchants", [])):
            return rule
    for rule in rules.get("category_rules", []):
        if category and category in rule.get("categories", []):
            return rule
    return None


def estimate_card(card: dict, amount: float, category: str | None, merchant: str | None) -> dict:
    """card = {"id", "name", "rules": {...}, "cycle_spend": {category: amount}, "milestone_progress": {...}}"""
    rules = card.get("rules") or {}
    why: list[str] = []
    caveats: list[str] = []
    incomplete: list[str] = []
    currency = rules.get("reward_currency")
    unit_name = rules.get("currency_name", currency or "rewards")

    if not rules:
        return {
            "card_id": card["id"], "card_name": card["name"], "computable": False,
            "reward_units": None, "unit_name": None, "value_inr": None, "why": [],
            "caveats": ["No reward rules are available for this card, so VITTRM can't estimate rewards."],
            "incomplete": ["Card reward rules"],
        }

    excl = rules.get("exclusions", {})
    if category and category in excl.get("categories", []):
        return {
            "card_id": card["id"], "card_name": card["name"], "computable": True,
            "reward_units": 0.0, "unit_name": unit_name, "value_inr": 0.0 if rules.get("valuation") else None,
            "why": [], "caveats": [f"{category.replace('_', ' ').capitalize()} spends earn no rewards on this card."],
            "incomplete": [], "excluded": True,
        }
    if merchant and any(m.lower() in merchant.lower() for m in excl.get("merchants", [])):
        return {
            "card_id": card["id"], "card_name": card["name"], "computable": True,
            "reward_units": 0.0, "unit_name": unit_name, "value_inr": 0.0 if rules.get("valuation") else None,
            "why": [], "caveats": [f"{merchant} is excluded from rewards on this card."], "incomplete": [],
            "excluded": True,
        }
    min_txn = rules.get("min_txn_amount")
    if min_txn and amount < min_txn:
        caveats.append(f"Transactions below {inr(min_txn)} earn nothing on this card.")
        return {
            "card_id": card["id"], "card_name": card["name"], "computable": True, "reward_units": 0.0,
            "unit_name": unit_name, "value_inr": 0.0 if rules.get("valuation") else None,
            "why": [], "caveats": caveats, "incomplete": [],
        }

    base = rules.get("base_rate") or {}
    base_rate_per_100 = base.get("earn_per_100")
    rule = _match_rule(rules, category, merchant)
    if rule:
        rate = rule["earn_per_100"]
        why.append(rule.get("label") or f"Accelerated rate of {rate:g} {unit_name} per ₹100 on this category.")
    elif base_rate_per_100 is not None:
        rate = base_rate_per_100
        why.append(f"Base rate of {rate:g} {unit_name} per ₹100.")
    else:
        return {
            "card_id": card["id"], "card_name": card["name"], "computable": False, "reward_units": None,
            "unit_name": unit_name, "value_inr": None, "why": [], "caveats": [],
            "incomplete": ["Base reward rate"],
        }

    # cashback cards express earn_per_100 in rupees
    units = amount * rate / 100
    uncapped = units

    cap = (rule or {}).get("cap")
    if cap:
        spent_key = (rule or {}).get("cap_key") or (category or "")
        cycle_spend = (card.get("cycle_spend") or {})
        if spent_key in cycle_spend:
            already_units = cycle_spend[spent_key] * rate / 100
            remaining = max(cap["units"] - already_units, 0)
            if units > remaining:
                over_amount = (units - remaining) / rate * 100
                fallback = (base_rate_per_100 or 0) * over_amount / 100
                units = remaining + fallback
                caveats.append(
                    f"Accelerated {unit_name} are capped at {group(cap['units'])} per {cap.get('period', 'cycle')}; "
                    f"about {group(remaining)} remain, so the rest earns the base rate."
                )
        else:
            if units > cap["units"]:
                units = cap["units"] + (base_rate_per_100 or 0) * (amount - cap["units"] / rate * 100) / 100
                caveats.append(f"Accelerated {unit_name} are capped at {group(cap['units'])} per {cap.get('period', 'cycle')}.")
            incomplete.append(f"This cycle's {category or 'category'} spend — cap usage assumed zero")

    milestone_notes = [m.get("label") or f"Milestone: spend {inr(m['spend'])} per {m.get('period', 'year')} for a bonus."
                       for m in rules.get("milestones") or []]

    valuation = rules.get("valuation")
    value_inr = None
    if currency == "cashback":
        value_inr = units
    elif valuation and valuation.get("per_unit_inr") is not None:
        value_inr = units * valuation["per_unit_inr"]
        why.append(f"Valued at ₹{valuation['per_unit_inr']:g} per {unit_name[:-1] if unit_name.endswith('s') else unit_name} "
                   f"({valuation.get('basis', 'programme valuation')}).")
    else:
        incomplete.append(f"A rupee value for {unit_name} — programme valuation not available")

    for b in rules.get("benefits", []):
        if category and category in b.get("categories", []):
            why.append(b["label"])

    return {
        "card_id": card["id"], "card_name": card["name"], "computable": True,
        "reward_units": units, "uncapped_units": uncapped, "unit_name": unit_name,
        "reward_currency": currency, "value_inr": value_inr, "why": why, "caveats": caveats,
        "incomplete": incomplete, "rate_per_100": rate, "milestones": milestone_notes,
    }


def best_for_spend(cards: list[dict], amount: float, category: str | None, merchant: str | None = None) -> dict:
    """Rank the user's own cards for one purchase.

    Cards with a rupee value are ranked by it. Cards without a valuation are
    listed separately and ordered only within their own reward currency.
    """
    if amount <= 0:
        raise ValueError("Purchase amount must be positive")
    estimates = [estimate_card(c, amount, category, merchant) for c in cards]
    valued = sorted([e for e in estimates if e.get("value_inr") is not None], key=lambda e: -e["value_inr"])
    unvalued = sorted(
        [e for e in estimates if e.get("value_inr") is None],
        key=lambda e: (e.get("unit_name") or "", -(e.get("reward_units") or 0)),
    )
    notes = []
    if unvalued and valued:
        notes.append("Some cards earn rewards without a known rupee value, so they can't be ranked against the others.")
    return {
        "purchase": {"amount": amount, "category": category, "merchant": merchant},
        "ranked": valued,
        "unranked": unvalued,
        "recommended_card_id": valued[0]["card_id"] if valued and valued[0]["value_inr"] > 0 else None,
        "notes": notes,
        "formula_version": FORMULA_VERSION,
    }
