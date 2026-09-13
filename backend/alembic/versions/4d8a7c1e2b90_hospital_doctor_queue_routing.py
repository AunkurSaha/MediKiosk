"""hospital doctor specialty and queue routing

Revision ID: 4d8a7c1e2b90
Revises: 139bb8bf648a
"""

import sqlalchemy as sa

from alembic import op

revision = "4d8a7c1e2b90"
down_revision = "139bb8bf648a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hospitals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address", sa.String(240)),
        sa.Column("city", sa.String(100)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("code", name="uq_hospitals_code"),
    )
    op.create_index("ix_hospitals_code", "hospitals", ["code"], unique=True)
    op.bulk_insert(
        sa.table("hospitals", sa.column("id"), sa.column("code"), sa.column("name"), sa.column("address"), sa.column("city"), sa.column("active")),
        [
            {"id": "10000000-0000-4000-8000-000000000001", "code": "DEMO-KOL-01", "name": "MediKiosk City Hospital", "address": "Central Kolkata", "city": "Kolkata", "active": True},
            {"id": "10000000-0000-4000-8000-000000000002", "code": "DEMO-KOL-02", "name": "MediKiosk Lake Medical Centre", "address": "South Kolkata", "city": "Kolkata", "active": True},
            {"id": "10000000-0000-4000-8000-000000000099", "code": "DEMO-INACTIVE", "name": "Inactive Demo Hospital", "address": None, "city": "Kolkata", "active": False},
        ],
    )
    op.create_table(
        "doctor_profiles",
        sa.Column("doctor_user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("qualification", sa.String(160)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("accepting_patients", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "doctor_hospital_memberships",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("doctor_id", sa.String(), sa.ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("doctor_id", "hospital_id", name="uq_doctor_hospital"),
    )
    op.create_index("ix_doctor_hospital_doctor", "doctor_hospital_memberships", ["doctor_id"])
    op.create_index("ix_doctor_hospital_hospital", "doctor_hospital_memberships", ["hospital_id"])
    op.create_table(
        "doctor_specialty_memberships",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("doctor_id", sa.String(), sa.ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("specialty_code", sa.String(40), nullable=False),
        sa.UniqueConstraint("doctor_id", "specialty_code", name="uq_doctor_specialty"),
    )
    op.create_index("ix_doctor_specialty_doctor", "doctor_specialty_memberships", ["doctor_id"])
    op.create_index("ix_doctor_specialty_code", "doctor_specialty_memberships", ["specialty_code"])
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("hospital_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("selected_doctor_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_sessions_hospital", "hospitals", ["hospital_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_sessions_selected_doctor", "doctor_profiles", ["selected_doctor_id"], ["doctor_user_id"], ondelete="SET NULL")
        batch.create_index("ix_sessions_hospital_id", ["hospital_id"])
        batch.create_index("ix_sessions_selected_doctor_id", ["selected_doctor_id"])
    op.create_table(
        "doctor_queue_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("doctor_id", sa.String(), sa.ForeignKey("doctor_profiles.doctor_user_id"), nullable=False),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="WAITING"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("called_at", sa.DateTime(timezone=True)),
        sa.Column("consultation_started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    )
    for column in ("session_id", "doctor_id", "hospital_id", "status"):
        op.create_index(f"ix_doctor_queue_entries_{column}", "doctor_queue_entries", [column], unique=column == "session_id")


def downgrade() -> None:
    op.drop_table("doctor_queue_entries")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_sessions_selected_doctor", type_="foreignkey")
        batch.drop_constraint("fk_sessions_hospital", type_="foreignkey")
        batch.drop_index("ix_sessions_selected_doctor_id")
        batch.drop_index("ix_sessions_hospital_id")
        batch.drop_column("selected_doctor_id")
        batch.drop_column("hospital_id")
    op.drop_table("doctor_specialty_memberships")
    op.drop_table("doctor_hospital_memberships")
    op.drop_table("doctor_profiles")
    op.drop_index("ix_hospitals_code", table_name="hospitals")
    op.drop_table("hospitals")
