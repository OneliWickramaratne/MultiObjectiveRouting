"""Align legacy SQLite databases with the model constraints.

Revision ID: 0002_align_legacy_sqlite
Revises: 0001_initial_schema
Create Date: 2026-07-13
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_align_legacy_sqlite"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_foreign_key(
    inspector: sa.Inspector,
    table_name: str,
    constrained_columns: tuple[str, ...],
    referred_table: str,
) -> bool:
    return any(
        tuple(foreign_key.get("constrained_columns") or ()) == constrained_columns
        and foreign_key.get("referred_table") == referred_table
        for foreign_key in inspector.get_foreign_keys(table_name)
    )


def _has_unique_constraint(
    inspector: sa.Inspector,
    table_name: str,
    columns: tuple[str, ...],
) -> bool:
    return any(
        tuple(constraint.get("column_names") or ()) == columns
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _column_is_nullable(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
) -> bool:
    return next(
        column["nullable"]
        for column in inspector.get_columns(table_name)
        if column["name"] == column_name
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    inspector = sa.inspect(bind)

    if not _has_foreign_key(inspector, "users", ("ambulance_id",), "ambulances"):
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.create_foreign_key(
                "fk_users_ambulance_id_ambulances",
                "ambulances",
                ["ambulance_id"],
                ["id"],
            )

    transfer_needs_bed_fk = not _has_foreign_key(
        inspector,
        "transfer_requests",
        ("assigned_bed_id",),
        "icu_beds",
    )
    transfer_needs_not_null = _column_is_nullable(
        inspector,
        "transfer_requests",
        "patient_isolation_required",
    )
    if transfer_needs_bed_fk or transfer_needs_not_null:
        with op.batch_alter_table("transfer_requests", recreate="always") as batch_op:
            if transfer_needs_bed_fk:
                batch_op.create_foreign_key(
                    "fk_transfer_requests_assigned_bed_id_icu_beds",
                    "icu_beds",
                    ["assigned_bed_id"],
                    ["id"],
                )
            if transfer_needs_not_null:
                batch_op.alter_column(
                    "patient_isolation_required",
                    existing_type=sa.Boolean(),
                    nullable=False,
                )

    patient_needs_transfer_fk = not _has_foreign_key(
        inspector,
        "patient_records",
        ("transfer_id",),
        "transfer_requests",
    )
    patient_needs_unique = not _has_unique_constraint(
        inspector,
        "patient_records",
        ("bed_id",),
    )
    patient_needs_not_null = _column_is_nullable(
        inspector,
        "patient_records",
        "isolation_required",
    )
    if patient_needs_unique:
        index_names = {index["name"] for index in inspector.get_indexes("patient_records")}
        if "uq_patient_records_bed_id" in index_names:
            op.drop_index("uq_patient_records_bed_id", table_name="patient_records")
    if patient_needs_transfer_fk or patient_needs_unique or patient_needs_not_null:
        with op.batch_alter_table("patient_records", recreate="always") as batch_op:
            if patient_needs_transfer_fk:
                batch_op.create_foreign_key(
                    "fk_patient_records_transfer_id_transfer_requests",
                    "transfer_requests",
                    ["transfer_id"],
                    ["id"],
                )
            if patient_needs_unique:
                batch_op.create_unique_constraint(
                    "uq_patient_records_bed_id",
                    ["bed_id"],
                )
            if patient_needs_not_null:
                batch_op.alter_column(
                    "isolation_required",
                    existing_type=sa.Boolean(),
                    nullable=False,
                )

    bed_needs_unique = not _has_unique_constraint(
        inspector,
        "icu_beds",
        ("hospital_id", "bed_no"),
    )
    if bed_needs_unique:
        index_names = {index["name"] for index in inspector.get_indexes("icu_beds")}
        if "uq_icu_beds_hospital_bed_no" in index_names:
            op.drop_index("uq_icu_beds_hospital_bed_no", table_name="icu_beds")
        with op.batch_alter_table("icu_beds", recreate="always") as batch_op:
            batch_op.create_unique_constraint(
                "uq_icu_beds_hospital_bed_no",
                ["hospital_id", "bed_no"],
            )


def downgrade() -> None:
    # The alignment migration only repairs legacy SQLite drift. Reversing it
    # would deliberately reintroduce missing integrity constraints.
    pass
