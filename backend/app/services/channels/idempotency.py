"""At-most-once processing of provider webhooks.

Providers retry deliveries, so each event is recorded under a unique
``(provider, external_id)`` key; the database's unique constraint decides the winner,
which stays correct with several API workers (no in-process cache involved).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import WebhookEvent


def first_time(db: Session, provider: str, external_id: str) -> bool:
    """Record the event; True the first time it is seen, False for a replay."""
    try:
        with db.begin_nested():  # SAVEPOINT: a duplicate must not poison the outer transaction
            db.add(WebhookEvent(provider=provider, external_id=external_id))
        return True
    except IntegrityError:
        return False
