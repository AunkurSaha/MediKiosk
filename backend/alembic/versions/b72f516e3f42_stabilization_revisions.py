"""Version alert evidence and document reviews without rewriting source data."""
import sqlalchemy as sa

from alembic import op

revision = "b72f516e3f42"
down_revision = "a61e405d2e31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alerts", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_extractions", sa.Column("review_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("document_extractions", "review_version")
    op.drop_column("alerts", "revision")
