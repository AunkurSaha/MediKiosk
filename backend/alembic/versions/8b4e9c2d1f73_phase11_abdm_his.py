"""Add Phase 11 ABDM records table.

Revision ID: 8b4e9c2d1f73
Revises: 7a3e8b1c4f92
Create Date: 2026-09-10 21:40:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "8b4e9c2d1f73"
down_revision = "7a3e8b1c4f92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abdm_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "patient_id",
            sa.String(),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("abha_number", sa.String(length=32), nullable=True),
        sa.Column("abha_address", sa.String(length=128), nullable=True),
        sa.Column(
            "abha_status",
            sa.String(length=32),
            server_default="unverified",
            nullable=False,
            index=True,
        ),
        sa.Column("care_context_reference", sa.String(length=128), nullable=True),
        sa.Column("care_context_display", sa.String(length=256), nullable=True),
        sa.Column(
            "care_context_status",
            sa.String(length=32),
            server_default="unlinked",
            nullable=False,
            index=True,
        ),
        sa.Column("care_context_linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "his_dispatch_status",
            sa.String(length=32),
            server_default="not_dispatched",
            nullable=False,
            index=True,
        ),
        sa.Column("his_dispatch_receipt", sa.Text(), nullable=True),
        sa.Column("his_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_artefact_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("abdm_records")
