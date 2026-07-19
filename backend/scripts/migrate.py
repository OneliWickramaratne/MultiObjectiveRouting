from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.services.migration_service import alembic_config  # noqa: E402
from app import models  # noqa: E402,F401


def validate_existing_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Existing database cannot be stamped because tables are missing: "
            + ", ".join(sorted(missing_tables))
        )

    column_errors: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        expected_columns = set(table.columns.keys())
        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = expected_columns - existing_columns
        if missing_columns:
            column_errors.append(
                f"{table_name}: {', '.join(sorted(missing_columns))}"
            )
    if column_errors:
        raise RuntimeError(
            "Existing database cannot be stamped because columns are missing: "
            + "; ".join(column_errors)
        )


def bootstrap() -> None:
    config = alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables:
        command.upgrade(config, "head")
        return
    application_tables = tables & set(Base.metadata.tables)
    if not application_tables:
        # PostGIS may create spatial_ref_sys before the application schema.
        command.upgrade(config, "head")
        return
    validate_existing_schema()
    command.stamp(config, "0001_initial_schema")
    command.upgrade(config, "head")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hospital DSS database migrations")
    parser.add_argument(
        "action",
        choices=("bootstrap", "upgrade", "current", "history", "downgrade"),
    )
    parser.add_argument(
        "revision",
        nargs="?",
        default=None,
        help="Revision for upgrade/downgrade; defaults to head or -1.",
    )
    args = parser.parse_args()
    config = alembic_config()

    if args.action == "bootstrap":
        bootstrap()
    elif args.action == "upgrade":
        command.upgrade(config, args.revision or "head")
    elif args.action == "downgrade":
        command.downgrade(config, args.revision or "-1")
    elif args.action == "current":
        command.current(config, verbose=True)
    else:
        command.history(config, verbose=True)


if __name__ == "__main__":
    main()
