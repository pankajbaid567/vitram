"""emis.first_due_date — EMIs from loan documents don't appear before their first instalment.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emis") as batch:
        batch.add_column(sa.Column("first_due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("emis") as batch:
        batch.drop_column("first_due_date")
