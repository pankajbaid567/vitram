"""Labelled sample workspace for the capability demo (RD §30).

Creates a separate, clearly marked sample account and runs the fixture
documents through the *real* pipeline — nothing is hard-coded into the UI.
"""

import hashlib
import secrets
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import BACKEND_DIR
from app.db import get_db
from app.models import BankAccount, Consent, Document, FamilyMember, User, UserCard
from app.routers.auth import start_session, user_out
from app.security import hash_password
from app.services import pipeline, profile_engine, storage
from app.services.channels import scheduler

router = APIRouter(prefix="/demo", tags=["demo"])
FIXTURES = BACKEND_DIR / "fixtures"


def _upload(db: Session, user: User, path: Path, doc_type: str, mime: str, **kw) -> Document:
    data = path.read_bytes()
    d = Document(owner_user_id=user.id, type=doc_type, display_name=path.name, mime=mime, size_bytes=len(data),
                 file_key=storage.put_sample(data), checksum=hashlib.sha256(data).hexdigest(), **kw)
    db.add(d)
    db.commit()
    pipeline.process_document(d.id)
    db.refresh(d)
    return d


@router.post("/workspace")
def create_workspace(request: Request, response: Response, db: Session = Depends(get_db)):
    user = User(email=f"sample-{secrets.token_hex(4)}@sample.vitram.local", name="Sample User",
                password_hash=hash_password(secrets.token_urlsafe(24)), is_sample=True,
                dob=date(1994, 2, 11), city="Mumbai", employment_type="salaried", employer="Acme Technologies (sample)",
                designation="Senior Engineer", onboarding_step="done", preferred_language="en")
    db.add(user)
    db.flush()
    for purpose in ("terms", "financial_documents", "ai_processing"):
        db.add(Consent(user_id=user.id, purpose=purpose))
    spouse = FamilyMember(user_id=user.id, name="Asha Sample", relation="spouse", dob=date(1996, 6, 2))
    mother = FamilyMember(user_id=user.id, name="Kamala Sample", relation="mother", dob=date(1965, 1, 20), is_dependant=True)
    db.add_all([spouse, mother])
    acct = BankAccount(user_id=user.id, label="Salary account", bank_name="Aravali Bank (sample)", masked_account_ref="••••7730", is_primary=True)
    db.add(acct)
    db.commit()

    _upload(db, user, FIXTURES / "sample_statement_6m.csv", "bank_statement", "text/csv", bank_account_id=acct.id, period_months=6)
    _upload(db, user, FIXTURES / "sample_policy_family_health.pdf", "insurance_policy", "application/pdf", meta={"member_ids": ["self", spouse.id]})
    _upload(db, user, FIXTURES / "sample_policy_senior_care.pdf", "insurance_policy", "application/pdf", meta={"member_ids": [mother.id]},
            family_member_id=mother.id)
    _upload(db, user, FIXTURES / "sample_policy_term_life.pdf", "insurance_policy", "application/pdf", meta={"member_ids": ["self"]})
    _upload(db, user, FIXTURES / "sample_loan_kfs.pdf", "loan_document", "application/pdf")

    today = date.today()
    cards = [
        UserCard(user_id=user.id, catalogue_id="horizon-voyager", nickname="Horizon Voyager", last4="4821", credit_limit=300000,
                 outstanding=24650, due_date=today + timedelta(days=9),
                 points={"balance": 18400, "as_of": today.isoformat(), "expiring": [{"amount": 2500, "date": (today + timedelta(days=75)).isoformat()}], "source": "sample"},
                 cycle_spend={"travel": 8000}),
        UserCard(user_id=user.id, catalogue_id="deccan-everyday-cashback", nickname="Deccan Cashback", last4="1937", credit_limit=120000,
                 outstanding=6320, due_date=today + timedelta(days=16), points={"balance": 740, "as_of": today.isoformat(), "expiring": [], "source": "sample"},
                 cycle_spend={"food_delivery": 3200}),
        UserCard(user_id=user.id, catalogue_id="coastal-shopper-points", nickname="Coastal Shopper", last4="5502", credit_limit=150000,
                 outstanding=3890, due_date=today + timedelta(days=21), points={"balance": 9200, "as_of": today.isoformat(), "expiring": [], "source": "sample"}),
    ]
    db.add_all(cards)
    db.flush()
    profile_engine.build_profile(db, user)
    scheduler.schedule_for_user(db, user)
    start_session(db, response, user, request)
    audit(db, user.id, "demo.workspace_created")
    db.commit()
    return {**user_out(user, db), "sample_note": "Sample workspace: every document is a generated sample with fictional institutions."}


@router.get("/fixtures")
def list_fixtures():
    """Downloadable sample files so the upload flow itself can be demonstrated."""
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(FIXTURES.glob("sample_*"))]


@router.get("/fixtures/{name}")
def get_fixture(name: str):
    path = FIXTURES / name
    if not name.startswith("sample_") or "/" in name or not path.exists():
        from app.errors import NotFound
        raise NotFound("Sample file")
    mime = "application/pdf" if name.endswith(".pdf") else "text/csv"
    return Response(path.read_bytes(), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})

