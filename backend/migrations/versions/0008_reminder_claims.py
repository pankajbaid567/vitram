"""Reminder claims: lets several workers share the queue without double-sending.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: a pre-Alembic database created from the current models already has the column.
    if "claimed_at" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("reminders")}:
        return
    with op.batch_alter_table("reminders") as batch:
        batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("claimed_at")
