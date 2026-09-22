"""doctor directory and explainable matching

Revision ID: 1b8e4d6f9a20
Revises: 0a7f3c9d2e51
"""

import sqlalchemy as sa

from alembic import op

revision = "1b8e4d6f9a20"
down_revision = "0a7f3c9d2e51"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("doctor_profiles") as batch:
        batch.add_column(sa.Column("department", sa.String(64), nullable=True))
        batch.add_column(sa.Column("primary_specialty", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("subspecialties_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("expertise_tags_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("years_of_experience", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("languages_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "consultation_types_json", sa.JSON(), nullable=False, server_default='["IN_PERSON"]'
            )
        )
        batch.add_column(
            sa.Column(
                "availability_status", sa.String(24), nullable=False, server_default="UNKNOWN"
            )
        )
        batch.add_column(
            sa.Column("availability_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "directory_version", sa.String(80), nullable=False, server_default="demo_doctors_v1"
            )
        )
        batch.add_column(
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"))
        batch.create_index("ix_doctor_profiles_primary_specialty", ["primary_specialty"])
    op.create_table(
        "doctor_match_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.String(),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clinical_routing_result_id",
            sa.String(),
            sa.ForeignKey("clinical_routing_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mediroute_result_id",
            sa.String(),
            sa.ForeignKey("mediroute_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("facility_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("required_specialty", sa.String(64), nullable=False),
        sa.Column("directory_version", sa.String(80), nullable=False),
        sa.Column("protocol_version", sa.String(32), nullable=False),
        sa.Column("input_signature", sa.String(64), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column(
            "selected_doctor_id",
            sa.String(),
            sa.ForeignKey("doctor_profiles.doctor_user_id"),
            nullable=True,
        ),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("input_signature", name="uq_doctor_match_signature"),
    )
    for column in ("session_id", "patient_id", "facility_id"):
        op.create_index(f"ix_doctor_match_results_{column}", "doctor_match_results", [column])
    op.create_table(
        "doctor_match_recommendations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "doctor_match_result_id",
            sa.String(),
            sa.ForeignKey("doctor_match_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(),
            sa.ForeignKey("doctor_profiles.doctor_user_id"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("eligibility_reasons_json", sa.JSON(), nullable=False),
        sa.Column("ranking_reasons_json", sa.JSON(), nullable=False),
        sa.Column("score_components_json", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("doctor_match_result_id", "doctor_id", name="uq_doctor_match_doctor"),
    )
    op.create_index(
        "ix_doctor_match_recommendations_result",
        "doctor_match_recommendations",
        ["doctor_match_result_id"],
    )
    op.create_index(
        "ix_doctor_match_recommendations_doctor", "doctor_match_recommendations", ["doctor_id"]
    )


def downgrade():
    op.drop_table("doctor_match_recommendations")
    op.drop_table("doctor_match_results")
    with op.batch_alter_table("doctor_profiles") as batch:
        batch.drop_index("ix_doctor_profiles_primary_specialty")
        for name in (
            "metadata",
            "is_demo",
            "directory_version",
            "availability_revision",
            "availability_status",
            "consultation_types_json",
            "languages_json",
            "years_of_experience",
            "expertise_tags_json",
            "subspecialties_json",
            "primary_specialty",
            "department",
        ):
            batch.drop_column(name)
