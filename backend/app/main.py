import asyncio
import contextlib
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
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


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    rid = new_request_id(request.headers.get("x-request-id"))
    token = request_id_var.set(rid)
    try:
        if (blocked := _csrf_violation(request, get_settings().app_origin)) is not None:
            response = blocked
        else:
            try:
                response = await call_next(request)
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
