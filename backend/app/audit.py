"""Audit trail (RD §23.1). Metadata must never contain document text or raw financial details."""

from sqlalchemy.orm import Session

from app.models import AuditEvent


def audit(
    db: Session,
    user_id: str | None,
    action: str,
    object_type: str | None = None,
    object_id: str | None = None,
    **meta,
) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, object_type=object_type, object_id=object_id, meta=meta))
