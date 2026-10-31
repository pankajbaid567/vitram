import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import SESSION_COOKIE, current_user
from app.errors import DomainError
from app.models import AuthSession, AuthToken, Consent, PasswordReset, User
from app.security import hash_password, new_session_token, token_id, verify_password
from app.services import mailer

router = APIRouter(prefix="/auth", tags=["auth"])

_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS, WINDOW = 8, 300


def _rate_limit(key: str) -> None:
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < WINDOW]
    if len(_attempts[key]) >= MAX_ATTEMPTS:
        raise DomainError("TOO_MANY_ATTEMPTS", "Too many sign-in attempts. Wait a few minutes and try again.", status_code=429)
    _attempts[key].append(now)


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    accept_terms: bool

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User, db: Session) -> dict:
    consents = db.query(Consent).filter(Consent.user_id == u.id, Consent.revoked_at.is_(None)).all()
    return {
        "id": u.id, "name": u.name, "email": u.email, "dob": u.dob.isoformat() if u.dob else None,
        "city": u.city, "employment_type": u.employment_type, "employer": u.employer, "designation": u.designation,
        "salary_manual": u.salary_manual, "preferred_language": u.preferred_language, "phone_masked": u.phone_masked,
        "phone_verified": bool(u.phone_verified_at),
        "email_verified": bool(u.email_verified_at),
        "onboarding_step": u.onboarding_step, "is_sample": u.is_sample,
        "consents": sorted({c.purpose for c in consents}),
    }


def start_session(db: Session, response: Response, user: User, request: Request) -> None:
    token, sid = new_session_token()
    settings = get_settings()
    db.add(AuthSession(id=sid, user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days)))
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=request.url.scheme == "https",
        max_age=settings.session_days * 86400, path="/",
    )


def _issue_account_token(db: Session, user: User, purpose: str) -> str:
    now = datetime.now(timezone.utc)
    for old in db.query(AuthToken).filter(AuthToken.user_id == user.id, AuthToken.purpose == purpose,
                                           AuthToken.used_at.is_(None)):
        old.used_at = now
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(id=token_id(raw), user_id=user.id, purpose=purpose, expires_at=now + timedelta(minutes=30),
                     created_at=now))
    return raw


def _consume_account_token(db: Session, raw: str, purpose: str) -> User:
    now = datetime.now(timezone.utc)
    item_id = token_id(raw)
    updated = db.execute(update(AuthToken).where(AuthToken.id == item_id, AuthToken.purpose == purpose,
                                                 AuthToken.used_at.is_(None), AuthToken.expires_at > now)
                         .values(used_at=now))
    if updated.rowcount != 1:
        raise DomainError("INVALID_TOKEN", "This link is invalid or expired. Request a new one.", status_code=400)
    item = db.get(AuthToken, item_id)
    user = db.get(User, item.user_id)
    if not user:
        raise DomainError("INVALID_TOKEN", "This link is invalid or expired. Request a new one.", status_code=400)
    item.used_at = now
    return user


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.post("/email-verification/request")
def request_email_verification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.email_verified_at:
        return {"status": "verified"}
    if not get_settings().email_configured:
        raise DomainError("EMAIL_NOT_CONFIGURED", "Email verification is not configured yet.", status_code=503)
    _rate_limit(f"verify-email:{user.id}")
    raw = _issue_account_token(db, user, "email_verify")
    audit(db, user.id, "email.verification_requested")
    db.commit()
    url = f"{get_settings().app_origin.rstrip('/')}/verify-email?token={raw}"
    try:
        mailer.send(user.email, "Verify your VITTRM email", f"Verify your address within 30 minutes:\n{url}\n")
    except Exception as exc:
        raise DomainError("EMAIL_UNAVAILABLE", "Email could not be sent. Try again later.", status_code=503) from exc
    return {"status": "sent"}


@router.post("/email-verification/confirm")
def confirm_email_verification(body: TokenIn, db: Session = Depends(get_db)):
    user = _consume_account_token(db, body.token, "email_verify")
    user.email_verified_at = datetime.now(timezone.utc)
    audit(db, user.id, "email.verified")
    db.commit()
    return {"status": "verified"}


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not body.accept_terms:
        raise DomainError("TERMS_REQUIRED", "Accept the terms and privacy notice to create an account.", field="accept_terms")
    if db.query(User).filter(User.email == body.email).first():
        raise DomainError("EMAIL_TAKEN", "An account with this email already exists. Sign in instead.", field="email", status_code=409)
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password), onboarding_step="about")
    db.add(user)
    db.flush()
    db.add(Consent(user_id=user.id, purpose="terms"))
    audit(db, user.id, "auth.signup")
    start_session(db, response, user, request)
    db.commit()
    return user_out(user, db)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    _rate_limit(f"{email}|{request.client.host if request.client else ''}")
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise DomainError("INVALID_CREDENTIALS", "That email and password don't match.", status_code=401)
    start_session(db, response, user, request)
    audit(db, user.id, "auth.login")
    db.commit()
    return user_out(user, db)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        s = db.get(AuthSession, token_id(token))
        if s:
            db.delete(s)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Change the password (current password required). Every other session is signed out; this one stays."""
    _rate_limit(f"pw|{user.id}")
    if not verify_password(body.current_password, user.password_hash):
        raise DomainError("INVALID_CREDENTIALS", "Your current password isn't right.", field="current_password", status_code=400)
    if body.current_password == body.new_password:
        raise DomainError("SAME_PASSWORD", "Choose a password different from your current one.", field="new_password")
    user.password_hash = hash_password(body.new_password)
    token = request.cookies.get(SESSION_COOKIE)
    keep = token_id(token) if token else None
    ended = db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.id != keep).delete(synchronize_session=False)
    audit(db, user.id, "auth.password_changed", other_sessions_ended=ended)
    db.commit()
    return {"ok": True, "other_sessions_ended": ended}


RESET_MINUTES = 30


class ResetRequestIn(BaseModel):
    email: str = Field(max_length=254)


@router.get("/password-reset/status")
def reset_status():
    """Whether this server can send reset emails (shown on the login page before the user types anything)."""
    return {"email_configured": get_settings().email_configured}


@router.post("/password-reset/request")
def reset_request(body: ResetRequestIn, request: Request, db: Session = Depends(get_db)):
    """Always answers the same way whether or not the email has an account (no account enumeration)."""
    settings = get_settings()
    email = body.email.strip().lower()
    _rate_limit(f"reset|{email}|{request.client.host if request.client else ''}")
    if not settings.email_configured:
        return {"sent": False, "email_configured": False,
                "message": "Password reset by email isn't set up on this VITTRM server yet."}
    user = db.query(User).filter(User.email == email, User.is_sample.is_(False)).first()
    if user:
        token, tid = new_session_token()
        db.add(PasswordReset(id=tid, user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES)))
        link = f"{settings.app_origin.rstrip('/')}/reset-password?token={token}"
        try:
            mailer.send(email, "Reset your VITTRM password",
                        f"Someone asked to reset the password for this VITTRM account.\n\nReset it here within {RESET_MINUTES} minutes:\n{link}\n\n"
                        "If this wasn't you, ignore this email — your password stays the same.")
            audit(db, user.id, "auth.reset_requested")
            db.commit()
        except Exception:  # noqa: BLE001 — never reveal delivery details to the caller
            db.rollback()
    return {"sent": True, "email_configured": True,
            "message": "If that email has a VITTRM account, a reset link is on its way. It works for 30 minutes."}


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password-reset/confirm")
def reset_confirm(body: ResetConfirmIn, db: Session = Depends(get_db)):
    r = db.get(PasswordReset, token_id(body.token))
    now = datetime.now(timezone.utc)
    expires = r.expires_at.replace(tzinfo=timezone.utc) if r and r.expires_at.tzinfo is None else (r.expires_at if r else None)
    if not r or r.used_at is not None or expires < now:
        raise DomainError("RESET_LINK_INVALID", "This reset link has expired or was already used. Ask for a new one.", status_code=400)
    user = db.get(User, r.user_id)
    user.password_hash = hash_password(body.new_password)
    r.used_at = now
    ended = db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    audit(db, user.id, "auth.password_reset", sessions_ended=ended)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(user, db)
