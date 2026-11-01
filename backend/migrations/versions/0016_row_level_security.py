"""Row Level Security policies on user-owned tables (PostgreSQL only).

Revision ID: 0016
Revises: 0015

Policies are created and enabled for every table with an owner column. They only restrict sessions that declare a user
(``app.user_id``); system code and a role with BYPASSRLS are unaffected, so applying this cannot change behaviour until
``RLS_ENABLED=true`` and a non-bypass role are in use. See app/rls.py and docs/SECURITY_MODEL.md.
"""

from typing import Sequence, Union

from alembic import op

from app import rls

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        rls.enable(conn)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        rls.disable(conn)
