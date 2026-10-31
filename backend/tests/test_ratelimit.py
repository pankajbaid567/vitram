from app.ratelimit import SlidingWindowLimiter


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
