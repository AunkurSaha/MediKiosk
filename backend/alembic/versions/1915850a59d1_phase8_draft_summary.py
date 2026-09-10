"""Add Phase 8 draft summary enhancement fields.

Revision ID: 1915850a59d1
Revises: d12f4a7b9c31
Create Date: 2026-09-10 19:40:18.535833
"""

import sqlalchemy as sa

from alembic import op

revision = "1915850a59d1"
down_revision = "d12f4a7b9c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enhance clinical_summaries with confirmed_text, draft_provider, draft_version
    with op.batch_alter_table("clinical_summaries") as batch:
        batch.add_column(sa.Column("confirmed_text", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("draft_provider", sa.String(length=64), server_default="deterministic", nullable=False)
        )
        batch.add_column(
            sa.Column("draft_version", sa.Integer(), server_default="1", nullable=False)
        )

    # 2. Enhance summary_revisions with revision_type, actor_type, review_notes, structured_snapshot
    with op.batch_alter_table("summary_revisions") as batch:
        batch.alter_column("actor_user_id", existing_type=sa.String(), nullable=True)
        batch.add_column(
            sa.Column("revision_type", sa.String(length=32), server_default="edit", nullable=False)
        )
        batch.add_column(
            sa.Column("actor_type", sa.String(length=32), server_default="DOCTOR", nullable=False)
        )
        batch.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("structured_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("summary_revisions") as batch:
        batch.drop_column("structured_snapshot")
        batch.drop_column("review_notes")
        batch.drop_column("actor_type")
        batch.drop_column("revision_type")
        batch.alter_column("actor_user_id", existing_type=sa.String(), nullable=False)

    with op.batch_alter_table("clinical_summaries") as batch:
        batch.drop_column("draft_version")
        batch.drop_column("draft_provider")
        batch.drop_column("confirmed_text")
