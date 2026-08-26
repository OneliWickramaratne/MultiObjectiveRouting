from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


DATABASE_URL = settings.database_url
# Some hosts (Railway, Render, Heroku-style) hand back a bare postgres:// or
# postgresql:// URL with no driver specified. SQLAlchemy then defaults to the
# old psycopg2, which this project never installs (it uses psycopg v3
# throughout local dev and Docker) — so explicitly normalize to psycopg here,
# regardless of which host's URL format we're given.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args: dict = {"check_same_thread": False} if is_sqlite else {}
engine_options: dict = {
    "connect_args": connect_args,
    "future": True,
    "pool_pre_ping": True,
}
if not is_sqlite:
    connect_args["options"] = (
        f"-c statement_timeout={settings.db_statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={settings.db_idle_transaction_timeout_ms}"
    )
    engine_options.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
    )

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
