"""Track exactly which saved-card values came from a document.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.add_column(sa.Column("source_fields", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.drop_column("source_fields")
