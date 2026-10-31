"""What-if scenarios (RD §12.8, §14.4, §22.3).

Every scenario returns baseline vs scenario side by side. When a governing
contract rule is missing the result is `computable: False` with the list of
missing inputs — no penalty is ever fabricated.
"""

from app.services.finance import emi as emi_math
from app.fmt import inr

FORMULA_VERSION = "what_if.v1"


def _loan_snapshot(principal: float, rate: float, months: int) -> dict:
    t = emi_math.totals(principal, rate, months)
    return {
        "principal": principal,
        "annual_rate_pct": rate,
        "tenure_months": months,
        "monthly_emi": t["monthly_emi"],
        "total_interest": t["total_interest"],
        "total_repayment": t["total_repayment"],
    }


def _result(kind: str, inputs: dict, baseline: dict | None, scenario: dict | None, *,
            computable: bool = True, missing: list[str] | None = None,
            assumptions: list[str] | None = None, notes: list[str] | None = None) -> dict:
    return {
        "kind": kind,
        "computable": computable,
        "inputs": inputs,
        "baseline": baseline,
        "scenario": scenario,
        "missing": missing or [],
        "assumptions": assumptions or [],
        "notes": notes or [],
        "formula_version": FORMULA_VERSION,
    }


def tenure_change(principal: float, rate: float, months: int, new_months: int) -> dict:
    return _result(
        "tenure_change",
        {"principal": principal, "annual_rate_pct": rate, "tenure_months": months, "new_tenure_months": new_months},
        _loan_snapshot(principal, rate, months),
        _loan_snapshot(principal, rate, new_months),
        assumptions=["Same fixed rate for both tenures."],
    )


def amount_change(principal: float, rate: float, months: int, new_principal: float) -> dict:
    return _result(
        "amount_change",
        {"principal": principal, "annual_rate_pct": rate, "tenure_months": months, "new_principal": new_principal},
        _loan_snapshot(principal, rate, months),
        _loan_snapshot(new_principal, rate, months),
        assumptions=["Same rate and tenure; fees that scale with the amount are not included here."],
    )


def prepayment(
    principal: float,
    rate: float,
    months: int,
    prepay_amount: float,
    after_month: int,
    mode: str = "reduce_tenure",
    rule: dict | None = None,
    gst_pct: float = 18.0,
) -> dict:
    """Part-prepayment after `after_month` EMIs.

    mode = reduce_tenure (keep EMI) | reduce_emi (keep remaining tenure).
    rule = {"allowed": bool, "allowed_after_months": int, "charge_pct": float,
            "max_per_year_pct": float, "gst_applicable": bool} or None (unknown).
    """
    inputs = {
        "principal": principal, "annual_rate_pct": rate, "tenure_months": months,
        "prepay_amount": prepay_amount, "after_month": after_month, "mode": mode, "rule": rule,
    }
    if not 0 < after_month < months:
        raise ValueError("Prepayment month must fall within the tenure")
    baseline = _loan_snapshot(principal, rate, months)
    base_emi = baseline["monthly_emi"]
    outstanding = emi_math.outstanding_after(principal, rate, months, after_month)
    if prepay_amount <= 0:
        raise ValueError("Prepayment amount must be positive")
    if prepay_amount >= outstanding:
        prepay_amount = outstanding

    missing: list[str] = []
    notes: list[str] = []
    if rule is not None and rule.get("allowed") is False:
        return _result("prepayment", inputs, baseline, None, computable=False,
                       notes=["The stated terms do not permit part-prepayment."])
    if rule is not None and rule.get("allowed_after_months") and after_month < rule["allowed_after_months"]:
        return _result("prepayment", inputs, baseline, None, computable=False,
                       notes=[f"Terms permit part-prepayment only after {rule['allowed_after_months']} EMIs."])
    if rule is not None and rule.get("max_per_year_pct") is not None:
        cap = outstanding * rule["max_per_year_pct"] / 100
        if prepay_amount > cap + 0.01:
            notes.append(
                f"Terms cap part-prepayment at {rule['max_per_year_pct']:g}% of outstanding per year "
                f"(about {inr(cap)} here); a larger amount may not be accepted."
            )

    paid_so_far = base_emi * after_month
    remaining_balance = outstanding - prepay_amount
    remaining_months = months - after_month
    if mode == "reduce_emi":
        new_emi = emi_math.emi(remaining_balance, rate, remaining_months) if remaining_balance > 0 else 0.0
        new_months_left = remaining_months if remaining_balance > 0 else 0
    else:
        new_emi = base_emi
        new_months_left = emi_math.months_to_repay(remaining_balance, rate, base_emi) or 0
    future = sum(r["payment"] for r in emi_math.schedule(remaining_balance, rate, new_months_left, new_emi)) if new_months_left else 0.0
    scenario_total = paid_so_far + prepay_amount + future
    interest_saved = baseline["total_repayment"] - scenario_total

    charge = None
    if rule is None or rule.get("charge_pct") is None:
        missing.append("Part-prepayment charge (percentage) — not available in the terms")
    else:
        charge = prepay_amount * rule["charge_pct"] / 100
        if rule.get("gst_applicable"):
            charge *= 1 + gst_pct / 100

    scenario = {
        "outstanding_before_prepayment": outstanding,
        "prepay_amount": prepay_amount,
        "monthly_emi": new_emi,
        "remaining_months": new_months_left,
        "total_tenure_months": after_month + new_months_left,
        "total_repayment": scenario_total,
        "interest_saved": interest_saved,
        "prepayment_charge": charge,
        "net_saving": interest_saved - charge if charge is not None else None,
    }
    assumptions = [
        "Prepayment is applied immediately after the stated EMI.",
        "Fixed rate for the remaining tenure.",
        "Keeps the EMI and shortens the tenure." if mode == "reduce_tenure" else "Keeps the tenure and lowers the EMI.",
    ]
    return _result("prepayment", inputs, baseline, scenario, computable=True, missing=missing,
                   assumptions=assumptions, notes=notes)


def missed_payment(emi_amount: float, late_rule: dict | None, days_late: int = 30,
                   gst_pct: float = 18.0, label: str = "missed_payment") -> dict:
    """Extra cost of paying one EMI `days_late` days late under the stated rule.

    late_rule = {"flat_fee": float|None, "penal_rate_pa": float|None, "gst_applicable": bool}
    """
    inputs = {"emi_amount": emi_amount, "days_late": days_late, "late_rule": late_rule}
    baseline = {"amount_due": emi_amount, "extra_cost": 0.0}
    notes = [
        "The missed EMI remains payable in addition to later EMIs.",
        "VITRAM does not estimate credit-score effects.",
    ]
    if not late_rule or (late_rule.get("flat_fee") is None and late_rule.get("penal_rate_pa") is None):
        return _result(
            label, inputs, baseline, None, computable=False,
            missing=["Late-payment rule (flat fee and/or penal interest rate) from your loan terms"],
            notes=notes,
        )
    flat = late_rule.get("flat_fee") or 0.0
    penal = 0.0
    if late_rule.get("penal_rate_pa") is not None:
        penal = emi_amount * late_rule["penal_rate_pa"] / 100 * days_late / 365
    gst = (flat + penal) * gst_pct / 100 if late_rule.get("gst_applicable") else 0.0
    extra = flat + penal + gst
    assumptions = [f"Penal interest accrues on the overdue EMI for {days_late} days (simple, 365-day year)."]
    if late_rule.get("gst_applicable"):
        assumptions.append(f"GST at {gst_pct:g}% on the charges, as the terms state GST applies.")
    missing = []
    if late_rule.get("flat_fee") is None:
        missing.append("Flat late fee — not stated")
    if late_rule.get("penal_rate_pa") is None:
        missing.append("Penal interest rate — not stated")
    scenario = {
        "amount_due": emi_amount + extra,
        "late_fee": flat,
        "penal_interest": penal,
        "gst": gst,
        "extra_cost": extra,
        "days_late": days_late,
    }
    return _result(label, inputs, baseline, scenario, missing=missing, assumptions=assumptions, notes=notes)


def rate_change(outstanding: float, current_rate: float, remaining_months: int, new_rate: float,
                hold: str = "emi") -> dict:
    """Floating-rate change. hold = 'emi' (tenure changes) or 'tenure' (EMI changes)."""
    inputs = {"outstanding": outstanding, "current_rate_pct": current_rate,
              "remaining_months": remaining_months, "new_rate_pct": new_rate, "hold": hold}
    base = _loan_snapshot(outstanding, current_rate, remaining_months)
    assumptions = [f"New rate of {new_rate:g}% p.a. applies from the next EMI for the rest of the loan."]
    if hold == "tenure":
        scen = _loan_snapshot(outstanding, new_rate, remaining_months)
        assumptions.append("Tenure held constant; EMI is recalculated.")
        return _result("rate_change", inputs, base, scen, assumptions=assumptions)
    n = emi_math.months_to_repay(outstanding, new_rate, base["monthly_emi"])
    assumptions.append("EMI held constant; tenure is recalculated.")
    if n is None:
        return _result("rate_change", inputs, base, None, computable=False, assumptions=assumptions,
                       notes=["At this rate the current EMI no longer covers the monthly interest; "
                              "the lender would need to raise the EMI."])
    rows = emi_math.schedule(outstanding, new_rate, n, base["monthly_emi"])
    total = sum(r["payment"] for r in rows)
    scen = {
        "principal": outstanding, "annual_rate_pct": new_rate, "tenure_months": n,
        "monthly_emi": base["monthly_emi"], "total_repayment": total, "total_interest": total - outstanding,
    }
    return _result("rate_change", inputs, base, scen, assumptions=assumptions)


def new_emi_affordability(monthly_income: float | None, existing_emis: float, new_emi: float,
                          monthly_expenses: float | None = None) -> dict:
    inputs = {"monthly_income": monthly_income, "existing_emis": existing_emis, "new_emi": new_emi,
              "monthly_expenses": monthly_expenses}
    if not monthly_income:
        return _result("new_emi_affordability", inputs, None, None, computable=False,
                       missing=["Monthly income — confirm it from your bank statement or enter it"])

    def snap(emis: float) -> dict:
        surplus = None if monthly_expenses is None else monthly_income - monthly_expenses - emis
        return {"monthly_emis": emis, "obligation_share_pct": emis / monthly_income * 100, "monthly_surplus": surplus}

    assumptions = ["Income is your confirmed or estimated monthly take-home."]
    if monthly_expenses is not None:
        assumptions.append("Surplus = income − average non-EMI spending − EMIs.")
    return _result("new_emi_affordability", inputs, snap(existing_emis), snap(existing_emis + new_emi),
                   assumptions=assumptions)
