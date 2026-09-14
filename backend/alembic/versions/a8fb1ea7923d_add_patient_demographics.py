"""add patient demographics

Revision ID: a8fb1ea7923d
Revises: 4d8a7c1e2b90
Create Date: 2026-09-14 14:04:53.764095

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8fb1ea7923d"
down_revision: Union[str, None] = "4d8a7c1e2b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("gender", sa.String(length=32), nullable=True))
    op.add_column("patients", sa.Column("age_years", sa.Integer(), nullable=True))
    op.add_column("patients", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("patients", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_patients_gender",
        "patients",
        "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'other', 'prefer_not_to_say')",
    )
    op.create_check_constraint(
        "ck_patients_age_years", "patients", "age_years IS NULL OR age_years BETWEEN 0 AND 120"
    )
    op.create_check_constraint(
        "ck_patients_height_cm", "patients", "height_cm IS NULL OR height_cm BETWEEN 30 AND 250"
    )
    op.create_check_constraint(
        "ck_patients_weight_kg", "patients", "weight_kg IS NULL OR weight_kg BETWEEN 1 AND 500"
    )


def downgrade() -> None:
    op.drop_constraint("ck_patients_weight_kg", "patients", type_="check")
    op.drop_constraint("ck_patients_height_cm", "patients", type_="check")
    op.drop_constraint("ck_patients_age_years", "patients", type_="check")
    op.drop_constraint("ck_patients_gender", "patients", type_="check")
    op.drop_column("patients", "weight_kg")
    op.drop_column("patients", "height_cm")
    op.drop_column("patients", "age_years")
    op.drop_column("patients", "gender")
