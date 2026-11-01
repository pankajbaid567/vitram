"""A small durable job queue on the application database.

* **Enqueue in the caller's transaction.** ``enqueue`` only adds a row; the upload that created the document commits the
  job with it, so there is never a document without its job (or the reverse).
* **Claim with a lease.** ``claim`` finds the oldest runnable job and takes it with one conditional ``UPDATE`` (compare-and-set), so
  among competing workers exactly one wins. On PostgreSQL the candidate scan uses ``FOR UPDATE SKIP LOCKED`` so workers do not queue
  behind each other. A job whose lease has expired belongs to a dead worker and is claimable again (at-least-once delivery).
* **Retry, then park.** A failure re-queues the job with exponential back-off and jitter. After ``max_attempts`` it becomes ``dead``
  and its kind's dead-letter hook runs (the document is marked failed so the user can press Retry).
* **Handlers must be idempotent.** A job may run more than once (a worker can die after finishing but before acknowledging).
"""

import asyncio
import logging
import os
import random
import socket
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app import metrics
from app.db import SessionLocal
from app.models import Job

log = logging.getLogger("vitram.jobs")

LEASE = timedelta(minutes=5)
BASE_BACKOFF_SECONDS = 20.0
MAX_BACKOFF_SECONDS = 15 * 60.0

Handler = Callable[[dict], None]
_handlers: dict[str, Handler] = {}
_on_dead: dict[str, Callable[[dict, str], None]] = {}


def register(kind: str, handler: Handler, on_dead: Callable[[dict, str], None] | None = None) -> None:
    _handlers[kind] = handler
    if on_dead:
        _on_dead[kind] = on_dead


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, kind: str, payload: dict, *, dedupe_key: str | None = None, max_attempts: int = 4,
            run_after: datetime | None = None) -> Job:
    """Add a job to the caller's transaction (the caller commits). A second job with the same ``dedupe_key`` that is still
    queued or running is not created; the existing one is returned. A finished or dead job with that key is replaced."""
    if dedupe_key:
        existing = db.execute(select(Job).where(Job.dedupe_key == dedupe_key)).scalar_one_or_none()
        if existing is not None:
            if existing.status in ("queued", "running"):
                return existing
            db.delete(existing)
            db.flush()
    job = Job(kind=kind, payload=payload, dedupe_key=dedupe_key, max_attempts=max_attempts, run_after=run_after or _now())
    db.add(job)
    db.flush()
    return job


def _runnable(now: datetime):
    return or_(
        (Job.status == "queued") & (Job.run_after <= now),
        (Job.status == "running") & (Job.locked_until < now),  # the previous owner died or stalled
    )


def claim(db: Session, wid: str, now: datetime | None = None, lease: timedelta = LEASE) -> Job | None:
    """Take the oldest runnable job, or None. Committed before the job runs."""
    now = now or _now()
    query = select(Job.id).where(_runnable(now)).order_by(Job.run_after).limit(5)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    for (job_id,) in db.execute(query).all():
        won = db.execute(
            update(Job).where(Job.id == job_id, _runnable(now))
            .values(status="running", locked_by=wid, locked_until=now + lease, attempts=Job.attempts + 1)
        ).rowcount
        if won == 1:
            db.commit()
            db.expire_all()
            return db.get(Job, job_id)
    db.rollback()
    return None


def complete(db: Session, job: Job) -> None:
    job.status, job.locked_by, job.locked_until, job.finished_at, job.last_error = "done", None, None, _now(), None
    db.commit()


def backoff(attempts: int) -> float:
    base = min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * 2 ** max(0, attempts - 1))
    return base * random.uniform(0.75, 1.25)  # jitter: a burst of failures must not retry in lock-step


def fail(db: Session, job: Job, error: str) -> None:
    job.last_error = error[:300]
    job.locked_by = job.locked_until = None
    if job.attempts >= job.max_attempts:
        job.status, job.finished_at = "dead", _now()
        db.commit()
        hook = _on_dead.get(job.kind)
        if hook:
            try:
                hook(job.payload, job.last_error)
            except Exception:  # noqa: BLE001 - the parked job is already recorded
                log.exception("dead-letter hook failed for job %s", job.id)
        log.error("job %s (%s) is dead after %s attempts", job.id, job.kind, job.attempts)
        return
    job.status = "queued"
    job.run_after = _now() + timedelta(seconds=backoff(job.attempts))
    db.commit()


def run_next(wid: str | None = None) -> bool:
    """Claim and run one job in a fresh session. Returns False when nothing was runnable."""
    from app.services import pipeline  # noqa: F401 - importing registers the handlers (avoids a circular import at module load)

    wid = wid or worker_id()
    db = SessionLocal()
    try:
        job = claim(db, wid)
        if job is None:
            return False
        handler = _handlers.get(job.kind)
        started = time.perf_counter()
        try:
            if handler is None:
                raise LookupError(f"no handler registered for job kind {job.kind!r}")
            handler(job.payload)
        except Exception as exc:  # noqa: BLE001 - any failure is a retry decision, not a crash
            db.rollback()
            log.exception("job %s (%s) failed on attempt %s", job.id, job.kind, job.attempts)
            row = db.get(Job, job.id)
            fail(db, row, f"{type(exc).__name__}: {exc}")
            metrics.JOB_DURATION.labels(job.kind).observe(time.perf_counter() - started)
            metrics.JOBS_FINISHED.labels(job.kind, "dead" if row.status == "dead" else "retry").inc()
            return True
        complete(db, db.get(Job, job.id))
        metrics.JOB_DURATION.labels(job.kind).observe(time.perf_counter() - started)
        metrics.JOBS_FINISHED.labels(job.kind, "done").inc()
        return True
    finally:
        db.close()


def run_available(limit: int = 50, wid: str | None = None) -> int:
    """Run runnable jobs until none are left (or ``limit``). Used by the in-process fast path and by the worker loop."""
    done = 0
    while done < limit and run_next(wid):
        done += 1
    return done


def stats(db: Session) -> dict:
    """Counts by status plus the age in seconds of the oldest queued job (the number to alert on)."""
    rows = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    oldest = db.execute(select(func.min(Job.run_after)).where(Job.status == "queued")).scalar()
    age = None
    if oldest is not None:
        oldest = oldest if oldest.tzinfo else oldest.replace(tzinfo=timezone.utc)
        age = max(0.0, (_now() - oldest).total_seconds())
    return {"queued": rows.get("queued", 0), "running": rows.get("running", 0), "dead": rows.get("dead", 0),
            "done": rows.get("done", 0), "oldest_queued_age_seconds": age}


async def job_loop(interval: float = 5.0) -> None:
    """Poll for runnable jobs forever (run beside the API when ``RUN_SCHEDULER`` is on, or in ``python -m app.worker``)."""
    while True:
        try:
            ran = await asyncio.to_thread(run_available)
        except Exception:  # noqa: BLE001
            log.exception("job loop pass failed")
            ran = 0
        if ran == 0:
            await asyncio.sleep(interval)
