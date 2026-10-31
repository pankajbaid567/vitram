"""Insurance consultation calls via Twilio (RD §15.5, §17.2, S46).

The user reviews the exact context summary before consenting. No call is ever
reported as placed unless Twilio accepted it; failures show and can be retried.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.errors import DomainError, NotFound
from app.models import ConsultationRequest, Consent, InsuranceProduct, User, UserPolicy
from app.security import decrypt_str, encrypt_str, mask_phone, normalize_indian_phone
from app.services import slices
from app.services.channels import twilio_voice
from app.fmt import inr

router = APIRouter(prefix="/consultations", tags=["consultations"])

STATUS_TEXT = {
    "requested": "Request saved", "not_configured": "Saved — calling isn't set up here, so no call was placed",
    "calling": "Calling you now", "ringing": "Your phone is ringing", "in_progress": "Call in progress",
    "completed": "Call completed", "failed": "Call failed", "no_answer": "No answer", "cancelled": "Cancelled",
}


def build_summary(db: Session, user: User, topic: str, policy_id: str | None, product_id: str | None, member_key: str | None) -> str:
    """Concise consented context: person, relevant policies, question, products considered. No banking data."""
    lines = [f"Topic: {topic.strip()}"]
    members = {m["key"]: m for m in slices.insurance_members(db, user)}
    if member_key and member_key in members:
        m = members[member_key]
        age = f", age {m['age']}" if m.get("age") is not None else ""
        lines.append(f"For: {m['name']} ({m['relation']}{age})")
    pols = slices.policies_for(db, user)
    relevant = [p for p in pols if (policy_id and p["id"] == policy_id) or (member_key and member_key in p["member_keys"])]
    for p in relevant[:3]:
        si = f", sum insured {inr(p['sum_insured'])}" if p.get("sum_insured") else ""
        lines.append(f"Existing policy: {p['product_name'] or 'Policy'} — {p['insurer'] or 'insurer unknown'}{si}")
    if product_id:
        prod = db.get(InsuranceProduct, product_id)
        if prod:
            lines.append(f"Considering: {prod.product_name} — {prod.insurer} (VITTRM sample catalogue)")
    return "\n".join(lines)


def c_out(c: ConsultationRequest) -> dict:
    return {"id": c.id, "topic": c.topic, "context_summary": c.context_summary, "phone_masked": c.phone_masked,
            "status": c.status, "status_text": STATUS_TEXT.get(c.status, c.status), "error": c.error,
            "twilio_call_sid": c.twilio_call_sid, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
            "policy_id": c.policy_id, "product_id": c.product_id, "family_member_id": c.family_member_id}


class PreviewIn(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    policy_id: str | None = None
    product_id: str | None = None
    member_key: str | None = None


@router.post("/preview")
def preview(body: PreviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.policy_id and not db.query(UserPolicy).filter(UserPolicy.id == body.policy_id, UserPolicy.user_id == user.id).first():
        raise NotFound("Policy")
    s = get_settings()
    return {"context_summary": build_summary(db, user, body.topic, body.policy_id, body.product_id, body.member_key),
            "phone_on_file": user.phone_masked, "calling_configured": s.twilio_configured}


class ConsultIn(PreviewIn):
    phone: str | None = None
    use_phone_on_file: bool = True
    consent: bool


def _place_call(db: Session, c: ConsultationRequest) -> None:
    s = get_settings()
    if not s.twilio_configured:
        c.status, c.error = "not_configured", "Twilio credentials aren't configured in this environment."
        return
    callback = f"{s.public_api_url.rstrip('/')}/api/webhooks/twilio" if s.public_api_url else None
    intro = "Hello, this is VITTRM connecting your insurance consultation. Please hold while we connect you to the consultant."
    try:
        res = twilio_voice.create_call(decrypt_str(c.phone_enc), intro, callback)
        c.twilio_call_sid, c.status, c.error = res["sid"], twilio_voice.TWILIO_TO_STATUS.get(res.get("status") or "queued", "calling"), None
    except twilio_voice.CallError as exc:
        c.status, c.error = "failed", str(exc)[:300]


@router.post("")
def request_call(body: ConsultIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.consent:
        raise DomainError("CONSENT_REQUIRED", "Agree to the call and to sharing this summary with the consultant.", field="consent")
    if body.phone and not body.use_phone_on_file:
        e164 = normalize_indian_phone(body.phone)
        if not e164:
            raise DomainError("INVALID_PHONE", "Enter a 10-digit Indian mobile number.", field="phone")
        phone_enc = encrypt_str(e164)
        masked = mask_phone(e164)
    elif user.phone_enc:
        phone_enc, masked = user.phone_enc, user.phone_masked
    else:
        raise DomainError("PHONE_REQUIRED", "Enter the number we should call.", field="phone")
    if get_settings().twilio_configured:
        if not user.phone_verified_at or decrypt_str(phone_enc) != decrypt_str(user.phone_enc or ""):
            raise DomainError("PHONE_NOT_VERIFIED", "Verify this mobile number in your profile before placing a call.",
                              field="phone", status_code=403)
    now = datetime.now(timezone.utc)
    if not db.query(Consent).filter(Consent.user_id == user.id, Consent.purpose == "consultation_calls", Consent.revoked_at.is_(None)).first():
        db.add(Consent(user_id=user.id, purpose="consultation_calls"))
    c = ConsultationRequest(
        user_id=user.id, topic=body.topic.strip(), policy_id=body.policy_id, product_id=body.product_id,
        family_member_id=None if body.member_key in (None, "self") else body.member_key,
        context_summary=build_summary(db, user, body.topic, body.policy_id, body.product_id, body.member_key),
        phone_enc=phone_enc, phone_masked=masked, consent_at=now, status="requested",
    )
    db.add(c)
    db.flush()
    _place_call(db, c)
    audit(db, user.id, "consultation.requested", "consultation", c.id, status=c.status)
    db.commit()
    return c_out(c)


@router.get("")
def list_requests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(ConsultationRequest).filter(ConsultationRequest.user_id == user.id).order_by(ConsultationRequest.created_at.desc()).all()
    return {"items": [c_out(c) for c in rows], "calling_configured": get_settings().twilio_configured}


def _get(db: Session, user: User, cid: str) -> ConsultationRequest:
    c = db.query(ConsultationRequest).filter(ConsultationRequest.id == cid, ConsultationRequest.user_id == user.id).first()
    if not c:
        raise NotFound("Consultation request")
    return c


@router.get("/{cid}")
def get_request(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return c_out(_get(db, user, cid))


@router.post("/{cid}/retry")
def retry(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get(db, user, cid)
    if c.status in ("calling", "ringing", "in_progress"):
        raise DomainError("IN_PROGRESS", "This call is already in progress.")
    _place_call(db, c)
    audit(db, user.id, "consultation.retry", "consultation", c.id, status=c.status)
    db.commit()
    return c_out(c)


@router.post("/{cid}/cancel")
def cancel(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get(db, user, cid)
    if c.status in ("completed",):
        raise DomainError("ALREADY_DONE", "This call has already finished.")
    c.status = "cancelled"
    db.commit()
    return c_out(c)
