"""PostgreSQL Row Level Security as a second lock behind the application's own ``WHERE user_id = …``.

The application already filters every query by owner, and ``tests/test_access_matrix.py`` proves it for every route. RLS protects against the
mistake that test cannot see: a *future* query written without the filter. With RLS on, the database itself refuses to return or change another
user's rows to a request that has declared whose request it is.

How it works
* Each table that has a ``user_id`` / ``owner_user_id`` column (and ``users`` itself) gets a policy: a row is visible and writable when the
  session's ``app.user_id`` setting equals its owner. ``FORCE ROW LEVEL SECURITY`` makes this apply to the table owner too.
* An authenticated request sets ``app.user_id`` once per transaction (``set_config(..., true)``: transaction-local, so it is also correct behind
  a transaction-pooling proxy such as Neon's pooled endpoint). See :func:`install_session_hook`.
* **No context means no restriction.** Sign-in, sign-up, webhooks, the reminder loop and the job workers do not declare a user and see everything,
  exactly as before; only code running *as a user's request* is boxed in. That is why switching this on cannot break system paths.

Limits, stated plainly
* Tables owned only through a parent (``policy_members``, ``goal_contributions``) have no owner column and are not covered.
* A role with ``BYPASSRLS`` or superuser ignores every policy. Neon's default ``neondb_owner`` has ``BYPASSRLS``, so on Neon the policies only
  bite when the API connects as a separate role without it (see ``docs/SECURITY_MODEL.md`` for the two statements to create one).
"""

from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.config import get_settings

POLICY = "vitram_user_isolation"
OWNER_COLUMNS = ("user_id", "owner_user_id")


def _expr(column: str) -> str:
    # empty / unset context = system code: unrestricted. A declared user sees and writes only their own rows.
    return f"(coalesce(current_setting('app.user_id', true), '') = '' OR {column} = current_setting('app.user_id', true))"


def owned_tables(conn) -> list[tuple[str, str]]:
    """(table, owner column) for every public table that has one."""
    rows = conn.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND column_name = ANY(:cols) ORDER BY table_name"), {"cols": list(OWNER_COLUMNS)}).all()
    found: dict[str, str] = {}
    for table, column in rows:
        found.setdefault(table, column)
    found["users"] = "id"
    return sorted(found.items())


def enable(conn) -> int:
    n = 0
    for table, column in owned_tables(conn):
        conn.execute(text(f'DROP POLICY IF EXISTS {POLICY} ON "{table}"'))
        # WITH CHECK also admits an ownerless row (NULL owner): the audit trail keeps anonymised events after an account is deleted.
        # Such rows are written by anyone but readable by no declared user (NULL = x is never true).
        conn.execute(text(f'CREATE POLICY {POLICY} ON "{table}" USING {_expr(column)} WITH CHECK ({_expr(column)} OR {column} IS NULL)'))
        conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        n += 1
    return n


def disable(conn) -> int:
    n = 0
    for table, _ in owned_tables(conn):
        conn.execute(text(f'DROP POLICY IF EXISTS {POLICY} ON "{table}"'))
        conn.execute(text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        conn.execute(text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
        n += 1
    return n


def _apply(connection, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": user_id})


_installed = False


def install_session_hook() -> None:
    """Re-declare the request's user at the start of every transaction of a session that has one (handlers commit mid-request)."""
    global _installed
    if _installed:
        return
    _installed = True

    @event.listens_for(Session, "after_begin")
    def _after_begin(session, _transaction, connection):
        uid = session.info.get("rls_user")
        if uid and connection.dialect.name == "postgresql":
            _apply(connection, uid)


@contextmanager
def system(db: Session):
    """Run a deliberately cross-row operation (erasing an account also anonymises its audit trail) as system code, not as the user.

    PostgreSQL requires an updated row to still satisfy the SELECT policy, so a declared user cannot, for example, set an owned row's owner to
    NULL. Use sparingly and only for operations that are the user's own request and touch only their own data.
    """
    user_id = db.info.pop("rls_user", None)
    if user_id and db.get_bind().dialect.name == "postgresql":
        _apply(db.connection(), "")
    try:
        yield
    finally:
        if user_id:
            db.info["rls_user"] = user_id


def bind_request(db: Session, user_id: str) -> None:
    """Called once a request is authenticated: from now on this session acts as ``user_id``."""
    if not get_settings().rls_enabled or db.get_bind().dialect.name != "postgresql":
        return
    install_session_hook()
    db.info["rls_user"] = user_id
    _apply(db.connection(), user_id)
