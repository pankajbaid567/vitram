"""Database migrations (Alembic) with automatic pre-migration backups.

Startup behaviour (`upgrade_to_head`):
  * Fresh database          → run all migrations.
  * Alembic-managed database → back up (SQLite), then apply pending migrations.
  * Pre-Alembic database     → detect which released schema it matches, stamp
                               that revision (no schema change), back up, upgrade.

Nothing is ever dropped automatically; downgrades are manual (see README).
CLI:  uv run python -m app.migrate status | upgrade | backup | restore <file>
"""

import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.config import BACKEND_DIR, get_settings

log = logging.getLogger("vitram.migrate")


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["skip_logging_config"] = True
    if url:
        cfg.attributes["url"] = url
    return cfg


def head_revision(cfg: Config) -> str:
    return ScriptDirectory.from_config(cfg).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def detect_legacy_revision(engine: Engine) -> str | None:
    """For databases created by the pre-Alembic `create_all` start-up: which released schema do they match?"""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "alembic_version" in tables or "users" not in tables:
        return None
    if "goals" in tables:  # M13 schema, possibly followed by the local integration migrations
        user_cols = {c["name"] for c in insp.get_columns("users")}
        card_cols = {c["name"] for c in insp.get_columns("user_credit_cards")} if "user_credit_cards" in tables else set()
        if "source_fields" in card_cols:
            return "0006"
        if "email_verified_at" in user_cols and "auth_tokens" in tables:
            return "0005"
        if "phone_verified_at" in user_cols:
            return "0004"
        return "0003"
    emi_cols = {c["name"] for c in insp.get_columns("emis")} if "emis" in tables else set()
    return "0002" if "first_due_date" in emi_cols else "0001"


def detect_rebased_revision(engine: Engine) -> str | None:
    """Identify the pre-pull local 0003/0004 history, whose numbers now mean M13/phone.

    Those databases have phone verification, but no M13 goals table. Never infer
    this from a revision number alone: a fresh merged-chain 0004 also exists.
    """
    current = current_revision(engine)
    if current not in ("0003", "0004"):
        return None
    insp = inspect(engine)
    if "goals" in insp.get_table_names():
        return None
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "phone_verified_at" not in user_cols:
        return None
    return current


def sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    p = url.removeprefix("sqlite:///")
    return None if p in ("", ":memory:") else Path(p)


def backup_sqlite(url: str, label: str) -> Path | None:
    """Consistent online copy using SQLite's backup API (safe with WAL and open connections)."""
    src = sqlite_path(url)
    if src is None or not src.exists():
        return None
    dest_dir = get_settings().data_dir / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}-{datetime.now():%Y%m%d-%H%M%S}-{label}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    dest.chmod(0o600)
    log.info("Database backed up before migration → %s", dest)
    return dest


def upgrade_to_head(engine: Engine, url: str | None = None) -> dict:
    url = url or str(engine.url.render_as_string(hide_password=False))
    cfg = alembic_config(url)
    head = head_revision(cfg)
    legacy = detect_legacy_revision(engine)
    rebased = detect_rebased_revision(engine)
    backup = None
    if rebased:
        backup = backup_sqlite(url, f"pre-rebase-{head}")
        if backup is None and not url.startswith("sqlite"):
            log.warning("Rebasing old migration revision %s. Take a database backup first (e.g. pg_dump) in production.", rebased)
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            log.info("Pre-pull migration history %s detected; stamping 0002 after backup", rebased)
            command.stamp(cfg, "0002")
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        if legacy:
            log.info("Pre-Alembic database detected; stamping revision %s (no schema change)", legacy)
            command.stamp(cfg, legacy)
    current = current_revision(engine)
    if current != head:
        if current is not None:
            backup = backup or backup_sqlite(url, f"pre-{head}")
            if backup is None and not url.startswith("sqlite"):
                log.warning("Applying migrations %s → %s. Take a database backup first (e.g. pg_dump) in production.", current, head)
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
    cfg.attributes.pop("connection", None)
    return {"from": legacy if legacy else rebased or current, "to": head, "stamped_legacy": legacy,
            "rebased_from": rebased, "backup": str(backup) if backup else None}


def _cli(argv: list[str]) -> int:
    from app.db import engine

    settings = get_settings()
    cmd = argv[0] if argv else "status"
    cfg = alembic_config(settings.database_url)
    if cmd == "status":
        print(f"current: {current_revision(engine) or detect_legacy_revision(engine) or 'empty'}  head: {head_revision(cfg)}")
    elif cmd == "upgrade":
        print(upgrade_to_head(engine, settings.database_url))
    elif cmd == "backup":
        print(backup_sqlite(settings.database_url, "manual") or "Not a SQLite file database — use pg_dump for PostgreSQL.")
    elif cmd == "restore" and len(argv) == 2:
        target = sqlite_path(settings.database_url)
        src = Path(argv[1])
        if target is None or not src.exists():
            print("Restore supports SQLite file databases only, from an existing backup file.")
            return 1
        backup_sqlite(settings.database_url, "pre-restore")
        engine.dispose()
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        shutil.copyfile(src, target)
        print(f"Restored {target} from {src}. Restart the API.")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(_cli(sys.argv[1:]))
