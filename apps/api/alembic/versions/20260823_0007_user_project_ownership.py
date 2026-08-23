"""Persist real users, per-user invites, and project ownership identities.

Revision ID: 20260823_0007
Revises: 20260822_0006
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0007"
down_revision: str | None = "20260822_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_status", "users", ["status"])
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

    # Preserve every existing internal/test owner as an explicit identity. The
    # application will only create new projects for authenticated active users.
    op.execute(
        """
        INSERT INTO users (id, display_name, role, status, created_at, last_login_at)
        SELECT
          p.owner_user_id,
          CASE WHEN p.owner_user_id = 'local-admin' THEN '内部管理员' ELSE p.owner_user_id END,
          CASE WHEN p.owner_user_id = 'local-admin' THEN 'admin' ELSE 'user' END,
          'active',
          MIN(p.created_at),
          NULL::timestamptz
        FROM projects p
        GROUP BY p.owner_user_id
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_invites_user_id", table_name="user_invites")
    op.drop_index("ix_user_invites_status", table_name="user_invites")
    op.drop_table("user_invites")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
