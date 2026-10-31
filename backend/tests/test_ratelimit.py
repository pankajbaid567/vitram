from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import RateLimitHit
from app.ratelimit import DatabaseLimiter, SlidingWindowLimiter, limiter, purge_expired


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_blocks_after_limit_and_recovers_when_the_window_slides():
    clock = Clock()
    rl = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b")                     # keys are independent
    clock.t = 61
    assert rl.allow("a")                     # the old attempts aged out


def test_rejected_attempts_do_not_extend_the_lockout():
    clock = Clock()
    rl = SlidingWindowLimiter(limit=1, window_seconds=10, clock=clock)
    assert rl.allow("a")
    clock.t = 9
    assert not rl.allow("a")
    clock.t = 10.5
    assert rl.allow("a")                     # unlocked 10 s after the *first* attempt


def test_memory_is_bounded_when_spraying_unique_keys():
    clock = Clock()
    rl = SlidingWindowLimiter(limit=1, window_seconds=5, clock=clock, max_keys=100)
    for i in range(100):
        rl.allow(f"k{i}")
    clock.t = 6                              # everything so far is stale
    for i in range(100, 150):
        rl.allow(f"k{i}")
    assert len(rl) <= 100


# --- database backend: one count across processes -------------------------------------------------

class DbClock:
    def __init__(self): self.now = datetime.now(timezone.utc)
    def __call__(self): return self.now


def test_database_limiter_is_shared_between_instances():
    clock = DbClock()
    a, b = DatabaseLimiter(2, 60, clock=clock), DatabaseLimiter(2, 60, clock=clock)   # two "workers"
    key = f"shared-{id(clock)}"
    assert a.allow(key) and b.allow(key)
    assert not a.allow(key) and not b.allow(key), "the second worker sees the first one's attempts"


def test_database_limiter_slides_and_refusals_do_not_extend_the_lockout():
    clock = DbClock()
    rl = DatabaseLimiter(1, 10, clock=clock)
    key = f"slide-{id(clock)}"
    assert rl.allow(key)
    clock.now += timedelta(seconds=9)
    assert not rl.allow(key)
    clock.now += timedelta(seconds=1.5)       # 10.5 s after the *allowed* attempt
    assert rl.allow(key)


def test_purge_removes_only_expired_rows():
    db = SessionLocal()
    old, fresh = f"old-{id(db)}", f"fresh-{id(db)}"
    db.add_all([RateLimitHit(key=old, hit_at=datetime.now(timezone.utc) - timedelta(hours=3)),
                RateLimitHit(key=fresh, hit_at=datetime.now(timezone.utc))])
    db.commit()
    assert purge_expired() >= 1
    keys = {h.key for h in db.query(RateLimitHit).filter(RateLimitHit.key.in_([old, fresh]))}
    db.close()
    assert keys == {fresh}


def test_backend_setting_is_validated_and_selects_the_implementation(monkeypatch):
    assert Settings(rate_limit_backend="").rate_limit_backend == "memory"
    with pytest.raises(ValidationError):
        Settings(rate_limit_backend="redis")
    monkeypatch.setattr(get_settings(), "rate_limit_backend", "database")
    assert isinstance(limiter("t-select", 1, 1), DatabaseLimiter)
    monkeypatch.setattr(get_settings(), "rate_limit_backend", "memory")
    assert isinstance(limiter("t-select", 1, 1), SlidingWindowLimiter)
