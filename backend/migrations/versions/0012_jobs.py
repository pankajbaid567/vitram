"""Durable job queue.

Revision ID: 0012
Revises: 0011

Document processing used to run as an in-process background task, so a restart lost the work. Jobs are rows now:
enqueued in the same transaction as the upload, claimed with a lease, retried with back-off and parked as ``dead``
after the last attempt.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: a pre-Alembic database created from the current models already has the table.
    if "jobs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.String(60)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("dedupe_key", sa.String(120)),
        sa.Column("last_error", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("dedupe_key", name="uq_jobs_dedupe_key"),
    )
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status_run_after", table_name="jobs")
    op.drop_table("jobs")
