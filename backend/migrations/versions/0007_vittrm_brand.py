"""Rename generated product copy from VITRAM to VITTRM.

Revision ID: 0007
Revises: 0006

Original uploaded document text, source snippets, email addresses, cookie names,
and other technical identifiers remain unchanged.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace(old: str, new: str) -> None:
    for table, column in (("documents", "meta"), ("messages", "content"), ("messages", "cards")):
        op.execute(
            f'UPDATE "{table}" SET "{column}" = '
            f'REPLACE("{column}", \'{old}\', \'{new}\') '
            f'WHERE "{column}" LIKE \'%{old}%\''
        )


def upgrade() -> None:
    _replace("VITRAM", "VITTRM")


def downgrade() -> None:
    _replace("VITTRM", "VITRAM")
