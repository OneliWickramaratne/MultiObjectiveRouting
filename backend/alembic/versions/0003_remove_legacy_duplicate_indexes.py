"""Remove redundant legacy SQLite unique indexes.

Revision ID: 0003_remove_legacy_indexes
Revises: 0002_align_legacy_sqlite
Create Date: 2026-07-13
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_remove_legacy_indexes"
down_revision: str | None = "0002_align_legacy_sqlite"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    inspector = sa.inspect(bind)
    indexes = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in ("icu_beds", "patient_records")
    }
    if "uq_icu_beds_hospital_bed_no" in indexes["icu_beds"]:
        op.drop_index("uq_icu_beds_hospital_bed_no", table_name="icu_beds")
    if "uq_patient_records_bed_id" in indexes["patient_records"]:
        op.drop_index("uq_patient_records_bed_id", table_name="patient_records")


def downgrade() -> None:
    pass
