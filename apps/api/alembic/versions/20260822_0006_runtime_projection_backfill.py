"""Backfill persisted tool and recovery projections from audited RunSteps.

Revision ID: 20260822_0006
Revises: 20260822_0005
Create Date: 2026-08-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260822_0006"
down_revision: str | None = "20260822_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tool_runs (
          id, task_id, run_id, capability_id, tool_name, state,
          input_hash, idempotency_key, result_ref, created_at
        )
        SELECT
          rs.id,
          ar.task_id,
          rs.run_id,
          'CAP-02',
          'web_research',
          rs.state,
          rs.input_hash,
          rs.idempotency_key,
          rs.output_ref,
          rs.created_at
        FROM run_steps rs
        JOIN agent_runs ar ON ar.id = rs.run_id
        WHERE rs.step_type = 'tool'
          AND rs.idempotency_key IS NOT NULL
        ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE permission_requests
        SET reason = '公开搜索是计费网络调用，需要一次性授权。',
            redacted_parameters = json_build_object('input_hash', input_hash)
        WHERE tool_name = 'web_research' AND reason = ''
        """
    )
    op.execute(
        """
        WITH candidates AS (
          SELECT
            tr.id,
            at.project_id,
            tr.run_id,
            tr.task_id,
            tr.tool_name,
            tr.state,
            tr.idempotency_key,
            tr.result_ref,
            tr.created_at,
            row_number() OVER (PARTITION BY at.project_id ORDER BY tr.created_at, tr.id) AS rn
          FROM tool_runs tr
          JOIN agent_tasks at ON at.id = tr.task_id
          WHERE NOT EXISTS (
            SELECT 1 FROM events e
            WHERE e.project_id = at.project_id
              AND e.event_type = 'tool_run.recovered'
              AND e.payload->>'tool_run_id' = tr.id
          )
        ), bases AS (
          SELECT project_id, COALESCE(MAX(sequence), 0) AS base
          FROM events
          GROUP BY project_id
        )
        INSERT INTO events (id, project_id, sequence, event_type, payload, created_at)
        SELECT
          c.id,
          c.project_id,
          b.base + c.rn,
          'tool_run.recovered',
          json_build_object(
            'tool_run_id', c.id,
            'run_id', c.run_id,
            'task_id', c.task_id,
            'tool_id', c.tool_name,
            'state', c.state,
            'idempotency_key', c.idempotency_key,
            'result_ref', c.result_ref,
            'migration', '20260822_0006'
          ),
          c.created_at
        FROM candidates c
        JOIN bases b ON b.project_id = c.project_id
        """
    )
    op.execute(
        """
        INSERT INTO events (id, project_id, sequence, event_type, payload, created_at)
        SELECT
          'f5321d65-748a-4bc5-9b17-4ea2a2442501',
          p.id,
          COALESCE(MAX(e.sequence), 0) + 1,
          'run.recovery_recorded',
          json_build_object(
            'failed_run_id', 'f5321d65-748a-4bc5-9b17-4ea2a2442501',
            'retry_run_id', 'd6b2444e-5995-4485-9576-1162a5b53193',
            'strategy', 'new_clean_context_run_after_provider_failure',
            'migration', '20260822_0006'
          ),
          now()
        FROM projects p
        LEFT JOIN events e ON e.project_id = p.id
        WHERE p.id = '2a3c38e1-9704-4f83-a096-84cb5a5025e7'
          AND NOT EXISTS (
            SELECT 1 FROM events existing
            WHERE existing.project_id = p.id
              AND existing.event_type = 'run.recovery_recorded'
              AND existing.payload->>'failed_run_id' = 'f5321d65-748a-4bc5-9b17-4ea2a2442501'
          )
        GROUP BY p.id
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM events WHERE payload->>'migration' = '20260822_0006'"
    )
    # ToolRun and Permission metadata are durable audit facts stored in schema
    # that already exists at 0005. Keep them on downgrade because rows that
    # predated this backfill cannot be distinguished safely from inserted rows.
