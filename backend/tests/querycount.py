"""Count SQL statements issued inside a block (used by tests/test_query_budget.py)."""

from contextlib import contextmanager

from sqlalchemy import event

from app.db import engine


@contextmanager
def count_queries():
    stmts: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if not statement.lstrip().upper().startswith(("PRAGMA", "SAVEPOINT", "RELEASE", "BEGIN", "COMMIT", "ROLLBACK", "SELECT SET_CONFIG")):   # RLS context is plumbing, not a query
            stmts.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield stmts
    finally:
        event.remove(engine, "before_cursor_execute", before)
