"""Onboarding (S02), consents, bank accounts."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import AuditEvent, BankAccount, Consent, User
from app.routers.auth import user_out
from app.security import decrypt_str, encrypt_str, mask_phone, normalize_indian_phone, phone_lookup_hash
from app.services import profile_engine

router = APIRouter(tags=["onboarding"])

PURPOSES = {
    "financial_documents": "Process my bank statements and financial documents to build my financial profile",
    "ai_processing": "Let Vitt Saathi use my approved profile to answer questions",
    "whatsapp_reminders": "Send reminders and support messages on WhatsApp",
    "consultation_calls": "Call me for insurance consultations I request",
}


class AboutIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    dob: date | None = None
    city: str | None = Field(default=None, max_length=80)
    employment_type: Literal["salaried", "other"] | None = None
    employer: str | None = Field(default=None, max_length=120)
    designation: str | None = Field(default=None, max_length=120)
    salary_manual: float | None = Field(default=None, ge=0, le=100_000_000)
    preferred_language: Literal["en", "hi", "hinglish"] | None = None
    phone: str | None = None

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        if v is None:
            return v
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18 or age > 100:
            raise ValueError("You need to be at least 18 to use VITTRM")
        return v


@router.patch("/onboarding/about")
def update_about(body: AboutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    phone = data.pop("phone", None)
    if "phone" in body.model_fields_set:
        if phone:
            e164 = normalize_indian_phone(phone)
            if not e164:
                raise DomainError("INVALID_PHONE", "Enter a 10-digit Indian mobile number.", field="phone")
            lookup = phone_lookup_hash(e164)
            owner = db.query(User).filter(User.phone_lookup == lookup, User.id != user.id).first()
            if owner:
                raise DomainError("PHONE_ALREADY_LINKED", "This mobile number is already linked to an account.", field="phone", status_code=409)
            if user.phone_lookup != lookup:
                user.phone_verified_at = None
                from app.models import Reminder
                for reminder in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.channel == "whatsapp",
                                                          Reminder.status == "scheduled"):
                    reminder.channel = "in_app"
            user.phone_enc = encrypt_str(e164)
            user.phone_masked = mask_phone(e164)
            user.phone_lookup = lookup
        else:
            user.phone_enc = user.phone_masked = user.phone_lookup = None
            user.phone_verified_at = None
            from app.models import Reminder
            for reminder in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.channel == "whatsapp",
                                                      Reminder.status == "scheduled"):
                reminder.channel = "in_app"
    for k, v in data.items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    if user.onboarding_step == "about":
        user.onboarding_step = "family"
    profile_engine.build_profile(db, user)
    audit(db, user.id, "profile.about_updated", fields=sorted(data))
    db.commit()
    return user_out(user, db)


class VerifyCodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{4,10}$")


@router.post("/onboarding/phone/verification")
def start_phone_verification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.channels import phone_verify

    if not user.phone_enc:
        raise DomainError("PHONE_REQUIRED", "Add a mobile number before verifying it.", field="phone")
    if db.query(User).filter(User.phone_lookup == user.phone_lookup).count() != 1:
        raise DomainError("PHONE_ALREADY_LINKED", "This number is linked to another account. Change it before verifying.", status_code=409)
    if user.phone_verified_at:
        return {"status": "verified", "phone_masked": user.phone_masked}
    recent = (db.query(AuditEvent).filter(AuditEvent.user_id == user.id,
                                          AuditEvent.action == "phone.verification_started",
                                          AuditEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))
              .order_by(AuditEvent.created_at.desc()).all())
    if len(recent) >= 3 or (recent and recent[0].created_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) - timedelta(seconds=60)):
        raise DomainError("VERIFY_RATE_LIMITED", "Wait before requesting another code.", status_code=429)
    try:
        started = phone_verify.start(decrypt_str(user.phone_enc))
    except phone_verify.VerifyUnavailable as exc:
        raise DomainError("VERIFY_UNAVAILABLE", str(exc), status_code=503) from exc
    if not started:
        raise DomainError("VERIFY_UNAVAILABLE", "A verification code could not be sent. Please retry later.", status_code=503)
    audit(db, user.id, "phone.verification_started")
    db.commit()
    return {"status": "pending", "phone_masked": user.phone_masked}


@router.post("/onboarding/phone/verification/check")
def check_phone_verification(body: VerifyCodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.channels import phone_verify

    if not user.phone_enc:
        raise DomainError("PHONE_REQUIRED", "Add a mobile number before verifying it.", field="phone")
    if db.query(User).filter(User.phone_lookup == user.phone_lookup).count() != 1:
        raise DomainError("PHONE_ALREADY_LINKED", "This number is linked to another account. Change it before verifying.", status_code=409)
    recent_checks = db.query(AuditEvent).filter(AuditEvent.user_id == user.id,
                                                 AuditEvent.action == "phone.verification_checked",
                                                 AuditEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)).count()
    if recent_checks >= 10:
        raise DomainError("VERIFY_RATE_LIMITED", "Too many attempts. Try again later.", status_code=429)
    try:
        valid = phone_verify.check(decrypt_str(user.phone_enc), body.code)
    except phone_verify.VerifyUnavailable as exc:
        raise DomainError("VERIFY_UNAVAILABLE", str(exc), status_code=503) from exc
    audit(db, user.id, "phone.verification_checked", approved=valid)
    if not valid:
        db.commit()
        raise DomainError("INVALID_CODE", "That code was not approved. Check it and try again.", field="code", status_code=400)
    user.phone_verified_at = datetime.now(timezone.utc)
    audit(db, user.id, "phone.verified")
    db.commit()
    return {"status": "verified", "phone_masked": user.phone_masked}


class StepIn(BaseModel):
    step: Literal["about", "family", "statement", "processing", "review", "done"]


@router.post("/onboarding/step")
def set_step(body: StepIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.onboarding_step = body.step
    db.commit()
    return user_out(user, db)


@router.get("/consents")
def list_consents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Consent).filter(Consent.user_id == user.id).order_by(Consent.granted_at.desc()).all()
    active = {c.purpose: c for c in rows if c.revoked_at is None}
    return {
        "purposes": [
            {"purpose": p, "description": d, "granted": p in active,
             "granted_at": active[p].granted_at.isoformat() if p in active else None}
            for p, d in PURPOSES.items()
        ]
    }


class ConsentIn(BaseModel):
    purpose: str


@router.post("/consents")
def grant(body: ConsentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.purpose not in PURPOSES:
        raise DomainError("UNKNOWN_PURPOSE", "Unknown consent purpose.", field="purpose")
    if body.purpose in ("whatsapp_reminders", "consultation_calls") and not user.phone_enc:
        raise DomainError("PHONE_REQUIRED", "Add your mobile number first.", field="phone")
    existing = db.query(Consent).filter(Consent.user_id == user.id, Consent.purpose == body.purpose, Consent.revoked_at.is_(None)).first()
    if not existing:
        db.add(Consent(user_id=user.id, purpose=body.purpose))
        audit(db, user.id, "consent.granted", "consent", body.purpose)
    db.commit()
    return list_consents(user, db)


@router.delete("/consents/{purpose}")
def revoke(purpose: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    for c in db.query(Consent).filter(Consent.user_id == user.id, Consent.purpose == purpose, Consent.revoked_at.is_(None)):
        c.revoked_at = now
    if purpose == "whatsapp_reminders":
        from app.models import Reminder, ReminderPreference
        pref = db.get(ReminderPreference, user.id)
        if pref:
            pref.whatsapp_enabled = False
        for reminder in db.query(Reminder).filter(Reminder.user_id == user.id, Reminder.channel == "whatsapp",
                                                  Reminder.status == "scheduled"):
            reminder.channel = "in_app"
    audit(db, user.id, "consent.revoked", "consent", purpose)
    db.commit()
    return list_consents(user, db)


class AccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    bank_name: str | None = Field(default=None, max_length=80)
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_primary: bool = False


def account_out(a: BankAccount) -> dict:
    return {"id": a.id, "label": a.label, "bank_name": a.bank_name, "masked_ref": a.masked_account_ref, "is_primary": a.is_primary}


@router.get("/accounts")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [account_out(a) for a in db.query(BankAccount).filter(BankAccount.user_id == user.id, BankAccount.active.is_(True))]


def create_account(db: Session, user: User, body: AccountIn) -> BankAccount:
    first = db.query(BankAccount).filter(BankAccount.user_id == user.id).count() == 0
    a = BankAccount(user_id=user.id, label=body.label.strip(), bank_name=body.bank_name,
                    masked_account_ref=f"••••{body.last4}" if body.last4 else None, is_primary=body.is_primary or first)
    if a.is_primary:
        for other in db.query(BankAccount).filter(BankAccount.user_id == user.id):
            other.is_primary = False
    db.add(a)
    db.flush()
    return a


@router.post("/accounts")
def add_account(body: AccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = create_account(db, user, body)
    db.commit()
    return account_out(a)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.query(BankAccount).filter(BankAccount.id == account_id, BankAccount.user_id == user.id).first()
    if not a:
        raise NotFound("Account")
    from app.models import Document
    from app.routers.documents import delete_document_cascade
    for d in db.query(Document).filter(Document.bank_account_id == a.id).all():
        delete_document_cascade(db, d)
    db.delete(a)
    profile_engine.rebuild_recurring(db, user.id)
    profile_engine.build_profile(db, user)
    db.commit()
    return {"ok": True}
