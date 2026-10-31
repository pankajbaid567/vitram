"""Reducing-balance EMI maths (RD §22.1).

EMI = P × r × (1 + r)^n / ((1 + r)^n − 1), r = annual_rate / 12 / 100.
If r = 0, EMI = P / n.
"""

import math

FORMULA_VERSION = "emi.reducing_balance.v1"


def _r(annual_rate_pct: float) -> float:
    if annual_rate_pct < 0:
        raise ValueError("Interest rate cannot be negative")
    return annual_rate_pct / 12 / 100


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    if principal <= 0:
        raise ValueError("Principal must be positive")
    if months <= 0:
        raise ValueError("Tenure must be at least one month")
    r = _r(annual_rate_pct)
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def schedule(principal: float, annual_rate_pct: float, months: int, emi_amount: float | None = None) -> list[dict]:
    """Month-by-month amortization. Final instalment absorbs rounding residue."""
    r = _r(annual_rate_pct)
    pay = emi_amount if emi_amount is not None else emi(principal, annual_rate_pct, months)
    rows = []
    balance = principal
    for m in range(1, months + 1):
        interest = balance * r
        principal_part = pay - interest
        if m == months or principal_part >= balance:
            principal_part = balance
            payment = balance + interest
        else:
            payment = pay
        balance = balance - principal_part
        rows.append(
            {
                "month": m,
                "payment": payment,
                "interest": interest,
                "principal": principal_part,
                "closing_balance": max(balance, 0.0),
            }
        )
        if balance <= 1e-6:
            break
    return rows


def totals(principal: float, annual_rate_pct: float, months: int) -> dict:
    e = emi(principal, annual_rate_pct, months)
    total = e * months
    return {
        "monthly_emi": e,
        "total_repayment": total,
        "total_interest": total - principal,
        "months": months,
    }


def outstanding_after(principal: float, annual_rate_pct: float, months: int, paid_months: int) -> float:
    """Closed-form outstanding principal after `paid_months` instalments."""
    r = _r(annual_rate_pct)
    if paid_months <= 0:
        return principal
    if paid_months >= months:
        return 0.0
    if r == 0:
        return principal - principal / months * paid_months
    e = emi(principal, annual_rate_pct, months)
    f = (1 + r) ** paid_months
    return principal * f - e * (f - 1) / r


def months_to_repay(balance: float, annual_rate_pct: float, emi_amount: float) -> int | None:
    """Tenure needed to clear `balance` at a fixed EMI. None if EMI never covers interest."""
    r = _r(annual_rate_pct)
    if balance <= 0:
        return 0
    if r == 0:
        return math.ceil(balance / emi_amount)
    if emi_amount <= balance * r:
        return None
    n = -math.log(1 - r * balance / emi_amount) / math.log(1 + r)
    return math.ceil(n - 1e-9)


def monthly_irr(net_disbursal: float, payments: list[float]) -> float | None:
    """Monthly IRR by bisection: net_disbursal = Σ payment_t / (1+i)^t."""
    if net_disbursal <= 0 or not payments or sum(payments) <= net_disbursal:
        return 0.0 if payments and abs(sum(payments) - net_disbursal) < 1e-6 else None

    def npv(i: float) -> float:
        return sum(p / (1 + i) ** (t + 1) for t, p in enumerate(payments)) - net_disbursal

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
