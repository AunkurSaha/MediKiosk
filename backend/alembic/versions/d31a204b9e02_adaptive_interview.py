"""Pin adaptive flow snapshots, cursor/revision, and retry receipts. Preserve all Phase 1 rows."""

import sqlalchemy as sa

from alembic import op

revision = "d31a204b9e02"
down_revision = "c92f104a7e21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_runs",
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("flow_version", sa.String(), nullable=False),
        sa.Column("flow_snapshot", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.String(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "interview_requests",
        sa.Column(
            "session_id", sa.String(), sa.ForeignKey("interview_runs.session_id"), primary_key=True
        ),
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("payload_hash", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("interview_requests")
    op.drop_table("interview_runs")
