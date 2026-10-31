"""Calculation snapshots (RD §23.3): no result is shown without its inputs, outputs and formula version on record."""

from sqlalchemy.orm import Session

from app.models import CalculationRun


def record(db: Session, user_id: str, kind: str, inputs: dict, outputs: dict, formula_version: str) -> str:
    """Persist one calculation and return its id, so the response (and the assistant) can cite it."""
    run = CalculationRun(user_id=user_id, kind=kind, inputs=inputs, outputs=outputs, formula_version=formula_version)
    db.add(run)
    db.flush()
    return run.id
