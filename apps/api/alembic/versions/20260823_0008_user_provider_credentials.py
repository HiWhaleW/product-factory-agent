"""Store per-user provider credential metadata without secret values.

Revision ID: 20260823_0008
Revises: 20260823_0007
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0008"
down_revision: str | None = "20260823_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_provider_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("secret_ref", sa.String(length=200), nullable=False),
        sa.Column("masked_hint", sa.String(length=40), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"),
    )
    op.create_index(
        "ix_user_provider_credentials_user_id",
        "user_provider_credentials",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_provider_credentials_user_id",
        table_name="user_provider_credentials",
    )
    op.drop_table("user_provider_credentials")
