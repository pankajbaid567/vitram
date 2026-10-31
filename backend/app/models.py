"""Relational model — mirrors RD §19 entity boundaries.

Money is stored in rupees as floats rounded to 2 dp at write time; every API
response wraps it as {amount, currency: "INR"} (RD §20.1).
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fk(target: str, nullable: bool = False, ondelete: str = "CASCADE"):
    return mapped_column(
        String(36), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    employer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    salary_manual: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    # Phone is PII: stored encrypted, shown masked.
    phone_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_masked: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Keyed HMAC of the E.164 number so inbound WhatsApp messages can be matched without decrypting.
    phone_lookup: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_step: Mapped[str] = mapped_column(String(30), default="about")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of token
    user_id: Mapped[str] = _fk("users.id")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256 of bearer token
    user_id: Mapped[str] = _fk("users.id")
    purpose: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    purpose: Mapped[str] = mapped_column(String(40))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notice_version: Mapped[str] = mapped_column(String(20), default="2026-09")


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    name: Mapped[str] = mapped_column(String(80))
    relation: Mapped[str] = mapped_column(String(30))
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_dependant: Mapped[bool] = mapped_column(Boolean, default=False)
    added_by_owner: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    label: Mapped[str] = mapped_column(String(60))
    bank_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    masked_account_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = _fk("users.id")
    family_member_id: Mapped[str | None] = _fk("family_members.id", nullable=True, ondelete="SET NULL")
    bank_account_id: Mapped[str | None] = _fk("bank_accounts.id", nullable=True, ondelete="SET NULL")
    type: Mapped[str] = mapped_column(String(30))  # bank_statement | insurance_policy | loan_document
    display_name: Mapped[str] = mapped_column(String(160))
    mime: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    file_key: Mapped[str] = mapped_column(String(80))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processing_status: Mapped[str] = mapped_column(String(20), default="queued")
    processing_stage: Mapped[str] = mapped_column(String(30), default="uploaded")
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    retention_state: Mapped[str] = mapped_column(String(20), default="active")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class DocumentFact(Base):
    __tablename__ = "document_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = _fk("documents.id")
    user_id: Mapped[str] = _fk("users.id")
    fact_type: Mapped[str] = mapped_column(String(30))  # group, e.g. financials / restrictions
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    value: Mapped[object] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(120), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    state: Mapped[str] = mapped_column(String(20), default="extracted")
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = _fk("documents.id")
    user_id: Mapped[str] = _fk("users.id")
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(120), nullable=True)
    text: Mapped[str] = mapped_column(Text)


class RecurringGroup(Base):
    __tablename__ = "recurring_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    bank_account_id: Mapped[str | None] = _fk("bank_accounts.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(120))
    counterparty_key: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(6))
    typical_amount: Mapped[float] = mapped_column(Float)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer)
    first_date: Mapped[date] = mapped_column(Date)
    last_date: Mapped[date] = mapped_column(Date)
    confidence: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(20), default="extracted")  # extracted|confirmed|rejected
    user_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("bank_account_id", "fingerprint", name="uq_txn_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    bank_account_id: Mapped[str] = _fk("bank_accounts.id")
    source_document_id: Mapped[str] = _fk("documents.id")
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(6))  # credit | debit
    description: Mapped[str] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(12), nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="other")
    category_source: Mapped[str] = mapped_column(String(10), default="rule")
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    recurring_group_id: Mapped[str | None] = _fk("recurring_groups.id", nullable=True, ondelete="SET NULL")
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_ref: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=0.9)


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)


class ProfileOverride(Base):
    __tablename__ = "profile_overrides"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    path: Mapped[str] = mapped_column(String(160), index=True)
    prior_value: Mapped[object] = mapped_column(JSON, nullable=True)
    corrected_value: Mapped[object] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoanProduct(Base):
    __tablename__ = "loan_catalogue"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    lender: Mapped[str] = mapped_column(String(80))
    product_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30))
    secured: Mapped[bool] = mapped_column(Boolean)
    data: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[date] = mapped_column(Date)


class UserLoan(Base):
    __tablename__ = "user_loans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    lender: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    principal: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_emi: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenure_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_document_id: Mapped[str | None] = _fk("documents.id", nullable=True, ondelete="SET NULL")
    status: Mapped[str] = mapped_column(String(20), default="active")
    terms: Mapped[dict] = mapped_column(JSON, default=dict)


class CardProduct(Base):
    __tablename__ = "credit_card_catalogue"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(80))
    card_name: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[date] = mapped_column(Date)


class UserCard(Base):
    __tablename__ = "user_credit_cards"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    catalogue_id: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("credit_card_catalogue.id", ondelete="SET NULL"), nullable=True
    )
    nickname: Mapped[str] = mapped_column(String(60))
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # {"balance": 12000, "as_of": "2026-09-01", "expiring": [{"amount": 2000, "date": "2026-12-31"}]}
    points: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Month-to-date category spend used for cap tracking, user-provided or imported.
    cycle_spend: Mapped[dict] = mapped_column(JSON, default=dict)
    source_document_id: Mapped[str | None] = _fk("documents.id", nullable=True, ondelete="SET NULL")
    source_fields: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Benefits the user typed in themselves (shown as "You entered", never mixed with catalogue terms).
    user_benefits: Mapped[list] = mapped_column(JSON, default=list)
    catalogue: Mapped[CardProduct | None] = relationship()


class Emi(Base):
    __tablename__ = "emis"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    user_loan_id: Mapped[str | None] = _fk("user_loans.id", nullable=True, ondelete="SET NULL")
    title: Mapped[str] = mapped_column(String(120))
    emi_type: Mapped[str] = mapped_column(String(30), default="personal_loan")
    lender: Mapped[str | None] = mapped_column(String(80), nullable=True)
    principal: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    due_day: Mapped[int] = mapped_column(Integer)
    remaining_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # fixed | floating
    # {"flat_fee": 500, "penal_rate_pa": 24, "gst_applicable": true, "source": "..."}
    late_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {"allowed": true, "charge_pct": 2, "lock_in_months": 6}
    prepayment_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")  # manual|bank_detection|document
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recurring_group_id: Mapped[str | None] = _fk("recurring_groups.id", nullable=True, ondelete="SET NULL")
    source_document_id: Mapped[str | None] = _fk("documents.id", nullable=True, ondelete="SET NULL")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InsuranceProduct(Base):
    __tablename__ = "insurance_catalogue"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    insurer: Mapped[str] = mapped_column(String(80))
    product_name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[date] = mapped_column(Date)


class UserPolicy(Base):
    __tablename__ = "user_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    document_id: Mapped[str | None] = _fk("documents.id", nullable=True, ondelete="CASCADE")
    insurer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    type: Mapped[str] = mapped_column(String(30), default="health")
    policy_ref_masked: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    premium: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    coverage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    members_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    members: Mapped[list["PolicyMember"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class PolicyMember(Base):
    __tablename__ = "policy_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    policy_id: Mapped[str] = _fk("user_policies.id")
    family_member_id: Mapped[str | None] = _fk("family_members.id", nullable=True)  # None = account holder
    role: Mapped[str] = mapped_column(String(20), default="insured")


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    object_type: Mapped[str] = mapped_column(String(20))  # emi | card | policy
    object_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(12))  # whatsapp | in_app
    schedule_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    due_date: Mapped[date] = mapped_column(Date)
    template_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    opt_in_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set while a worker owns the reminder (status "sending"); see scheduler.claim_due.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReminderPreference(Base):
    __tablename__ = "reminder_preferences"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    days_before: Mapped[list] = mapped_column(JSON, default=lambda: [3])
    on_due_date: Mapped[bool] = mapped_column(Boolean, default=True)
    send_hour: Mapped[int] = mapped_column(Integer, default=9)  # IST hour
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    include: Mapped[list] = mapped_column(JSON, default=lambda: ["emi", "card", "policy"])
    # Individual items the user switched reminders off for, as "emi:<id>" / "card:<id>" / "policy:<id>".
    muted: Mapped[list] = mapped_column(JSON, default=list)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    context_type: Mapped[str] = mapped_column(String(20))
    context_object_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    channel: Mapped[str] = mapped_column(String(12), default="web")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = _fk("conversations.id")
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(10), default="text")  # text | voice
    mode: Mapped[str | None] = mapped_column(String(10), nullable=True)  # gemini | tool
    cards: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsultationRequest(Base):
    __tablename__ = "consultation_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    topic: Mapped[str] = mapped_column(String(300))
    context_summary: Mapped[str] = mapped_column(Text)
    policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    family_member_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    phone_enc: Mapped[str] = mapped_column(Text)
    phone_masked: Mapped[str] = mapped_column(String(20))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CalculationRun(Base):
    """RD §23.3: no calculation result is persisted without inputs + formula version."""

    __tablename__ = "calculation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    kind: Mapped[str] = mapped_column(String(40))
    inputs: Mapped[dict] = mapped_column(JSON)
    outputs: Mapped[dict] = mapped_column(JSON)
    formula_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    object_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    """Idempotency ledger for inbound provider webhooks (RD §26)."""

    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_webhook_event"),)


class Goal(Base):
    """A savings goal the user tracks by hand. VITTRM never moves money or promises returns."""

    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | achieved | archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoalContribution(Base):
    __tablename__ = "goal_contributions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    goal_id: Mapped[str] = _fk("goals.id")
    user_id: Mapped[str] = _fk("users.id")
    amount: Mapped[float] = mapped_column(Float)  # negative = withdrawal
    on_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExpectedPayment(Base):
    """A one-off amount the user expects (bonus in, school fee out) for the cash-flow estimate."""

    __tablename__ = "expected_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = _fk("users.id")
    label: Mapped[str] = mapped_column(String(80))
    amount: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(6))  # credit | debit
    on_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordReset(Base):
    """Single-use reset tokens; only a SHA-256 of the token is stored."""

    __tablename__ = "password_resets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[str] = _fk("users.id")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
