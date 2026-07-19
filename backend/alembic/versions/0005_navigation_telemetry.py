"""Add smooth navigation telemetry fields.

Revision ID: 0005_navigation_telemetry
Revises: 0004_production_auth
Create Date: 2026-07-13
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_navigation_telemetry"
down_revision: str | None = "0004_production_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ambulances") as batch_op:
        batch_op.add_column(sa.Column("heading_degrees", sa.Float(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("speed_kph", sa.Float(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("route_progress_m", sa.Float(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("navigation_leg", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("telemetry_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ambulances") as batch_op:
        batch_op.drop_column("telemetry_updated_at")
        batch_op.drop_column("navigation_leg")
        batch_op.drop_column("route_progress_m")
        batch_op.drop_column("speed_kph")
        batch_op.drop_column("heading_degrees")
