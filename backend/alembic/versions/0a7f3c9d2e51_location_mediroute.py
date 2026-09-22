"""location and deterministic facility routing

Revision ID: 0a7f3c9d2e51
Revises: f3a2c7d84b19
"""

import sqlalchemy as sa

from alembic import op

revision = "0a7f3c9d2e51"
down_revision = "f3a2c7d84b19"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hospitals") as batch:
        batch.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("locality", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("facility_type", sa.String(length=80), nullable=True))
        batch.add_column(
            sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "emergency_available", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column("opening_status", sa.String(length=20), nullable=False, server_default="OPEN")
        )
        batch.add_column(
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("directory_version", sa.String(length=80), nullable=True))
    op.create_table(
        "patient_routing_locations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("locality", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("precision", sa.String(length=32), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_patient_routing_location_session"),
    )
    op.create_index(
        "ix_patient_routing_locations_session_id", "patient_routing_locations", ["session_id"]
    )
    op.create_index(
        "ix_patient_routing_locations_patient_id", "patient_routing_locations", ["patient_id"]
    )
    op.create_table(
        "mediroute_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("clinical_routing_result_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("routing_state", sa.String(length=40), nullable=False),
        sa.Column("suggested_specialty", sa.String(length=64), nullable=False),
        sa.Column("directory_version", sa.String(length=80), nullable=False),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("input_signature", sa.String(length=64), nullable=False),
        sa.Column("required_specialty", sa.String(length=64), nullable=False),
        sa.Column("required_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("preferred_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clinical_routing_result_id"], ["clinical_routing_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["patient_routing_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("input_signature", name="uq_mediroute_input_signature"),
    )
    op.create_index("ix_mediroute_results_session_id", "mediroute_results", ["session_id"])
    op.create_index("ix_mediroute_results_patient_id", "mediroute_results", ["patient_id"])
    op.create_index(
        "ix_mediroute_results_clinical_routing_result_id",
        "mediroute_results",
        ["clinical_routing_result_id"],
    )
    op.create_table(
        "mediroute_recommendations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("mediroute_result_id", sa.String(), nullable=False),
        sa.Column("facility_id", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("eligibility_reasons_json", sa.JSON(), nullable=False),
        sa.Column("ranking_reasons_json", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["hospitals.id"]),
        sa.ForeignKeyConstraint(
            ["mediroute_result_id"], ["mediroute_results.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mediroute_result_id", "facility_id", name="uq_mediroute_result_facility"
        ),
    )
    op.create_index(
        "ix_mediroute_recommendations_mediroute_result_id",
        "mediroute_recommendations",
        ["mediroute_result_id"],
    )
    op.create_index(
        "ix_mediroute_recommendations_facility_id", "mediroute_recommendations", ["facility_id"]
    )


def downgrade():
    op.drop_table("mediroute_recommendations")
    op.drop_table("mediroute_results")
    op.drop_table("patient_routing_locations")
    with op.batch_alter_table("hospitals") as batch:
        for name in (
            "directory_version",
            "is_demo",
            "opening_status",
            "emergency_available",
            "capabilities_json",
            "facility_type",
            "locality",
            "longitude",
            "latitude",
        ):
            batch.drop_column(name)
