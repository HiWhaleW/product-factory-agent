from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
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
    GateDecision,
    IdempotencyRecord,
    Message,
    PermissionDecision,
    PermissionRequest,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
    RunStep,
    TaskDependency,
)
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL database",
    ),
]


@pytest.fixture
def namespace() -> str:
    value = f"it-{uuid4()}"
    yield value
    with SessionLocal.begin() as session:
        session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key.like(f"{value}%")))
        session.execute(delete(Project).where(Project.owner_user_id == value))


def create_project(namespace: str, suffix: str = "project") -> dict:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": f"{namespace}-{suffix}"},
            json={"name": f"Integration {suffix}", "owner_user_id": namespace},
        )
    assert response.status_code == 201, response.text
    return response.json()


def brief_body(*, context_version: int = 1, previous_version: int = 0) -> dict:
    return {
        "expected_context_version": context_version,
        "expected_previous_version": previous_version,
        "objective": "帮助销售团队形成可追溯的复盘结论",
        "target_users": ["销售负责人"],
        "success_criteria": ["结论可回溯到证据"],
        "in_scope": ["项目对齐", "市场需求"],
        "out_of_scope": ["自动部署", "模型调用"],
        "timeline": "D5 完成定义链路底座",
        "open_questions": [],
        "source_clarification_ids": [],
        "created_by": "factory-lead",
    }


def create_and_approve_g0(namespace: str, suffix: str) -> tuple[str, dict]:
    project_id = create_project(namespace, suffix)["id"]
    with TestClient(app) as client:
        brief_response = client.post(
            f"/api/v1/projects/{project_id}/briefs",
            headers={"Idempotency-Key": f"{namespace}-{suffix}-brief"},
            json=brief_body(),
        )
        assert brief_response.status_code == 201, brief_response.text
        gate_id = brief_response.json()["gate"]["id"]
        decision = client.post(
            f"/api/v1/gates/{gate_id}/decisions",
            json={"decision": "approve", "context_version": 1, "comment": "批准 G0"},
        )
    assert decision.status_code == 200, decision.text
    return project_id, brief_response.json()["brief"]


def concurrent_posts(path: str, *, count: int, headers: dict | None, body: dict) -> list:
    barrier = Barrier(count)

    def post_once(_: int):
        barrier.wait()
        with TestClient(app) as client:
            return client.post(path, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=count) as executor:
        return list(executor.map(post_once, range(count)))


def seed_gate(namespace: str, *, context_version: int = 1) -> tuple[str, str]:
    project_id = create_project(namespace, f"gate-{uuid4()}")["id"]
    with SessionLocal.begin() as session:
        brief = ProjectBrief(project_id=project_id, latest_version=1)
        session.add(brief)
        session.flush()
        brief_version = ProjectBriefVersion(
            brief_id=brief.id,
            version=1,
            context_version=context_version,
            approval_status="draft",
            objective="Integration objective",
            target_users=["AI PM"],
            success_criteria=["Gate is deterministic"],
            in_scope=["G0"],
            out_of_scope=["model call"],
            timeline="D5",
            open_questions=[],
            source_clarification_ids=[],
            created_by="factory-lead",
        )
        session.add(brief_version)
        gate = Gate(
            project_id=project_id,
            gate_type="G0",
            context_version=context_version,
            status="open",
            target_state="mrd",
            reason="Approve integration Brief",
            impacted_artifact_refs=[
                {"resource_type": "project_brief", "resource_id": brief.id, "version": 1}
            ],
        )
        session.add(gate)
        session.flush()
        gate_id = gate.id
    return project_id, gate_id


def seed_permission(
    namespace: str,
    input_hash: str,
    *,
    context_version: int = 1,
    expires_at: datetime | None = None,
) -> tuple[str, str]:
    project_id = create_project(namespace, f"permission-{uuid4()}")["id"]
    task = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="Integration task",
        state="ready",
        context_version=context_version,
    )
    with SessionLocal.begin() as session:
        session.add(task)
        session.flush()
        run = AgentRun(task_id=task.id, input_hash="a" * 64)
        session.add(run)
        session.flush()
        request = PermissionRequest(
            run_id=run.id,
            tool_name="workspace.write",
            input_hash=input_hash,
            risk_level="medium",
            status="open",
            expires_at=expires_at,
        )
        session.add(request)
        session.flush()
        permission_id = request.id
    return project_id, permission_id


def test_health_uses_live_postgresql() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "postgresql"


def test_runtime_status_checks_codex_without_exposing_secrets() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/runtime/status")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "postgresql"
    assert body["codex"]["configured"] is True
    assert body["event_transport"] == "sse_cursor"
    assert body["short_polling_degraded"] is True
    assert "api_key" not in response.text.lower()


def test_project_sequential_idempotency_and_input_conflict(namespace: str) -> None:
    headers = {"Idempotency-Key": f"{namespace}-sequential"}
    body = {"name": "Same project", "owner_user_id": namespace}
    with TestClient(app) as client:
        first = client.post("/api/v1/projects", headers=headers, json=body)
        repeated = client.post("/api/v1/projects", headers=headers, json=body)
        conflict = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Different project", "owner_user_id": namespace},
        )
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_message_event_cursor_and_content_conflict(namespace: str) -> None:
    project_id = create_project(namespace)["id"]
    body = {"client_message_id": f"{namespace}-message", "content": "hello"}
    path = f"/api/v1/projects/{project_id}/messages"
    with TestClient(app) as client:
        first = client.post(path, json=body)
        repeated = client.post(path, json=body)
        conflict = client.post(path, json={**body, "content": "changed"})
        messages = client.get(f"/api/v1/projects/{project_id}/messages")
        all_events = client.get(f"/api/v1/projects/{project_id}/events")
        after_bootstrap = client.get(
            f"/api/v1/projects/{project_id}/events", params={"cursor": 3}
        )
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "MESSAGE_ID_CONFLICT"
    assert [message["content"] for message in messages.json()] == ["hello"]
    assert [event["sequence"] for event in all_events.json()] == [1, 2, 3, 4]
    assert [event["event_type"] for event in all_events.json()] == [
        "project.created",
        "agent.joined",
        "context.pack_created",
        "message.created",
    ]
    assert [event["sequence"] for event in after_bootstrap.json()] == [4]


def test_project_creates_initial_context_and_factory_lead_membership(namespace: str) -> None:
    project = create_project(namespace, "initial-context")
    with SessionLocal() as session:
        context = session.scalar(
            select(ContextVersion).where(
                ContextVersion.project_id == project["id"], ContextVersion.version == 1
            )
        )
        membership = session.scalar(
            select(AgentMembership).where(
                AgentMembership.project_id == project["id"],
                AgentMembership.agent_id == "factory-lead",
            )
        )
    assert context is not None
    assert (context.stage, context.approval_status) == ("alignment", "active")
    assert membership is not None
    assert membership.joined_context_version == 1


def test_clarification_is_idempotent_context_bound_and_conflict_safe(namespace: str) -> None:
    project_id = create_project(namespace, "clarification")["id"]
    path = f"/api/v1/projects/{project_id}/clarifications"
    body = {
        "client_clarification_id": f"{namespace}-clarification",
        "question": "目标用户是销售主管还是一线销售？",
        "answer": "销售主管",
        "scope_impact": "user",
        "expected_context_version": 1,
    }
    with TestClient(app) as client:
        first = client.post(path, json=body)
        repeated = client.post(path, json=body)
        conflict = client.post(path, json={**body, "answer": "一线销售"})
        stale = client.post(
            path,
            json={
                **body,
                "client_clarification_id": f"{namespace}-stale",
                "expected_context_version": 2,
            },
        )
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CLARIFICATION_ID_CONFLICT"
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CONTEXT"


def test_project_brief_is_versioned_idempotent_and_opens_g0(namespace: str) -> None:
    project_id = create_project(namespace, "brief-version")["id"]
    path = f"/api/v1/projects/{project_id}/briefs"
    headers = {"Idempotency-Key": f"{namespace}-brief-v1"}
    with TestClient(app) as client:
        first = client.post(path, headers=headers, json=brief_body())
        repeated = client.post(path, headers=headers, json=brief_body())
        conflict = client.post(
            path,
            headers=headers,
            json={**brief_body(), "objective": "different"},
        )
        fetched = client.get(f"{path}/1")
    assert first.status_code == repeated.status_code == 201
    assert first.json()["brief"]["version"] == 1
    assert first.json()["gate"]["gate_type"] == "G0"
    assert repeated.json()["idempotent"] is True
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert fetched.json()["objective"] == brief_body()["objective"]


def test_g0_changes_preserves_brief_v1_and_creates_v2(namespace: str) -> None:
    project_id = create_project(namespace, "brief-changes")["id"]
    path = f"/api/v1/projects/{project_id}/briefs"
    with TestClient(app) as client:
        first = client.post(
            path,
            headers={"Idempotency-Key": f"{namespace}-changes-v1"},
            json=brief_body(),
        )
        decision = client.post(
            f"/api/v1/gates/{first.json()['gate']['id']}/decisions",
            json={"decision": "changes", "context_version": 1, "comment": "补充成功标准"},
        )
        second = client.post(
            path,
            headers={"Idempotency-Key": f"{namespace}-changes-v2"},
            json={
                **brief_body(context_version=2, previous_version=1),
                "success_criteria": ["结论可回溯到证据", "用户确认复盘可执行"],
            },
        )
        v1 = client.get(f"{path}/1")
        v2 = client.get(f"{path}/2")
    assert decision.status_code == 200
    assert second.status_code == 201
    assert v1.json()["approval_status"] == "changes_requested"
    assert v2.json()["approval_status"] == "draft"
    assert v1.json()["id"] != v2.json()["id"]


def test_g0_approve_versions_context_joins_ai_pm_and_supports_exact_retrieval(
    namespace: str,
) -> None:
    project_id, brief = create_and_approve_g0(namespace, "g0-contract")
    params = {
        "stage": "mrd",
        "context_version": 2,
        "resource_type": "project_brief",
        "resource_id": brief["brief_id"],
        "resource_version": 1,
        "approval_status": "approved",
        "recipient_agent_id": "ai-pm",
    }
    with TestClient(app) as client:
        project = client.get(f"/api/v1/projects/{project_id}")
        context = client.get(f"/api/v1/projects/{project_id}/context-versions/2")
        exact = client.get(f"/api/v1/projects/{project_id}/context-packs/exact", params=params)
        wrong_version = client.get(
            f"/api/v1/projects/{project_id}/context-packs/exact",
            params={**params, "resource_version": 2},
        )
        events = client.get(f"/api/v1/projects/{project_id}/events")
        cursor = events.json()[-2]["sequence"]
        resumed = client.get(
            f"/api/v1/projects/{project_id}/events", params={"cursor": cursor}
        )
        sse = client.get(
            f"/api/v1/projects/{project_id}/events/stream", params={"cursor": cursor}
        )
    assert project.json()["state"] == "mrd"
    assert project.json()["context_version"] == 2
    assert context.json()["stage"] == "mrd"
    assert exact.status_code == 200
    assert exact.json()["primary_resource"]["version"] == 1
    assert wrong_version.status_code == 404
    assert resumed.json()[0]["sequence"] == cursor + 1
    assert sse.headers["content-type"].startswith("text/event-stream")
    assert f"id: {cursor + 1}" in sse.text
    event_types = [event["event_type"] for event in events.json()]
    assert "context.updated" in event_types
    assert "context.pack_created" in event_types
    assert "agent.joined" in event_types
    with SessionLocal() as session:
        membership = session.scalar(
            select(AgentMembership).where(
                AgentMembership.project_id == project_id,
                AgentMembership.agent_id == "ai-pm",
            )
        )
    assert membership is not None


def test_g1_requires_exact_evidence_set_and_approves_versions(namespace: str) -> None:
    project_id, _ = create_and_approve_g0(namespace, "g1-contract")
    artifacts: list[tuple[Artifact, ArtifactVersion]] = []
    with SessionLocal.begin() as session:
        for kind in ("evidence_index", "mrd", "red_team_review"):
            artifact = Artifact(
                project_id=project_id,
                title=kind,
                kind=kind,
                stage="mrd",
                status="draft",
            )
            session.add(artifact)
            session.flush()
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=2,
                approval_status="draft",
                content_ref=f"integration/{namespace}-{kind}.md",
                content_hash=hashlib.sha256(kind.encode()).hexdigest(),
                summary=kind,
            )
            session.add(version)
            artifacts.append((artifact, version))
        session.flush()
        refs = [{"artifact_id": artifact.id, "version": 1} for artifact, _ in artifacts]
        mrd_id = next(artifact.id for artifact, _ in artifacts if artifact.kind == "mrd")
    with TestClient(app) as client:
        missing = client.post(
            f"/api/v1/projects/{project_id}/gates",
            headers={"Idempotency-Key": f"{namespace}-g1-missing"},
            json={
                "gate_type": "G1",
                "context_version": 2,
                "target_state": "prd",
                "reason": "missing evidence",
                "impacted_artifact_refs": refs[:-1],
            },
        )
        opened = client.post(
            f"/api/v1/projects/{project_id}/gates",
            headers={"Idempotency-Key": f"{namespace}-g1-complete"},
            json={
                "gate_type": "G1",
                "context_version": 2,
                "target_state": "prd",
                "reason": "evidence complete",
                "impacted_artifact_refs": refs,
            },
        )
        decision = client.post(
            f"/api/v1/gates/{opened.json()['id']}/decisions",
            json={"decision": "approve", "context_version": 2, "comment": "批准 G1"},
        )
        exact = client.get(
            f"/api/v1/projects/{project_id}/context-packs/exact",
            params={
                "stage": "prd",
                "context_version": 3,
                "resource_type": "artifact",
                "resource_id": mrd_id,
                "resource_version": 1,
                "approval_status": "approved",
                "recipient_agent_id": "ai-pm",
            },
        )
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "GATE_EVIDENCE_MISSING"
    assert opened.status_code == 201
    assert decision.status_code == 200
    assert decision.json()["target_state"] == "prd"
    assert decision.json()["context_version"] == 3
    assert exact.status_code == 200
    assert len(exact.json()["required_resources"]) == 2
    with SessionLocal() as session:
        statuses = session.scalars(
            select(ArtifactVersion.approval_status).where(
                ArtifactVersion.artifact_id.in_([artifact.id for artifact, _ in artifacts])
            )
        ).all()
    assert statuses == ["approved", "approved", "approved"]


def test_context_pack_rejects_unapproved_or_cross_project_resource(namespace: str) -> None:
    project_id, _ = create_and_approve_g0(namespace, "context-reject")
    other_project_id = create_project(namespace, "context-other")["id"]
    artifact = Artifact(
        project_id=other_project_id,
        title="foreign evidence",
        kind="evidence_index",
        stage="alignment",
        status="draft",
    )
    with SessionLocal.begin() as session:
        session.add(artifact)
        session.flush()
        session.add(
            ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=1,
                approval_status="draft",
                content_ref="integration/foreign.md",
                content_hash="1" * 64,
                summary="foreign",
            )
        )
        artifact_id = artifact.id
    body = {
        "context_version": 2,
        "stage": "mrd",
        "recipient_agent_id": "ai-pm",
        "primary_resource": {
            "resource_type": "artifact",
            "resource_id": artifact_id,
            "version": 1,
            "approval_status": "approved",
        },
        "task": "must fail closed",
    }
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{project_id}/context-packs",
            headers={"Idempotency-Key": f"{namespace}-foreign-context"},
            json=body,
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTEXT_RESOURCE_PROJECT_MISMATCH"


def test_artifact_graph_is_projected_from_postgresql(namespace: str) -> None:
    project_id = create_project(namespace)["id"]
    source = Artifact(
        project_id=project_id,
        title="Brief",
        kind="brief",
        stage="alignment",
        status="approved",
    )
    target = Artifact(
        project_id=project_id,
        title="MRD",
        kind="mrd",
        stage="mrd",
        status="draft",
    )
    with SessionLocal.begin() as session:
        session.add_all([source, target])
        session.flush()
        edge = ArtifactEdge(project_id=project_id, source_id=source.id, target_id=target.id)
        session.add(edge)
        source_id, target_id = source.id, target.id
    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{project_id}/graph")
    assert response.status_code == 200
    assert {node["id"] for node in response.json()["nodes"]} == {source_id, target_id}
    assert response.json()["edges"][0]["source_id"] == source_id
    assert response.json()["edges"][0]["target_id"] == target_id


def test_artifact_content_is_hash_verified_and_scoped(namespace: str) -> None:
    project_id = create_project(namespace, "artifact-content")["id"]
    relative_path = f"integration/{namespace}.md"
    root = get_settings().ARTIFACT_ROOT
    content_path = root / relative_path
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content = "# 可验证产物\n\n来自 PostgreSQL 版本记录。"
    content_path.write_text(content, encoding="utf-8")
    artifact = Artifact(
        project_id=project_id,
        title="项目简报",
        kind="markdown",
        stage="alignment",
        status="approved",
    )
    try:
        with SessionLocal.begin() as session:
            session.add(artifact)
            session.flush()
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=1,
                content_ref=relative_path,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                summary="集成测试产物",
            )
            session.add(version)
            session.flush()
            artifact_id = artifact.id
        with TestClient(app) as client:
            metadata = client.get(f"/api/v1/artifacts/{artifact_id}/versions/1")
            preview = client.get(f"/api/v1/artifacts/{artifact_id}/content")
        assert metadata.status_code == 200
        assert metadata.json()["content_hash"] == hashlib.sha256(content.encode()).hexdigest()
        assert preview.status_code == 200
        assert preview.json()["content"] == content
        assert preview.json()["filename"] == "项目简报.md"
    finally:
        content_path.unlink(missing_ok=True)


def test_agent_definition_artifact_contract_is_versioned_and_idempotent(namespace: str) -> None:
    project_id, _ = create_and_approve_g0(namespace, "agent-artifact")
    relative_path = f"integration/{namespace}-evidence.md"
    root = get_settings().ARTIFACT_ROOT
    content_path = root / relative_path
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content = "# Evidence Index\n\nPublic evidence references only."
    content_path.write_text(content, encoding="utf-8")
    body = {
        "project_id": project_id,
        "context_version": 2,
        "artifact_kind": "evidence_index",
        "title": "Evidence Index",
        "content_ref": relative_path,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "summary": "Evidence contract",
    }
    try:
        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/projects/{project_id}/definition-artifacts",
                headers={"Idempotency-Key": f"{namespace}-evidence-v1"},
                json=body,
            )
            repeated = client.post(
                f"/api/v1/projects/{project_id}/definition-artifacts",
                headers={"Idempotency-Key": f"{namespace}-evidence-v1"},
                json=body,
            )
        assert first.status_code == repeated.status_code == 201
        assert first.json()["artifact_id"] == repeated.json()["artifact_id"]
        assert first.json()["version"] == repeated.json()["version"] == 1
        assert first.json()["approval_status"] == "draft"
    finally:
        content_path.unlink(missing_ok=True)


def test_gate_decision_is_idempotent_and_rejects_stale_context(namespace: str) -> None:
    project_id, gate_id = seed_gate(namespace)
    path = f"/api/v1/gates/{gate_id}/decisions"
    body = {
        "decision": "approve",
        "context_version": 1,
        "comment": "用户批准 G0",
        "decided_by": "integration-user",
    }
    with TestClient(app) as client:
        open_gates = client.get(f"/api/v1/projects/{project_id}/gates")
        first = client.post(path, json=body)
        repeated = client.post(path, json=body)
        remaining = client.get(f"/api/v1/projects/{project_id}/gates")
        all_gates = client.get(f"/api/v1/projects/{project_id}/gates", params={"status": "all"})
        decisions = client.get(f"/api/v1/projects/{project_id}/gate-decisions")
    assert open_gates.status_code == 200
    assert open_gates.json()[0]["id"] == gate_id
    assert first.status_code == repeated.status_code == 200
    assert first.json()["idempotent"] is False
    assert repeated.json()["idempotent"] is True
    assert remaining.json() == []
    assert all_gates.json()[0]["status"] == "approved"
    assert decisions.status_code == 200
    assert decisions.json() == [
        {
            "id": decisions.json()[0]["id"],
            "gate_id": gate_id,
            "project_id": project_id,
            "gate_type": "G0",
            "decision": "approve",
            "comment": "用户批准 G0",
            "decided_by": "integration-user",
            "context_version_before": 1,
            "context_version_after": 2,
            "target_state": "mrd",
            "decided_at": decisions.json()[0]["decided_at"],
        }
    ]
    with SessionLocal() as session:
        assert session.get(Project, project_id).state == "mrd"
        decisions = session.scalars(
            select(GateDecision).where(GateDecision.gate_id == gate_id)
        ).all()
        assert len(decisions) == 1

    _, stale_gate_id = seed_gate(namespace, context_version=2)
    with TestClient(app) as client:
        stale = client.post(
            f"/api/v1/gates/{stale_gate_id}/decisions",
            json={"decision": "approve", "context_version": 1},
        )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_CONTEXT"


@pytest.mark.parametrize(
    ("decision_name", "expected_state", "expected_gate_status"),
    [
        ("changes", "alignment", "changes_requested"),
        ("pause", "paused", "paused"),
        ("kill", "killed", "killed"),
    ],
)
def test_g0_non_approve_decisions_are_deterministic(
    namespace: str,
    decision_name: str,
    expected_state: str,
    expected_gate_status: str,
) -> None:
    project_id, gate_id = seed_gate(namespace)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/gates/{gate_id}/decisions",
            json={
                "decision": decision_name,
                "context_version": 1,
                "comment": f"integration {decision_name}",
            },
        )
        project = client.get(f"/api/v1/projects/{project_id}")
        gates = client.get(f"/api/v1/projects/{project_id}/gates", params={"status": "all"})
    assert response.status_code == 200
    assert response.json()["context_version"] == 2
    assert project.json()["state"] == expected_state
    assert project.json()["context_version"] == 2
    assert gates.json()[0]["status"] == expected_gate_status


def test_request_id_is_preserved_in_structured_api_errors(namespace: str) -> None:
    request_id = f"req-{namespace}"
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/projects/does-not-exist",
            headers={"X-Request-Id": request_id},
        )
    assert response.status_code == 404
    assert response.headers["x-request-id"] == request_id
    assert response.json()["error"]["request_id"] == request_id


def test_permission_decision_is_idempotent_and_binds_input_hash(namespace: str) -> None:
    input_hash = "b" * 64
    project_id, permission_id = seed_permission(namespace, input_hash)
    path = f"/api/v1/permissions/{permission_id}/decisions"
    body = {"decision": "allow", "input_hash": input_hash}
    with TestClient(app) as client:
        before = client.get(f"/api/v1/projects/{project_id}").json()
        open_permissions = client.get(f"/api/v1/projects/{project_id}/permissions")
        first = client.post(path, json=body)
        repeated = client.post(path, json=body)
        after = client.get(f"/api/v1/projects/{project_id}").json()
        remaining = client.get(f"/api/v1/projects/{project_id}/permissions")
    assert open_permissions.status_code == 200
    assert open_permissions.json()[0]["id"] == permission_id
    assert open_permissions.json()[0]["task_id"]
    assert first.status_code == repeated.status_code == 200
    assert first.json()["idempotent"] is False
    assert repeated.json()["idempotent"] is True
    assert before["state"] == after["state"] == "alignment"
    assert remaining.json() == []

    _, changed_id = seed_permission(namespace, "c" * 64)
    with TestClient(app) as client:
        changed = client.post(
            f"/api/v1/permissions/{changed_id}/decisions",
            json={"decision": "allow", "input_hash": "d" * 64},
        )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "PERMISSION_INPUT_CHANGED"


def test_permission_rejects_expired_and_stale_requests(namespace: str) -> None:
    expired_project_id, expired_id = seed_permission(
        namespace,
        "f" * 64,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    stale_project_id, stale_id = seed_permission(namespace, "a" * 64, context_version=2)
    with TestClient(app) as client:
        expired = client.post(
            f"/api/v1/permissions/{expired_id}/decisions",
            json={"decision": "allow", "input_hash": "f" * 64},
        )
        stale = client.post(
            f"/api/v1/permissions/{stale_id}/decisions",
            json={"decision": "allow", "input_hash": "a" * 64},
        )
        expired_open = client.get(f"/api/v1/projects/{expired_project_id}/permissions")
        stale_open = client.get(f"/api/v1/projects/{stale_project_id}/permissions")
    assert expired.status_code == stale.status_code == 409
    assert expired.json()["error"]["code"] == "PERMISSION_EXPIRED"
    assert stale.json()["error"]["code"] == "STALE_CONTEXT"
    assert expired_open.json() == stale_open.json() == []


def test_concurrent_project_create_returns_one_resource(namespace: str) -> None:
    responses = concurrent_posts(
        "/api/v1/projects",
        count=8,
        headers={"Idempotency-Key": f"{namespace}-concurrent-project"},
        body={"name": "Concurrent project", "owner_user_id": namespace},
    )
    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["id"] for response in responses}) == 1


def test_concurrent_project_brief_submission_creates_one_version_and_gate(namespace: str) -> None:
    project_id = create_project(namespace, "concurrent-brief")["id"]
    responses = concurrent_posts(
        f"/api/v1/projects/{project_id}/briefs",
        count=8,
        headers={"Idempotency-Key": f"{namespace}-concurrent-brief"},
        body=brief_body(),
    )
    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["brief"]["id"] for response in responses}) == 1
    assert sum(response.json()["idempotent"] is False for response in responses) == 1
    with SessionLocal() as session:
        brief = session.scalar(select(ProjectBrief).where(ProjectBrief.project_id == project_id))
        versions = session.scalars(
            select(ProjectBriefVersion).where(ProjectBriefVersion.brief_id == brief.id)
        ).all()
        gates = session.scalars(
            select(Gate).where(Gate.project_id == project_id, Gate.gate_type == "G0")
        ).all()
    assert len(versions) == len(gates) == 1


def test_concurrent_same_message_returns_one_message_and_event(namespace: str) -> None:
    project_id = create_project(namespace)["id"]
    message_id = f"{namespace}-same-message"
    responses = concurrent_posts(
        f"/api/v1/projects/{project_id}/messages",
        count=8,
        headers=None,
        body={"client_message_id": message_id, "content": "same"},
    )
    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["id"] for response in responses}) == 1
    with SessionLocal() as session:
        messages = session.scalars(
            select(Message).where(
                Message.project_id == project_id,
                Message.client_message_id == message_id,
            )
        ).all()
        events = session.scalars(
            select(Event).where(
                Event.project_id == project_id,
                Event.event_type == "message.created",
            )
        ).all()
    assert len(messages) == len(events) == 1


def test_concurrent_distinct_messages_have_contiguous_event_sequence(namespace: str) -> None:
    project_id = create_project(namespace)["id"]
    count = 12
    barrier = Barrier(count)

    def create_message(index: int):
        barrier.wait()
        with TestClient(app) as client:
            return client.post(
                f"/api/v1/projects/{project_id}/messages",
                json={"client_message_id": f"{namespace}-{index}", "content": str(index)},
            )

    with ThreadPoolExecutor(max_workers=count) as executor:
        responses = list(executor.map(create_message, range(count)))
    assert {response.status_code for response in responses} == {201}
    with SessionLocal() as session:
        events = session.scalars(
            select(Event).where(Event.project_id == project_id).order_by(Event.sequence)
        ).all()
    assert [event.sequence for event in events] == list(range(1, count + 4))
    assert [event.event_type for event in events[:3]] == [
        "project.created",
        "agent.joined",
        "context.pack_created",
    ]
    assert [event.event_type for event in events[3:]] == ["message.created"] * count


def test_concurrent_gate_double_click_returns_original_decision(namespace: str) -> None:
    project_id, gate_id = seed_gate(namespace)
    responses = concurrent_posts(
        f"/api/v1/gates/{gate_id}/decisions",
        count=8,
        headers=None,
        body={"decision": "approve", "context_version": 1},
    )
    assert {response.status_code for response in responses} == {200}
    assert sum(response.json()["idempotent"] is False for response in responses) == 1
    with SessionLocal() as session:
        assert session.get(Project, project_id).state == "mrd"
        decisions = session.scalars(
            select(GateDecision).where(GateDecision.gate_id == gate_id)
        ).all()
        assert len(decisions) == 1


def test_concurrent_permission_double_click_returns_original_decision(namespace: str) -> None:
    input_hash = "e" * 64
    _, permission_id = seed_permission(namespace, input_hash)
    responses = concurrent_posts(
        f"/api/v1/permissions/{permission_id}/decisions",
        count=8,
        headers=None,
        body={"decision": "allow", "input_hash": input_hash},
    )
    assert {response.status_code for response in responses} == {200}
    assert sum(response.json()["idempotent"] is False for response in responses) == 1
    with SessionLocal() as session:
        decisions = session.scalars(
            select(PermissionDecision).where(
                PermissionDecision.permission_request_id == permission_id
            )
        ).all()
    assert len(decisions) == 1


def test_concurrent_ready_task_is_claimed_by_exactly_one_worker(namespace: str) -> None:
    project_id = create_project(namespace, "task-claim")["id"]
    task = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="Atomic claim",
        state="ready",
        context_version=1,
    )
    with SessionLocal.begin() as session:
        session.add(task)
        session.flush()
        task_id = task.id

    count = 8
    barrier = Barrier(count)

    def claim(index: int):
        barrier.wait()
        with TestClient(app, raise_server_exceptions=False) as client:
            return client.post(
                f"/api/v1/tasks/{task_id}/claim",
                json={"worker_id": f"worker-{index}"},
            )

    with ThreadPoolExecutor(max_workers=count) as executor:
        responses = list(executor.map(claim, range(count)))

    assert [response.status_code for response in responses].count(200) == 1
    assert [response.status_code for response in responses].count(409) == count - 1
    winner = next(response.json() for response in responses if response.status_code == 200)
    with SessionLocal() as session:
        stored = session.get(AgentTask, task_id)
        events = session.scalars(
            select(Event).where(
                Event.project_id == project_id,
                Event.event_type == "task.claimed",
            )
        ).all()
    assert stored is not None
    assert stored.state == "running"
    assert stored.claimed_by == winner["claimed_by"]
    assert len(events) == 1


def test_task_claim_waits_for_completed_dependencies(namespace: str) -> None:
    project_id = create_project(namespace, "task-dependency")["id"]
    upstream = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="Backend",
        state="running",
        context_version=1,
    )
    downstream = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="Frontend",
        state="ready",
        context_version=1,
    )
    with SessionLocal.begin() as session:
        session.add_all([upstream, downstream])
        session.flush()
        session.add(TaskDependency(task_id=downstream.id, depends_on_task_id=upstream.id))
        upstream_id, downstream_id = upstream.id, downstream.id
    with TestClient(app) as client:
        blocked = client.post(
            f"/api/v1/tasks/{downstream_id}/claim",
            json={"worker_id": "frontend-worker"},
        )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "TASK_DEPENDENCY_BLOCKED"
    with SessionLocal.begin() as session:
        session.get(AgentTask, upstream_id).state = "completed"
    with TestClient(app) as client:
        claimed = client.post(
            f"/api/v1/tasks/{downstream_id}/claim",
            json={"worker_id": "frontend-worker"},
        )
    assert claimed.status_code == 200
    assert claimed.json()["state"] == "running"


def test_run_snapshot_and_idempotent_resume(namespace: str) -> None:
    project_id = create_project(namespace, "run-resume")["id"]
    task = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="Recoverable run",
        state="running",
        context_version=1,
    )
    with SessionLocal.begin() as session:
        session.add(task)
        session.flush()
        run = AgentRun(task_id=task.id, input_hash="9" * 64, state="failed")
        session.add(run)
        session.flush()
        session.add(
            RunStep(
                run_id=run.id,
                step_index=0,
                step_type="plan",
                state="completed",
                input_hash="8" * 64,
                output_ref="artifact://plan",
            )
        )
        session.flush()
        run_id, resume_token = run.id, run.resume_token
    body = {"resume_token": resume_token, "input_hash": "9" * 64}
    with TestClient(app) as client:
        before = client.get(f"/api/v1/runs/{run_id}")
        resumed = client.post(f"/api/v1/runs/{run_id}/resume", json=body)
        repeated = client.post(f"/api/v1/runs/{run_id}/resume", json=body)
    assert before.status_code == 200
    assert before.json()["steps"][0]["state"] == "completed"
    assert resumed.json() == {"run_id": run_id, "state": "pending", "idempotent": False}
    assert repeated.json() == {"run_id": run_id, "state": "pending", "idempotent": True}


def test_run_resume_requires_side_effect_reconciliation(namespace: str) -> None:
    project_id = create_project(namespace, "run-reconcile")["id"]
    task = AgentTask(
        project_id=project_id,
        assigned_agent="builder",
        title="External effect",
        state="running",
        context_version=1,
    )
    with SessionLocal.begin() as session:
        session.add(task)
        session.flush()
        run = AgentRun(task_id=task.id, input_hash="7" * 64, state="failed")
        session.add(run)
        session.flush()
        session.add(
            RunStep(
                run_id=run.id,
                step_index=0,
                step_type="tool",
                state="running",
                idempotency_key=f"{namespace}-effect",
                input_hash="6" * 64,
                external_effect_confirmed=False,
            )
        )
        session.flush()
        run_id, resume_token = run.id, run.resume_token
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/runs/{run_id}/resume",
            json={"resume_token": resume_token, "input_hash": "7" * 64},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SIDE_EFFECT_RECONCILIATION_REQUIRED"
