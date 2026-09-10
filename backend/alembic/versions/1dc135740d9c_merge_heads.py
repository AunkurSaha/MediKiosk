"""merge heads

Revision ID: 1dc135740d9c
Revises: b72f516e3f42, f27074ce1ef6
Create Date: 2026-09-10 09:38:34.888744

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "1dc135740d9c"
down_revision: Union[str, None] = ("b72f516e3f42", "f27074ce1ef6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
