"""Worker heartbeats, shared rate-limit ledger, and composite indexes for hot queries.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = (
    ("ix_transactions_user_date", "transactions", ["user_id", "txn_date"]),
    ("ix_document_facts_doc_key", "document_facts", ["document_id", "key"]),
    ("ix_reminders_status_schedule", "reminders", ["status", "schedule_at"]),
)


def upgrade() -> None:
    # Idempotent throughout: a pre-Alembic database created from the current models already has these objects.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "worker_heartbeats" not in tables:
        op.create_table("worker_heartbeats", sa.Column("name", sa.String(40), primary_key=True),
                        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False))
    if "rate_limit_hits" not in tables:
        op.create_table("rate_limit_hits", sa.Column("id", sa.String(36), primary_key=True),
                        sa.Column("key", sa.String(240), nullable=False), sa.Column("hit_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_rate_limit_hits_key", "rate_limit_hits", ["key"])
        op.create_index("ix_rate_limit_hits_hit_at", "rate_limit_hits", ["hit_at"])
    for name, table, cols in INDEXES:
        if name not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}:
            op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _ in INDEXES:
        op.drop_index(name, table_name=table)
    op.drop_table("rate_limit_hits")
    op.drop_table("worker_heartbeats")
