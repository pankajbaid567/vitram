"""Zero-downtime migration policy (expand / contract), enforced.

During a deploy the old and new code run against the same database. So a migration that ships with new code may only **expand** the schema
(new tables, new nullable or defaulted columns, new indexes). Anything that would break the *previous* release (dropping or renaming a
column or table, tightening a column to NOT NULL without a default) is a **contract** step and must wait until no running code uses it.
A contract migration has to say so, and why it is safe, in its docstring on a line starting `CONTRACT:`.

Migrations before 0012 predate this rule and are grandfathered.
"""

import ast
import re
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parent.parent / "migrations" / "versions"
DESTRUCTIVE = {"drop_column", "drop_table", "rename_table", "drop_constraint", "drop_index"}
FIRST_ENFORCED = 12


def _revision(path: Path) -> int:
    return int(re.match(r"(\d+)_", path.name).group(1))


def _destructive_calls(tree: ast.AST) -> list[tuple[str, int]]:
    out = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "upgrade":
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    if name in DESTRUCTIVE:
                        out.append((name, node.lineno))
                    if name == "alter_column":
                        kw = {k.arg: k.value for k in node.keywords}
                        nullable = kw.get("nullable")
                        if isinstance(nullable, ast.Constant) and nullable.value is False and "server_default" not in kw:
                            out.append(("alter_column(nullable=False without a default)", node.lineno))
                        if "new_column_name" in kw:
                            out.append(("alter_column(rename)", node.lineno))
    return out


FILES = sorted(p for p in VERSIONS.glob("[0-9]*.py") if _revision(p) >= FIRST_ENFORCED)


def test_there_are_migrations_under_the_policy():
    assert FILES


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_destructive_changes_are_declared_contract_steps(path):
    tree = ast.parse(path.read_text())
    found = _destructive_calls(tree)
    if not found:
        return
    doc = ast.get_docstring(tree) or ""
    declared = [ln for ln in doc.splitlines() if ln.strip().startswith("CONTRACT:")]
    assert declared, (f"{path.name} contains {[n for n, _ in found]} but its docstring has no 'CONTRACT:' line saying why the previous release "
                      "still works. Expand first, deploy, and contract in a later release.")


def test_the_checker_actually_catches_a_destructive_migration():
    bad = ast.parse("from alembic import op\ndef upgrade():\n    op.drop_column('users', 'phone')\n")
    assert _destructive_calls(bad) == [("drop_column", 3)]
    renamed = ast.parse("from alembic import op\ndef upgrade():\n    op.alter_column('t', 'a', new_column_name='b')\n")
    assert _destructive_calls(renamed)
    tightened = ast.parse("from alembic import op\ndef upgrade():\n    op.alter_column('t', 'a', nullable=False)\n")
    assert _destructive_calls(tightened)
    safe = ast.parse("from alembic import op\ndef upgrade():\n    op.add_column('t', None)\n    op.create_index('i', 't', ['a'])\n")
    assert _destructive_calls(safe) == []
