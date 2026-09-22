"""Add secure persisted pre-arrival packet lifecycle.

Revision ID: 2d9a6f8c1b73
Revises: 7c4f2a9d1e60
"""

import sqlalchemy as sa

from alembic import op

revision = "2d9a6f8c1b73"
down_revision = "7c4f2a9d1e60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pre_arrival_packets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("hospital_id", sa.String(), nullable=False),
        sa.Column("doctor_id", sa.String(), nullable=False),
        sa.Column("packet_version", sa.String(length=16), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("handoff_token_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handoff_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctor_profiles.doctor_user_id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_token_hash"),
        sa.UniqueConstraint("session_id", "packet_version", name="uq_pre_arrival_packet_version"),
    )
    for column in ("session_id", "patient_id", "hospital_id", "doctor_id", "handoff_token_hash"):
        op.create_index(f"ix_pre_arrival_packets_{column}", "pre_arrival_packets", [column])


def downgrade():
    op.drop_table("pre_arrival_packets")
