"""A small read-through cache whose entries are invalidated by *data version*, not by hand.

Every user has a version number. Any committed change to a row that belongs to them (any table with ``user_id`` / ``owner_user_id``) bumps it,
and cache keys embed it (``dashboard:<user>:<version>:<today>``), so a change makes every old entry unreachable at once: there is no list of
keys to remember to delete, which is where stale-data bugs usually come from. Entries also expire after ``cache_ttl_seconds`` as a backstop
for the things a version cannot see (bulk SQL deletes, rows whose owner is only reachable through a parent).

State lives in Redis when ``REDIS_URL`` is set (shared by every API instance, so a write on one instance invalidates for all); otherwise in
this process, where a second API instance could serve an entry up to ``cache_ttl_seconds`` old. A cache that cannot reach Redis is skipped,
never an error.
"""

import json
import logging
import threading
import time
from collections.abc import Callable

from fastapi.encoders import jsonable_encoder
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import metrics
from app.config import get_settings

log = logging.getLogger("vitram.cache")

_OWNER_ATTRS = ("user_id", "owner_user_id")
# Append-only logs nothing cached depends on: writing them (every calculation records one) must not throw away cached pages.
_LOG_TABLES = {"audit_events", "calculation_runs"}


class MemoryStore:
    def __init__(self, clock=time.monotonic):
        self._clock, self._data, self._versions, self._lock = clock, {}, {}, threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            if hit[0] < self._clock():
                del self._data[key]
                return None
            return hit[1]

    def set(self, key: str, value: str, ttl: float) -> None:
        with self._lock:
            if len(self._data) > 5000:
                now = self._clock()
                for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                    del self._data[k]
            self._data[key] = (self._clock() + ttl, value)

    def version(self, user_id: str) -> int:
        with self._lock:
            return self._versions.get(user_id, 0)

    def bump(self, user_id: str) -> None:
        with self._lock:
            self._versions[user_id] = self._versions.get(user_id, 0) + 1


class RedisStore:
    def __init__(self, url: str, prefix: str = "vitram:c:"):
        import redis

        t = get_settings().redis_timeout_seconds
        self.prefix = prefix
        self._r = redis.Redis.from_url(url, socket_timeout=t, socket_connect_timeout=t * 2, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._r.get(self.prefix + key)

    def set(self, key: str, value: str, ttl: float) -> None:
        self._r.set(self.prefix + key, value, ex=max(1, int(ttl)))

    def version(self, user_id: str) -> int:
        return int(self._r.get(f"{self.prefix}uv:{user_id}") or 0)

    def bump(self, user_id: str) -> None:
        self._r.incr(f"{self.prefix}uv:{user_id}")


_store = None
_store_url: str | None = None
_lock = threading.Lock()


def store():
    global _store, _store_url
    url = get_settings().redis_url
    with _lock:
        if _store is None or url != _store_url:
            _store = RedisStore(url) if url else MemoryStore()
            _store_url = url
        return _store


def reset() -> None:
    global _store, _store_url
    with _lock:
        _store, _store_url = None, None


def bump(user_id: str) -> None:
    try:
        store().bump(user_id)
    except Exception as exc:  # noqa: BLE001 - invalidation failing must not fail the user's write; the TTL bounds the staleness
        log.warning("cache invalidation failed (%s); entries expire within %ss", type(exc).__name__, get_settings().cache_ttl_seconds)


def cached(namespace: str, user_id: str, builder: Callable[[], object], *, daily: bool = False):
    """Return ``builder()``'s JSON-able result, from cache when the user's data has not changed since it was stored."""
    s = get_settings()
    if not s.cache_enabled:
        return builder()
    try:
        st = store()
        day = time.strftime("%Y%m%d") if daily else ""
        key = f"{namespace}:{user_id}:{st.version(user_id)}:{day}"
        raw = st.get(key)
        if raw is not None:
            metrics.CACHE.labels(namespace, "hit").inc()
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - a broken cache is a miss, not an outage
        metrics.CACHE.labels(namespace, "unavailable").inc()
        log.warning("cache unavailable (%s); serving uncached", type(exc).__name__)
        return builder()
    metrics.CACHE.labels(namespace, "miss").inc()
    result = jsonable_encoder(builder())
    try:
        st.set(key, json.dumps(result), s.cache_ttl_seconds)
    except Exception:  # noqa: BLE001
        pass
    return result


def etag_response(request, payload, *, max_age: int = 300):
    """JSON with a strong ETag and a short private max-age, answering 304 when the client already has it.

    For reference data that is the same for everyone (the product catalogues): the browser revalidates for the price of a header instead
    of re-downloading and re-serialising the list. User-specific data keeps ``Cache-Control: no-store`` (set in the security middleware).
    """
    import hashlib

    from fastapi import Response

    body = json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
    headers = {"ETag": etag, "Cache-Control": f"private, max-age={max_age}"}
    if etag in [t.strip().removeprefix("W/") for t in (request.headers.get("if-none-match") or "").split(",")]:
        metrics.CACHE.labels("http-etag", "hit").inc()
        return Response(status_code=304, headers=headers)
    metrics.CACHE.labels("http-etag", "miss").inc()
    return Response(body, media_type="application/json", headers=headers)


# --- automatic invalidation ------------------------------------------------------------------------------------------------------

def _owner(obj) -> str | None:
    table = getattr(obj, "__tablename__", None)
    if table in _LOG_TABLES:
        return None
    if table == "users":
        return obj.id
    for attr in _OWNER_ATTRS:
        value = getattr(obj, attr, None) if hasattr(type(obj), attr) else None
        if isinstance(value, str):
            return value
    return None


@event.listens_for(Session, "after_flush")
def _collect(session: Session, _ctx) -> None:
    owners = session.info.setdefault("cache_owners", set())
    for obj in (*session.new, *session.dirty, *session.deleted):
        if (uid := _owner(obj)) is not None:
            owners.add(uid)


@event.listens_for(Session, "after_commit")
def _invalidate(session: Session) -> None:
    for uid in session.info.pop("cache_owners", ()):
        bump(uid)


@event.listens_for(Session, "after_rollback")
def _forget(session: Session) -> None:
    session.info.pop("cache_owners", None)
