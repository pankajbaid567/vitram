"""Documents & Data (RD §9–10, §20, S04/S05/S41/S50)."""

import hashlib
import json
import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_db
from app.deps import current_user, require_consent
from app.errors import DomainError, NotFound
from app.models import (
    BankAccount,
    Document,
    DocumentFact,
    Emi,
    FamilyMember,
    ProfileOverride,
    Transaction,
    User,
    UserLoan,
    UserPolicy,
)
from app.routers.onboarding import AccountIn, create_account
from app.services import pipeline, profile_engine, receipts, retrieval, storage
from app.services.card_import import clear_linked_values
from app.services.vision import IMAGE_MIMES, VisionError, prepare_image, sniff_image

router = APIRouter(prefix="/documents", tags=["documents"])

DocType = Literal["bank_statement", "insurance_policy", "loan_document", "card_document", "receipt"]
TYPE_LABELS = {"bank_statement": "Bank statement", "insurance_policy": "Insurance policy", "loan_document": "Loan document",
               "card_document": "Card document", "receipt": "Receipt / invoice"}
FILE_EXT = {"application/pdf": "pdf", "text/csv": "csv", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _safe_name(name: str | None, doc_type: str) -> str:
    base = re.sub(r"[^\w .()\-]", "", (name or "").split("/")[-1].split("\\")[-1])[:120]
    return base or TYPE_LABELS[doc_type]


def _sniff(data: bytes, doc_type: str) -> str:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    img = sniff_image(data)
    if img == "image/heic":
        raise DomainError("UNSUPPORTED_FORMAT", "HEIC photos aren't supported yet. Share the photo as JPG (most phones do this automatically when you upload).", field="file")
    if img in IMAGE_MIMES:
        return img
    if doc_type == "bank_statement":
        head = data[:4096]
        if b"\x00" not in head:
            try:
                head.decode("utf-8")
                return "text/csv"
            except UnicodeDecodeError:
                pass
    raise DomainError(
        "UNSUPPORTED_FORMAT",
        "Upload a PDF, a photo (JPG or PNG), or a CSV export for bank statements." if doc_type == "bank_statement"
        else "Upload a PDF or a photo (JPG or PNG).",
        field="file",
    )


def doc_out(d: Document, db: Session | None = None) -> dict:
    meta = d.meta or {}
    out = {
        "id": d.id, "type": d.type, "type_label": TYPE_LABELS.get(d.type, d.type), "display_name": d.display_name,
        "mime": d.mime, "size_bytes": d.size_bytes, "upload_time": d.upload_time.isoformat(),
        "status": d.processing_status, "stage": d.processing_stage, "error_code": d.error_code, "error_message": d.error_message,
        "period_months": d.period_months, "period_start": d.period_start.isoformat() if d.period_start else None,
        "period_end": d.period_end.isoformat() if d.period_end else None, "page_count": d.page_count,
        "extraction_method": d.extraction_method, "bank_account_id": d.bank_account_id, "family_member_id": d.family_member_id,
        "warnings": meta.get("warnings", []), "transactions_found": meta.get("transactions_found"),
        "facts_found": meta.get("facts_found"), "policy_id": meta.get("policy_id"), "user_loan_id": meta.get("user_loan_id"),
        "read_from_scan": (d.extraction_method or "").startswith("ocr"), "ocr": meta.get("ocr"),
        "receipt": meta.get("receipt"), "linked_transaction_id": meta.get("linked_transaction_id"),
    }
    if db is not None and d.bank_account_id:
        a = db.get(BankAccount, d.bank_account_id)
        out["account_label"] = a.label if a else None
    return out


def get_doc(db: Session, user: User, doc_id: str) -> Document:
    d = db.query(Document).filter(Document.id == doc_id, Document.owner_user_id == user.id).first()
    if not d:
        raise NotFound("Document")
    return d


@router.post("")
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    type: DocType = Form(...),
    bank_account_id: str | None = Form(None),
    account_label: str | None = Form(None),
    bank_name: str | None = Form(None),
    account_last4: str | None = Form(None),
    period_months: int | None = Form(None),
    member_ids: str | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_consent(db, user.id, "financial_documents",
                    "Allow VITTRM to process your financial documents before uploading.")
    settings = get_settings()
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DomainError("FILE_TOO_LARGE", f"Files can be up to {settings.max_upload_mb} MB.", field="file", status_code=413)
    if not data:
        raise DomainError("EMPTY_FILE", "This file is empty.", field="file")
    mime = _sniff(data, type)
    if type == "card_document":
        from app.services.extractors.card import _CVV, _PAN
        from app.services.pdf_text import PdfError, extract_pages
        if _PAN.search(file.filename or ""):
            raise DomainError("CARD_CREDENTIAL_FOUND", "Rename this file without its full card number before uploading.", field="file")
        if mime != "application/pdf":
            raise DomainError("UNSUPPORTED_FORMAT", "Upload a digital, redacted card statement PDF.", field="file")
        try:
            pages = extract_pages(data)
        except PdfError as exc:
            raise DomainError(exc.code, "Upload a digital, redacted card statement PDF. Scanned card PDFs are not accepted.", field="file") from exc
        if any(_PAN.search(page) or _CVV.search(page) for page in pages):
            raise DomainError("CARD_CREDENTIAL_FOUND", "Redact the full card number, CVV and PIN before uploading. Only the last four digits are needed.",
                              field="file")
    checksum = hashlib.sha256(data).hexdigest()  # original upload, so duplicates are caught
    dup = db.query(Document).filter(Document.owner_user_id == user.id, Document.checksum == checksum,
                                    Document.processing_status != "failed").first()
    if dup:
        raise DomainError("DUPLICATE_DOCUMENT", f"You've already uploaded this file ({dup.display_name}).",
                          field="file", status_code=409,
                          details={"document_id": dup.id, "type": dup.type, "display_name": dup.display_name,
                                   "status": dup.processing_status, "policy_id": (dup.meta or {}).get("policy_id"),
                                   "read_from_scan": (dup.extraction_method or "").startswith("ocr")})

    meta: dict = {}
    fam_id = None
    if type == "bank_statement":
        if period_months not in (3, 6, 12):
            raise DomainError("INVALID_PERIOD", "Choose a 3, 6 or 12-month statement.", field="period_months")
        if bank_account_id:
            acct = db.query(BankAccount).filter(BankAccount.id == bank_account_id, BankAccount.user_id == user.id).first()
            if not acct:
                raise NotFound("Bank account")
        else:
            if not account_label:
                raise DomainError("ACCOUNT_REQUIRED", "Name this bank account, for example 'Salary account'.", field="account_label")
            acct = create_account(db, user, AccountIn(label=account_label, bank_name=bank_name or None,
                                                      last4=account_last4 or None))
        bank_account_id = acct.id
    elif type == "insurance_policy" and member_ids:
        try:
            ids = json.loads(member_ids)
        except json.JSONDecodeError as exc:
            raise DomainError("INVALID_MEMBERS", "Couldn't read the selected family members.", field="member_ids") from exc
        valid = {m.id for m in db.query(FamilyMember).filter(FamilyMember.user_id == user.id)} | {"self"}
        if not isinstance(ids, list) or any(i not in valid for i in ids):
            raise DomainError("INVALID_MEMBERS", "One of the selected family members wasn't found.", field="member_ids")
        meta["member_ids"] = ids
        fam_id = next((i for i in ids if i != "self"), None)

    if mime in IMAGE_MIMES:
        # rotate by EXIF, downscale and re-encode: drops metadata such as GPS location before anything is stored
        try:
            data, mime = prepare_image(data, mime)
        except VisionError as exc:
            raise DomainError(exc.code, exc.message, field="file") from exc
    key = storage.put(data)
    doc = Document(
        owner_user_id=user.id, type=type, display_name=_safe_name(file.filename, type), mime=mime, size_bytes=len(data),
        file_key=key, checksum=checksum, bank_account_id=bank_account_id, family_member_id=fam_id,
        period_months=period_months if type == "bank_statement" else None, meta=meta,
    )
    db.add(doc)
    if type == "bank_statement" and user.onboarding_step in ("about", "family", "statement"):
        user.onboarding_step = "processing"
    audit(db, user.id, "document.uploaded", "document", doc.id, type=type, size=len(data))
    db.commit()
    background.add_task(pipeline.process_document, doc.id)
    return doc_out(doc, db)


@router.get("")
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.owner_user_id == user.id).order_by(Document.upload_time.desc()).all()
    return [doc_out(d, db) for d in docs]


@router.get("/{doc_id}")
def get_document(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return doc_out(get_doc(db, user, doc_id), db)


def fact_out(f: DocumentFact, d: Document) -> dict:
    return {
        "id": f.id, "fact_type": f.fact_type, "key": f.key, "label": f.label, "value": f.value, "unit": f.unit,
        "state": f.state, "confidence": f.confidence, "user_verified": f.user_verified,
        "citation": {"document_id": d.id, "document_type": d.type, "document_name": d.display_name, "page": f.page,
                     "section": f.section, "snippet": f.snippet, "fact_key": f.key, "confidence": f.confidence,
                     "user_verified": f.user_verified},
    }


@router.get("/{doc_id}/facts")
def get_facts(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    facts = db.query(DocumentFact).filter(DocumentFact.document_id == d.id, DocumentFact.key != "_terms").all()
    audit(db, user.id, "document.facts_viewed", "document", d.id)
    db.commit()
    return {"document": doc_out(d, db), "facts": [fact_out(f, d) for f in facts]}


class FactCorrection(BaseModel):
    value: object | None = None
    confirm_only: bool = False
    reason: str | None = Field(default=None, max_length=200)


@router.patch("/{doc_id}/facts/{fact_id}")
def correct_fact(doc_id: str, fact_id: str, body: FactCorrection, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    f = db.query(DocumentFact).filter(DocumentFact.id == fact_id, DocumentFact.document_id == d.id).first()
    if not f:
        raise NotFound("Fact")
    prior = f.value
    if not body.confirm_only:
        if body.value is None or (isinstance(body.value, str) and not body.value.strip()):
            raise DomainError("VALUE_REQUIRED", "Enter the corrected value.", field="value")
        if isinstance(prior, (int, float)) and not isinstance(prior, bool):
            try:
                f.value = float(str(body.value).replace(",", "").replace("₹", ""))
            except ValueError as exc:
                raise DomainError("INVALID_NUMBER", "Enter a number.", field="value") from exc
        else:
            f.value = body.value
    f.state = "confirmed"
    f.user_verified = True
    db.add(ProfileOverride(user_id=user.id, path=f"fact/{d.id}/{f.key}", prior_value=prior, corrected_value=f.value, reason=body.reason))
    _apply_fact_to_links(db, d, f)
    audit(db, user.id, "fact.corrected" if not body.confirm_only else "fact.confirmed", "document_fact", f.id, key=f.key)
    profile_engine.build_profile(db, user)
    db.commit()
    return fact_out(f, d)


def _apply_fact_to_links(db: Session, d: Document, f: DocumentFact) -> None:
    if d.type == "insurance_policy":
        p = db.query(UserPolicy).filter(UserPolicy.document_id == d.id).first()
        if not p:
            return
        if f.key in ("insurer", "product_name"):
            setattr(p, f.key, f.value)
        elif f.key == "policy_type":
            p.type = f.value
        elif f.key in ("start_date", "end_date"):
            try:
                setattr(p, f.key, date.fromisoformat(str(f.value)))
            except ValueError as exc:
                raise DomainError("INVALID_DATE", "Enter the date as YYYY-MM-DD.", field="value") from exc
        elif f.key == "premium":
            p.premium = {**(p.premium or {}), "amount": f.value}
        elif f.key in ("sum_insured", "deductible", "room_rent_limit"):
            p.coverage = {**(p.coverage or {}), f.key: f.value}
        elif f.key == "copay":
            p.coverage = {**(p.coverage or {}), "copay_pct": f.value}
        remaining = db.query(DocumentFact).filter(DocumentFact.document_id == d.id, DocumentFact.state == "extracted",
                                                  DocumentFact.confidence < 0.6).count()
        if remaining == 0 and p.members_confirmed:
            p.status = "active"
    elif d.type == "receipt":
        if f.key == "purchase_date":
            try:
                f.value = date.fromisoformat(str(f.value)).isoformat()
            except ValueError as exc:
                raise DomainError("INVALID_DATE", "Enter the date as YYYY-MM-DD.", field="value") from exc
        if f.key in ("merchant", "total", "purchase_date"):
            d.meta = {**(d.meta or {}), "receipt": {**((d.meta or {}).get("receipt") or {}), f.key: f.value}}
    elif d.type == "loan_document":
        loan = db.query(UserLoan).filter(UserLoan.source_document_id == d.id).first()
        if not loan:
            return
        mapping = {"principal": "principal", "annual_rate_pct": "rate", "tenure_months": "tenure_months", "stated_emi": "current_emi"}
        if f.key in mapping:
            setattr(loan, mapping[f.key], f.value)
            terms = dict(loan.terms or {})
            terms[f.key] = f.value
            loan.terms = terms
    elif d.type == "card_document" and f.key in ("last4", "outstanding", "due_date", "points_balance"):
        # A correction after an import invalidates that snapshot. The user can
        # re-import the reviewed values once all facts are correct.
        clear_linked_values(db, d.id)


@router.post("/{doc_id}/facts/{fact_id}/reject")
def reject_fact(doc_id: str, fact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The user says this value is wrong or doesn't apply. It stays visible as rejected and is never used."""
    d = get_doc(db, user, doc_id)
    f = db.query(DocumentFact).filter(DocumentFact.id == fact_id, DocumentFact.document_id == d.id).first()
    if not f:
        raise NotFound("Fact")
    f.state = "rejected"
    f.user_verified = True
    db.add(ProfileOverride(user_id=user.id, path=f"fact/{d.id}/{f.key}", prior_value=f.value, corrected_value=None, reason="rejected"))
    if d.type == "receipt" and f.key in ("merchant", "total", "purchase_date"):
        d.meta = {**(d.meta or {}), "receipt": {**((d.meta or {}).get("receipt") or {}), f.key: None}}
    audit(db, user.id, "fact.rejected", "document_fact", f.id, key=f.key)
    profile_engine.build_profile(db, user)
    db.commit()
    return fact_out(f, d)


@router.get("/{doc_id}/receipt")
def receipt_detail(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    if d.type != "receipt":
        raise NotFound("Receipt")
    s = receipts.summary(db, d)
    linked = None
    if s["linked_transaction_id"]:
        t = db.query(Transaction).filter(Transaction.id == s["linked_transaction_id"], Transaction.user_id == user.id).first()
        linked = {"id": t.id, "date": t.txn_date.isoformat(), "amount": t.amount, "description": t.description} if t else None
    return {"document": doc_out(d, db), "receipt": s, "linked_transaction": linked,
            "candidates": [] if linked else receipts.candidates(db, user.id, s["total"], s["purchase_date"], s["merchant"]),
            "note": "Matching is a suggestion: a receipt shows a purchase, not that the payment went through."}


class ReceiptLinkIn(BaseModel):
    transaction_id: str | None = None


@router.post("/{doc_id}/receipt/link")
def receipt_link(doc_id: str, body: ReceiptLinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    if d.type != "receipt":
        raise NotFound("Receipt")
    if body.transaction_id:
        t = db.query(Transaction).filter(Transaction.id == body.transaction_id, Transaction.user_id == user.id).first()
        if not t:
            raise NotFound("Transaction")
    d.meta = {**(d.meta or {}), "linked_transaction_id": body.transaction_id}
    audit(db, user.id, "receipt.linked" if body.transaction_id else "receipt.unlinked", "document", d.id)
    db.commit()
    return receipt_detail(doc_id, user, db)


@router.post("/{doc_id}/reprocess")
def reprocess(doc_id: str, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    if d.type == "card_document":
        clear_linked_values(db, d.id)
        profile_engine.build_profile(db, user)
    d.processing_status, d.processing_stage = "queued", "uploaded"
    audit(db, user.id, "document.reprocess", "document", d.id)
    db.commit()
    background.add_task(pipeline.process_document, d.id)
    return doc_out(d, db)


def delete_document_cascade(db: Session, d: Document) -> None:
    if d.type == "card_document":
        clear_linked_values(db, d.id)
    db.query(Emi).filter(Emi.source_document_id == d.id, Emi.confirmed.is_(False)).delete()
    db.query(UserLoan).filter(UserLoan.source_document_id == d.id).delete()
    for p in db.query(UserPolicy).filter(UserPolicy.document_id == d.id).all():
        db.delete(p)
    storage.delete(d.file_key)
    db.delete(d)
    db.flush()


@router.delete("/{doc_id}")
def delete_document(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    was_statement = d.type == "bank_statement"
    delete_document_cascade(db, d)
    if was_statement:
        profile_engine.rebuild_recurring(db, user.id)
    profile_engine.build_profile(db, user)
    audit(db, user.id, "document.deleted", "document", doc_id)
    db.commit()
    return {"ok": True}


@router.get("/{doc_id}/file")
def download(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    data = storage.get(d.file_key)
    audit(db, user.id, "document.downloaded", "document", d.id)
    db.commit()
    ext = FILE_EXT.get(d.mime, "bin")
    return Response(data, media_type=d.mime, headers={
        "Content-Disposition": f'inline; filename="vitram-{d.type}.{ext}"',
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)


@router.post("/{doc_id}/search")
def search_document(doc_id: str, body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, doc_id)
    return retrieval.search(db, user.id, body.query, document_ids=[d.id])
