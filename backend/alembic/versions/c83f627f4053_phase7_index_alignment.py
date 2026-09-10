"""Align indexes with existing fact models without rewriting rows."""

from alembic import op

revision = "c83f627f4053"
down_revision = "1dc135740d9c"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("medication_fact", "lab_fact", "timeline_fact"):
        op.create_index(f"ix_{table}_created_at", table, ["created_at"])


def downgrade():
    for table in ("timeline_fact", "lab_fact", "medication_fact"):
        op.drop_index(f"ix_{table}_created_at", table_name=table)
