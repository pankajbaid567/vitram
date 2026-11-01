"""Row versions for optimistic concurrency on user-editable records.

Revision ID: 0015
Revises: 0014
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("family_members", "user_credit_cards", "goals", "emis")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table in TABLES:
        if "version" not in {c["name"] for c in insp.get_columns(table)}:
            op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "version")
