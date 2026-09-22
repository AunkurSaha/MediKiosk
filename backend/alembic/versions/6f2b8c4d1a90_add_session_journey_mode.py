"""Persist patient journey mode and allow on-site doctor matching.

Revision ID: 6f2b8c4d1a90
Revises: 2d9a6f8c1b73
"""

import sqlalchemy as sa

from alembic import op

revision = "6f2b8c4d1a90"
down_revision = "2d9a6f8c1b73"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(
            sa.Column(
                "journey_mode",
                sa.String(length=24),
                nullable=False,
                server_default="PRE_ARRIVAL",
            )
        )
    with op.batch_alter_table("doctor_match_results") as batch:
        batch.alter_column("mediroute_result_id", existing_type=sa.String(), nullable=True)


def downgrade():
    with op.batch_alter_table("doctor_match_results") as batch:
        batch.alter_column("mediroute_result_id", existing_type=sa.String(), nullable=False)
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("journey_mode")
