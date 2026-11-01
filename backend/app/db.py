from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Serverless Postgres (Neon) closes idle connections and scales to zero: test a pooled connection before use and retire
        # old ones, so the first request after a quiet period reconnects instead of failing with "connection closed".
        s = get_settings()
        kwargs.update(pool_pre_ping=True, pool_recycle=s.db_pool_recycle_seconds, pool_size=s.db_pool_size,
                      max_overflow=s.db_max_overflow)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Bring the schema to the latest Alembic revision (with a pre-migration backup for SQLite files).

    Set AUTO_MIGRATE=false to manage migrations manually (`uv run python -m app.migrate upgrade`).
    """
    from app import models  # noqa: F401  (register tables)
    from app.migrate import upgrade_to_head

    settings = get_settings()
    if settings.auto_migrate:
        upgrade_to_head(engine, settings.database_url)
