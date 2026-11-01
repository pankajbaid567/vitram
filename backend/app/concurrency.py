"""Optimistic concurrency for editable records.

Two layers, so a lost update is impossible:

1. **Client intent (HTTP).** Every record the API returns carries ``version``. A client sends it back as ``If-Match: "<version>"`` on
   PATCH; if the record has moved on, the answer is ``412 STALE_VERSION`` (with the current version) and nothing is written. Omitting
   the header keeps the old last-write-wins behaviour for simple clients.
2. **Database guard.** The ORM adds ``AND version = :loaded`` to every UPDATE (``version_id_col``). Two requests that load the same
   row and both write cannot both win: the loser gets ``StaleDataError``, which the API turns into ``409 CONFLICT``.
"""

from fastapi import Request

from app.errors import DomainError


def require_match(request: Request, current_version: int) -> None:
    raw = request.headers.get("if-match")
    if raw is None:
        return
    token = raw.strip()
    if token.startswith("W/"):
        token = token[2:]
    token = token.strip('"')
    if token == "*":
        return
    if token != str(current_version):
        raise DomainError("STALE_VERSION", "This was changed somewhere else since you opened it. Reload to see the latest, then try again.",
                          status_code=412, details={"current_version": current_version})
