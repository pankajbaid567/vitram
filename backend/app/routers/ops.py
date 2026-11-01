"""Operational endpoints: liveness lives in main (`/api/health`); readiness here."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.migrate import alembic_config, current_revision, head_revision
from app.services import jobs
from app.services.channels import scheduler

router = APIRouter(tags=["ops"])

STALE_AFTER_SECONDS = 300   # the dispatcher ticks every 60 s
JOBS_STALE_AFTER_SECONDS = 600   # a runnable job that waits this long means no worker is draining the queue


@router.get("/ready")
def ready():
    """Can this instance serve traffic? Database reachable and schema at the code's head revision.

    The reminder loop's state is reported for operators but does not make the *API* unready: a stalled worker is an
    alert, not a reason to stop answering requests.
    """
    settings = get_settings()
    checks: dict = {}
    ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report the class, never connection strings
        checks["database"] = f"unreachable ({type(exc).__name__})"
        ok = False
    if checks["database"] == "ok":
        current, head = current_revision(engine), head_revision(alembic_config(settings.database_url))
        checks["migrations"] = "ok" if current == head else f"behind (at {current}, code needs {head})"
        ok = ok and current == head
        db = SessionLocal()
        try:
            age = scheduler.heartbeat_age(db)
            queue = jobs.stats(db)
        finally:
            db.close()
        state = "never_ran" if age is None else "ok" if age.total_seconds() < STALE_AFTER_SECONDS else "stale"
        oldest = queue["oldest_queued_age_seconds"]
        checks["jobs"] = {"state": "stale" if (oldest or 0) > JOBS_STALE_AFTER_SECONDS else "ok", "queued": queue["queued"],
                          "dead": queue["dead"], "oldest_queued_age_seconds": None if oldest is None else int(oldest)}
        checks["reminder_loop"] = {"state": state, "runs_in_api": settings.run_scheduler,
                                   "last_beat_seconds_ago": None if age is None else int(age.total_seconds())}
    return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)
