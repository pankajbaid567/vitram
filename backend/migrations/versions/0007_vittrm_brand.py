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


# (table, column, is_json). SQLite stores JSON as text; PostgreSQL's json type has neither LIKE nor
# REPLACE, so there the value is round-tripped through text.
_COLUMNS = (("documents", "meta", True), ("messages", "content", False), ("messages", "cards", True))


def statements(old: str, new: str, postgres: bool) -> list[str]:
    """The UPDATEs that rewrite ``old`` to ``new`` (pure, so each dialect's SQL can be unit-tested)."""
    out = []
    for table, column, is_json in _COLUMNS:
        as_text = f'CAST("{column}" AS TEXT)' if postgres and is_json else f'"{column}"'
        replaced = f"REPLACE({as_text}, '{old}', '{new}')"
        value = f"CAST({replaced} AS JSON)" if postgres and is_json else replaced
        out.append(f'UPDATE "{table}" SET "{column}" = {value} WHERE {as_text} LIKE \'%{old}%\'')
    return out


def _replace(old: str, new: str) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    for sql in statements(old, new, postgres):
        op.execute(sql)


def upgrade() -> None:
    _replace("VITRAM", "VITTRM")


def downgrade() -> None:
    _replace("VITTRM", "VITRAM")
