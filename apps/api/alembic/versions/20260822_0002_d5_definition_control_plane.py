"""Add the D5 definition-chain deterministic contracts.

Revision ID: 20260822_0002
Revises: 20260820_0001
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0002"
down_revision: str | None = "20260820_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("paused_from_state", sa.String(length=64)))

    op.add_column("context_versions", sa.Column("stage", sa.String(length=64)))
    op.add_column("context_versions", sa.Column("approval_status", sa.String(length=32)))
    op.add_column("context_versions", sa.Column("change_reason", sa.Text()))
    op.add_column("context_versions", sa.Column("gate_decision_id", sa.String(length=36)))
    op.execute(
        """
        INSERT INTO context_versions
            (id, project_id, version, stage, approval_status, change_reason, summary, created_at)
        SELECT
            md5(random()::text || clock_timestamp()::text)::uuid::text,
            p.id, p.context_version, p.state, 'active', 'legacy_backfill', '', p.created_at
        FROM projects p
        WHERE NOT EXISTS (
            SELECT 1 FROM context_versions cv
            WHERE cv.project_id = p.id AND cv.version = p.context_version
        )
        """
    )
    op.execute(
        """
        UPDATE context_versions cv
        SET stage = p.state,
            approval_status = 'active',
            change_reason = COALESCE(cv.change_reason, 'legacy_backfill')
        FROM projects p
        WHERE cv.project_id = p.id
        """
    )
    op.alter_column("context_versions", "stage", nullable=False)
    op.alter_column("context_versions", "approval_status", nullable=False)
    op.alter_column("context_versions", "change_reason", nullable=False)

    op.add_column("artifact_versions", sa.Column("approval_status", sa.String(length=32)))
    op.execute(
        """
        UPDATE artifact_versions av
        SET approval_status = CASE WHEN a.status = 'approved' THEN 'approved' ELSE 'draft' END
        FROM artifacts a
        WHERE av.artifact_id = a.id
        """
    )
    op.alter_column("artifact_versions", "approval_status", nullable=False)

    op.add_column("gates", sa.Column("reason", sa.Text()))
    op.add_column("gates", sa.Column("impacted_artifact_refs", sa.JSON()))
    op.execute("UPDATE gates SET reason = '', impacted_artifact_refs = '[]'::json")
    op.alter_column("gates", "reason", nullable=False)
    op.alter_column("gates", "impacted_artifact_refs", nullable=False)

    op.add_column("gate_decisions", sa.Column("context_version_before", sa.Integer()))
    op.add_column("gate_decisions", sa.Column("context_version_after", sa.Integer()))
    op.add_column("gate_decisions", sa.Column("target_state", sa.String(length=64)))
    op.execute(
        """
        UPDATE gate_decisions gd
        SET context_version_before = g.context_version,
            context_version_after = g.context_version,
            target_state = g.target_state
        FROM gates g
        WHERE gd.gate_id = g.id
        """
    )
    op.alter_column("gate_decisions", "context_version_before", nullable=False)
    op.alter_column("gate_decisions", "context_version_after", nullable=False)

    op.add_column("context_packs", sa.Column("project_id", sa.String(length=36)))
    op.add_column("context_packs", sa.Column("context_version", sa.Integer()))
    op.add_column("context_packs", sa.Column("stage", sa.String(length=64)))
    op.add_column("context_packs", sa.Column("approval_status", sa.String(length=32)))
    op.add_column("context_packs", sa.Column("primary_resource_type", sa.String(length=32)))
    op.add_column("context_packs", sa.Column("primary_resource_id", sa.String(length=36)))
    op.add_column("context_packs", sa.Column("primary_resource_version", sa.Integer()))
    op.execute(
        """
        UPDATE context_packs cp
        SET project_id = cv.project_id,
            context_version = cv.version,
            stage = cv.stage,
            approval_status = 'approved',
            primary_resource_type = 'legacy',
            primary_resource_id = cv.id,
            primary_resource_version = cv.version
        FROM context_versions cv
        WHERE cp.context_version_id = cv.id
        """
    )
    for column in (
        "project_id",
        "context_version",
        "stage",
        "approval_status",
        "primary_resource_type",
        "primary_resource_id",
        "primary_resource_version",
    ):
        op.alter_column("context_packs", column, nullable=False)
    op.create_foreign_key(
        "fk_context_pack_project", "context_packs", "projects", ["project_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_context_pack_exact_binding",
        "context_packs",
        [
            "project_id", "stage", "context_version", "primary_resource_type",
            "primary_resource_id", "primary_resource_version", "approval_status", "agent_id",
        ],
    )

    op.create_table(
        "clarification_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("client_clarification_id", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("scope_impact", sa.String(length=32), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "client_clarification_id", name="uq_clarification_client"
        ),
    )
    op.create_table(
        "project_briefs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_project_brief_project"),
    )
    op.create_table(
        "project_brief_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("brief_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("target_users", sa.JSON(), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("in_scope", sa.JSON(), nullable=False),
        sa.Column("out_of_scope", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.Text(), nullable=False),
        sa.Column("open_questions", sa.JSON(), nullable=False),
        sa.Column("source_clarification_ids", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brief_id"], ["project_briefs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brief_id", "version", name="uq_project_brief_version"),
    )
    op.create_table(
        "agent_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("joined_context_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "agent_id", name="uq_agent_membership"),
    )
    op.execute(
        """
        INSERT INTO agent_memberships
            (id, project_id, agent_id, joined_context_version, status, joined_at)
        SELECT
            md5(random()::text || clock_timestamp()::text)::uuid::text,
            p.id, 'factory-lead', p.context_version, 'active', p.created_at
        FROM projects p
        ON CONFLICT (project_id, agent_id) DO NOTHING
        """
    )
    op.create_index(
        "uq_gate_open_project_type_context",
        "gates",
        ["project_id", "gate_type", "context_version"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_gate_open_project_type_context", table_name="gates")
    op.drop_table("agent_memberships")
    op.drop_table("project_brief_versions")
    op.drop_table("project_briefs")
    op.drop_table("clarification_records")
    op.drop_index("ix_context_pack_exact_binding", table_name="context_packs")
    op.drop_constraint("fk_context_pack_project", "context_packs", type_="foreignkey")
    for column in (
        "primary_resource_version",
        "primary_resource_id",
        "primary_resource_type",
        "approval_status",
        "stage",
        "context_version",
        "project_id",
    ):
        op.drop_column("context_packs", column)
    op.drop_column("gate_decisions", "target_state")
    op.drop_column("gate_decisions", "context_version_after")
    op.drop_column("gate_decisions", "context_version_before")
    op.drop_column("gates", "impacted_artifact_refs")
    op.drop_column("gates", "reason")
    op.drop_column("artifact_versions", "approval_status")
    op.drop_column("context_versions", "gate_decision_id")
    op.drop_column("context_versions", "change_reason")
    op.drop_column("context_versions", "approval_status")
    op.drop_column("context_versions", "stage")
    op.drop_column("projects", "paused_from_state")
