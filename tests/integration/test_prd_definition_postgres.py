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
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL database",
    ),
]


@pytest.fixture
def prd_scope() -> tuple[str, str, str, str]:
    owner = f"prd-it-{uuid4()}"
    project_id = str(uuid4())
    settings = get_settings()
    with SessionLocal.begin() as session:
        project = Project(
            id=project_id,
            owner_user_id=owner,
            name="真实 PRD 契约集成测试",
            state="prd",
            context_version=3,
        )
        session.add(project)
        session.flush()
        context = ContextVersion(
            project_id=project_id,
            version=3,
            stage="prd",
            approval_status="active",
            change_reason="G1 approved integration fixture",
        )
        session.add(context)
        session.flush()
        mrd = Artifact(
            project_id=project_id,
            title="MRD v2",
            kind="mrd",
            stage="mrd",
            status="approved",
            latest_version=2,
            owner_agent="ai-pm",
        )
        session.add(mrd)
        session.flush()
        content_ref, content_hash = write_immutable_artifact(
            settings.ARTIFACT_ROOT,
            project_id=project_id,
            kind="mrd",
            content="# MRD v2\n\n已批准的销售复盘需求。",
        )
        session.add(
            ArtifactVersion(
                artifact_id=mrd.id,
                version=2,
                context_version=2,
                approval_status="approved",
                content_ref=content_ref,
                content_hash=content_hash,
                summary="approved MRD",
                created_by="ai-pm",
            )
        )
        pack = ContextPack(
            project_id=project_id,
            context_version_id=context.id,
            context_version=3,
            stage="prd",
            approval_status="approved",
            primary_resource_type="artifact",
            primary_resource_id=mrd.id,
            primary_resource_version=2,
            agent_id="ai-pm",
            task="基于已批准 MRD 形成 PRD。",
            references=[],
            policy={
                "allowed_capability_ids": ["CAP-04"],
                "forbidden_actions": ["approve_gate", "start_builder"],
            },
        )
        session.add(pack)
        session.add_all(
            [
                AgentMembership(
                    project_id=project_id,
                    agent_id="factory-lead",
                    joined_context_version=1,
                ),
                AgentMembership(
                    project_id=project_id,
                    agent_id="ai-pm",
                    joined_context_version=2,
                ),
            ]
        )
        session.flush()
        ai_pm_run = _seed_run(
            session,
            project_id=project_id,
            pack=pack,
            agent_id="ai-pm",
        )
    yield project_id, owner, pack.id, ai_pm_run
    with SessionLocal.begin() as session:
        session.execute(
            delete(IdempotencyRecord).where(
                (IdempotencyRecord.scope == f"prd.submission:{project_id}")
                | IdempotencyRecord.key.like(f"{owner}%")
            )
        )
        session.execute(delete(Project).where(Project.id == project_id))


def test_prd_submission_review_opens_g2_without_advancing_or_builder(prd_scope) -> None:
    project_id, owner, pack_id, ai_pm_run_id = prd_scope
    with SessionLocal() as session:
        pack = session.get(ContextPack, pack_id)
        source_ref = f"artifact:{pack.primary_resource_id}:v2"
    submission_body = {
        "source_run_id": ai_pm_run_id,
        "context_pack_id": pack_id,
        "expected_context_version": 3,
        "artifact_proposal": {
            "kind": "prd",
            "title": "销售复盘 Agent PRD",
            "content": f"# PRD\n\n核心闭环、范围、验收、反指标。来源：{source_ref}",
            "evidence_refs": [source_ref],
            "assumptions": ["引用粒度需用户访谈验证"],
        },
    }
    with TestClient(app) as client:
        submission = client.post(
            f"/api/v1/agent-runtime/projects/{project_id}/prd-submissions",
            headers={"Idempotency-Key": f"{owner}-prd"},
            json=submission_body,
        )
    assert submission.status_code == 201, submission.text
    payload = submission.json()
    candidate_ref = payload["prd"]["artifact_ref"]
    with SessionLocal.begin() as session:
        reviewer_pack = session.get(ContextPack, payload["reviewer_context_pack_id"])
        reviewer_run_id = _seed_run(
            session,
            project_id=project_id,
            pack=reviewer_pack,
            agent_id="reviewer",
        )
    review_body = {
        "source_run_id": reviewer_run_id,
        "context_pack_id": payload["reviewer_context_pack_id"],
        "expected_context_version": 3,
        "verdict": "pass_with_known_issues",
        "message": "PRD 可进入 G2，保留 P2。",
        "findings": [
            {
                "severity": "P2",
                "title": "引用粒度需用户访谈验证",
                "evidence_refs": [candidate_ref],
                "reproduction": ["查看 PRD 已知问题"],
                "impact": "不阻断范围评审。",
                "recommended_fix": "进入种子访谈后补证。",
            }
        ],
        "review_artifact": {
            "kind": "prd_review",
            "title": "PRD Review",
            "content": f"# PRD Review\n\n可进入 G2。候选：{candidate_ref}",
            "evidence_refs": [candidate_ref],
        },
    }
    path = (
        f"/api/v1/agent-runtime/projects/{project_id}/prd-submissions/"
        f"{payload['submission_id']}/review"
    )
    headers = {"Idempotency-Key": f"{owner}-prd-review"}
    with TestClient(app) as client:
        first = client.post(path, headers=headers, json=review_body)
        second = client.post(path, headers=headers, json=review_body)
        events = client.get(f"/api/v1/projects/{project_id}/events?cursor=0")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "waiting_g2"
    assert first.json()["gate"]["gate_type"] == "G2"
    assert first.json()["gate"]["status"] == "open"
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True
    event_types = [event["event_type"] for event in events.json()]
    assert "prd.submitted" in event_types
    assert "prd.reviewed" in event_types
    assert event_types.count("tool_run.started") == 2
    assert event_types.count("tool_run.completed") == 2
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        assert project.state == "prd"
        assert project.context_version == 3
        assert session.scalar(
            select(func.count()).select_from(Gate).where(
                Gate.project_id == project_id,
                Gate.gate_type == "G2",
                Gate.status == "open",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(AgentMembership).where(
                AgentMembership.project_id == project_id,
                AgentMembership.agent_id == "builder",
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(AgentTask).where(
                AgentTask.project_id == project_id,
                AgentTask.assigned_agent == "builder",
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(ToolRun).join(
                AgentTask, ToolRun.task_id == AgentTask.id
            ).where(AgentTask.project_id == project_id)
        ) == 2


def _seed_run(
    session,
    *,
    project_id: str,
    pack: ContextPack,
    agent_id: str,
) -> str:
    task = AgentTask(
        project_id=project_id,
        assigned_agent=agent_id,
        title=f"{agent_id} PRD integration run",
        state="completed",
        context_version=pack.context_version,
        claimed_by="integration-runtime",
    )
    session.add(task)
    session.flush()
    run = AgentRun(
        task_id=task.id,
        state="succeeded",
        input_hash=hashlib.sha256(task.id.encode()).hexdigest(),
    )
    session.add(run)
    session.flush()
    session.add(
        RunStep(
            run_id=run.id,
            step_index=0,
            step_type="model",
            state="completed",
            input_hash=run.input_hash,
            output_ref="model://deepseek-integration-double",
        )
    )
    session.add(
        Event(
            project_id=project_id,
            sequence=(
                session.scalar(
                    select(func.max(Event.sequence)).where(Event.project_id == project_id)
                )
                or 0
            )
            + 1,
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
