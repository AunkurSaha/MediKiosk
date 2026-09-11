"""Add user_id to sessions table for patient ownership.

Revision ID: a1b2c3d4e5f6
Revises: 9c5d0e3f2a84
Create Date: 2026-09-11 17:50:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "9c5d0e3f2a84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_sessions_user_id", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_sessions_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("fk_sessions_user_id", type_="foreignkey")
        batch_op.drop_index("ix_sessions_user_id")
        batch_op.drop_column("user_id")
