"""Boundaries and error paths of the EMI maths, written from surviving mutants (see pyproject [tool.mutmut]): every assertion here
kills a change that the example and property tests let through."""

import math

import pytest

from app.services.finance import emi as E


def test_negative_rate_is_rejected_but_zero_is_fine():
    with pytest.raises(ValueError, match="Interest rate cannot be negative"):
        E.emi(100_000, -0.01, 12)
    assert E.emi(120_000, 0, 12) == 10_000


def test_principal_and_tenure_boundaries():
    with pytest.raises(ValueError, match="Principal must be positive"):
        E.emi(0, 10, 12)
    with pytest.raises(ValueError, match="Principal must be positive"):
        E.emi(-1, 10, 12)
    with pytest.raises(ValueError, match="at least one month"):
        E.emi(1000, 10, 0)
    assert E.emi(1000, 12, 1) == pytest.approx(1010)                 # one month: principal plus a month's interest


def test_known_emi_value():
    assert E.emi(100_000, 12, 12) == pytest.approx(8884.88, abs=0.01)
    assert E.emi(500_000, 9.5, 60) == pytest.approx(10_501.2, abs=0.5)


def test_schedule_rows_have_the_documented_shape_and_values():
    rows = E.schedule(100_000, 12, 12)
    assert len(rows) == 12 and [r["month"] for r in rows] == list(range(1, 13))
    first = rows[0]
    assert set(first) == {"month", "payment", "interest", "principal", "closing_balance"}
    assert first["interest"] == pytest.approx(1000.0)               # 1% of 100,000
    assert first["payment"] == pytest.approx(8884.88, abs=0.01)
    assert first["principal"] == pytest.approx(first["payment"] - first["interest"])
    assert first["closing_balance"] == pytest.approx(100_000 - first["principal"])
    assert rows[-1]["closing_balance"] == 0


def test_schedule_with_a_larger_emi_ends_early_and_the_last_payment_is_smaller():
    rows = E.schedule(100_000, 12, 12, emi_amount=20_000)
    assert len(rows) < 12
    assert rows[-1]["payment"] < 20_000 and rows[-1]["closing_balance"] == 0
    assert all(r["payment"] == 20_000 for r in rows[:-1])


def test_schedule_final_instalment_clears_whatever_is_left():
    rows = E.schedule(10_000, 10, 6, emi_amount=1_000)              # an EMI that is too small to clear the loan in 6 months
    assert len(rows) == 6
    assert rows[-1]["closing_balance"] == 0
    assert rows[-1]["payment"] > 1_000


def test_totals_add_up():
    t = E.totals(100_000, 12, 12)
    assert set(t) == {"monthly_emi", "total_repayment", "total_interest", "months"}
    assert t["months"] == 12
    assert t["total_repayment"] == pytest.approx(t["monthly_emi"] * 12)
    assert t["total_interest"] == pytest.approx(t["total_repayment"] - 100_000)
    assert t["total_interest"] == pytest.approx(6619.0, abs=1.0)


def test_outstanding_after_boundaries_and_zero_rate():
    assert E.outstanding_after(100_000, 12, 12, 0) == 100_000
    assert E.outstanding_after(100_000, 12, 12, -3) == 100_000
    assert E.outstanding_after(100_000, 12, 12, 12) == 0.0
    assert E.outstanding_after(100_000, 12, 12, 99) == 0.0
    assert E.outstanding_after(120_000, 0, 12, 3) == pytest.approx(90_000)
    assert E.outstanding_after(100_000, 12, 12, 1) == pytest.approx(E.schedule(100_000, 12, 12)[0]["closing_balance"])


def test_months_to_repay_edges():
    assert E.months_to_repay(0, 12, 1000) == 0
    assert E.months_to_repay(-5, 12, 1000) == 0
    assert E.months_to_repay(10_000, 0, 1_000) == 10
    assert E.months_to_repay(10_001, 0, 1_000) == 11                 # rounds up
    assert E.months_to_repay(100_000, 12, 1_000) is None             # exactly the monthly interest: never ends
    assert E.months_to_repay(100_000, 12, 999) is None
    assert E.months_to_repay(100_000, 12, 1_001) is not None
    assert E.months_to_repay(100_000, 12, 8884.88) == 12
    assert E.months_to_repay(100_000, 12, 20_000) == 6


def test_irr_guards_and_degenerate_inputs():
    assert E.monthly_irr(0, [100.0]) is None
    assert E.monthly_irr(-10, [100.0]) is None
    assert E.monthly_irr(100, []) is None
    assert E.monthly_irr(100, [50.0, 50.0]) == 0.0                   # repays exactly what was lent: 0% interest
    assert E.monthly_irr(100, [50.0, 49.0]) is None                  # repays less than was lent
    assert E.monthly_irr(100, [50.0, 50.0000001]) is not None


def test_irr_values_and_range():
    assert E.monthly_irr(100_000, [E.emi(100_000, 12, 12)] * 12) == pytest.approx(0.01, abs=1e-9)
    big = E.monthly_irr(100, [190.0])                                # 90% in one month: near the top of the search bracket
    assert big == pytest.approx(0.9, abs=1e-9)
    assert 0 < E.monthly_irr(1_000, [600.0, 600.0]) < 1
    uneven = [100.0, 300.0, 700.0]
    irr = E.monthly_irr(900, uneven)
    assert sum(p / (1 + irr) ** (t + 1) for t, p in enumerate(uneven)) == pytest.approx(900, abs=1e-6)


def test_compound_is_stable_for_tiny_rates():
    f, fm1 = E._compound(1e-15, 12)
    assert f == pytest.approx(1.0) and fm1 == pytest.approx(12e-15, rel=1e-6)
    assert math.isfinite(E.emi(1000, 1e-300, 6))
