"""Rollback rehearsal: the schema can go back to the previous release's revision and forward again, with data intact.

This is the database half of a rollback. (The code half is redeploying the previous commit; see docs/DEPLOY.md.) Because every migration after
0011 only expands the schema, the previous release also runs fine against the newer schema, so a code rollback needs no downgrade at all;
this test proves the downgrade path exists for the case where you do want the schema back.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from app.migrate import alembic_config, current_revision, head_revision
from alembic import command

BASELINE = "0011"   # the revision the previous production release ran on


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'rt.db'}"


def _run(url, fn, *args):
    engine = create_engine(url)
    cfg = alembic_config(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        fn(cfg, *args)
    return engine


def test_downgrade_to_the_previous_release_and_upgrade_again_keeps_data(db_url):
    engine = _run(db_url, command.upgrade, "head")
    head = head_revision(alembic_config(db_url))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, name, preferred_language, onboarding_step, is_sample, created_at) "
                          "VALUES ('u1','rt@example.com','x','Round Trip','en','done',0,'2026-01-01')"))
    assert current_revision(engine) == head

    engine = _run(db_url, command.downgrade, BASELINE)
    names = set(inspect(engine).get_table_names())
    assert current_revision(engine) == BASELINE
    assert "jobs" not in names and "idempotency_keys" not in names          # the new tables are gone
    cols = {c["name"] for c in inspect(engine).get_columns("goals")}
    assert "version" not in cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users WHERE id='u1'")).scalar() == "rt@example.com"   # data survived the way back

    engine = _run(db_url, command.upgrade, "head")
    assert current_revision(engine) == head
    assert {"jobs", "idempotency_keys"} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users WHERE id='u1'")).scalar() == "rt@example.com"
