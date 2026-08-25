"""Add user-selected OpenAI-compatible provider metadata.

Revision ID: 20260823_0009
Revises: 20260823_0008
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0009"
down_revision: str | None = "20260823_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_provider_credentials",
        sa.Column("provider_name", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "user_provider_credentials",
        sa.Column("base_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "user_provider_credentials",
        sa.Column("model_name", sa.String(length=120), nullable=True),
    )
    op.execute(
        "UPDATE user_provider_credentials "
        "SET provider_name = 'DeepSeek', "
        "base_url = 'https://api.deepseek.com', model_name = 'deepseek-chat'"
    )
    op.alter_column("user_provider_credentials", "provider_name", nullable=False)
    op.alter_column("user_provider_credentials", "base_url", nullable=False)
    op.alter_column("user_provider_credentials", "model_name", nullable=False)


def downgrade() -> None:
    op.drop_column("user_provider_credentials", "model_name")
    op.drop_column("user_provider_credentials", "base_url")
    op.drop_column("user_provider_credentials", "provider_name")
