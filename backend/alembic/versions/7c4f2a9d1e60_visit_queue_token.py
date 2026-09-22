"""Persist daily doctor queue reservation tokens.

Revision ID: 7c4f2a9d1e60
Revises: 1b8e4d6f9a20
"""

import sqlalchemy as sa

from alembic import op

revision = "7c4f2a9d1e60"
down_revision = "1b8e4d6f9a20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("doctor_queue_entries") as batch:
        batch.add_column(sa.Column("patient_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("service_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("sequence_number", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("visit_token", sa.String(40), nullable=True))
        batch.create_foreign_key("fk_queue_patient", "patients", ["patient_id"], ["id"])
        batch.create_unique_constraint(
            "uq_doctor_daily_queue_sequence",
            ["hospital_id", "doctor_id", "service_date", "sequence_number"],
        )
        batch.create_index("ix_doctor_queue_entries_patient_id", ["patient_id"])
        batch.create_index("ix_doctor_queue_entries_service_date", ["service_date"])


def downgrade():
    with op.batch_alter_table("doctor_queue_entries") as batch:
        batch.drop_index("ix_doctor_queue_entries_service_date")
        batch.drop_index("ix_doctor_queue_entries_patient_id")
        batch.drop_constraint("uq_doctor_daily_queue_sequence", type_="unique")
        batch.drop_constraint("fk_queue_patient", type_="foreignkey")
        batch.drop_column("visit_token")
        batch.drop_column("sequence_number")
        batch.drop_column("service_date")
        batch.drop_column("patient_id")
