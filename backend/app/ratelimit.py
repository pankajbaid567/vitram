"""Sliding-window rate limiting for sign-in and recovery endpoints.

Process-local by design (no extra infrastructure to run the app), thread-safe, and
memory-bounded: stale keys are evicted so an attacker cannot grow it by spraying
unique emails. With several API workers each enforces the limit independently, so the
effective ceiling is ``limit × workers``; swap :class:`SlidingWindowLimiter` for a
shared store (e.g. Redis or a table) if a hard global limit is required.
"""

import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, *, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.limit, self.window, self._clock, self._max_keys = limit, window_seconds, clock, max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record an attempt for ``key``; False when it would exceed the limit."""
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > self._max_keys:
                self._evict(now)
            return True

    def _evict(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window]:
            del self._hits[k]

    def __len__(self) -> int:
        return len(self._hits)
