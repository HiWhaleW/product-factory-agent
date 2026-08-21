from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from app.core.database import SessionLocal
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    ContextPack,
    DefinitionReview,
    DefinitionSubmission,
    Event,
    Gate,
    PermissionDecision,
    PermissionRequest,
    Project,
    RunStep,
)
from app.main import app
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
def definition_scope() -> tuple[str, str, dict]:
    owner = f"definition-it-{uuid4()}"
    with TestClient(app) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": f"{owner}-project"},
            json={"name": "Definition chain", "owner_user_id": owner},
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        brief_response = client.post(
            f"/api/v1/projects/{project_id}/briefs",
            headers={"Idempotency-Key": f"{owner}-brief"},
            json={
                "expected_context_version": 1,
                "expected_previous_version": 0,
                "objective": "验证 Evidence/MRD/Reviewer/G1 确定性链路",
                "target_users": ["产品负责人"],
                "success_criteria": ["每个结论可追溯"],
                "in_scope": ["Evidence Index", "MRD"],
                "out_of_scope": ["PRD", "Builder"],
                "timeline": "D5",
                "open_questions": [],
                "source_clarification_ids": [],
                "created_by": "factory-lead",
            },
        )
        assert brief_response.status_code == 201, brief_response.text
        approve = client.post(
            f"/api/v1/gates/{brief_response.json()['gate']['id']}/decisions",
            json={
                "decision": "approve",
                "context_version": 1,
                "comment": "integration fixture only",
            },
        )
        assert approve.status_code == 200, approve.text

    research_results = [_research_set()]
    evidence_hash = hashlib.sha256(
        json.dumps(research_results, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    with SessionLocal.begin() as session:
        pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project_id,
                ContextPack.agent_id == "ai-pm",
                ContextPack.stage == "mrd",
            )
        )
        assert pack is not None
        run_id = _seed_successful_run(
            session,
            project_id=project_id,
            context_pack=pack,
            agent_id="ai-pm",
            evidence_hash=evidence_hash,
            with_research_permission=True,
        )
    body = {
        "source_run_id": run_id,
        "context_pack_id": pack.id,
        "expected_context_version": 2,
        "evidence_set_hash": evidence_hash,
        "research_results": research_results,
        "artifact_proposals": [
            {
                "kind": "evidence_index",
                "title": "Evidence Index",
                "content": "# Evidence Index\n\n- 官方报告：bocha evidence",
                "evidence_refs": [_evidence_ref()],
                "assumptions": [],
                "status": "waiting_review",
            },
            {
                "kind": "mrd",
                "title": "MRD",
                "content": "# MRD\n\n基于公开证据的市场需求草案。",
                "evidence_refs": [_evidence_ref()],
                "assumptions": ["需要用户访谈继续验证"],
                "status": "waiting_review",
            },
        ],
    }
    yield project_id, owner, body
    with SessionLocal.begin() as session:
        submission_ids = select(DefinitionSubmission.id).where(
            DefinitionSubmission.project_id == project_id
        )
        session.execute(
            delete(DefinitionReview).where(
                DefinitionReview.submission_id.in_(submission_ids)
            )
        )
        session.execute(
            delete(DefinitionSubmission).where(
                DefinitionSubmission.project_id == project_id
            )
        )
        session.execute(delete(Project).where(Project.id == project_id))


def test_definition_submission_is_atomic_idempotent_and_cursor_recoverable(
    definition_scope,
) -> None:
    project_id, owner, body = definition_scope
    with SessionLocal() as session:
        cursor_before = session.scalar(
            select(func.max(Event.sequence)).where(Event.project_id == project_id)
        )
    path = f"/api/v1/projects/{project_id}/definition-submissions"
    barrier = Barrier(2)

    def submit_once(_: int):
        barrier.wait()
        with TestClient(app) as client:
            return client.post(
                path,
                headers={"Idempotency-Key": f"{owner}-definition"},
                json=body,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(submit_once, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    payloads = [response.json() for response in responses]
    assert {payload["id"] for payload in payloads}.__len__() == 1
    assert sorted(payload["idempotent"] for payload in payloads) == [False, True]
    result = payloads[0]
    assert {ref["kind"] for ref in result["artifact_refs"]} == {"evidence_index", "mrd"}
    assert result["status"] == "waiting_reviewer"

    with SessionLocal() as session:
        assert session.scalar(
            select(func.count()).select_from(DefinitionSubmission).where(
                DefinitionSubmission.project_id == project_id
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.project_id == project_id)
        ) == 2
        stored = session.scalar(
            select(DefinitionSubmission).where(DefinitionSubmission.id == result["id"])
        )
        assert stored.evidence_refs == [_evidence_ref()]
        assert "research_results" not in stored.__dict__

    with TestClient(app) as client:
        reviewer = client.get(
            f"/api/v1/projects/{project_id}/definition-submissions/{result['id']}"
            "/reviewer-input"
        )
        events = client.get(
            f"/api/v1/projects/{project_id}/events?cursor={cursor_before}"
        )
    assert reviewer.status_code == 200, reviewer.text
    assert {item["kind"] for item in reviewer.json()["artifacts"]} == {
        "evidence_index",
        "mrd",
    }
    sequences = [event["sequence"] for event in events.json()]
    assert sequences == list(range(cursor_before + 1, cursor_before + 1 + len(sequences)))
    assert "definition.submitted" in [event["event_type"] for event in events.json()]


def test_definition_submission_rejects_missing_permission(definition_scope) -> None:
    project_id, owner, body = definition_scope
    with SessionLocal.begin() as session:
        request = session.scalar(
            select(PermissionRequest).where(PermissionRequest.run_id == body["source_run_id"])
        )
        decision = session.scalar(
            select(PermissionDecision).where(
                PermissionDecision.permission_request_id == request.id
            )
        )
        session.delete(decision)
        request.status = "open"
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{project_id}/definition-submissions",
            headers={"Idempotency-Key": f"{owner}-no-permission"},
            json=body,
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESEARCH_PERMISSION_NOT_CONFIRMED"
    with SessionLocal() as session:
        assert session.scalar(
            select(func.count()).select_from(DefinitionSubmission).where(
                DefinitionSubmission.project_id == project_id
            )
        ) == 0


def test_reviewer_pass_opens_g1_once_without_advancing_project(definition_scope) -> None:
    project_id, owner, body = definition_scope
    with TestClient(app) as client:
        submission_response = client.post(
            f"/api/v1/projects/{project_id}/definition-submissions",
            headers={"Idempotency-Key": f"{owner}-definition-review"},
            json=body,
        )
    assert submission_response.status_code == 201, submission_response.text
    submission = submission_response.json()
    with SessionLocal.begin() as session:
        pack = session.get(ContextPack, submission["reviewer_context_pack_id"])
        reviewer_run_id = _seed_successful_run(
            session,
            project_id=project_id,
            context_pack=pack,
            agent_id="reviewer",
        )
    review_body = {
        "source_run_id": reviewer_run_id,
        "context_pack_id": submission["reviewer_context_pack_id"],
        "expected_context_version": 2,
        "verdict": "pass_with_known_issues",
        "message": "证据可追溯，保留一个 P2 风险。",
        "findings": [
            {
                "severity": "P2",
                "title": "样本仍需扩展",
                "evidence_refs": [_evidence_ref()],
                "reproduction": ["检查 Evidence Index"],
                "impact": "结论外推范围有限",
                "recommended_fix": "G1 后继续补充访谈",
            }
        ],
        "red_team_review": {
            "kind": "red_team_review",
            "title": "MRD Red Team Review",
            "content": "# Red Team Review\n\n结论：可进入 G1，但需记录样本风险。",
            "evidence_refs": [_evidence_ref()],
        },
    }
    path = (
        f"/api/v1/projects/{project_id}/definition-submissions/{submission['id']}/review"
    )
    headers = {"Idempotency-Key": f"{owner}-review"}
    with TestClient(app) as client:
        first = client.post(path, headers=headers, json=review_body)
        second = client.post(path, headers=headers, json=review_body)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "waiting_g1"
    assert first.json()["gate"]["gate_type"] == "G1"
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        assert project.state == "mrd"
        assert project.context_version == 2
        assert session.scalar(
            select(func.count()).select_from(Gate).where(
                Gate.project_id == project_id,
                Gate.gate_type == "G1",
                Gate.status == "open",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(DefinitionReview).join(
                DefinitionSubmission,
                DefinitionReview.submission_id == DefinitionSubmission.id,
            ).where(DefinitionSubmission.project_id == project_id)
        ) == 1


def _seed_successful_run(
    session,
    *,
    project_id: str,
    context_pack: ContextPack,
    agent_id: str,
    evidence_hash: str | None = None,
    with_research_permission: bool = False,
) -> str:
    task = AgentTask(
        project_id=project_id,
        assigned_agent=agent_id,
        title=f"{agent_id} integration run",
        state="completed",
        context_version=context_pack.context_version,
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
    if evidence_hash:
        session.add(
            RunStep(
                run_id=run.id,
                step_index=0,
                step_type="tool",
                state="completed",
                idempotency_key=f"web_research:{run.id}:1",
                input_hash=run.input_hash,
                output_ref=f"evidence-set://{evidence_hash}",
                external_effect_confirmed=True,
            )
        )
        next_step_index = 1
    else:
        next_step_index = 0
    session.add(
        RunStep(
            run_id=run.id,
            step_index=next_step_index,
            step_type="model",
            state="completed",
            input_hash=run.input_hash,
            output_ref="model://deepseek-integration-double",
        )
    )
    checkpoint_hash = hashlib.sha256(f"checkpoint:{run.id}".encode()).hexdigest()
    session.add(
        RunStep(
            run_id=run.id,
            step_index=next_step_index + 1,
            step_type="checkpoint",
            state="completed",
            idempotency_key=f"checkpoint:{checkpoint_hash}",
            input_hash=checkpoint_hash,
            output_ref=f".runtime-checkpoints/{run.id}/{checkpoint_hash}.json",
            external_effect_confirmed=True,
        )
    )
    if with_research_permission:
        request = PermissionRequest(
            run_id=run.id,
            tool_name="web_research",
            input_hash=hashlib.sha256(f"permission:{run.id}".encode()).hexdigest(),
            risk_level="high",
            status="decided",
        )
        session.add(request)
        session.flush()
        session.add(
            PermissionDecision(
                permission_request_id=request.id,
                decision="allow",
                input_hash=request.input_hash,
                decided_by="local-admin",
            )
        )
    sequence = session.scalar(
        select(func.max(Event.sequence)).where(Event.project_id == project_id)
    )
    session.add(
        Event(
            project_id=project_id,
            sequence=(sequence or 0) + 1,
            event_type="run.started",
            payload={
                "run_id": run.id,
                "task_id": task.id,
                "agent_id": agent_id,
                "context_pack_id": context_pack.id,
                "context_version": context_pack.context_version,
            },
        )
    )
    return run.id


def _research_set() -> dict:
    return {
        "provider": "bocha",
        "provider_request_id": "bocha-definition-integration",
        "query": "AI Agent 市场需求",
        "total_estimated_matches": 1,
        "results": [
            {
                "evidence_ref": _evidence_ref(),
                "title": "官方市场报告",
                "url": _evidence_url(),
                "site_name": "Example",
                "snippet": "市场需求证据",
                "summary": "公开报告摘要",
                "date_published": "2026-08-20T00:00:00+08:00",
            }
        ],
    }


def _evidence_url() -> str:
    return "https://example.com/definition-chain-report"


def _evidence_ref() -> str:
    return f"bocha:web:{hashlib.sha256(_evidence_url().encode()).hexdigest()}"
