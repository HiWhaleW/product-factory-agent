"""Add deterministic AI PM submission and Reviewer result records.

Revision ID: 20260822_0004
Revises: 20260822_0003
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0004"
down_revision: str | None = "20260822_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "definition_submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=False),
        sa.Column("context_pack_id", sa.String(length=36), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_set_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evidence_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_artifact_version", sa.Integer(), nullable=False),
        sa.Column("mrd_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("mrd_artifact_version", sa.Integer(), nullable=False),
        sa.Column("reviewer_context_pack_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_pack_id"], ["context_packs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["mrd_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reviewer_context_pack_id"], ["context_packs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key", name="uq_definition_submission_key"
        ),
        sa.UniqueConstraint("source_run_id", name="uq_definition_submission_source_run"),
    )
    op.create_table(
        "definition_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=False),
        sa.Column("context_pack_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("red_team_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("red_team_artifact_version", sa.Integer(), nullable=False),
        sa.Column("gate_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["definition_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_pack_id"], ["context_packs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["red_team_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["gate_id"], ["gates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", name="uq_definition_review_submission"),
        sa.UniqueConstraint("source_run_id", name="uq_definition_review_source_run"),
    )


def downgrade() -> None:
    op.drop_table("definition_reviews")
    op.drop_table("definition_submissions")
