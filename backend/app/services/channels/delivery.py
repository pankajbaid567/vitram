"""Delivery-status state machine for outbound reminders.

Providers deliver acknowledgements at-least-once and out of order, so a status may
only move *forward* along ``sent → delivered → read``. A ``failed`` report is
terminal and always recorded. Pure functions, no I/O: easy to test exhaustively.
"""

from app.models import Reminder

LADDER = ("sent", "delivered", "read")
ACCEPTED = frozenset((*LADDER, "failed"))


def next_status(current: str, incoming: str | None) -> str:
    """Return the status a reminder should have after ``incoming`` is reported."""
    if incoming not in ACCEPTED:
        return current
    if incoming == "failed":
        return "failed"
    if current not in LADDER:  # e.g. still "scheduled": any positive receipt is progress
        return incoming
    return incoming if LADDER.index(incoming) >= LADDER.index(current) else current


def apply_status(reminder: Reminder, incoming: str | None, error: str | None = None) -> bool:
    """Apply a provider receipt to ``reminder``. Returns True when anything changed."""
    new = next_status(reminder.status, incoming)
    if new == reminder.status and not (new == "failed" and error and reminder.last_error != error):
        return False
    reminder.status = new
    if new == "failed":
        reminder.last_error = error
    return True
