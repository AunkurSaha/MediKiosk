"""Add Phase 1 audit, review revisions and session uniqueness.

Revision ID: c92f104a7e21
Revises: be34ca26f420
"""

import sqlalchemy as sa

from alembic import op

revision = "c92f104a7e21"
down_revision = "be34ca26f420"
branch_labels = None
depends_on = None


def upgrade():
    # Do not discard pre-existing records to satisfy the new constraints.
    for table in ("consents", "clinical_summaries"):
        duplicate = (
            op.get_bind()
            .execute(
                sa.text(f"SELECT session_id FROM {table} GROUP BY session_id HAVING COUNT(*) > 1")
            )
            .first()
        )
        if duplicate:
            raise RuntimeError(
                f"Duplicate sessions in {table}; reconcile records before migrating."
            )
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(f"uq_{table}_session", ["session_id"])
    with op.batch_alter_table("clinical_summaries") as batch:
        batch.create_foreign_key("fk_summary_reviewed_by", "users", ["reviewed_by"], ["id"])
        batch.create_foreign_key("fk_summary_confirmed_by", "users", ["confirmed_by"], ["id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_user_id", sa.String(), nullable=True),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_table(
        "summary_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "summary_id", sa.String(), sa.ForeignKey("clinical_summaries.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_text", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("summary_id", "version", name="uq_summary_revision_version"),
    )
    op.create_index("ix_summary_revisions_summary_id", "summary_revisions", ["summary_id"])


def downgrade():
    op.drop_table("summary_revisions")
    op.drop_table("audit_logs")
    with op.batch_alter_table("clinical_summaries") as batch:
        batch.drop_constraint("fk_summary_reviewed_by", type_="foreignkey")
        batch.drop_constraint("fk_summary_confirmed_by", type_="foreignkey")
    for table in ("clinical_summaries", "consents"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"uq_{table}_session", type_="unique")
