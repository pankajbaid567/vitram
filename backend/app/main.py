import asyncio
import contextlib
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.errors import DomainError, domain_error_handler
from app.deps import SESSION_COOKIE
from app.security import RedactingFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for h in logging.getLogger().handlers:
    h.addFilter(RedactingFilter())
log = logging.getLogger("vitram")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PREFIXES = ("/api/webhooks/",)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from app.services.catalogue import load_catalogues
    from app.services.channels.scheduler import reminder_loop

    load_catalogues()
    task = asyncio.create_task(reminder_loop())
    yield
    task.cancel()


app = FastAPI(title="VITTRM API", version="0.1.0", lifespan=lifespan)
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


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if (blocked := _csrf_violation(request, get_settings().app_origin)) is not None:
        _harden(request, blocked)
        return blocked
    response = await call_next(request)
    _harden(request, response)
    return response


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
        profile,
        reminders,
        webhooks,
    )

    for module in (auth, onboarding, family, documents, profile, dashboard, loans, cards, emis, insurance,
                   consultations, reminders, notifications, ai, webhooks, demo, insights, goals):
        app.include_router(module.router, prefix="/api")


_include_routers()
