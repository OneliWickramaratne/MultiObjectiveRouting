"""Allow patient records to be deleted after discharge.

bed_lifecycle_events.patient_id previously had no ON DELETE policy, which
meant a patient record could never be deleted once any lifecycle event
(created automatically the moment a bed is reserved) referenced it —
making "remove patient" / bed discharge permanently fail once a bed had
ever been occupied. This changes the constraint to ON DELETE SET NULL:
historical events keep their other details (status, reason, transfer_id)
but their patient_id reference is cleared once that patient is removed,
which is the correct semantics for an audit trail referencing a
short-lived per-occupancy record.

Revision ID: 0006_patient_delete_setnull
Revises: 0005_navigation_telemetry
Create Date: 2026-08-14
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "0006_patient_delete_setnull"
down_revision: str | None = "0005_navigation_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bed_lifecycle_events") as batch_op:
        batch_op.drop_constraint("bed_lifecycle_events_patient_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "bed_lifecycle_events_patient_id_fkey",
            "patient_records",
            ["patient_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("bed_lifecycle_events") as batch_op:
        batch_op.drop_constraint("bed_lifecycle_events_patient_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "bed_lifecycle_events_patient_id_fkey",
            "patient_records",
            ["patient_id"],
            ["id"],
        )
