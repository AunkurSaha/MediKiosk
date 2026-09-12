"""add embedding metadata to knowledge chunks

Revision ID: 139bb8bf648a
Revises: 061f1249a7d4
Create Date: 2026-09-12 22:17:13.463087

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '139bb8bf648a'
down_revision: Union[str, None] = '061f1249a7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("embedding_provider", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("embedding_dimension", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.drop_column("embedding_dimension")
        batch_op.drop_column("embedding_provider")
