"""Add Phase 8 draft summary enhancement fields.

Revision ID: 1915850a59d1
Revises: d12f4a7b9c31
Create Date: 2026-09-10 19:40:18.535833
"""

from alembic import op
import sqlalchemy as sa


revision = "1915850a59d1"
down_revision = "d12f4a7b9c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enhance clinical_summaries with confirmed_text, draft_provider, draft_version
    op.add_column("clinical_summaries", sa.Column("confirmed_text", sa.Text(), nullable=True))
    op.add_column(
        "clinical_summaries",
        sa.Column("draft_provider", sa.String(length=64), server_default="deterministic", nullable=False),
    )
    op.add_column(
        "clinical_summaries",
        sa.Column("draft_version", sa.Integer(), server_default="1", nullable=False),
    )

    # 2. Enhance summary_revisions with revision_type, actor_type, review_notes, structured_snapshot
    op.alter_column("summary_revisions", "actor_user_id", existing_type=sa.String(), nullable=True)
    op.add_column(
        "summary_revisions",
        sa.Column("revision_type", sa.String(length=32), server_default="edit", nullable=False),
    )
    op.add_column(
        "summary_revisions",
        sa.Column("actor_type", sa.String(length=32), server_default="DOCTOR", nullable=False),
    )
    op.add_column("summary_revisions", sa.Column("review_notes", sa.Text(), nullable=True))
    op.add_column("summary_revisions", sa.Column("structured_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("summary_revisions", "structured_snapshot")
    op.drop_column("summary_revisions", "review_notes")
    op.drop_column("summary_revisions", "actor_type")
    op.drop_column("summary_revisions", "revision_type")
    op.alter_column("summary_revisions", "actor_user_id", existing_type=sa.String(), nullable=False)

    op.drop_column("clinical_summaries", "draft_version")
    op.drop_column("clinical_summaries", "draft_provider")
    op.drop_column("clinical_summaries", "confirmed_text")
