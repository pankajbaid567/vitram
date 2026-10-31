"""RD §27.1 — EMI formula, zero interest, total cost aggregation, prepayment,
missed payment and reward calculations with caps and exclusions."""

import pytest

from app.services.finance import emi as emi_math
from app.services.finance.loan_cost import loan_cost_breakdown
from app.services.finance.rewards import best_for_spend, estimate_card
from app.services.finance import what_if


# --- EMI ------------------------------------------------------------------

def test_emi_reference_value():
    # ₹1,00,000 at 12% p.a. for 12 months: textbook EMI ₹8,884.88
    assert emi_math.emi(100_000, 12, 12) == pytest.approx(8884.88, abs=0.01)


def test_emi_zero_interest():
    assert emi_math.emi(120_000, 0, 12) == pytest.approx(10_000)


def test_emi_rejects_bad_inputs():
    with pytest.raises(ValueError):
        emi_math.emi(0, 10, 12)
    with pytest.raises(ValueError):
        emi_math.emi(1000, 10, 0)
    with pytest.raises(ValueError):
        emi_math.emi(1000, -1, 12)


def test_schedule_repays_principal_exactly():
    rows = emi_math.schedule(500_000, 10.5, 60)
    assert len(rows) == 60
    assert sum(r["principal"] for r in rows) == pytest.approx(500_000, abs=0.01)
    assert rows[-1]["closing_balance"] == pytest.approx(0, abs=0.01)
    t = emi_math.totals(500_000, 10.5, 60)
    assert sum(r["payment"] for r in rows) == pytest.approx(t["total_repayment"], abs=0.05)


def test_outstanding_matches_schedule():
    rows = emi_math.schedule(300_000, 11, 36)
    assert emi_math.outstanding_after(300_000, 11, 36, 12) == pytest.approx(rows[11]["closing_balance"], abs=0.01)


def test_months_to_repay_none_when_emi_below_interest():
    assert emi_math.months_to_repay(1_000_000, 12, 5_000) is None
    assert emi_math.months_to_repay(100_000, 12, emi_math.emi(100_000, 12, 12)) == 12


# --- Real cost ------------------------------------------------------------

CHARGES = [
    {"key": "processing_fee", "label": "Processing fee", "basis": "percent_of_principal", "value": 2,
     "min": 1999, "gst_applicable": True},
    {"key": "documentation", "label": "Documentation", "basis": "flat", "value": 500, "gst_applicable": True},
    {"key": "stamp_duty", "label": "Stamp duty", "basis": "flat", "value": 300, "gst_applicable": False},
    {"key": "protection_cover", "label": "Optional loan cover", "basis": "flat", "value": 4000, "mandatory": False},
]
CONTINGENT = [
    {"key": "late_payment", "label": "Late payment", "rule": {"flat_fee": 600, "penal_rate_pa": 24, "gst_applicable": True}},
    {"key": "foreclosure", "label": "Foreclosure", "rule": None},
]


def test_loan_cost_separates_scheduled_and_contingent():
    b = loan_cost_breakdown(500_000, 11, 36, CHARGES, CONTINGENT, gst_pct=18)
    fee = 10_000.0
    assert b["processing_fee"] == pytest.approx(fee)
    assert b["tax_on_fees"] == pytest.approx((fee + 500) * 0.18)
    upfront = fee + 500 + 300 + (fee + 500) * 0.18
    assert b["upfront_charges_total"] == pytest.approx(upfront)
    t = emi_math.totals(500_000, 11, 36)
    assert b["scheduled_total_outflow"] == pytest.approx(t["total_repayment"] + upfront)
    # optional cover is never added to the scheduled total
    assert [c["key"] for c in b["optional_charges"]] == ["protection_cover"]
    # contingent charges are listed separately, unknown rule is flagged not zeroed
    keys = {c["key"]: c for c in b["contingent_charges"]}
    assert keys["foreclosure"]["status"] == "not_available"
    assert any("Foreclosure" in m for m in b["missing"])
    # annualized cost is higher than nominal because of fees
    assert b["annualized_cost_pct"] > 11


def test_unknown_mandatory_fee_is_not_zero_and_blocks_apr():
    charges = [{"key": "legal", "label": "Legal & valuation", "basis": "flat", "value": None}]
    b = loan_cost_breakdown(2_000_000, 8.5, 240, charges, [])
    item = b["documented_mandatory_charges"][0]
    assert item["amount"] is None and item["status"] == "not_available"
    assert b["annualized_cost_pct"] is None
    assert any("Legal" in m for m in b["missing"])


def test_processing_fee_min_applies():
    b = loan_cost_breakdown(50_000, 14, 12, CHARGES[:1], [])
    assert b["processing_fee"] == 1999


# --- What-if --------------------------------------------------------------

def test_prepayment_reduce_tenure_saves_interest_and_charge_applied():
    rule = {"allowed": True, "allowed_after_months": 6, "charge_pct": 2, "gst_applicable": True}
    r = what_if.prepayment(500_000, 10.5, 60, 100_000, 12, "reduce_tenure", rule)
    assert r["computable"]
    s = r["scenario"]
    assert s["remaining_months"] < 48
    assert s["interest_saved"] > 0
    assert s["prepayment_charge"] == pytest.approx(100_000 * 0.02 * 1.18)
    assert s["net_saving"] == pytest.approx(s["interest_saved"] - s["prepayment_charge"])
    assert r["baseline"]["monthly_emi"] == pytest.approx(s["monthly_emi"])


def test_prepayment_reduce_emi_keeps_tenure():
    r = what_if.prepayment(500_000, 10.5, 60, 100_000, 12, "reduce_emi", None)
    s = r["scenario"]
    assert s["total_tenure_months"] == 60
    assert s["monthly_emi"] < r["baseline"]["monthly_emi"]
    # unknown charge: flagged, never fabricated
    assert s["prepayment_charge"] is None and s["net_saving"] is None
    assert r["missing"]


def test_prepayment_blocked_by_lock_in():
    rule = {"allowed": True, "allowed_after_months": 12, "charge_pct": 3}
    r = what_if.prepayment(500_000, 10.5, 60, 50_000, 6, "reduce_tenure", rule)
    assert not r["computable"]


def test_missed_payment_without_rule_is_not_computable():
    r = what_if.missed_payment(12_000, None)
    assert not r["computable"] and r["scenario"] is None
    assert r["missing"]


def test_missed_payment_with_rule():
    r = what_if.missed_payment(12_000, {"flat_fee": 500, "penal_rate_pa": 24, "gst_applicable": True}, days_late=30)
    penal = 12_000 * 0.24 * 30 / 365
    expected = (500 + penal) * 1.18
    assert r["scenario"]["extra_cost"] == pytest.approx(expected)
    assert any("credit-score" in n for n in r["notes"])


def test_rate_change_hold_emi_and_tenure():
    up = what_if.rate_change(1_000_000, 8.5, 180, 9.5, hold="emi")
    assert up["scenario"]["tenure_months"] > 180
    t = what_if.rate_change(1_000_000, 8.5, 180, 9.5, hold="tenure")
    assert t["scenario"]["monthly_emi"] > t["baseline"]["monthly_emi"]
    extreme = what_if.rate_change(1_000_000, 8.5, 180, 40, hold="emi")
    assert not extreme["computable"]


def test_affordability_requires_income():
    assert not what_if.new_emi_affordability(None, 5000, 8000)["computable"]
    r = what_if.new_emi_affordability(100_000, 10_000, 15_000, monthly_expenses=40_000)
    assert r["scenario"]["obligation_share_pct"] == pytest.approx(25)
    assert r["scenario"]["monthly_surplus"] == pytest.approx(35_000)


# --- Rewards --------------------------------------------------------------

TRAVEL_CARD = {
    "id": "a", "name": "Travel card",
    "rules": {
        "reward_currency": "miles", "currency_name": "miles",
        "base_rate": {"earn_per_100": 2},
        "category_rules": [{"categories": ["travel"], "earn_per_100": 10, "cap": {"units": 2000, "period": "month"},
                            "cap_key": "travel"}],
        "exclusions": {"categories": ["fuel"]},
        "valuation": {"per_unit_inr": 0.5, "basis": "airline transfer"},
    },
    "cycle_spend": {"travel": 5000},
}
CASHBACK_CARD = {
    "id": "b", "name": "Cashback card",
    "rules": {"reward_currency": "cashback", "currency_name": "cashback",
              "base_rate": {"earn_per_100": 1},
              "category_rules": [{"categories": ["food_delivery"], "earn_per_100": 5}]},
}
UNVALUED_CARD = {
    "id": "c", "name": "Points card",
    "rules": {"reward_currency": "points", "currency_name": "points", "base_rate": {"earn_per_100": 4}},
}


def test_reward_cap_applies_with_known_cycle_spend():
    # already used 500 of 2000 accelerated miles; ₹30,000 flight would earn 3000 → 1500 capped + base on rest
    e = estimate_card(TRAVEL_CARD, 30_000, "travel", None)
    over_amount = (3000 - 1500) / 10 * 100
    assert e["reward_units"] == pytest.approx(1500 + 2 * over_amount / 100)
    assert e["caveats"]


def test_reward_exclusion():
    e = estimate_card(TRAVEL_CARD, 2_000, "fuel", None)
    assert e["reward_units"] == 0 and e.get("excluded")


def test_best_for_spend_does_not_rank_unvalued_currency():
    r = best_for_spend([TRAVEL_CARD, CASHBACK_CARD, UNVALUED_CARD], 30_000, "travel")
    assert [x["card_id"] for x in r["ranked"]] == ["a", "b"]
    assert [x["card_id"] for x in r["unranked"]] == ["c"]
    assert r["recommended_card_id"] == "a"
    assert r["notes"]
