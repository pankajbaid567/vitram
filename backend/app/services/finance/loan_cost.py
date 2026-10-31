"""Real Cost of Loan (RD §12.5, §22.2).

Scheduled cost (paid if every EMI is on time) is kept strictly separate from
contingent charges (late payment, foreclosure, bounce…), so a worst-case fee is
never added to normal repayment. A charge whose value is unknown is reported
as "not available", never as zero (RD §26).
"""

from app.services.finance import emi as emi_math
from app.fmt import inr

FORMULA_VERSION = "loan_cost.v1"


def _charge_amount(spec: dict, principal: float) -> float | None:
    value = spec.get("value")
    if value is None:
        return None
    basis = spec.get("basis", "flat")
    if basis == "percent_of_principal":
        amount = principal * value / 100
        if spec.get("min") is not None:
            amount = max(amount, spec["min"])
        if spec.get("max") is not None:
            amount = min(amount, spec["max"])
        return amount
    return float(value)


def loan_cost_breakdown(
    principal: float,
    annual_rate_pct: float,
    tenure_months: int,
    charges: list[dict] | None = None,
    contingent: list[dict] | None = None,
    gst_pct: float = 18.0,
    source_refs: list[dict] | None = None,
) -> dict:
    """Return a LoanCostBreakdown (RD §22.2) with raw floats; callers wrap as Money."""
    charges = charges or []
    contingent = contingent or []
    t = emi_math.totals(principal, annual_rate_pct, tenure_months)

    assumptions = [
        f"Fixed rate of {annual_rate_pct:g}% p.a. for the full tenure on a reducing balance.",
        "All EMIs are paid on time; contingent charges are shown separately.",
    ]
    missing: list[str] = []
    mandatory: list[dict] = []
    optional: list[dict] = []
    processing_fee = None
    fee_items_taxable = 0.0
    upfront_total = 0.0

    for spec in charges:
        amount = _charge_amount(spec, principal)
        gst = None
        if amount is not None and spec.get("gst_applicable"):
            gst = amount * gst_pct / 100
        item = {
            "key": spec["key"],
            "label": spec.get("label", spec["key"]),
            "amount": amount,
            "gst": gst,
            "basis": spec.get("basis", "flat"),
            "rate_value": spec.get("value"),
            "status": "known" if amount is not None else "not_available",
            "note": spec.get("note"),
            "source": spec.get("source"),
        }
        is_mandatory = spec.get("mandatory", True)
        if amount is None:
            missing.append(f"{item['label']} — amount not available from the source")
        if not is_mandatory:
            optional.append(item)
            continue
        mandatory.append(item)
        if amount is not None:
            upfront_total += amount + (gst or 0)
            if spec.get("gst_applicable"):
                fee_items_taxable += amount
        if spec["key"] == "processing_fee":
            processing_fee = amount

    if fee_items_taxable:
        assumptions.append(f"GST at {gst_pct:g}% applied to service fees marked taxable.")

    tax_on_fees = sum(i["gst"] or 0 for i in mandatory)
    scheduled_total_outflow = t["total_repayment"] + upfront_total

    # APR-style annualized cost: IRR of net amount received vs EMI stream.
    # Upfront charges are assumed deducted from / paid at disbursal.
    annualized = None
    if not any(i["status"] == "not_available" for i in mandatory):
        net = principal - upfront_total
        irr = emi_math.monthly_irr(net, [t["monthly_emi"]] * tenure_months)
        if irr is not None:
            annualized = irr * 12 * 100
            assumptions.append(
                "Annualized cost = monthly IRR × 12 of (principal − upfront charges) against the EMI "
                "stream; an estimate, not a lender-issued APR."
            )
    else:
        assumptions.append("Annualized cost not computed because some mandatory charges are unknown.")

    contingent_items = []
    for c in contingent:
        contingent_items.append(
            {
                "key": c["key"],
                "label": c.get("label", c["key"]),
                "rule": c.get("rule"),
                "description": describe_contingent(c),
                "status": "known" if c.get("rule") else "not_available",
                "source": c.get("source"),
            }
        )
        if not c.get("rule"):
            missing.append(f"{c.get('label', c['key'])} — rule not available from the source")

    return {
        "principal": principal,
        "annual_rate_pct": annual_rate_pct,
        "tenure_months": tenure_months,
        "monthly_emi": t["monthly_emi"],
        "scheduled_interest": t["total_interest"],
        "processing_fee": processing_fee,
        "tax_on_fees": tax_on_fees,
        "documented_mandatory_charges": mandatory,
        "optional_charges": optional,
        "upfront_charges_total": upfront_total,
        "scheduled_total_outflow": scheduled_total_outflow,
        "total_cost_of_credit": scheduled_total_outflow - principal,
        "contingent_charges": contingent_items,
        "annualized_cost_pct": annualized,
        "assumptions": assumptions,
        "missing": missing,
        "source_refs": source_refs or [],
        "formula_version": FORMULA_VERSION,
    }


def describe_contingent(c: dict) -> str:
    rule = c.get("rule")
    if not rule:
        return "Not stated in the available terms."
    parts = []
    if rule.get("flat_fee") is not None:
        parts.append(f"{inr(rule['flat_fee'])} per instance")
    if rule.get("penal_rate_pa") is not None:
        parts.append(f"{rule['penal_rate_pa']:g}% p.a. on the overdue amount")
    if rule.get("charge_pct") is not None:
        on = rule.get("on", "outstanding principal")
        parts.append(f"{rule['charge_pct']:g}% of {on}")
    if rule.get("allowed_after_months") is not None:
        parts.append(f"allowed after {rule['allowed_after_months']} EMIs")
    if rule.get("max_per_year_pct") is not None:
        parts.append(f"up to {rule['max_per_year_pct']:g}% of outstanding per year")
    if rule.get("allowed") is False:
        parts.append("not permitted")
    if rule.get("gst_applicable"):
        parts.append("plus GST")
    return ", ".join(parts) if parts else "See source terms."
