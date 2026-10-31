"""goals, goal contributions, expected payments, password resets; card user benefits; per-item reminder muting (M13).

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.String(length=36), sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _fk("user_id", "users.id"),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.create_table(
        "goal_contributions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _fk("goal_id", "goals.id"),
        _fk("user_id", "users.id"),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_goal_contributions_goal_id", "goal_contributions", ["goal_id"])
    op.create_index("ix_goal_contributions_user_id", "goal_contributions", ["user_id"])
    op.create_table(
        "expected_payments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        _fk("user_id", "users.id"),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_expected_payments_user_id", "expected_payments", ["user_id"])
    op.create_table(
        "password_resets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        _fk("user_id", "users.id"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.add_column(sa.Column("user_benefits", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("reminder_preferences") as batch:
        batch.add_column(sa.Column("muted", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("reminder_preferences") as batch:
        batch.drop_column("muted")
    with op.batch_alter_table("user_credit_cards") as batch:
        batch.drop_column("user_benefits")
    for t in ("password_resets", "expected_payments", "goal_contributions", "goals"):
        op.drop_table(t)
