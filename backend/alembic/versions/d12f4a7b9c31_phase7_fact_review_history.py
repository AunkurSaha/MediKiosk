"""Add Phase 7 fact fields and additive review history.

Revision ID: d12f4a7b9c31
Revises: c83f627f4053
"""

import sqlalchemy as sa

from alembic import op

revision = "d12f4a7b9c31"
down_revision = "c83f627f4053"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("medication_fact", sa.Column("unit", sa.String(), nullable=True))
    op.add_column(
        "medication_fact", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "medication_fact", sa.Column("end_date", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "medication_fact",
        sa.Column("review_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "lab_fact",
        sa.Column("review_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "medical_fact_revisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("fact_type", sa.String(), nullable=False),
        sa.Column("fact_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("original_data", sa.JSON(), nullable=False),
        sa.Column("corrected_data", sa.JSON(), nullable=True),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_type", "fact_id", "version", name="uq_fact_revision_version"),
    )
    op.create_index(
        "ix_medical_fact_revisions_session_id",
        "medical_fact_revisions",
        ["session_id"],
    )
    op.create_index("ix_medical_fact_revisions_fact_id", "medical_fact_revisions", ["fact_id"])


def downgrade():
    op.drop_index("ix_medical_fact_revisions_fact_id", table_name="medical_fact_revisions")
    op.drop_index("ix_medical_fact_revisions_session_id", table_name="medical_fact_revisions")
    op.drop_table("medical_fact_revisions")
    op.drop_column("lab_fact", "review_version")
    op.drop_column("medication_fact", "review_version")
    op.drop_column("medication_fact", "end_date")
    op.drop_column("medication_fact", "start_date")
    op.drop_column("medication_fact", "unit")
