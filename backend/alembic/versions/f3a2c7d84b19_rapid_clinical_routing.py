"""rapid clinical routing

Revision ID: f3a2c7d84b19
Revises: e7c1d9a42f60
"""

import sqlalchemy as sa

from alembic import op

revision = "f3a2c7d84b19"
down_revision = "e7c1d9a42f60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rapid_routing_runs",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("complaint_input_json", sa.JSON(), nullable=True),
        sa.Column("chief_complaint", sa.String(length=64), nullable=True),
        sa.Column("complaint_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_rapid_routing_runs_patient_id", "rapid_routing_runs", ["patient_id"])
    op.create_index(
        "ix_rapid_routing_runs_chief_complaint", "rapid_routing_runs", ["chief_complaint"]
    )
    op.create_table(
        "clinical_routing_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("chief_complaint", sa.String(length=64), nullable=False),
        sa.Column("routing_state", sa.String(length=40), nullable=False),
        sa.Column("suggested_specialty", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("supporting_evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("triggered_rule_ids_json", sa.JSON(), nullable=False),
        sa.Column("questions_asked_json", sa.JSON(), nullable=False),
        sa.Column("questions_skipped_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_clinical_routing_results_patient_id", "clinical_routing_results", ["patient_id"]
    )
    op.create_index(
        "ix_clinical_routing_results_routing_state", "clinical_routing_results", ["routing_state"]
    )


def downgrade():
    op.drop_index(
        "ix_clinical_routing_results_routing_state", table_name="clinical_routing_results"
    )
    op.drop_index("ix_clinical_routing_results_patient_id", table_name="clinical_routing_results")
    op.drop_table("clinical_routing_results")
    op.drop_index("ix_rapid_routing_runs_chief_complaint", table_name="rapid_routing_runs")
    op.drop_index("ix_rapid_routing_runs_patient_id", table_name="rapid_routing_runs")
    op.drop_table("rapid_routing_runs")
