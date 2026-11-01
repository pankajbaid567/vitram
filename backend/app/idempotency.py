"""``Idempotency-Key`` support for state-changing requests (Stripe-style).

A client that is unsure whether a request arrived (timeout, flaky mobile network, double click) repeats it with the same key and
gets the *original* response instead of a second effect. Rules:

* Applies to POST/PUT/PATCH/DELETE from a signed-in session that sends the header; scoped per session, so users cannot collide.
* Same key, same request -> the stored response is replayed with ``Idempotent-Replay: true``.
* Same key, different request -> 422 ``IDEMPOTENCY_KEY_REUSED`` (a client bug, surfaced loudly).
* Same key while the first is still running -> 409 ``IDEMPOTENCY_IN_PROGRESS`` with ``Retry-After``.
* Server errors and non-JSON responses are not stored, so the client can retry for real.
Records expire after 24 hours.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import IdempotencyKey

HEADER = "idempotency-key"
TTL = timedelta(hours=24)
STALE_IN_PROGRESS = timedelta(minutes=5)   # a crashed first attempt must not block the key forever
MAX_BODY = 12 * 1024 * 1024
MAX_STORED = 512 * 1024


@dataclass
class Ctx:
    row_id: str


@dataclass
class Replay:
    status: int
    body: str
    error: tuple[str, str] | None = None   # (code, message) when this is a refusal rather than a replay


def _valid(key: str | None) -> bool:
    return bool(key) and 8 <= len(key) <= 120 and key.isprintable()


def applies(method: str, key: str | None, session_token: str | None) -> bool:
    return method in ("POST", "PUT", "PATCH", "DELETE") and _valid(key) and bool(session_token)


def scope_of(session_token: str) -> str:
    return hashlib.sha256(session_token.encode()).hexdigest()


def fingerprint(method: str, path: str, query: str, body: bytes) -> str:
    h = hashlib.sha256()
    for part in (method.encode(), path.encode(), query.encode(), body):
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()


def begin(scope: str, key: str, fp: str) -> Ctx | Replay:
    """Claim the key, or say why not. Blocking (call from a thread)."""
    db = SessionLocal()
    try:
        row = IdempotencyKey(scope=scope, key=key, fingerprint=fp)
        db.add(row)
        try:
            db.commit()
            return Ctx(row.id)
        except IntegrityError:
            db.rollback()
        existing = db.query(IdempotencyKey).filter_by(scope=scope, key=key).one_or_none()
        if existing is None:                       # expired and purged between the two statements: just retry once
            return begin(scope, key, fp)
        if existing.fingerprint != fp:
            return Replay(422, "", ("IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was already used for a different request."))
        age = datetime.now(timezone.utc) - (existing.created_at if existing.created_at.tzinfo else existing.created_at.replace(tzinfo=timezone.utc))
        if existing.state == "done":
            return Replay(existing.status_code or 200, existing.response_body or "")
        if age > STALE_IN_PROGRESS:                # the first attempt died: take the key over
            existing.created_at = datetime.now(timezone.utc)
            db.commit()
            return Ctx(existing.id)
        return Replay(409, "", ("IDEMPOTENCY_IN_PROGRESS", "The first request with this Idempotency-Key is still running. Retry in a moment."))
    finally:
        db.close()


def finish(ctx: Ctx, status: int, body: str | None) -> None:
    """Store the response (``body`` None means: do not keep it, so a retry runs for real)."""
    db = SessionLocal()
    try:
        row = db.get(IdempotencyKey, ctx.row_id)
        if row is None:
            return
        if body is None:
            db.delete(row)
        else:
            row.state, row.status_code, row.response_body = "done", status, body
        db.commit()
    finally:
        db.close()


def purge_expired() -> int:
    db = SessionLocal()
    try:
        n = db.query(IdempotencyKey).filter(IdempotencyKey.created_at < datetime.now(timezone.utc) - TTL).delete(synchronize_session=False)
        db.commit()
        return n
    finally:
        db.close()
