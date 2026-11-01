"""Property-based tests for the finance engine: facts that must hold for *every* loan, not just the examples someone thought of.

Hypothesis generates thousands of principals, rates and tenures (and shrinks any failure to a minimal case). These pin the identities a
borrower's numbers rest on: the schedule really repays the loan, interest is never negative, a prepayment never makes a loan costlier,
and the closed forms agree with month-by-month simulation.
"""

import math

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from app.services.finance import emi as E
from app.services.finance import what_if

PRINCIPAL = st.floats(min_value=10_000, max_value=5_00_00_000, allow_nan=False, allow_infinity=False)
RATE = st.floats(min_value=0.0, max_value=48.0, allow_nan=False, allow_infinity=False)
MONTHS = st.integers(min_value=1, max_value=360)

CFG = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@CFG
@given(PRINCIPAL, RATE, MONTHS)
def test_emi_is_positive_and_repays_at_least_the_principal(p, r, n):
    e = E.emi(p, r, n)
    assert e > 0
    assert e * n >= p * (1 - 1e-9)                                  # you never repay less than you borrowed


@CFG
@given(PRINCIPAL, RATE, MONTHS)
def test_the_schedule_clears_the_loan_exactly(p, r, n):
    rows = E.schedule(p, r, n)
    assert rows[-1]["closing_balance"] < 0.01
    assert math.isclose(sum(x["principal"] for x in rows), p, rel_tol=1e-9, abs_tol=0.01)   # principal parts add back to the loan
    assert all(x["interest"] >= 0 and x["principal"] >= -1e-9 for x in rows)
    assert len(rows) <= n


@CFG
@given(PRINCIPAL, RATE, MONTHS)
def test_balance_never_rises_and_interest_never_goes_negative(p, r, n):
    balances = [p] + [x["closing_balance"] for x in E.schedule(p, r, n)]
    assert all(b2 <= b1 + 1e-6 for b1, b2 in zip(balances, balances[1:]))


@CFG
@given(PRINCIPAL, RATE, MONTHS)
def test_total_interest_equals_total_paid_minus_principal(p, r, n):
    rows = E.schedule(p, r, n)
    paid = sum(x["payment"] for x in rows)
    assert math.isclose(paid - p, sum(x["interest"] for x in rows), rel_tol=1e-7, abs_tol=0.05)


@CFG
@given(PRINCIPAL, RATE, MONTHS, st.data())
def test_closed_form_outstanding_matches_the_simulated_schedule(p, r, n, data):
    k = data.draw(st.integers(min_value=1, max_value=max(1, n - 1)))
    assume(n > 1)
    rows = E.schedule(p, r, n)
    simulated = rows[k - 1]["closing_balance"]
    assert math.isclose(E.outstanding_after(p, r, n, k), simulated, rel_tol=1e-6, abs_tol=0.5)


@CFG
@given(PRINCIPAL, st.floats(min_value=0.5, max_value=48.0), MONTHS)
def test_a_higher_rate_never_lowers_the_emi_or_total_interest(p, r, n):
    assert E.emi(p, r + 1, n) >= E.emi(p, r, n)
    assert E.totals(p, r + 1, n)["total_interest"] >= E.totals(p, r, n)["total_interest"] - 1e-6


@CFG
@given(PRINCIPAL, RATE, st.integers(min_value=2, max_value=359))
def test_a_longer_tenure_lowers_the_emi_but_never_the_total_interest(p, r, n):
    assert E.emi(p, r, n + 1) <= E.emi(p, r, n) + 1e-9
    assert E.totals(p, r, n + 1)["total_interest"] >= E.totals(p, r, n)["total_interest"] - 1e-6


@CFG
@given(PRINCIPAL, st.floats(min_value=1.0, max_value=36.0), MONTHS)
def test_months_to_repay_inverts_emi(p, r, n):
    e = E.emi(p, r, n)
    assert E.months_to_repay(p, r, e) in (n, n + 1, n - 1) or math.isclose(E.months_to_repay(p, r, e), n, abs_tol=1)


@CFG
@given(PRINCIPAL, st.floats(min_value=1.0, max_value=36.0), MONTHS)
def test_an_emi_that_does_not_cover_interest_never_repays(p, r, n):
    interest_only = p * r / 12 / 100
    assert E.months_to_repay(p, r, interest_only * 0.99) is None


@CFG
@given(PRINCIPAL, st.floats(min_value=1.0, max_value=36.0), st.integers(min_value=6, max_value=240))
def test_irr_of_a_level_loan_is_the_loans_own_rate(p, r, n):
    e = E.emi(p, r, n)
    irr = E.monthly_irr(p, [e] * n)
    assert irr is not None and math.isclose(irr * 12 * 100, r, rel_tol=1e-6, abs_tol=1e-6)


@CFG
@given(PRINCIPAL, st.floats(min_value=1.0, max_value=36.0), st.integers(min_value=12, max_value=240), st.data())
def test_a_part_prepayment_never_makes_the_loan_cost_more(p, r, n, data):
    after = data.draw(st.integers(min_value=1, max_value=n - 1))
    outstanding = E.outstanding_after(p, r, n, after)
    amount = data.draw(st.floats(min_value=1.0, max_value=max(1.0, outstanding), allow_nan=False, allow_infinity=False))
    out = what_if.prepayment(p, r, n, amount, after, mode="reduce_tenure", rule={"allowed": True, "charge_pct": 0.0, "gst_applicable": False})
    assume(out["computable"] and out["scenario"])
    sc = out["scenario"]
    assert sc["interest_saved"] >= -1.0                              # paying early with no charge never costs more (a rupee of rounding)
    assert sc["total_tenure_months"] <= n + 1                        # reduce_tenure never lengthens the loan beyond rounding


@CFG
@given(PRINCIPAL, RATE, MONTHS)
def test_zero_rate_is_plain_division(p, r, n):
    assert math.isclose(E.emi(p, 0.0, n), p / n, rel_tol=1e-12)


def test_regression_a_vanishingly_small_rate_does_not_divide_by_zero():
    """Found by Hypothesis: (1 + 1e-232) ** n == 1.0 exactly, so the naive f - 1 was 0. expm1/log1p keep the cancellation out."""
    assert math.isclose(E.emi(10_000, 1e-232, 1), 10_000, rel_tol=1e-9)
    assert math.isclose(E.emi(10_000, 1e-20, 12), 10_000 / 12, rel_tol=1e-9)
    assert E.schedule(10_000, 1e-106, 1)[-1]["closing_balance"] < 0.01
