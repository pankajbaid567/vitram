import asyncio
import contextlib
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from sqlalchemy.orm.exc import StaleDataError

from app import idempotency
from app.deps import SESSION_COOKIE
from app.errors import DomainError, domain_error_handler
from app.observability import configure_logging, new_request_id, request_id_var

configure_logging(get_settings().log_format)
log = logging.getLogger("vitram")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PREFIXES = ("/api/webhooks/",)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.assert_production_ready()   # refuse to start misconfigured rather than fail on the first request
    init_db()
    from app.services.catalogue import load_catalogues
    from app.services.channels.scheduler import reminder_loop
    from app.services.jobs import job_loop

    load_catalogues()
    # The reminder loop can live in this process (default) or in a dedicated worker: RUN_SCHEDULER=false + `python -m app.worker`.
    tasks = [asyncio.create_task(reminder_loop()), asyncio.create_task(job_loop())] if settings.run_scheduler else []
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="VITRAM API", version="0.1.0", lifespan=lifespan)
app.add_exception_handler(DomainError, domain_error_handler)


async def _stale_write(_: Request, __: StaleDataError) -> JSONResponse:
    """Two requests edited the same record at once; the second write was refused by the database's version check."""
    return JSONResponse({"error": {"code": "CONFLICT", "message": "This was changed at the same time somewhere else. Reload and try again."}}, 409)


app.add_exception_handler(StaleDataError, _stale_write)


def _bad_origin(message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": "BAD_ORIGIN", "message": message}}, 403)


def _csrf_violation(request: Request, app_origin: str) -> JSONResponse | None:
    """Origin check for cookie-authenticated state changes (defence in depth on top of SameSite=Lax)."""
    if request.method not in UNSAFE or request.url.path.startswith(CSRF_EXEMPT_PREFIXES):
        return None
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        if urlparse(origin).netloc not in {urlparse(app_origin).netloc, request.url.netloc}:
            return _bad_origin("Request origin not allowed.")
    elif request.cookies.get(SESSION_COOKIE):
        # Browsers always send Origin on cross-site unsafe requests; a cookie without Origin is suspicious.
        return _bad_origin("Missing request origin.")
    return None


def _harden(request: Request, response: Response) -> None:
    """Defensive headers on every response. HSTS only over HTTPS; a strict CSP only on JSON bodies
    (documents are served back as PDFs/images, which a ``default-src 'none'`` policy could break)."""
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Cache-Control", "no-store")
    if request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if h.get("content-type", "").startswith("application/json"):
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")


def _internal_error(request_id: str) -> JSONResponse:
    body = {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong on our side. Try again, and quote this reference if it persists.",
                      "request_id": request_id}}
    return JSONResponse(body, status_code=500)


async def _with_idempotency(request: Request, call_next):
    key = request.headers.get(idempotency.HEADER)
    token = request.cookies.get(SESSION_COOKIE)
    if (not idempotency.applies(request.method, key, token) or request.url.path.startswith(CSRF_EXEMPT_PREFIXES)
            or int(request.headers.get("content-length") or 0) > idempotency.MAX_BODY):
        return await call_next(request)
    body = await request.body()
    fp = idempotency.fingerprint(request.method, request.url.path, request.url.query, body)
    outcome = await asyncio.to_thread(idempotency.begin, idempotency.scope_of(token), key, fp)
    if isinstance(outcome, idempotency.Replay):
        if outcome.error:
            code, message = outcome.error
            extra = {"Retry-After": "1"} if outcome.status == 409 else {}
            return JSONResponse({"error": {"code": code, "message": message}}, outcome.status, headers=extra)
        return Response(outcome.body, outcome.status, media_type="application/json", headers={"Idempotent-Replay": "true"})
    try:
        response = await call_next(request)
        stored = None
        if response.status_code < 500 and response.headers.get("content-type", "").startswith("application/json"):
            chunks = [chunk async for chunk in response.body_iterator]
            raw = b"".join(chunks)
            response = Response(raw, response.status_code, dict(response.headers), response.media_type)
            if len(raw) <= idempotency.MAX_STORED:
                stored = raw.decode()
        await asyncio.to_thread(idempotency.finish, outcome, response.status_code, stored)
        return response
    except BaseException:
        await asyncio.to_thread(idempotency.finish, outcome, 500, None)   # release the key: the retry should run for real
        raise


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    rid = new_request_id(request.headers.get("x-request-id"))
    token = request_id_var.set(rid)
    try:
        if (blocked := _csrf_violation(request, get_settings().app_origin)) is not None:
            response = blocked
        else:
            try:
                response = await _with_idempotency(request, call_next)
            except Exception:  # noqa: BLE001 - last line of defence: log with the request id, never leak internals
                log.exception("unhandled error on %s %s", request.method, request.url.path)
                response = _internal_error(rid)
        response.headers["X-Request-ID"] = rid
        _harden(request, response)
        return response
    finally:
        request_id_var.reset(token)


@app.get("/api/health")
def health():
    return {"ok": True}


def _include_routers() -> None:
    from app.routers import (
        ai,
        auth,
        cards,
        consultations,
        dashboard,
        demo,
        documents,
        emis,
        family,
        goals,
        insights,
        insurance,
        loans,
        notifications,
        onboarding,
        ops,
        profile,
        reminders,
        webhooks,
    )

    for module in (auth, onboarding, family, documents, profile, dashboard, loans, cards, emis, insurance,
                   consultations, reminders, notifications, ai, webhooks, demo, insights, goals, ops):
        app.include_router(module.router, prefix="/api")


_include_routers()
