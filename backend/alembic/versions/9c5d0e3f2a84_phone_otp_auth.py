"""Add phone OTP authentication tables and user phone columns.

Revision ID: 9c5d0e3f2a84
Revises: 8b4e9c2d1f73
Create Date: 2026-09-11 17:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "9c5d0e3f2a84"
down_revision = "8b4e9c2d1f73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add phone columns to users and make email nullable
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column("phone_number", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("phone_verified", sa.Boolean(), server_default="0", nullable=False),
        )
        batch_op.add_column(
            sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        batch_op.create_index("ix_users_phone_number", ["phone_number"], unique=True)

    # Create otp_challenges table
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("phone_number", sa.String(length=32), nullable=False, index=True),
        sa.Column("purpose", sa.String(length=32), server_default="login", nullable=False),
        sa.Column("otp_salt", sa.String(length=64), nullable=False),
        sa.Column("otp_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
    )

    # Create auth_sessions table
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_table("otp_challenges")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_phone_number")
        batch_op.drop_column("phone_verified_at")
        batch_op.drop_column("phone_verified")
        batch_op.drop_column("phone_number")
