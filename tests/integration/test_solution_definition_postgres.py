from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentMembership,
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    Event,
    Gate,
    IdempotencyRecord,
    Project,
    RunStep,
    ToolRun,
)
from app.main import app
from app.services.artifact_store import write_immutable_artifact
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use PostgreSQL",
    ),
]


@pytest.fixture
def solution_scope() -> tuple[str, str, str, str, str, str]:
    owner = f"solution-it-{uuid4()}"
    project_id = str(uuid4())
    settings = get_settings()
    with SessionLocal.begin() as session:
        project = Project(
            id=project_id,
            owner_user_id=owner,
            name="真实方案契约集成测试",
            state="solution_confirmation",
            context_version=4,
        )
        session.add(project)
        session.flush()
        context = ContextVersion(
            project_id=project_id,
            version=4,
            stage="solution_confirmation",
            approval_status="active",
            change_reason="G2 approved integration fixture",
        )
        session.add(context)
        session.flush()
        artifacts: dict[str, tuple[Artifact, ArtifactVersion]] = {}
        for kind, title, content in [
            ("prd", "PRD v1", "# PRD v1\n\n已批准范围与验收标准。"),
            ("prd_review", "PRD Review v1", "# PRD Review v1\n\n结论 pass。"),
        ]:
            artifact = Artifact(
                project_id=project_id,
                title=title,
                kind=kind,
                stage="prd",
                status="approved",
                latest_version=1,
                owner_agent="ai-pm" if kind == "prd" else "reviewer",
            )
            session.add(artifact)
            session.flush()
            content_ref, content_hash = write_immutable_artifact(
                settings.ARTIFACT_ROOT,
                project_id=project_id,
                kind=kind,
                content=content,
            )
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=3,
                approval_status="approved",
                content_ref=content_ref,
                content_hash=content_hash,
                summary=title,
                created_by=artifact.owner_agent,
            )
            session.add(version)
            session.flush()
            artifacts[kind] = (artifact, version)
        prd, prd_version = artifacts["prd"]
        review, review_version = artifacts["prd_review"]
        pack = ContextPack(
            project_id=project_id,
            context_version_id=context.id,
            context_version=4,
            stage="solution_confirmation",
            approval_status="approved",
            primary_resource_type="artifact",
            primary_resource_id=prd.id,
            primary_resource_version=1,
            agent_id="builder",
            task="只生成 User Flow 与方案说明，不写代码。",
            references=[
                {
                    "resource_type": "artifact",
                    "resource_id": review.id,
                    "version": 1,
                    "approval_status": "approved",
                }
            ],
            policy={
                "allowed_capability_ids": ["CAP-07"],
                "forbidden_actions": [
                    "advance_project_state",
                    "approve_gate",
                    "codex_cli",
                    "project_fs_write",
                    "git_local",
                    "test_runner",
                ],
                "mode": "solution_document_only",
                "budget": {"max_turns": 3, "max_retries": 1, "max_tool_calls": 1},
            },
        )
        session.add(pack)
        session.add(
            AgentMembership(
                project_id=project_id,
                agent_id="builder",
                joined_context_version=4,
            )
        )
        session.flush()
        builder_run = _seed_run(session, project_id, pack, "builder")
    yield project_id, owner, pack.id, builder_run, prd.id, review.id
    with SessionLocal.begin() as session:
        session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.scope.in_(
                    [
                        f"solution.submission:{project_id}",
                    ]
                )
                | IdempotencyRecord.scope.like("solution.review:%")
            )
        )
        session.execute(delete(Project).where(Project.id == project_id))


def test_solution_review_opens_g3_without_code_or_state_advance(solution_scope) -> None:
    project_id, owner, pack_id, builder_run_id, prd_id, review_id = solution_scope
    prd_ref = f"artifact:{prd_id}:v1"
    review_ref = f"artifact:{review_id}:v1"
    submission_body = {
        "source_run_id": builder_run_id,
        "context_pack_id": pack_id,
        "expected_context_version": 4,
        "artifact_proposals": [
            {
                "kind": "user_flow",
                "title": "User Flow",
                "content": f"# User Flow\n\n固定前端下的核心流程。来源：{prd_ref}。",
                "evidence_refs": [prd_ref],
                "assumptions": [],
            },
            {
                "kind": "solution_design",
                "title": "方案说明",
                "content": (
                    f"# 方案说明\n\n不修改前端、不写代码。来源：{prd_ref}；审核：{review_ref}。"
                ),
                "evidence_refs": [prd_ref, review_ref],
                "assumptions": [],
            },
        ],
    }
    with TestClient(app) as client:
        submission = client.post(
            f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions",
            headers={"Idempotency-Key": f"{owner}-solution"},
            json=submission_body,
        )
    assert submission.status_code == 201, submission.text
    payload = submission.json()
    with SessionLocal.begin() as session:
        reviewer_pack = session.get(ContextPack, payload["reviewer_context_pack_id"])
        reviewer_run_id = _seed_run(session, project_id, reviewer_pack, "reviewer")
    candidate_refs = [
        payload["user_flow"]["artifact_ref"],
        payload["solution_design"]["artifact_ref"],
    ]
    review_body = {
        "source_run_id": reviewer_run_id,
        "context_pack_id": payload["reviewer_context_pack_id"],
        "expected_context_version": 4,
        "verdict": "pass",
        "message": "方案可进入 G3。",
        "findings": [],
        "review_artifact": {
            "kind": "solution_review",
            "title": "Solution Review",
            "content": (
                f"# Solution Review\n\nUser Flow：{candidate_refs[0]}；"
                f"方案：{candidate_refs[1]}。结论 pass。"
            ),
            "evidence_refs": candidate_refs,
            "assumptions": [],
        },
    }
    path = (
        f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions/"
        f"{payload['submission_id']}/review"
    )
    with TestClient(app) as client:
        first = client.post(
            path,
            headers={"Idempotency-Key": f"{owner}-solution-review"},
            json=review_body,
        )
        second = client.post(
            path,
            headers={"Idempotency-Key": f"{owner}-solution-review"},
            json=review_body,
        )
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "waiting_g3"
    assert first.json()["gate"]["gate_type"] == "G3"
    assert first.json()["gate"]["status"] == "open"
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        assert project.state == "solution_confirmation"
        assert project.context_version == 4
        assert session.scalar(
            select(func.count()).select_from(Gate).where(
                Gate.project_id == project_id,
                Gate.gate_type == "G3",
                Gate.status == "open",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ToolRun).join(
                AgentTask, ToolRun.task_id == AgentTask.id
            ).where(
                AgentTask.project_id == project_id,
                ToolRun.tool_name == "codex_cli",
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ToolRun).join(
                AgentTask, ToolRun.task_id == AgentTask.id
            ).where(
                AgentTask.project_id == project_id,
                ToolRun.tool_name == "artifact_store",
            )
        ) == 2


def _seed_run(
    session,
    project_id: str,
    pack: ContextPack,
    agent_id: str,
) -> str:
    task = AgentTask(
        project_id=project_id,
        assigned_agent=agent_id,
        title=pack.task[:240],
        state="completed",
        context_version=pack.context_version,
        claimed_by="integration-test",
    )
    session.add(task)
    session.flush()
    input_hash = hashlib.sha256(f"{project_id}:{pack.id}:{agent_id}".encode()).hexdigest()
    run = AgentRun(
        task_id=task.id,
        attempt=1,
        state="succeeded",
        input_hash=input_hash,
        turns_used=1,
        retries_used=0,
    )
    session.add(run)
    session.flush()
    session.add(
        RunStep(
            run_id=run.id,
            step_index=0,
            step_type="model",
            state="completed",
            input_hash=input_hash,
            output_ref=f"model-output://{input_hash}",
            external_effect_confirmed=True,
        )
    )
    sequence = session.scalar(
        select(func.max(Event.sequence)).where(Event.project_id == project_id)
    ) or 0
    session.add(
        Event(
            project_id=project_id,
            sequence=sequence + 1,
            event_type="run.started",
            payload={
                "run_id": run.id,
                "task_id": task.id,
                "agent_id": agent_id,
                "context_pack_id": pack.id,
                "context_version": pack.context_version,
            },
        )
    )
    return run.id
