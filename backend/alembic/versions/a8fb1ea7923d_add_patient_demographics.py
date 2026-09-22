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
    with op.batch_alter_table("patients") as batch:
        batch.add_column(sa.Column("gender", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("age_years", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("height_cm", sa.Float(), nullable=True))
        batch.add_column(sa.Column("weight_kg", sa.Float(), nullable=True))
        batch.create_check_constraint(
            "ck_patients_gender",
            "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'other', 'prefer_not_to_say')",
        )
        batch.create_check_constraint(
            "ck_patients_age_years", "age_years IS NULL OR age_years BETWEEN 0 AND 120"
        )
        batch.create_check_constraint(
            "ck_patients_height_cm", "height_cm IS NULL OR height_cm BETWEEN 30 AND 250"
        )
        batch.create_check_constraint(
            "ck_patients_weight_kg", "weight_kg IS NULL OR weight_kg BETWEEN 1 AND 500"
        )


def downgrade() -> None:
    with op.batch_alter_table("patients") as batch:
        batch.drop_constraint("ck_patients_weight_kg", type_="check")
        batch.drop_constraint("ck_patients_height_cm", type_="check")
        batch.drop_constraint("ck_patients_age_years", type_="check")
        batch.drop_constraint("ck_patients_gender", type_="check")
        batch.drop_column("weight_kg")
        batch.drop_column("height_cm")
        batch.drop_column("age_years")
        batch.drop_column("gender")
