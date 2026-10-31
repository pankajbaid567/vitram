"""Sliding-window rate limiting for sign-in and recovery endpoints.

Two backends behind one ``allow(key)`` interface. ``memory`` (default) is process-local, thread-safe and
memory-bounded: stale keys are evicted so an attacker cannot grow it by spraying unique emails, but with several
API workers each enforces the limit independently (ceiling = ``limit × workers``). ``database`` shares the count
across workers through the application database; select it with ``RATE_LIMIT_BACKEND=database``.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.config import get_settings
from app.db import SessionLocal
from app.models import RateLimitHit


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


class DatabaseLimiter:
    """The same limit, shared by every API process through the database.

    Each attempt is recorded *first*, then counted; if it pushed the count over the limit it is withdrawn. Two
    racing requests can therefore both be refused at the margin, but never both admitted: the safe direction for a
    brute-force guard. Rejected attempts leave no trace, so a lockout ends ``window`` after the last *allowed* try.
    """

    def __init__(self, limit: int, window_seconds: float, *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.limit, self.window, self._clock = limit, window_seconds, clock

    def allow(self, key: str) -> bool:
        now = self._clock()
        cutoff = now - timedelta(seconds=self.window)
        db = SessionLocal()
        try:
            db.query(RateLimitHit).filter(RateLimitHit.key == key, RateLimitHit.hit_at < cutoff).delete(synchronize_session=False)
            hit = RateLimitHit(key=key[:240], hit_at=now)
            db.add(hit)
            db.flush()
            used = db.query(func.count(RateLimitHit.id)).filter(RateLimitHit.key == key[:240], RateLimitHit.hit_at >= cutoff).scalar()
            if used > self.limit:
                db.delete(hit)
                db.commit()
                return False
            db.commit()
            return True
        finally:
            db.close()


def purge_expired(older_than: timedelta = timedelta(hours=1)) -> int:
    """Housekeeping for the shared ledger (called from the worker loop)."""
    db = SessionLocal()
    try:
        n = db.query(RateLimitHit).filter(RateLimitHit.hit_at < datetime.now(timezone.utc) - older_than).delete(synchronize_session=False)
        db.commit()
        return n
    finally:
        db.close()


_instances: dict[tuple[str, str], SlidingWindowLimiter | DatabaseLimiter] = {}


def limiter(name: str, limit: int, window_seconds: float) -> SlidingWindowLimiter | DatabaseLimiter:
    """The named limiter for the configured backend (``RATE_LIMIT_BACKEND=memory|database``)."""
    backend = get_settings().rate_limit_backend
    if (name, backend) not in _instances:
        _instances[(name, backend)] = (DatabaseLimiter if backend == "database" else SlidingWindowLimiter)(limit, window_seconds)
    return _instances[(name, backend)]
