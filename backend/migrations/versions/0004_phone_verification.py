"""Record when a stored phone was verified for outbound communications.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "phone_verified_at" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("phone_verified_at")
