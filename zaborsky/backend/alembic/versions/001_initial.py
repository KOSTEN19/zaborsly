"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rtsp_url", sa.String(length=512), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_online", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "vehicle_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate", sa.String(length=16), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_photo", sa.String(length=512), nullable=True),
        sa.Column("exit_photo", sa.String(length=512), nullable=True),
        sa.Column("status", sa.Enum("on_site", "completed", "unknown", name="sessionstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vehicle_sessions_plate", "vehicle_sessions", ["plate"])
    op.create_index("ix_vehicle_sessions_status", "vehicle_sessions", ["status"])
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("plate", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("direction", sa.Enum("entry", "exit", "unknown", name="direction"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("photo_path", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detections_plate", "detections", ["plate"])
    op.create_index("ix_detections_detected_at", "detections", ["detected_at"])


def downgrade() -> None:
    op.drop_index("ix_detections_detected_at", table_name="detections")
    op.drop_index("ix_detections_plate", table_name="detections")
    op.drop_table("detections")
    op.drop_index("ix_vehicle_sessions_status", table_name="vehicle_sessions")
    op.drop_index("ix_vehicle_sessions_plate", table_name="vehicle_sessions")
    op.drop_table("vehicle_sessions")
    op.drop_table("cameras")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
    op.execute("DROP TYPE IF EXISTS direction")
