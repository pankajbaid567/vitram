"""Card spend reconciled from confirmed statement purchases, kept apart from manual entries.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: a pre-Alembic database created from the current models already has the column.
    if "imported_spend" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user_credit_cards")}:
        return
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.add_column(sa.Column("imported_spend", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.drop_column("imported_spend")
