"""Index transactions by (user_id, txn_date, id) so keyset pages need no sort step.

Revision ID: 0013
Revises: 0012

Measured on 58,000 rows: the newest-100 query for the busiest user fell from 4.7 ms (an index scan plus an incremental
sort) to about 0.25 ms (a plain backward index scan). The new index starts with the old one's columns, so the old
index is redundant and is dropped.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes() -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("transactions")}


def upgrade() -> None:
    if "ix_transactions_user_date_id" not in _indexes():
        op.create_index("ix_transactions_user_date_id", "transactions", ["user_id", "txn_date", "id"])
    if "ix_transactions_user_date" in _indexes():
        op.drop_index("ix_transactions_user_date", table_name="transactions")


def downgrade() -> None:
    if "ix_transactions_user_date" not in _indexes():
        op.create_index("ix_transactions_user_date", "transactions", ["user_id", "txn_date"])
    if "ix_transactions_user_date_id" in _indexes():
        op.drop_index("ix_transactions_user_date_id", table_name="transactions")
