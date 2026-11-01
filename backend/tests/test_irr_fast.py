"""The faster IRR must agree with the original 200-step bisection to far better than any displayed precision."""

import random

from app.services.finance import emi as emi_math


def _reference(net: float, payments: list[float]) -> float | None:
    if net <= 0 or not payments or sum(payments) <= net:
        return 0.0 if payments and abs(sum(payments) - net) < 1e-6 else None

    def npv(i: float) -> float:
        return sum(p / (1 + i) ** (t + 1) for t, p in enumerate(payments)) - net

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def test_level_payments_match_reference():
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(3, 360)
        emi = rng.uniform(500, 90_000)
        net = emi * n * rng.uniform(0.35, 0.99)
        fast, ref = emi_math.monthly_irr(net, [emi] * n), _reference(net, [emi] * n)
        assert fast is not None and ref is not None
        assert abs(fast - ref) < 1e-12


def test_uneven_payments_match_reference():
    rng = random.Random(11)
    for _ in range(100):
        n = rng.randint(3, 60)
        pays = [rng.uniform(500, 5000) for _ in range(n)]
        net = sum(pays) * rng.uniform(0.4, 0.95)
        assert abs(emi_math.monthly_irr(net, pays) - _reference(net, pays)) < 1e-12


def test_degenerate_inputs_unchanged():
    assert emi_math.monthly_irr(0, [100.0]) is None
    assert emi_math.monthly_irr(1000, []) is None
    assert emi_math.monthly_irr(1000, [500.0, 500.0]) == 0.0
    assert emi_math.monthly_irr(1500, [500.0, 500.0]) is None
