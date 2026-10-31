"""Stable domain error codes → JSON `{error: {code, message, field?}}` (plan §6.7)."""

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, field: str | None = None, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details  # small, non-sensitive context the UI can act on (never document content)
        if status_code:
            self.status_code = status_code


class NotFound(DomainError):
    def __init__(self, what: str = "Item"):
        super().__init__("NOT_FOUND", f"{what} not found.", status_code=404)


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    body = {"code": exc.code, "message": exc.message}
    if exc.field:
        body["field"] = exc.field
    if getattr(exc, "details", None):
        body["details"] = exc.details
    return JSONResponse({"error": body}, status_code=exc.status_code)
