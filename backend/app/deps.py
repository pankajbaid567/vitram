from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import DomainError
from app.models import AuthSession, Consent, User
from app.security import token_id

SESSION_COOKIE = "vitram_session"


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise DomainError("UNAUTHENTICATED", "Sign in to continue.", status_code=401)
    session = db.get(AuthSession, token_id(token))
    if session is None:
        raise DomainError("UNAUTHENTICATED", "Your session has ended. Sign in again.", status_code=401)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise DomainError("UNAUTHENTICATED", "Your session has ended. Sign in again.", status_code=401)
    user = db.get(User, session.user_id)
    if user is None:
        raise DomainError("UNAUTHENTICATED", "Sign in to continue.", status_code=401)
    return user


def has_consent(db: Session, user_id: str, purpose: str) -> Consent | None:
    return (
        db.query(Consent)
        .filter(Consent.user_id == user_id, Consent.purpose == purpose, Consent.revoked_at.is_(None))
        .order_by(Consent.granted_at.desc())
        .first()
    )


def require_consent(db: Session, user_id: str, purpose: str, message: str) -> Consent:
    consent = has_consent(db, user_id, purpose)
    if consent is None:
        raise DomainError("CONSENT_REQUIRED", message, field=purpose, status_code=403)
    return consent
