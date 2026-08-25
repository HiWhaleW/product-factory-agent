"""Expose authoritative D5 project, version, issue, and session projection fields.

Revision ID: 20260822_0005
Revises: 20260822_0004
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0005"
down_revision: str | None = "20260822_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_FIXTURE_PROJECT_ID = "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
LEGACY_FIXTURE_G1_ID = "cec40b01-ba61-494b-a057-b2f5c74173f1"
LEGACY_FIXTURE_REVIEW_ID = "d383d981-e599-4daf-8dd1-836e9e360f93"

LEGACY_FIXTURE_KNOWN_ISSUES = """[
  {
    "issue": "引用粒度待用户访谈验证",
    "severity": "P2",
    "evidence_refs": [],
    "source_refs": [
      {"artifact_id": "ed02a37b-ce4b-4a20-b223-3c057ceaf932", "version": 2},
      {"artifact_id": "e6eeff60-d498-499c-9855-4c45e0bc233e", "version": 2}
    ],
    "status": "open"
  },
  {
    "issue": "商业数据与目标用户规模缺少直接证据",
    "severity": "P2",
    "evidence_refs": [],
    "source_refs": [
      {"artifact_id": "ed02a37b-ce4b-4a20-b223-3c057ceaf932", "version": 2},
      {"artifact_id": "6170b1b6-0288-4a33-8358-afd4376f4e6b", "version": 2},
      {"artifact_id": "e6eeff60-d498-499c-9855-4c45e0bc233e", "version": 2}
    ],
    "status": "open"
  }
]"""


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("iteration_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "artifacts",
        sa.Column("owner_agent", sa.String(length=64), nullable=False, server_default="system"),
    )
    op.add_column(
        "artifact_versions",
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default="system"),
    )
    op.add_column(
        "gates",
        sa.Column(
            "known_issues",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "definition_reviews",
        sa.Column(
            "known_issues",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "permission_requests",
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "permission_requests",
        sa.Column(
            "redacted_parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )

    op.execute(
        """
        UPDATE artifacts
        SET owner_agent = CASE
          WHEN kind IN ('evidence_index', 'mrd') THEN 'ai-pm'
          WHEN kind = 'red_team_review' THEN 'reviewer'
          ELSE 'system'
        END
        """
    )
    op.execute(
        """
        UPDATE artifact_versions av
        SET created_by = a.owner_agent
        FROM artifacts a
        WHERE a.id = av.artifact_id
        """
    )

    # This is a deterministic recovery of the already-audited D5 project, not a
    # fixture creation. Environments without the project remain unchanged.
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET owner_user_id = 'local-admin',
                name = '示例项目',
                iteration_version = 1
            WHERE id = :project_id
            """
        ).bindparams(project_id=LEGACY_FIXTURE_PROJECT_ID)
    )
    op.execute(
        sa.text(
            "UPDATE gates SET known_issues = CAST(:issues AS json) WHERE id = :gate_id"
        ).bindparams(issues=LEGACY_FIXTURE_KNOWN_ISSUES, gate_id=LEGACY_FIXTURE_G1_ID)
    )
    op.execute(
        sa.text(
            """
            UPDATE definition_reviews
            SET known_issues = CAST(:issues AS json)
            WHERE id = :review_id
            """
        ).bindparams(
            issues=LEGACY_FIXTURE_KNOWN_ISSUES,
            review_id=LEGACY_FIXTURE_REVIEW_ID,
        )
    )


def downgrade() -> None:
    op.drop_column("permission_requests", "redacted_parameters")
    op.drop_column("permission_requests", "reason")
    op.drop_column("definition_reviews", "known_issues")
    op.drop_column("gates", "known_issues")
    op.drop_column("artifact_versions", "created_by")
    op.drop_column("artifacts", "owner_agent")
    op.drop_column("projects", "iteration_version")
