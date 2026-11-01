"""Alembic migrations on disposable SQLite databases (never the developer's real database)."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.migrate import alembic_config, current_revision, head_revision, upgrade_to_head


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    engine = create_engine(url)
    yield url, engine, tmp_path / "m.db"
    engine.dispose()


def _upgrade(url, engine, target):
    cfg = alembic_config(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, target)


def _schema_diff(engine):
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


def test_fresh_database_matches_models(db):
    url, engine, _ = db
    info = upgrade_to_head(engine, url)
    assert info["to"] == head_revision(alembic_config(url))
    assert current_revision(engine) == info["to"]
    assert _schema_diff(engine) == []  # migrations reproduce the ORM models exactly


def test_upgrade_legacy_v1_database_preserves_data(db):
    """A database created by the old create_all start-up before emis.first_due_date existed."""
    url, engine, path = db
    _upgrade(url, engine, "0001")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))  # simulate pre-Alembic database
        conn.execute(text("INSERT INTO users (id, email, password_hash, name, preferred_language, onboarding_step, is_sample, created_at) "
                          "VALUES ('u1','a@b.c','x','A','en','done',0,'2026-01-01')"))
        conn.execute(text("INSERT INTO emis (id, user_id, title, emi_type, amount, due_day, source_type, confirmed, created_at) "
                          "VALUES ('e1','u1','Car loan','loan',5000,5,'manual',1,'2026-01-01')"))
    assert "first_due_date" not in {c["name"] for c in inspect(engine).get_columns("emis")}

    info = upgrade_to_head(engine, url)
    assert info["stamped_legacy"] == "0001"
    assert info["backup"] and Path(info["backup"]).exists()
    engine.dispose()
    assert "first_due_date" in {c["name"] for c in inspect(engine).get_columns("emis")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title, amount FROM emis WHERE id='e1'")).one() == ("Car loan", 5000)
        assert conn.execute(text("SELECT email FROM users")).scalar() == "a@b.c"
    # the backup is a readable copy of the pre-migration database
    with sqlite3.connect(info["backup"]) as b:
        assert b.execute("SELECT title FROM emis").fetchone() == ("Car loan",)
        assert "first_due_date" not in [r[1] for r in b.execute("PRAGMA table_info(emis)")]
    assert _schema_diff(engine) == []


def test_legacy_current_schema_is_only_stamped(db):
    url, engine, _ = db
    Base.metadata.create_all(engine)  # what the pre-Alembic start-up produced most recently
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, name, preferred_language, onboarding_step, is_sample, created_at) "
                          "VALUES ('u1','a@b.c','x','A','en','done',0,'2026-01-01')"))
    info = upgrade_to_head(engine, url)
    # The detector recognises the schema as of 0006; later revisions (brand copy, reminder claims)
    # are applied on top and are written to tolerate an already-current schema.
    assert info["stamped_legacy"] == "0006"
    assert current_revision(engine) == head_revision(alembic_config(url))
    assert info["backup"] and Path(info["backup"]).exists()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1


def test_downgrade_and_reupgrade(db):
    url, engine, _ = db
    upgrade_to_head(engine, url)
    cfg = alembic_config(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0001")
    assert current_revision(engine) == "0001"
    _upgrade(url, engine, "head")
    assert _schema_diff(engine) == []


def test_running_twice_is_a_no_op(db):
    url, engine, _ = db
    upgrade_to_head(engine, url)
    again = upgrade_to_head(engine, url)
    assert again["from"] == again["to"] and again["backup"] is None


def test_rebase_old_local_0004_history_without_losing_user_data(db):
    """Old branch 0004 meant phone + email tokens, not the pulled M13 revision chain."""
    url, engine, _ = db
    _upgrade(url, engine, "0002")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN phone_verified_at DATETIME"))
        conn.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME"))
        conn.execute(text("CREATE TABLE auth_tokens (id VARCHAR(64) NOT NULL PRIMARY KEY, user_id VARCHAR(36) NOT NULL, "
                          "purpose VARCHAR(30) NOT NULL, expires_at DATETIME NOT NULL, used_at DATETIME, "
                          "created_at DATETIME NOT NULL, FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE)"))
        conn.execute(text("CREATE INDEX ix_auth_tokens_user_id ON auth_tokens (user_id)"))
        conn.execute(text("INSERT INTO users (id, email, password_hash, name, preferred_language, onboarding_step, is_sample, created_at) "
                          "VALUES ('u1','a@b.c','x','A','en','done',0,'2026-01-01')"))
    cfg = alembic_config(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.stamp(cfg, "0004")
    info = upgrade_to_head(engine, url)
    assert info["rebased_from"] == "0004" and info["backup"] and Path(info["backup"]).exists()
    assert current_revision(engine) == "0013"
    assert _schema_diff(engine) == []
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users WHERE id='u1'")).scalar() == "a@b.c"


def _brand_migration():
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0007_vittrm_brand.py"
    spec = importlib.util.spec_from_file_location("brand_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_brand_rewrite_sql_is_valid_for_postgres_json_columns():
    """Regression: PostgreSQL's json type has no LIKE/REPLACE, so JSON columns must be cast through text."""
    mod = _brand_migration()
    pg = mod.statements("VITRAM", "VITTRM", postgres=True)
    lite = mod.statements("VITRAM", "VITTRM", postgres=False)
    meta_pg = next(s for s in pg if '"meta"' in s)
    assert 'CAST("meta" AS TEXT) LIKE' in meta_pg and "AS JSON)" in meta_pg
    content_pg = next(s for s in pg if '"content"' in s)
    assert "CAST" not in content_pg  # text columns need no cast
    assert all("CAST" not in s for s in lite)  # SQLite stores JSON as text already


def test_brand_rewrite_updates_existing_rows(db):
    url, engine, _ = db
    _upgrade(url, engine, "0006")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, name, preferred_language, onboarding_step, is_sample, created_at) "
                          "VALUES ('u1','a@b.c','x','A','en','done',0,'2026-01-01')"))
        conn.execute(text("INSERT INTO conversations (id, user_id, context_type, channel, started_at) "
                          "VALUES ('c1','u1','dashboard','web','2026-01-01')"))
        conn.execute(text("""INSERT INTO messages (id, conversation_id, role, content, modality, cards, citations, tool_calls, flags, created_at)
                             VALUES ('m1','c1','assistant','Welcome to VITRAM','text','[{"t":"VITRAM"}]','[]','[]','[]','2026-01-01')"""))
    _upgrade(url, engine, "0007")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT content, cards FROM messages WHERE id='m1'")).one()
    assert row[0] == "Welcome to VITTRM" and "VITTRM" in str(row[1]) and "VITRAM" not in str(row[1])
