from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentMembership,
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactEdge,
    ArtifactVersion,
    ContextVersion,
    Event,
    Gate,
    PermissionDecision,
    PermissionRequest,
    Project,
    RunStep,
    ToolRun,
)
from app.services.artifact_store import write_immutable_artifact

FIXTURE_PROJECT_ID = "c7f38c12-6c5a-4b2f-bd51-7d0d5f5e0001"
FIXTURE_OWNER = "d5-acceptance-fixture"
FIXTURE_NAME = "D5 Gate/Permission 联合验收（可回收）"


class AcceptanceFixtureError(RuntimeError):
    pass


def reseed_fixture() -> dict:
    settings = get_settings()
    with SessionLocal.begin() as session:
        existing = session.get(Project, FIXTURE_PROJECT_ID)
        if existing is not None:
            if existing.owner_user_id != FIXTURE_OWNER or existing.name != FIXTURE_NAME:
                raise AcceptanceFixtureError(
                    "固定 fixture project_id 已被非验收项目占用，拒绝删除。"
                )
            session.execute(delete(Project).where(Project.id == FIXTURE_PROJECT_ID))
            session.flush()

        project = Project(
            id=FIXTURE_PROJECT_ID,
            owner_user_id=FIXTURE_OWNER,
            name=FIXTURE_NAME,
            state="prd",
            context_version=3,
            iteration_version=1,
        )
        session.add(project)
        session.flush()
        context = ContextVersion(
            project_id=project.id,
            version=3,
            stage="prd",
            approval_status="active",
            change_reason="reseedable frontend Gate/Permission acceptance fixture",
            summary="仅用于联合验收，不代表真实业务或模型结论。",
        )
        session.add(context)
        session.flush()
        _event(session, project.id, "project.created", {"fixture": True})
        for agent_id in ("factory-lead", "ai-pm", "reviewer"):
            session.add(
                AgentMembership(
                    project_id=project.id,
                    agent_id=agent_id,
                    joined_context_version=3,
                )
            )
            _event(
                session,
                project.id,
                "agent.joined",
                {"agent_id": agent_id, "context_version": 3, "fixture": True},
            )

        prd, prd_version = _fixture_artifact(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project=project,
            kind="prd",
            title="Fixture PRD（非业务产物）",
            content="# Fixture PRD\n\n仅用于验证 G2 卡片、Artifact 和 cursor 投影。",
            owner_agent="ai-pm",
        )
        review, review_version = _fixture_artifact(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project=project,
            kind="prd_review",
            title="Fixture PRD Review（非业务产物）",
            content="# Fixture PRD Review\n\n仅用于验证 Reviewer 与 Gate 投影。",
            owner_agent="reviewer",
        )
        session.add(
            ArtifactEdge(
                project_id=project.id,
                source_id=prd.id,
                target_id=review.id,
                relation="reviewed_by",
            )
        )
        gate = Gate(
            project_id=project.id,
            gate_type="G2",
            context_version=3,
            status="open",
            target_state="solution_confirmation",
            reason="联合验收样本：可批准/退回，随后运行 reseed 恢复。",
            impacted_artifact_refs=[
                {"artifact_id": prd.id, "version": prd_version.version},
                {"artifact_id": review.id, "version": review_version.version},
            ],
            known_issues=[
                {
                    "issue": "该项目是明确标记的联合验收 fixture",
                    "severity": "P2",
                    "evidence_refs": [],
                    "source_refs": [],
                    "status": "accepted",
                }
            ],
        )
        session.add(gate)
        session.flush()
        _event(
            session,
            project.id,
            "gate.opened",
            {
                "gate_id": gate.id,
                "gate_type": "G2",
                "context_version": 3,
                "target_state": "solution_confirmation",
                "fixture": True,
            },
        )

        historical = _historical_resumed_run(session, project)
        current = _open_permission_run(session, project)
    return {
        "project_id": FIXTURE_PROJECT_ID,
        "project_name": FIXTURE_NAME,
        "fixture": True,
        "gate": {"id": gate.id, "type": "G2", "status": "open"},
        "permission": {
            "id": current["permission_id"],
            "status": "open",
            "tool_id": "llm_call",
            "input_hash": current["input_hash"],
        },
        "resumable_run": {
            "id": current["run_id"],
            "resume_token": current["resume_token"],
            "input_hash": current["input_hash"],
        },
        "historical_resumed_run_id": historical,
        "builder_started": False,
        "reset_command": "python -m app.agents.acceptance_fixture --reseed",
    }


def _historical_resumed_run(session, project: Project) -> str:
    task = AgentTask(
        project_id=project.id,
        assigned_agent="reviewer",
        title="Fixture 历史暂停/恢复事件",
        state="completed",
        context_version=3,
        claimed_by="acceptance-fixture",
    )
    session.add(task)
    session.flush()
    input_hash = hashlib.sha256(f"historical:{task.id}".encode()).hexdigest()
    run = AgentRun(
        task_id=task.id,
        state="succeeded",
        input_hash=input_hash,
        turns_used=1,
        retries_used=0,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    permission = PermissionRequest(
        run_id=run.id,
        tool_name="llm_call",
        input_hash=input_hash,
        risk_level="medium",
        reason="历史 fixture：验证暂停、授权和恢复事件。",
        redacted_parameters={"purpose": "frontend_acceptance", "fixture": True},
        status="decided",
    )
    session.add(permission)
    session.flush()
    session.add(
        PermissionDecision(
            permission_request_id=permission.id,
            decision="allow",
            input_hash=input_hash,
            decided_by=FIXTURE_OWNER,
        )
    )
    tool = ToolRun(
        task_id=task.id,
        run_id=run.id,
        capability_id="CAP-10",
        tool_name="llm_call",
        state="completed",
        input_hash=input_hash,
        idempotency_key=f"fixture:historical:{run.id}",
        result_ref="fixture://no-external-call",
    )
    session.add(tool)
    for index, (step_type, output_ref) in enumerate(
        [
            ("runtime_start", None),
            ("checkpoint", "fixture://checkpoint"),
            ("resume", "fixture://checkpoint"),
            ("tool", "fixture://no-external-call"),
        ]
    ):
        session.add(
            RunStep(
                run_id=run.id,
                step_index=index,
                step_type=step_type,
                state="completed",
                input_hash=input_hash,
                output_ref=output_ref,
                idempotency_key=(f"fixture:{step_type}:{run.id}" if index else None),
                external_effect_confirmed=index > 0,
            )
        )
    for event_type, payload in [
        ("run.started", {}),
        ("permission.opened", {"permission_id": permission.id}),
        ("run.waiting", {"reason": "permission"}),
        ("permission.decided", {"permission_id": permission.id, "decision": "allow"}),
        ("run.resumed", {"checkpoint_hash": input_hash}),
        ("tool_run.started", {"tool_run_id": tool.id, "tool_id": "llm_call"}),
        ("tool_run.completed", {"tool_run_id": tool.id, "tool_id": "llm_call"}),
        ("run.completed", {}),
    ]:
        _event(
            session,
            project.id,
            event_type,
            {"run_id": run.id, "task_id": task.id, "fixture": True, **payload},
        )
    return run.id


def _open_permission_run(session, project: Project) -> dict:
    task = AgentTask(
        project_id=project.id,
        assigned_agent="ai-pm",
        title="Fixture 开放 PermissionRequest",
        state="waiting_human",
        context_version=3,
        claimed_by="acceptance-fixture",
    )
    session.add(task)
    session.flush()
    input_hash = hashlib.sha256(f"open:{task.id}".encode()).hexdigest()
    run = AgentRun(
        task_id=task.id,
        state="waiting_for_human",
        input_hash=input_hash,
        turns_used=1,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    session.add_all(
        [
            RunStep(
                run_id=run.id,
                step_index=0,
                step_type="runtime_start",
                state="completed",
                input_hash=input_hash,
            ),
            RunStep(
                run_id=run.id,
                step_index=1,
                step_type="checkpoint",
                state="completed",
                input_hash=input_hash,
                output_ref="fixture://checkpoint",
                idempotency_key=f"fixture:checkpoint:{run.id}",
                external_effect_confirmed=True,
            ),
        ]
    )
    permission = PermissionRequest(
        run_id=run.id,
        tool_name="llm_call",
        input_hash=input_hash,
        risk_level="medium",
        reason="联合验收样本：允许一次脱敏 PRD 质量复核；fixture 不会实际调用模型。",
        redacted_parameters={"purpose": "frontend_acceptance", "fixture": True},
        status="open",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(permission)
    session.flush()
    _event(
        session,
        project.id,
        "run.started",
        {"run_id": run.id, "task_id": task.id, "agent_id": "ai-pm", "fixture": True},
    )
    _event(
        session,
        project.id,
        "permission.opened",
        {
            "permission_id": permission.id,
            "run_id": run.id,
            "tool_id": permission.tool_name,
            "input_hash": input_hash,
            "fixture": True,
        },
    )
    _event(
        session,
        project.id,
        "run.waiting",
        {"run_id": run.id, "task_id": task.id, "reason": "permission", "fixture": True},
    )
    return {
        "permission_id": permission.id,
        "run_id": run.id,
        "resume_token": run.resume_token,
        "input_hash": input_hash,
    }


def _fixture_artifact(
    session,
    *,
    artifact_root,
    project: Project,
    kind: str,
    title: str,
    content: str,
    owner_agent: str,
) -> tuple[Artifact, ArtifactVersion]:
    artifact = Artifact(
        project_id=project.id,
        title=title,
        kind=kind,
        stage="prd",
        status="waiting_gate",
        latest_version=1,
        owner_agent=owner_agent,
    )
    session.add(artifact)
    session.flush()
    content_ref, content_hash = write_immutable_artifact(
        artifact_root,
        project_id=project.id,
        kind=kind,
        content=content,
    )
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version=1,
        context_version=3,
        approval_status="waiting_gate",
        content_ref=content_ref,
        content_hash=content_hash,
        summary="明确标记的可回收联合验收 fixture。",
        created_by=owner_agent,
    )
    session.add(version)
    session.flush()
    _event(
        session,
        project.id,
        "artifact.created",
        {
            "artifact_id": artifact.id,
            "artifact_version_id": version.id,
            "kind": kind,
            "version": 1,
            "context_version": 3,
            "approval_status": "waiting_gate",
            "fixture": True,
        },
    )
    return artifact, version


def _event(session, project_id: str, event_type: str, payload: dict) -> Event:
    sequence = session.scalar(
        select(func.max(Event.sequence)).where(Event.project_id == project_id)
    )
    event = Event(
        project_id=project_id,
        sequence=(sequence or 0) + 1,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reseed", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(reseed_fixture(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

