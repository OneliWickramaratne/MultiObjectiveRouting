from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.database import engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def migration_revisions() -> tuple[str | None, str]:
    script = ScriptDirectory.from_config(alembic_config())
    head_revision = script.get_current_head()
    if not head_revision:
        raise RuntimeError("Alembic migration history has no head revision")
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    return current_revision, head_revision


def assert_database_current() -> None:
    current_revision, head_revision = migration_revisions()
    if current_revision != head_revision:
        raise RuntimeError(
            "Database migration is not current: "
            f"database={current_revision or 'unversioned'}, expected={head_revision}. "
            "Run 'python -m alembic -c alembic.ini upgrade head'."
        )


def database_is_ready(require_current_revision: bool = False) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        if require_current_revision:
            assert_database_current()
        return True
    except Exception:
        return False
