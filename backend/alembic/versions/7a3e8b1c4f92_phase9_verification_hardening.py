"""Add Phase 9 verification hardening fields and tables.

Revision ID: 7a3e8b1c4f92
Revises: 1915850a59d1
Create Date: 2026-09-10 20:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "7a3e8b1c4f92"
down_revision = "1915850a59d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add amendment columns to clinical_summaries
    with op.batch_alter_table("clinical_summaries") as batch:
        batch.add_column(sa.Column("amended_text", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "amended_by",
                sa.String(),
                sa.ForeignKey("users.id", name="fk_clinical_summaries_amended_by_users"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("amended_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("amendment_notes", sa.Text(), nullable=True))

    # 2. Create field_verifications table
    op.create_table(
        "field_verifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("field_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("field_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), server_default="unverified", nullable=False, index=True),
        sa.Column("verified_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "field_type", "field_id", name="uq_session_field_verification"),
    )

    # 3. Create field_verification_revisions table
    op.create_table(
        "field_verification_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("verification_id", sa.String(), sa.ForeignKey("field_verifications.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("field_verification_revisions")
    op.drop_table("field_verifications")
    with op.batch_alter_table("clinical_summaries") as batch:
        batch.drop_column("amendment_notes")
        batch.drop_column("amended_at")
        batch.drop_column("amended_by")
        batch.drop_column("amended_text")
