import asyncio
import contextlib
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.errors import DomainError, domain_error_handler
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


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    settings = get_settings()
    if request.method in UNSAFE and not request.url.path.startswith(CSRF_EXEMPT_PREFIXES):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            o = urlparse(origin)
            allowed = {urlparse(settings.app_origin).netloc, request.url.netloc}
            if o.netloc not in allowed:
                return JSONResponse({"error": {"code": "BAD_ORIGIN", "message": "Request origin not allowed."}}, 403)
        elif request.cookies.get("vitram_session"):
            # Browsers always send Origin on cross-site unsafe requests; a cookie without Origin is suspicious.
            return JSONResponse({"error": {"code": "BAD_ORIGIN", "message": "Missing request origin."}}, 403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
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
