"""Preserve one normalization snapshot per immutable source answer."""

import sqlalchemy as sa

from alembic import op

revision = "e43b205c0f13"
down_revision = "d31a204b9e02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "normalization_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column(
            "source_answer_id", sa.String(), sa.ForeignKey("interview_answers.id"), nullable=False
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_version", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("source_answer_id", name="uq_normalization_source_answer"),
    )
    op.create_index("ix_normalization_results_session_id", "normalization_results", ["session_id"])


def downgrade():
    op.drop_table("normalization_results")
