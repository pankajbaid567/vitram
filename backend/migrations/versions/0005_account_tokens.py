"""Email verification and password-reset token state.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "email_verified_at" not in {c["name"] for c in insp.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    if "auth_tokens" not in insp.get_table_names():
        op.create_table("auth_tokens",
                    sa.Column("id", sa.String(length=64), primary_key=True),
                    sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("purpose", sa.String(length=30), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
        op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
