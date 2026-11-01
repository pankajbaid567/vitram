"""Protection against slow or failing dependencies: circuit breaker, bulkhead, retry budget, and load-shed limits.

* **Circuit breaker** (closed -> open -> half-open). ``failure_threshold`` failures inside ``window`` seconds open it; calls then fail fast
  for ``cooldown`` seconds instead of piling up behind a dead service. After the cooldown *one* trial call is let through (half-open): success
  closes the circuit, failure re-opens it for another cooldown.
* **Bulkhead.** A cap on concurrent calls to one dependency, so a slow provider cannot use up every worker thread.
* **Retry budget.** Retries are allowed only while they stay under a fraction of recent traffic, so a failing dependency is not hammered
  by a retry storm on top of the normal load.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

from app import metrics

T = TypeVar("T")

CLOSED, HALF_OPEN, OPEN = 0, 1, 2


class CircuitOpen(Exception):
    """Raised instead of calling a dependency whose circuit is open."""

    def __init__(self, name: str, retry_in: float):
        super().__init__(f"{name} is paused after repeated failures (retry in {retry_in:.0f}s)")
        self.name, self.retry_in = name, retry_in


class Overloaded(Exception):
    """Raised when a dependency's bulkhead is full."""


class CircuitBreaker:
    def __init__(self, name: str, *, failure_threshold: int = 5, window: float = 60.0, cooldown: float = 30.0,
                 clock: Callable[[], float] = time.monotonic):
        self.name, self.threshold, self.window, self.cooldown, self._clock = name, failure_threshold, window, cooldown, clock
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._trial_in_flight = False
        self._lock = threading.Lock()
        metrics.CIRCUIT.labels(name).set(CLOSED)

    @property
    def state(self) -> int:
        with self._lock:
            return self._state()

    def _state(self) -> int:
        if self._opened_at is None:
            return CLOSED
        return HALF_OPEN if self._clock() - self._opened_at >= self.cooldown else OPEN

    def _publish(self) -> None:
        metrics.CIRCUIT.labels(self.name).set(self._state())

    def before(self) -> None:
        """Gate a call. Raises CircuitOpen when it must not go out."""
        with self._lock:
            state = self._state()
            if state == OPEN:
                raise CircuitOpen(self.name, self.cooldown - (self._clock() - (self._opened_at or 0)))
            if state == HALF_OPEN:
                if self._trial_in_flight:
                    raise CircuitOpen(self.name, 1.0)      # one probe at a time
                self._trial_in_flight = True
            self._publish()

    def success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at, self._trial_in_flight = None, False
            self._publish()

    def failure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._opened_at is not None and self._trial_in_flight:      # the half-open probe failed: another full cooldown
                self._opened_at, self._trial_in_flight = now, False
                self._publish()
                return
            self._failures.append(now)
            while self._failures and now - self._failures[0] > self.window:
                self._failures.popleft()
            if len(self._failures) >= self.threshold:
                self._opened_at = now
            self._publish()

    def release_trial(self) -> None:
        """A call that ended in a non-dependency error (e.g. bad input): free the half-open slot without judging the dependency."""
        with self._lock:
            self._trial_in_flight = False


class Bulkhead:
    def __init__(self, name: str, max_concurrent: int):
        self.name, self._sem = name, threading.BoundedSemaphore(max_concurrent)

    def __enter__(self):
        if not self._sem.acquire(blocking=False):
            metrics.SHED.labels(f"bulkhead:{self.name}").inc()
            raise Overloaded(f"{self.name} is at capacity")
        return self

    def __exit__(self, *exc):
        self._sem.release()


class RetryBudget:
    """Allow a retry only while retries are under ``ratio`` of calls in the last ``window`` seconds (plus ``min_per_window`` free ones)."""

    def __init__(self, ratio: float = 0.1, window: float = 60.0, min_per_window: int = 3, clock: Callable[[], float] = time.monotonic):
        self.ratio, self.window, self.min, self._clock = ratio, window, min_per_window, clock
        self._calls: deque[float] = deque()
        self._retries: deque[float] = deque()
        self._lock = threading.Lock()

    def _trim(self, now: float) -> None:
        for q in (self._calls, self._retries):
            while q and now - q[0] > self.window:
                q.popleft()

    def record_call(self) -> None:
        with self._lock:
            now = self._clock()
            self._calls.append(now)
            self._trim(now)

    def allow_retry(self) -> bool:
        with self._lock:
            now = self._clock()
            self._trim(now)
            if len(self._retries) < max(self.min, int(len(self._calls) * self.ratio)):
                self._retries.append(now)
                return True
            return False


_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def breaker(name: str, **kw) -> CircuitBreaker:
    with _registry_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name, **kw)
        return _breakers[name]


def reset_all() -> None:
    """Forget every breaker (tests)."""
    with _registry_lock:
        _breakers.clear()


def call(name: str, fn: Callable[[], T], *, is_dependency_failure: Callable[[Exception], bool] = lambda exc: True,
         bulkhead: Bulkhead | None = None) -> T:
    """Run ``fn`` through the breaker named ``name``, recording gateway metrics.

    ``is_dependency_failure`` decides which exceptions count against the dependency (a malformed request is our bug, not its outage).
    """
    cb = breaker(name)
    try:
        cb.before()
    except CircuitOpen:
        metrics.GATEWAY.labels(name, "circuit_open").inc()
        raise
    started = time.perf_counter()
    try:
        if bulkhead is not None:
            with bulkhead:
                result = fn()
        else:
            result = fn()
    except Overloaded:
        cb.release_trial()
        raise
    except Exception as exc:
        if is_dependency_failure(exc):
            cb.failure()
            metrics.GATEWAY.labels(name, "error").inc()
        else:
            cb.release_trial()
            metrics.GATEWAY.labels(name, "rejected").inc()
        metrics.GATEWAY_DURATION.labels(name).observe(time.perf_counter() - started)
        raise
    cb.success()
    metrics.GATEWAY.labels(name, "ok").inc()
    metrics.GATEWAY_DURATION.labels(name).observe(time.perf_counter() - started)
    return result
