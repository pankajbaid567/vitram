"""Common dashboard (RD §8.2, S07)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.models import Document, Emi, Notification, User, UserCard, UserLoan, UserPolicy
from app.services import obligations, profile_engine

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    p = profile_engine.get_profile(db, user)
    cf = p.get("cashflow_metrics", {})
    docs = db.query(Document).filter(Document.owner_user_id == user.id).all()
    statements = [d for d in docs if d.type == "bank_statement"]
    processing = [d for d in docs if d.processing_status in ("queued", "processing")]
    failed = [d for d in docs if d.processing_status == "failed"]

    emis = db.query(Emi).filter(Emi.user_id == user.id).all()
    cards = db.query(UserCard).filter(UserCard.user_id == user.id).all()
    policies = db.query(UserPolicy).filter(UserPolicy.user_id == user.id, UserPolicy.status != "failed").all()
    loans = db.query(UserLoan).filter(UserLoan.user_id == user.id).all()
    today = date.today()

    covered = set()
    for pol in policies:
        for m in pol.members:
            covered.add(m.family_member_id or "self")
    renewals = [pol for pol in policies if pol.end_date and today <= pol.end_date <= today + timedelta(days=60)]

    reward_balances = []
    for c in cards:
        if c.points and c.points.get("balance") is not None:
            unit = (c.catalogue.data.get("rules", {}).get("currency_name") if c.catalogue else None) or "points"
            reward_balances.append({"card": c.nickname, "balance": c.points["balance"], "unit": unit, "as_of": c.points.get("as_of")})
    next_card_due = min((c.due_date for c in cards if c.due_date and c.due_date >= today), default=None)

    upcoming = obligations.upcoming(db, user.id, 30)
    review = p.get("review_state", {})
    attention = []
    if not statements:
        attention.append({"kind": "upload_statement", "title": "Upload a bank statement", "body": "VITTRM builds your financial profile from it.", "link": "/onboarding/statement"})
    if review.get("items_needing_review"):
        attention.append({"kind": "review", "title": f"{review['items_needing_review']} items need your review",
                          "body": "Confirm salary, EMIs and other recurring payments so recommendations use the right numbers.", "link": "/profile/review"})
    unconfirmed_emis = [e for e in emis if not e.confirmed]
    if unconfirmed_emis:
        attention.append({"kind": "confirm_emi", "title": f"{len(unconfirmed_emis)} detected EMI{'s' if len(unconfirmed_emis) > 1 else ''} to confirm",
                          "body": "Confirm them to add them to your calendar and reminders.", "link": "/emis"})
    policies_review = [pol for pol in policies if pol.status == "needs_review"]
    if policies_review:
        attention.append({"kind": "policy_review", "title": f"Review {len(policies_review)} policy summar{'ies' if len(policies_review) > 1 else 'y'}",
                          "body": "Check the extracted coverage and who is covered.", "link": f"/insurance/policies/{policies_review[0].id}"})
    for d in failed[:2]:
        attention.append({"kind": "failed", "title": f"Couldn't process {d.display_name}", "body": d.error_message, "link": "/documents"})

    top_categories = [c for c in p.get("expense_summary", {}).get("category_totals", [])][:6]
    return {
        "currency": "INR",
        "user": {"name": user.name, "is_sample": user.is_sample, "onboarding_step": user.onboarding_step},
        "assistant": {"chat_mode": "gemini" if settings.gemini_configured else "tool", "voice_available": settings.gemini_live_configured},
        "money": {
            "monthly_income": p.get("income_summary", {}).get("monthly_estimate"),
            "avg_monthly_outflow": cf.get("avg_monthly_outflow"),
            "fixed_monthly": cf.get("fixed_monthly"),
            "monthly_surplus": cf.get("monthly_surplus"),
            "months_covered": cf.get("months_covered"),
            "period_start": cf.get("period_start"), "period_end": cf.get("period_end"),
            "top_categories": top_categories,
            "monthly_series": cf.get("monthly_series", []),
        },
        "journeys": {
            "loans": {"documents": len([d for d in docs if d.type == "loan_document"]), "tracked_loans": len(loans)},
            "insurance": {"active_policies": len(policies), "covered_people": len(covered),
                          "upcoming_renewals": [{"id": r.id, "name": r.product_name, "date": r.end_date.isoformat()} for r in renewals]},
            "cards": {"count": len(cards), "next_due": next_card_due.isoformat() if next_card_due else None, "reward_balances": reward_balances},
            "emis": {"count": len(emis), "confirmed": len([e for e in emis if e.confirmed]),
                     "monthly_total": round(sum(e.amount for e in emis), 2),
                     "monthly_total_confirmed": round(sum(e.amount for e in emis if e.confirmed), 2)},
        },
        "upcoming": upcoming[:8],
        "data_quality": {
            "statements_processed": len([d for d in statements if d.processing_status in ("ready", "needs_review")]),
            "documents_processing": len(processing), "documents_failed": len(failed),
            "items_needing_review": review.get("items_needing_review", 0),
        },
        "attention": attention,
        "unread_notifications": db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).count(),
    }
