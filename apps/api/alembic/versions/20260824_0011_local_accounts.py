"""Replace invitation redemption with locally registered accounts.

Revision ID: 20260824_0011
Revises: 20260823_0010
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0011"
down_revision: str | None = "20260823_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    op.execute(
        """
        UPDATE users
        SET username = 'legacy_' || substring(replace(id, '-', '') from 1 for 32),
            password_hash = 'disabled$' || id
        """
    )
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.drop_index("ix_user_invites_user_id", table_name="user_invites")
    op.drop_index("ix_user_invites_status", table_name="user_invites")
    op.drop_table("user_invites")


def downgrade() -> None:
    op.create_table(
        "user_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("uses_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_user_invite_code_hash"),
    )
    op.create_index("ix_user_invites_status", "user_invites", ["status"])
    op.create_index("ix_user_invites_user_id", "user_invites", ["user_id"])
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
