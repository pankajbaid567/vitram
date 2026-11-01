"""Idempotency keys for state-changing requests.

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "idempotency_keys" in sa.inspect(op.get_bind()).get_table_names():
        return   # a pre-Alembic database created from the current models already has it
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("response_body", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
