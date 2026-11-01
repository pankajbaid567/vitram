"""Per-user / per-IP rate limits as token buckets, in memory or shared through Redis.

Every API request spends one token from a bucket chosen by what it does, so one noisy client cannot starve the others and an expensive
action (a document upload, an assistant turn) costs more of its budget than a cheap read:

==========  ==========  =================  =========================================================
policy      burst       sustained          covers
==========  ==========  =================  =========================================================
read        120         240 / minute       GET
write       40          60 / minute        POST/PUT/PATCH/DELETE
upload      8           8 / minute         document uploads and card-statement imports
ai          15          15 / minute        assistant messages (plus ``ai_daily_cap`` per day)
==========  ==========  =================  =========================================================

The bucket key is the signed-in session (hashed) or, for anonymous traffic, the client IP. Redis keeps the count shared across API
instances (one Lua script, atomic, using Redis's own clock); without ``REDIS_URL`` each process counts alone. If Redis is unreachable the
limiter **fails open** (availability beats strictness for a non-security limit) behind a circuit breaker, and says so in the metrics.
Sign-in and recovery have their own, stricter limiters in ``app/ratelimit.py``.
"""

import hashlib
import logging
import math
import threading
import time
from dataclasses import dataclass

from app import metrics, resilience
from app.config import get_settings

log = logging.getLogger("vitram.throttle")


@dataclass(frozen=True)
class Policy:
    name: str
    capacity: float          # burst
    refill_per_sec: float    # sustained rate


POLICIES = {
    "read": Policy("read", 120, 4.0),
    "write": Policy("write", 40, 1.0),
    "upload": Policy("upload", 8, 8 / 60),
    "ai": Policy("ai", 15, 15 / 60),
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int          # seconds; 0 when allowed
    policy: str = ""
    reason: str = ""


EXEMPT = ("/api/health", "/api/ready", "/api/metrics", "/api/webhooks/")


def classify(method: str, path: str) -> str | None:
    if path.startswith(EXEMPT):
        return None
    if method in ("GET", "HEAD"):
        return "read"
    if path.startswith("/api/ai/"):
        return "ai"
    if method == "POST" and (path == "/api/documents" or path.endswith("/import-document")):
        return "upload"
    return "write"


def identity(session_token: str | None, forwarded_ip: str | None, client_ip: str | None) -> str:
    if session_token:
        return "u:" + hashlib.sha256(session_token.encode()).hexdigest()[:24]
    return "ip:" + (forwarded_ip or client_ip or "unknown")


class MemoryBuckets:
    def __init__(self, clock=time.monotonic):
        self._clock, self._state, self._days, self._lock = clock, {}, {}, threading.Lock()

    def take(self, key: str, p: Policy) -> Decision:
        now = self._clock()
        with self._lock:
            key = f"{p.name}|{key}"        # one bucket per user *per policy*
            tokens, ts = self._state.get(key, (p.capacity, now))
            tokens = min(p.capacity, tokens + (now - ts) * p.refill_per_sec)
            if tokens >= 1:
                self._state[key] = (tokens - 1, now)
                self._evict(now)
                return Decision(True, int(p.capacity), int(tokens - 1), 0, p.name)
            self._state[key] = (tokens, now)
            return Decision(False, int(p.capacity), 0, max(1, math.ceil((1 - tokens) / p.refill_per_sec)), p.name, "rate")

    def day_count(self, key: str, cap: int) -> bool:
        day = time.strftime("%Y%m%d")
        with self._lock:
            for k in [k for k in self._days if not k.endswith(day)]:
                del self._days[k]
            n = self._days.get(key + day, 0) + 1
            self._days[key + day] = n
            return n <= cap

    def _evict(self, now: float) -> None:
        if len(self._state) > 50_000:
            for k in [k for k, (t, ts) in self._state.items() if now - ts > 600]:
                del self._state[k]


_LUA = """
local cap, refill = tonumber(ARGV[1]), tonumber(ARGV[2])
local t = redis.call('TIME'); local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local h = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens, ts = tonumber(h[1]), tonumber(h[2])
if tokens == nil then tokens = cap; ts = now end
tokens = math.min(cap, tokens + math.max(0, now - ts) * refill)
local allowed, retry = 0, 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 else retry = math.ceil((1 - tokens) / refill) end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(cap / refill) * 2 + 1)
return {allowed, math.floor(tokens), retry}
"""


class RedisBuckets:
    def __init__(self, url: str, prefix: str = "vitram:tb:", timeout: float | None = None):
        import redis

        t = timeout if timeout is not None else get_settings().redis_timeout_seconds
        self.prefix = prefix
        self._r = redis.Redis.from_url(url, socket_timeout=t, socket_connect_timeout=t * 2, decode_responses=True)
        self._script = self._r.register_script(_LUA)

    def take(self, key: str, p: Policy) -> Decision:
        allowed, remaining, retry = self._script(keys=[f"{self.prefix}{p.name}:{key}"], args=[p.capacity, p.refill_per_sec])
        return Decision(bool(allowed), int(p.capacity), int(remaining), int(retry), p.name, "" if allowed else "rate")

    def day_count(self, key: str, cap: int) -> bool:
        k = f"{self.prefix}aiday:{key}:{time.strftime('%Y%m%d')}"
        pipe = self._r.pipeline()
        pipe.incr(k)
        pipe.expire(k, 172800)
        return int(pipe.execute()[0]) <= cap


_backend = None
_backend_url: str | None = None
_lock = threading.Lock()


def backend():
    global _backend, _backend_url
    url = get_settings().redis_url
    with _lock:
        if _backend is None or url != _backend_url:
            _backend = RedisBuckets(url) if url else MemoryBuckets()
            _backend_url = url
        return _backend


def reset() -> None:
    global _backend, _backend_url
    with _lock:
        _backend, _backend_url = None, None


def check(method: str, path: str, session_token: str | None, forwarded_ip: str | None, client_ip: str | None) -> Decision | None:
    """Spend a token. None = this route is exempt. Never raises: a broken limiter must not take the API down."""
    s = get_settings()
    name = classify(method, path)
    if not s.throttle_enabled or name is None:
        return None
    key = identity(session_token, forwarded_ip, client_ip)
    policy = POLICIES[name]
    be = backend()
    try:
        if isinstance(be, RedisBuckets):
            decision = resilience.call("redis", lambda: be.take(key, policy))
            if name == "ai" and decision.allowed and not resilience.call("redis", lambda: be.day_count(key, s.ai_daily_cap)):
                decision = Decision(False, s.ai_daily_cap, 0, 3600, "ai", "daily")
        else:
            decision = be.take(key, policy)
            if name == "ai" and decision.allowed and not be.day_count(key, s.ai_daily_cap):
                decision = Decision(False, s.ai_daily_cap, 0, 3600, "ai", "daily")
    except Exception as exc:  # noqa: BLE001 - fail open
        metrics.CACHE.labels("throttle", "unavailable").inc()
        log.warning("rate limiter unavailable (%s); allowing the request", type(exc).__name__)
        return None
    if not decision.allowed:
        metrics.RATE_LIMITED.labels(f"{name}:{decision.reason}").inc()
    return decision
