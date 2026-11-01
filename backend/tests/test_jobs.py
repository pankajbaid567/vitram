"""Durable job queue: exclusive claims, leases, retry with back-off, dead-letter, idempotent processing, and a real crash."""

import hashlib
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, update

from app.db import SessionLocal
from app.models import BankAccount, Document, Job, Transaction, User
from app.services import jobs, pipeline, storage
from tests.conftest import FIXTURES, signup

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def db(client_factory):   # client_factory boots the app, which creates the schema
    s = SessionLocal()
    s.query(Job).delete()
    s.commit()
    yield s
    s.query(Job).delete()
    s.commit()
    s.close()


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)   # SQLite returns naive datetimes


def _past(db, job_id, **cols):
    db.execute(update(Job).where(Job.id == job_id).values(**cols))
    db.commit()


def test_enqueue_deduplicates_while_active(db):
    a = jobs.enqueue(db, "noop", {"n": 1}, dedupe_key="k1")
    b = jobs.enqueue(db, "noop", {"n": 2}, dedupe_key="k1")
    db.commit()
    assert a.id == b.id and db.query(Job).count() == 1


def test_finished_job_with_same_key_is_replaced(db):
    a = jobs.enqueue(db, "noop", {}, dedupe_key="k2")
    db.commit()
    job = jobs.claim(db, "w1")
    jobs.complete(db, job)
    b = jobs.enqueue(db, "noop", {}, dedupe_key="k2")
    db.commit()
    assert b.id != a.id and db.query(Job).count() == 1 and b.status == "queued"


def test_only_one_worker_wins_a_job(db):
    jobs.enqueue(db, "noop", {})
    db.commit()
    first = jobs.claim(db, "w1")
    second = jobs.claim(db, "w2")
    assert first is not None and first.status == "running" and first.attempts == 1
    assert second is None


def test_expired_lease_is_taken_over_by_another_worker(db):
    jobs.enqueue(db, "noop", {})
    db.commit()
    jobs.claim(db, "dead-worker")
    assert jobs.claim(db, "w2") is None                      # lease still valid
    later = datetime.now(timezone.utc) + jobs.LEASE + timedelta(seconds=1)
    taken = jobs.claim(db, "w2", now=later)
    assert taken is not None and taken.locked_by == "w2" and taken.attempts == 2


def test_failure_retries_with_backoff_then_parks_as_dead(db):
    seen = {"runs": 0, "dead": None}

    def boom(_payload):
        seen["runs"] += 1
        raise RuntimeError("storage unreachable")

    jobs.register("flaky", boom, on_dead=lambda payload, err: seen.__setitem__("dead", (payload, err)))
    job = jobs.enqueue(db, "flaky", {"x": 1}, max_attempts=3)
    db.commit()
    jid = job.id
    for attempt in (1, 2, 3):
        assert jobs.run_next("w1") is True
        db.expire_all()
        row = db.get(Job, jid)
        assert row.attempts == attempt
        if attempt < 3:
            assert row.status == "queued" and _aware(row.run_after) > datetime.now(timezone.utc) - timedelta(seconds=1)
            assert jobs.run_next("w1") is False              # backing off: not runnable yet
            _past(db, jid, run_after=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert row.status == "dead" and "storage unreachable" in row.last_error
    assert seen["runs"] == 3 and seen["dead"] == ({"x": 1}, row.last_error)


def test_backoff_grows_and_is_capped():
    assert jobs.backoff(2) > jobs.backoff(1) * 1.2 or jobs.backoff(2) > 20
    assert jobs.backoff(30) <= jobs.MAX_BACKOFF_SECONDS * 1.25


def test_stats_report_queue_depth_and_age(db):
    jobs.enqueue(db, "noop", {})
    db.commit()
    s = jobs.stats(db)
    assert s["queued"] == 1 and s["oldest_queued_age_seconds"] is not None




def _make_statement(client, db) -> Document:
    me = signup(client)
    user = db.query(User).filter(User.email == me["email"]).one()
    data = (FIXTURES / "sample_statement_6m.csv").read_bytes()
    acct = BankAccount(user_id=user.id, label="Salary", bank_name="Test Bank", masked_account_ref="••••1", is_primary=True)
    db.add(acct)
    db.flush()
    doc = Document(owner_user_id=user.id, type="bank_statement", display_name="s.csv", mime="text/csv", size_bytes=len(data),
                   file_key=storage.put(data), checksum=hashlib.sha256(data).hexdigest(), period_months=6, bank_account_id=acct.id)
    db.add(doc)
    db.commit()
    return doc


def _txn_count(db, user_id):
    return db.query(func.count(Transaction.id)).filter(Transaction.user_id == user_id).scalar()


def test_processing_twice_does_not_duplicate_rows(client, db):
    doc = _make_statement(client, db)
    pipeline.process_document(doc.id)
    after_first = _txn_count(db, doc.owner_user_id)
    assert after_first > 0
    pipeline.process_document(doc.id)
    assert _txn_count(db, doc.owner_user_id) == after_first


def test_worker_killed_mid_job_is_recovered_exactly_once(client, db):
    """A real second process claims the job and dies without acknowledging; the lease expires; another worker finishes it once."""
    doc = _make_statement(client, db)
    pipeline.enqueue_processing(db, doc)
    db.commit()
    job = db.query(Job).one()

    crash = ("from app.services import jobs; j = jobs.claim(__import__('app.db', fromlist=['SessionLocal']).SessionLocal(), 'crashing-worker');"
             "assert j is not None; import os; os._exit(137)")
    proc = subprocess.run([sys.executable, "-c", crash], cwd=BACKEND, env=os.environ.copy(), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 137, proc.stderr

    db.expire_all()
    row = db.get(Job, job.id)
    assert row.status == "running" and row.locked_by == "crashing-worker" and row.attempts == 1
    assert jobs.run_next("healthy-worker") is False          # lease still held by the dead process

    _past(db, job.id, locked_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert jobs.run_next("healthy-worker") is True           # takes over and finishes
    db.expire_all()
    row, d = db.get(Job, job.id), db.get(Document, doc.id)
    assert row.status == "done" and row.attempts == 2 and row.locked_by is None
    assert d.processing_status in ("ready", "needs_review")
    assert jobs.run_next("healthy-worker") is False          # nothing left: it ran exactly once to completion
    count = _txn_count(db, doc.owner_user_id)
    assert count > 0


def test_many_workers_process_each_job_exactly_once(db):
    ran: list[int] = []
    jobs.register("count", lambda p: ran.append(p["n"]))
    for n in range(40):
        jobs.enqueue(db, "count", {"n": n})
    db.commit()
    import threading

    def work(name):
        while jobs.run_next(name):
            pass

    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(ran) == list(range(40))                    # every job ran, none twice
    assert db.query(Job).filter(Job.status == "done").count() == 40


def test_dead_document_job_marks_the_document_failed(client, db, monkeypatch):
    doc = _make_statement(client, db)
    pipeline.enqueue_processing(db, doc)
    db.commit()
    monkeypatch.setattr(storage, "get", lambda key: (_ for _ in ()).throw(OSError("bucket unreachable")))
    job = db.query(Job).one()
    for _ in range(job.max_attempts):
        assert jobs.run_next("w") is True
        _past(db, job.id, run_after=datetime.now(timezone.utc) - timedelta(seconds=1))
    db.expire_all()
    assert db.get(Job, job.id).status == "dead"
    d = db.get(Document, doc.id)
    assert d.processing_status == "failed" and d.error_code == "PROCESSING_ERROR"
