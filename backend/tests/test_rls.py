"""Row Level Security, proven against a real PostgreSQL role without BYPASSRLS (skipped on SQLite)."""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import rls
from app.db import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Row Level Security is a PostgreSQL feature")

ROLE = "vitram_rls_tester"


@pytest.fixture(scope="module")
def restricted(client_factory):
    """An engine connecting as a role that cannot bypass RLS, with the policies enabled."""
    with engine.begin() as conn:
        conn.execute(text(f"DROP OWNED BY {ROLE}")) if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:r"), {"r": ROLE}).first() else None
        conn.execute(text(f"DROP ROLE IF EXISTS {ROLE}"))
        conn.execute(text(f"CREATE ROLE {ROLE} LOGIN PASSWORD 'rls-test-pw' NOBYPASSRLS NOSUPERUSER"))
        conn.execute(text(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {ROLE}"))
        rls.enable(conn)
    url = engine.url.set(username=ROLE, password="rls-test-pw")
    eng = create_engine(url)
    yield eng
    eng.dispose()
    with engine.begin() as conn:
        rls.disable(conn)
        conn.execute(text(f"DROP OWNED BY {ROLE}"))
        conn.execute(text(f"DROP ROLE {ROLE}"))


def _as(eng, user_id=None):
    s = Session(eng)
    if user_id:
        s.info["rls_user"] = user_id
        rls.install_session_hook()
    return s


@pytest.fixture
def two_users(client_factory, restricted):
    from tests.conftest import signup

    ids = []
    for i in range(2):
        c = client_factory()
        me = signup(c)
        c.post("/api/goals", json={"name": f"goal-{i}", "target_amount": 1000 + i})
        c.post("/api/emis", json={"title": f"emi-{i}", "amount": 500, "due_day": 5, "remaining_count": 3})
        with engine.connect() as conn:
            ids.append(conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": me["email"]}).scalar())
    return ids


def test_policies_cover_every_owned_table(restricted):
    with engine.connect() as conn:
        tables = rls.owned_tables(conn)
        covered = {r[0] for r in conn.execute(text("SELECT tablename FROM pg_policies WHERE policyname=:p"), {"p": rls.POLICY})}
    assert len(tables) > 25 and {t for t, _ in tables} == covered
    assert ("users", "id") in tables and ("emis", "user_id") in tables and ("documents", "owner_user_id") in tables


def test_without_a_declared_user_system_code_sees_everything(restricted, two_users):
    with _as(restricted) as s:
        assert s.execute(text("SELECT count(*) FROM emis")).scalar() >= 2


def test_a_declared_user_cannot_see_another_users_rows_even_without_a_where_clause(restricted, two_users):
    a, b = two_users
    with _as(restricted, a) as s:
        emis = s.execute(text("SELECT user_id FROM emis")).scalars().all()          # note: no WHERE user_id = …
        goals = s.execute(text("SELECT user_id FROM goals")).scalars().all()
        users = s.execute(text("SELECT id FROM users")).scalars().all()
    assert emis and set(emis) == {a} and goals and set(goals) == {a} and users == [a]
    with _as(restricted, b) as s:
        assert set(s.execute(text("SELECT user_id FROM emis")).scalars()) == {b}


def test_a_declared_user_cannot_write_for_or_change_another_user(restricted, two_users):
    a, b = two_users
    s = _as(restricted, a)
    s.execute(text("SELECT 1"))                                                    # begin: the hook declares user a
    with pytest.raises(DBAPIError):                                                # INSERT for someone else violates WITH CHECK
        s.execute(text("INSERT INTO goals (id, user_id, name, target_amount, status, created_at, version) "
                       "VALUES (:i, :u, 'x', 1, 'active', now(), 1)"), {"i": str(uuid.uuid4()), "u": b})
    s.rollback()
    assert s.execute(text("UPDATE emis SET title='hijacked' WHERE user_id=:b"), {"b": b}).rowcount == 0   # invisible, so unchanged
    assert s.execute(text("DELETE FROM goals WHERE user_id=:b"), {"b": b}).rowcount == 0
    s.rollback()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM emis WHERE user_id=:b AND title='hijacked'"), {"b": b}).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM goals WHERE user_id=:b"), {"b": b}).scalar() >= 1


def test_the_declaration_survives_commits_within_one_session(restricted, two_users):
    a, _ = two_users
    s = _as(restricted, a)
    for _ in range(3):                                                              # handlers commit mid-request
        assert set(s.execute(text("SELECT user_id FROM emis")).scalars()) == {a}
        s.commit()
    s.close()


def test_orm_queries_are_boxed_in_too(restricted, two_users):
    from app.models import Emi

    a, b = two_users
    with _as(restricted, a) as s:
        assert {e.user_id for e in s.query(Emi).all()} == {a}


def test_the_setting_does_not_leak_to_the_next_user_of_a_pooled_connection(restricted, two_users):
    a, _ = two_users
    with _as(restricted, a) as s:
        s.execute(text("SELECT 1"))
        s.commit()
    with _as(restricted) as s2:                                                     # next borrower declares nothing
        assert s2.execute(text("SELECT coalesce(current_setting('app.user_id', true), '')")).scalar() == ""
