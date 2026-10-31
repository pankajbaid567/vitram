"""Document processing pipeline: Ingest → Parse → Normalize → Validate → Persist → Serve (RD Fig. 1).

Runs as a background task with its own DB session. Stage and status are
persisted so the UI can show progress (S05) and retry on failure.
Raw document text is never logged.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Document,
    DocumentChunk,
    DocumentFact,
    Emi,
    FamilyMember,
    Notification,
    PolicyMember,
    User,
    UserLoan,
    UserPolicy,
)
from app.services import profile_engine, storage
from app.services.extractors.common import Extraction
from app.services.extractors.card import extract_card
from app.services.extractors.insurance import extract_policy
from app.services.extractors.loan import extract_loan
from app.services.extractors.receipt import extract_receipt
from app.services.pdf_text import PdfError, extract_pages
from app.services.statements.parser import StatementParseError, parse_statement, parse_text_pages
from app.services.vision import IMAGE_MIMES, VisionError, provider_status, read_document

# Values read by OCR start below the auto-trust threshold so they always wait for the user's check.
OCR_CONFIDENCE_FACTOR = 0.8

log = logging.getLogger("vitram.pipeline")


def _stage(db: Session, doc: Document, stage: str, status: str = "processing") -> None:
    doc.processing_stage = stage
    doc.processing_status = status
    db.commit()


def _fail(db: Session, doc: Document, code: str, message: str) -> None:
    doc.processing_status = "failed"
    doc.error_code = code
    doc.error_message = message
    db.add(Notification(user_id=doc.owner_user_id, kind="document_failed", title=f"Couldn't process {doc.display_name}",
                        body=message, link=f"/documents?focus={doc.id}", dedupe_key=f"docfail:{doc.id}"))
    db.commit()


def process_document(document_id: str) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.error_code = doc.error_message = None
        _stage(db, doc, "reading")
        data = storage.get(doc.file_key)
        if doc.type == "bank_statement":
            _process_statement(db, doc, data)
        elif doc.type in ("insurance_policy", "loan_document", "card_document", "receipt"):
            _process_pdf_document(db, doc, data)
        else:
            _fail(db, doc, "UNSUPPORTED_TYPE", "This document type isn't supported yet.")
    except Exception:  # noqa: BLE001 — never leak content; record a generic failure
        log.exception("document processing failed for %s", document_id)
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            _fail(db, doc, "PROCESSING_ERROR", "Something went wrong while reading this document. Try again.")
    finally:
        db.close()


def _read_pages(db: Session, doc: Document, data: bytes) -> tuple[list[str], float | None] | None:
    """Page texts for a PDF or image. Digital PDFs are read directly; scans and photos go through OCR.
    Returns (pages, ocr_confidence or None) or None after recording a failure on the document."""
    if doc.mime == "application/pdf":
        try:
            pages = extract_pages(data)
            doc.extraction_method = "pdf_text"
            return pages, None
        except PdfError as exc:
            if exc.code != "NO_TEXT_LAYER":
                _fail(db, doc, exc.code, exc.message)
                return None
    elif doc.mime not in IMAGE_MIMES:
        _fail(db, doc, "UNSUPPORTED_FORMAT", "This file type isn't supported.")
        return None
    _stage(db, doc, "reading_scan")
    try:
        result = read_document(data, doc.mime)
    except VisionError as exc:
        _fail(db, doc, exc.code, exc.message)
        return None
    count = max((p.page for p in result.pages), default=0)
    pages = [""] * count
    for p in result.pages:
        pages[p.page - 1] = p.text
    doc.extraction_method = f"ocr_{result.provider}"
    status = provider_status()
    doc.meta = {**(doc.meta or {}), "ocr": {"provider": result.provider, "on_device": status["on_device"], "mean_confidence": result.mean_confidence}}
    db.commit()
    return pages, result.mean_confidence


def _process_statement(db: Session, doc: Document, data: bytes) -> None:
    scan_note = None
    try:
        if doc.mime == "text/csv":
            parsed = parse_statement(data, doc.mime)
        else:
            read = _read_pages(db, doc, data)
            if read is None:
                return
            pages, ocr_conf = read
            if ocr_conf is None:
                parsed = parse_text_pages(pages, method="pdf_text")
            else:
                parsed = parse_text_pages(pages, method=doc.extraction_method, base_confidence=round(0.6 * ocr_conf, 3))
                scan_note = "This statement was read from a scan or photo. Check the amounts and dates before relying on them."
    except StatementParseError as exc:
        _fail(db, doc, exc.code, exc.message)
        return
    _stage(db, doc, "categorising")
    start, end = parsed.period
    doc.period_start, doc.period_end = start, end
    doc.page_count = parsed.page_count
    doc.extraction_method = parsed.method
    result = profile_engine.ingest_statement(db, doc, parsed)
    warnings = list(parsed.warnings) + ([scan_note] if scan_note else [])
    if result["skipped_overlap"]:
        warnings.append(
            f"{result['skipped_overlap']} transactions were already in VITTRM from an overlapping statement and weren't added again."
        )
    if doc.period_months and start and end:
        covered = ((end - start).days + 1) / 30.44
        if covered < doc.period_months * 0.8:
            warnings.append(
                f"You chose a {doc.period_months}-month statement, but it covers about {covered:.1f} months."
            )
    doc.meta = {**(doc.meta or {}), "transactions_found": len(parsed.rows), "inserted": result["inserted"], "warnings": warnings}
    db.commit()
    _stage(db, doc, "building_profile")
    profile_engine.rebuild_recurring(db, doc.owner_user_id)
    user = db.get(User, doc.owner_user_id)
    profile = profile_engine.build_profile(db, user)
    needs = profile["review_state"]["items_needing_review"]
    doc.processing_status = "needs_review" if needs or warnings else "ready"
    doc.processing_stage = "done"
    db.add(Notification(
        user_id=doc.owner_user_id, kind="document_processed", title="Bank statement processed",
        body=f"{len(parsed.rows)} transactions read." + (f" {needs} items need your review." if needs else ""),
        link="/profile/review", dedupe_key=f"docdone:{doc.id}",
    ))
    if user.onboarding_step in ("statement", "processing"):
        user.onboarding_step = "review"
    db.commit()


def _save_extraction(db: Session, doc: Document, ex: Extraction) -> None:
    db.query(DocumentFact).filter(DocumentFact.document_id == doc.id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
    for f in ex.facts:
        db.add(DocumentFact(
            document_id=doc.id, user_id=doc.owner_user_id, fact_type=f.fact_type, key=f.key, label=f.label,
            value=f.value, unit=f.unit, page=f.page, section=f.section, snippet=f.snippet,
            confidence=f.confidence, state="extracted",
        ))
    for c in ex.chunks:
        db.add(DocumentChunk(document_id=doc.id, user_id=doc.owner_user_id, page=c["page"], section=c["section"], text=c["text"]))
    db.flush()


def _process_pdf_document(db: Session, doc: Document, data: bytes) -> None:
    read = _read_pages(db, doc, data)
    if read is None:
        return
    pages, ocr_conf = read
    doc.page_count = len(pages)
    _stage(db, doc, "extracting")
    if doc.type == "receipt":
        ex = extract_receipt(pages, ocr_conf)
    elif doc.type == "card_document":
        ex = extract_card(pages)
        if ocr_conf is not None:
            for f in ex.facts:
                f.confidence = round(f.confidence * OCR_CONFIDENCE_FACTOR * ocr_conf, 3)
    else:
        ex = extract_policy(pages) if doc.type == "insurance_policy" else extract_loan(pages)
        if ocr_conf is not None:
            for f in ex.facts:
                f.confidence = round(f.confidence * OCR_CONFIDENCE_FACTOR * ocr_conf, 3)
    if ocr_conf is not None:
        ex.warnings.insert(0, "Read from a scan or photo — check each value against the document before relying on it.")
    if doc.extraction_method == "pdf_text":
        doc.extraction_method = "heuristic_text"
    _save_extraction(db, doc, ex)
    doc.meta = {**(doc.meta or {}), "warnings": ex.warnings, "facts_found": len(ex.facts)}
    if doc.type == "receipt":
        _finish_receipt(db, doc, ex)
        return
    _stage(db, doc, "linking")
    if doc.type == "insurance_policy":
        _link_policy(db, doc, ex)
    elif doc.type == "loan_document":
        _link_loan(db, doc, ex)
    user = db.get(User, doc.owner_user_id)
    profile_engine.build_profile(db, user)
    doc.processing_status = "needs_review"
    doc.processing_stage = "done"
    kind = {"insurance_policy": "Policy", "loan_document": "Loan document", "card_document": "Card document"}[doc.type]
    link = (f"/insurance/policies/{doc.meta.get('policy_id')}" if doc.type == "insurance_policy" else
            f"/loans/documents/{doc.id}" if doc.type == "loan_document" else f"/documents?focus={doc.id}")
    db.add(Notification(user_id=doc.owner_user_id, kind="document_processed", title=f"{kind} analysed",
                        body="Review the summary and correct anything that looks wrong.", link=link,
                        dedupe_key=f"docdone:{doc.id}"))
    db.commit()


def _link_policy(db: Session, doc: Document, ex: Extraction) -> None:
    policy = db.query(UserPolicy).filter(UserPolicy.document_id == doc.id).first()
    if policy is None:
        policy = UserPolicy(user_id=doc.owner_user_id, document_id=doc.id)
        db.add(policy)
    policy.insurer = ex.value("insurer")
    policy.product_name = ex.value("product_name")
    policy.type = ex.value("policy_type", "other")
    policy.policy_ref_masked = ex.value("policy_number")
    s, e = ex.value("start_date"), ex.value("end_date")
    policy.start_date = date.fromisoformat(s) if s else None
    policy.end_date = date.fromisoformat(e) if e else None
    freq = (ex.value("premium_frequency") or "annual").lower().replace("yearly", "annual")
    policy.premium = {"amount": ex.value("premium"), "frequency": freq} if ex.value("premium") else None
    policy.coverage = {
        "sum_insured": ex.value("sum_insured"),
        "copay_pct": ex.value("copay"),
        "deductible": ex.value("deductible"),
        "room_rent_limit": ex.value("room_rent_limit"),
    }
    policy.status = "needs_review"
    db.flush()
    doc.meta = {**(doc.meta or {}), "policy_id": policy.id}

    # Covered members: pre-selected at upload wins; otherwise map extracted names to family by relation.
    if not policy.members:
        preselected = (doc.meta or {}).get("member_ids") or []
        family = db.query(FamilyMember).filter(FamilyMember.user_id == doc.owner_user_id).all()
        if preselected:
            for mid in preselected:
                policy.members.append(PolicyMember(family_member_id=None if mid == "self" else mid))
            policy.members_confirmed = True
        else:
            for m in ex.value("insured_members", []) or []:
                rel = m.get("relation")
                if rel == "self":
                    policy.members.append(PolicyMember(family_member_id=None))
                    continue
                match = next((f for f in family if f.relation == _norm_relation(rel) or f.name.lower() == m["name"].lower()), None)
                if match:
                    policy.members.append(PolicyMember(family_member_id=match.id))
            policy.members_confirmed = False

    _detect_policy_conflicts(db, doc, policy)


def _norm_relation(rel: str | None) -> str | None:
    return {"wife": "spouse", "husband": "spouse", "son": "child", "daughter": "child"}.get(rel or "", rel)


def _detect_policy_conflicts(db: Session, doc: Document, policy: UserPolicy) -> None:
    """Same policy uploaded twice with different values → both kept, facts marked conflicted (RD §26)."""
    if not policy.policy_ref_masked:
        return
    others = (
        db.query(UserPolicy)
        .filter(UserPolicy.user_id == policy.user_id, UserPolicy.id != policy.id,
                UserPolicy.policy_ref_masked == policy.policy_ref_masked, UserPolicy.insurer == policy.insurer)
        .all()
    )
    for other in others:
        for key in ("sum_insured", "premium", "end_date", "copay"):
            mine = db.query(DocumentFact).filter(DocumentFact.document_id == doc.id, DocumentFact.key == key).first()
            theirs = db.query(DocumentFact).filter(DocumentFact.document_id == other.document_id, DocumentFact.key == key).first()
            if mine and theirs and mine.value != theirs.value:
                mine.state = theirs.state = "conflicted"
    db.flush()


def _first_due(ex: Extraction) -> date | None:
    v = ex.value("first_due_date")
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _link_loan(db: Session, doc: Document, ex: Extraction) -> None:
    terms = ex.value("_terms", {}) or {}
    loan = db.query(UserLoan).filter(UserLoan.source_document_id == doc.id).first()
    if loan is None:
        loan = UserLoan(user_id=doc.owner_user_id, source_document_id=doc.id)
        db.add(loan)
    loan.lender = terms.get("lender")
    loan.product_name = terms.get("product_name")
    loan.principal = terms.get("principal")
    loan.rate = terms.get("annual_rate_pct")
    loan.tenure_months = terms.get("tenure_months")
    loan.current_emi = terms.get("stated_emi")
    loan.due_day = terms.get("due_day")
    loan.terms = terms
    loan.status = "documented"
    db.flush()
    doc.meta = {**(doc.meta or {}), "user_loan_id": loan.id}
    # Import as an unconfirmed EMI record when enough is known (RD §14.1 "import from uploaded loan documents").
    if loan.current_emi and loan.due_day:
        emi = db.query(Emi).filter(Emi.source_document_id == doc.id).first()
        if emi is None:
            late = next((c.get("rule") for c in terms.get("contingent", []) if c["key"] == "late_payment"), None)
            db.add(Emi(
                user_id=doc.owner_user_id, user_loan_id=loan.id, title=loan.product_name or "Loan EMI",
                emi_type="loan", lender=loan.lender, principal=loan.principal, amount=loan.current_emi,
                due_day=loan.due_day, remaining_count=loan.tenure_months, rate=loan.rate,
                rate_type=terms.get("rate_type"), late_rule=late,
                first_due_date=_first_due(ex), prepayment_rule=terms.get("prepayment_rule"),
                source_type="document", source_ref=doc.display_name, source_document_id=doc.id, confirmed=False,
            ))
    db.flush()


def _finish_receipt(db: Session, doc: Document, ex) -> None:
    """Receipts only hold extracted values until the user checks them; nothing is booked as a transaction."""
    doc.meta = {**(doc.meta or {}), "receipt": {"merchant": ex.value("merchant"), "total": ex.value("total"),
                                                  "purchase_date": ex.value("purchase_date")}}
    doc.processing_status = "needs_review"
    doc.processing_stage = "done"
    db.add(Notification(user_id=doc.owner_user_id, kind="document_processed", title="Receipt read",
                        body="Check the merchant, date and total, then match it to a bank transaction if you like.",
                        link=f"/documents/receipts/{doc.id}", dedupe_key=f"docdone:{doc.id}"))
    db.commit()
