"""Data-subject controls: export everything we hold about a user, and delete the account (RD §23.1).

The export is built from an explicit **allow-list of tables** and a **deny-list of columns**, so a newly
added secret column can never leak into a download by default: it must be added here on purpose.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import rls
from app.audit import audit
from app.models import (
    AuditEvent, BankAccount, CalculationRun, Consent, ConsultationRequest, Conversation, Document, DocumentFact,
    Emi, ExpectedPayment, FamilyMember, FinancialProfile, Goal, GoalContribution, Message, Notification, PolicyMember,
    ProfileOverride, RecurringGroup, Reminder, ReminderPreference, Transaction, User, UserCard, UserLoan, UserPolicy,
)
from app.services import storage

log = logging.getLogger("vitram.privacy")

# (key in the export, model, column that ties a row to the user)
EXPORT_TABLES: tuple[tuple[str, type, str], ...] = (
    ("consents", Consent, "user_id"),
    ("family_members", FamilyMember, "user_id"),
    ("bank_accounts", BankAccount, "user_id"),
    ("documents", Document, "owner_user_id"),
    ("document_facts", DocumentFact, "user_id"),
    ("transactions", Transaction, "user_id"),
    ("recurring_groups", RecurringGroup, "user_id"),
    ("profile_overrides", ProfileOverride, "user_id"),
    ("financial_profile", FinancialProfile, "user_id"),
    ("emis", Emi, "user_id"),
    ("loans", UserLoan, "user_id"),
    ("cards", UserCard, "user_id"),
    ("policies", UserPolicy, "user_id"),
    ("goals", Goal, "user_id"),
    ("goal_contributions", GoalContribution, "user_id"),
    ("expected_payments", ExpectedPayment, "user_id"),
    ("reminder_preferences", ReminderPreference, "user_id"),
    ("reminders", Reminder, "user_id"),
    ("notifications", Notification, "user_id"),
    ("consultation_requests", ConsultationRequest, "user_id"),
    ("calculation_runs", CalculationRun, "user_id"),
    ("audit_events", AuditEvent, "user_id"),
)

# Never exported: credentials, encrypted/hashed identifiers, and storage internals.
DENY_COLUMNS = frozenset({"password_hash", "phone_enc", "phone_lookup", "file_key"})


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _row(obj: Any) -> dict:
    return {c.key: _plain(getattr(obj, c.key)) for c in inspect(type(obj)).mapper.column_attrs if c.key not in DENY_COLUMNS}


def export_user(db: Session, user: User) -> dict:
    out: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "note": "Everything VITRAM holds about this account. Uploaded files are not included; download them from Documents & data. "
                "Passwords, session tokens and encrypted phone data are never exported.",
        "account": _row(user),
    }
    for key, model, col in EXPORT_TABLES:
        out[key] = [_row(r) for r in db.query(model).filter(getattr(model, col) == user.id)]
    conv_ids = [c.id for c in db.query(Conversation.id).filter(Conversation.user_id == user.id)]
    out["conversations"] = [_row(c) for c in db.query(Conversation).filter(Conversation.user_id == user.id)]
    out["messages"] = [_row(m) for m in db.query(Message).filter(Message.conversation_id.in_(conv_ids))] if conv_ids else []
    policy_ids = [p.id for p in db.query(UserPolicy.id).filter(UserPolicy.user_id == user.id)]
    out["policy_members"] = [_row(m) for m in db.query(PolicyMember).filter(PolicyMember.policy_id.in_(policy_ids))] if policy_ids else []
    return out


def delete_account(db: Session, user: User) -> None:
    """Erase the account and everything under it. Stored files go first (they are not covered by the database's cascades)."""
    for d in db.query(Document).filter(Document.owner_user_id == user.id):
        try:
            storage.delete(d.file_key)
        except OSError:  # a missing object must not block erasure
            log.warning("stored object for a deleted document was already gone")
    # Keep the audit trail's shape but cut its link to the person. (System context: see rls.system for why.)
    with rls.system(db):
        db.query(AuditEvent).filter(AuditEvent.user_id == user.id).update({AuditEvent.user_id: None}, synchronize_session=False)
        audit(db, None, "account.deleted")  # no user id, no personal data
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)  # the database cascades to every child row
        db.commit()
