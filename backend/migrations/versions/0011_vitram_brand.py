"""Rename generated product copy back from VITTRM to VITRAM (the product's name).

Revision ID: 0011
Revises: 0010

Reuses the rewrite from 0007 in the opposite direction. Original uploaded document text, email
addresses and technical identifiers are untouched, as before.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (("documents", "meta", True), ("messages", "content", False), ("messages", "cards", True))


def _replace(old: str, new: str) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for table, column, is_json in _COLUMNS:
        as_text = f'CAST("{column}" AS TEXT)' if postgres and is_json else f'"{column}"'
        replaced = f"REPLACE({as_text}, '{old}', '{new}')"
        value = f"CAST({replaced} AS JSON)" if postgres and is_json else replaced
        op.execute(f'UPDATE "{table}" SET "{column}" = {value} WHERE {as_text} LIKE \'%{old}%\'')


def upgrade() -> None:
    _replace("VITTRM", "VITRAM")


def downgrade() -> None:
    _replace("VITRAM", "VITTRM")
