from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import (
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
from app.domain.schemas import (
    BackendDeliveryCreate,
    BackendVerificationEvidence,
    FrontendDeliveryCreate,
    FrontendVerificationEvidence,
    InternalAcceptanceCreate,
    InternalAcceptanceEvidence,
)
from app.main import app
from app.services.artifact_store import write_immutable_artifact
from app.services.backend_delivery import BackendDeliveryService
from app.services.builder_runtime import BuilderRuntimeService
from app.services.frontend_delivery import FrontendDeliveryService
from app.services.internal_acceptance import InternalAcceptanceService
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
def technical_scope() -> tuple[str, str, str]:
    owner = f"technical-it-{uuid4()}"
    project_id = str(uuid4())
    settings = get_settings()
    with SessionLocal.begin() as session:
        project = Project(
            id=project_id,
            owner_user_id=owner,
            name="真实技术定义契约集成测试",
            state="solution_confirmation",
            context_version=4,
        )
        session.add(project)
        session.flush()
        session.add(
            ContextVersion(
                project_id=project_id,
                version=4,
                stage="solution_confirmation",
                approval_status="active",
                change_reason="solution reviewed integration fixture",
            )
        )
        artifacts: dict[str, tuple[Artifact, ArtifactVersion]] = {}
        for kind, title in [
            ("user_flow", "User Flow"),
            ("solution_design", "方案说明"),
            ("solution_review", "Solution Review"),
        ]:
            artifact = Artifact(
                project_id=project_id,
                title=title,
                kind=kind,
                stage="solution_confirmation",
                status="waiting_gate",
                latest_version=1,
                owner_agent="builder" if kind != "solution_review" else "reviewer",
            )
            session.add(artifact)
            session.flush()
            content_ref, content_hash = write_immutable_artifact(
                settings.ARTIFACT_ROOT,
                project_id=project_id,
                kind=kind,
                content=f"# {title}\n\n已审方案。",
            )
            version = ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=4,
                approval_status="waiting_gate",
                content_ref=content_ref,
                content_hash=content_hash,
                summary=title,
                created_by=artifact.owner_agent,
            )
            session.add(version)
            session.flush()
            artifacts[kind] = (artifact, version)
        gate = Gate(
            project_id=project_id,
            gate_type="G3",
            context_version=4,
            status="open",
            target_state="tech_stack_confirmation",
            reason="方案审核通过",
            impacted_artifact_refs=[
                {"artifact_id": artifact.id, "version": version.version}
                for artifact, version in artifacts.values()
            ],
            known_issues=[],
        )
        session.add(gate)
        session.flush()
        gate_id = gate.id
    yield project_id, owner, gate_id
    with SessionLocal.begin() as session:
        session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.scope.in_(
                    [
                        f"technical.submission:{project_id}",
                        f"builder.run:{project_id}",
                        f"backend.delivery:{project_id}",
                    ]
                )
                | IdempotencyRecord.scope.like("technical.review:%")
            )
        )
        session.execute(delete(Project).where(Project.id == project_id))


def test_g3_approval_to_technical_review_opens_g4_without_code(
    technical_scope, tmp_path
) -> None:
    project_id, owner, gate_id = technical_scope
    with TestClient(app) as client:
        decision = client.post(
            f"/api/v1/gates/{gate_id}/decisions",
            json={
                "decision": "approve",
                "context_version": 4,
                "comment": "批准 G3",
            },
        )
    assert decision.status_code == 200, decision.text
    assert decision.json()["target_state"] == "tech_stack_confirmation"
    assert decision.json()["context_version"] == 5
    with SessionLocal.begin() as session:
        pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project_id,
                ContextPack.context_version == 5,
                ContextPack.stage == "tech_stack_confirmation",
                ContextPack.agent_id == "builder",
            )
        )
        assert pack is not None
        assert pack.policy["mode"] == "technical_document_only"
        builder_run_id = _seed_run(session, project_id, pack, "builder")
        primary_ref = f"artifact:{pack.primary_resource_id}:v{pack.primary_resource_version}"
    body = {
        "source_run_id": builder_run_id,
        "context_pack_id": pack.id,
        "expected_context_version": 5,
        "artifact_proposals": [
            {
                "kind": "technical_adaptation",
                "title": "Technical Adaptation",
                "content": f"# Technical Adaptation\n\n冻结技术与回退。来源：{primary_ref}",
                "evidence_refs": [primary_ref],
                "assumptions": [],
            },
            {
                "kind": "api_contract",
                "title": "API Contract",
                "content": f"# API Contract\n\nAPI、数据库与错误契约。来源：{primary_ref}",
                "evidence_refs": [primary_ref],
                "assumptions": [],
            },
        ],
    }
    with TestClient(app) as client:
        submission = client.post(
            f"/api/v1/agent-runtime/projects/{project_id}/technical-submissions",
            headers={"Idempotency-Key": f"{owner}-technical"},
            json=body,
        )
    assert submission.status_code == 201, submission.text
    payload = submission.json()
    with SessionLocal.begin() as session:
        reviewer_pack = session.get(ContextPack, payload["reviewer_context_pack_id"])
        reviewer_run_id = _seed_run(session, project_id, reviewer_pack, "reviewer")
    refs = [
        payload["technical_adaptation"]["artifact_ref"],
        payload["api_contract"]["artifact_ref"],
    ]
    review_body = {
        "source_run_id": reviewer_run_id,
        "context_pack_id": payload["reviewer_context_pack_id"],
        "expected_context_version": 5,
        "verdict": "pass",
        "message": "技术定义可进入 G4。",
        "findings": [],
        "review_artifact": {
            "kind": "technical_review",
            "title": "Technical Review",
            "content": f"# Technical Review\n\n适配：{refs[0]}；API：{refs[1]}。结论 pass。",
            "evidence_refs": refs,
            "assumptions": [],
        },
    }
    path = (
        f"/api/v1/agent-runtime/projects/{project_id}/technical-submissions/"
        f"{payload['submission_id']}/review"
    )
    with TestClient(app) as client:
        first = client.post(
            path,
            headers={"Idempotency-Key": f"{owner}-technical-review"},
            json=review_body,
        )
        second = client.post(
            path,
            headers={"Idempotency-Key": f"{owner}-technical-review"},
            json=review_body,
        )
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "waiting_g4"
    assert first.json()["gate"]["gate_type"] == "G4"
    assert first.json()["gate"]["status"] == "open"
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True
    g4_id = first.json()["gate"]["id"]
    with TestClient(app) as client:
        g4_decision = client.post(
            f"/api/v1/gates/{g4_id}/decisions",
            json={
                "decision": "approve",
                "context_version": 5,
                "comment": "批准 G4，启动后端开发",
            },
        )
    assert g4_decision.status_code == 200, g4_decision.text
    assert g4_decision.json()["target_state"] == "development_backend"
    assert g4_decision.json()["context_version"] == 6
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        assert project.state == "development_backend"
        assert project.context_version == 6
        assert (
            session.scalar(
                select(func.count())
                .select_from(Gate)
                .where(
                    Gate.project_id == project_id,
                    Gate.gate_type == "G4",
                    Gate.status == "approved",
                )
            )
            == 1
        )
        backend_pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project_id,
                ContextPack.context_version == 6,
                ContextPack.stage == "development_backend",
                ContextPack.agent_id == "builder",
            )
        )
        assert backend_pack is not None
        assert backend_pack.policy["mode"] == "backend_development"
        assert backend_pack.policy["workspace_scope"] == project_id
        assert backend_pack.policy["allowed_tools"] == [
            "codex_cli",
            "project_fs_read",
            "project_fs_write",
            "git_local",
            "test_runner",
        ]
        assert {
            "git_push",
            "deploy_adapter",
            "workspace_delete",
            "read_secret_values",
        }.issubset(backend_pack.policy["forbidden_actions"])
        backend_task = session.scalar(
            select(AgentTask).where(
                AgentTask.project_id == project_id,
                AgentTask.context_version == 6,
                AgentTask.assigned_agent == "builder",
                AgentTask.title == "实现销售复盘 Agent 后端纵向切片",
            )
        )
        assert backend_task is not None
        assert backend_task.state == "ready"
        backend_pack_id = backend_pack.id
        backend_task_id = backend_task.id
        assert (
            session.scalar(
                select(func.count())
                .select_from(ToolRun)
                .join(AgentTask, ToolRun.task_id == AgentTask.id)
                .where(AgentTask.project_id == project_id, ToolRun.tool_name == "codex_cli")
            )
            == 0
        )

    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        """#!/usr/bin/env python3
import json
from pathlib import Path

Path("app.py").write_text("print('backend ready')\\n", encoding="utf-8")
message = {
    "message": "后端纵向切片完成",
    "technical_decisions": [],
    "tool_requests": [],
    "artifact_proposals": [],
    "test_results": [
        {"command": "pytest", "status": "passed", "summary": "all tests passed"}
    ],
    "known_issues": [],
    "gate_request": None,
    "transition_proposal": None,
}
print(json.dumps({
    "type": "item.completed",
    "item": {"type": "agent_message", "text": json.dumps(message, ensure_ascii=False)},
}, ensure_ascii=False))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    runtime_settings = get_settings().model_copy(
        update={"WORKSPACE_ROOT": workspace_root, "CODEX_CLI_PATH": fake_codex}
    )
    service = BuilderRuntimeService(runtime_settings)
    first_run = service.start(
        project_id=project_id,
        task_id=backend_task_id,
        context_pack_id=backend_pack_id,
        expected_context_version=6,
        idempotency_key=f"{owner}-builder-run",
    )
    repeated_run = service.start(
        project_id=project_id,
        task_id=backend_task_id,
        context_pack_id=backend_pack_id,
        expected_context_version=6,
        idempotency_key=f"{owner}-builder-run",
    )
    assert first_run["state"] == "succeeded"
    assert first_run["exit_code"] == 0
    assert first_run["output"]["message"] == "后端纵向切片完成"
    assert first_run["policy_violations"] == []
    assert repeated_run["run_id"] == first_run["run_id"]
    assert repeated_run["idempotent"] is True
    with SessionLocal() as session:
        task = session.get(AgentTask, backend_task_id)
        run = session.get(AgentRun, first_run["run_id"])
        tool = session.scalar(
            select(ToolRun).where(ToolRun.run_id == first_run["run_id"])
        )
        steps = list(
            session.scalars(
                select(RunStep)
                .where(RunStep.run_id == first_run["run_id"])
                .order_by(RunStep.step_index)
            )
        )
        assert task.state == "completed"
        assert run.state == "succeeded"
        assert tool.state == "completed"
        assert "exit_code=0" in tool.result_ref
        assert [step.step_type for step in steps] == [
            "runtime_start",
            "workspace_prepare",
            "codex_cli",
            "workspace_manifest",
            "builder_output",
        ]
    with SessionLocal.begin() as session:
        task = session.get(AgentTask, backend_task_id)
        run = session.get(AgentRun, first_run["run_id"])
        tool = session.scalar(
            select(ToolRun).where(ToolRun.run_id == first_run["run_id"])
        )
        task.state = "failed"
        run.state = "failed"
        tool.state = "failed"

    evidence = [
        BackendVerificationEvidence(
            check=name,
            status="passed",
            summary=f"{name} passed",
            evidence_hash=hashlib.sha256(name.encode()).hexdigest(),
        )
        for name in ["ruff", "pytest_postgresql", "alembic", "compileall"]
    ]
    delivery_body = BackendDeliveryCreate(
        source_builder_run_id=first_run["run_id"],
        expected_context_version=6,
        workspace_manifest_hash=first_run["workspace_manifest_hash"],
        evidence=evidence,
    )
    delivery_service = BackendDeliveryService(runtime_settings)
    delivery = delivery_service.complete(
        project_id=project_id,
        body=delivery_body,
        idempotency_key=f"{owner}-backend-delivery",
    )
    repeated_delivery = delivery_service.complete(
        project_id=project_id,
        body=delivery_body,
        idempotency_key=f"{owner}-backend-delivery",
    )
    assert delivery["target_state"] == "development_frontend"
    assert delivery["context_version"] == 7
    assert delivery["verdict"] == "pass_with_known_issues"
    assert repeated_delivery["delivery_run_id"] == delivery["delivery_run_id"]
    assert repeated_delivery["idempotent"] is True
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        frontend_pack = session.get(ContextPack, delivery["frontend_context_pack_id"])
        frontend_task = session.get(AgentTask, delivery["frontend_task_id"])
        assert project.state == "development_frontend"
        assert project.context_version == 7
        assert frontend_pack.policy["mode"] == "frontend_development"
        assert "modify_product_factory_frontend" in frontend_pack.policy["forbidden_actions"]
        assert frontend_task.state == "ready"

    frontend_run = service.start(
        project_id=project_id,
        task_id=delivery["frontend_task_id"],
        context_pack_id=delivery["frontend_context_pack_id"],
        expected_context_version=7,
        idempotency_key=f"{owner}-frontend-builder-run",
    )
    assert frontend_run["state"] == "succeeded"
    frontend_checks = [
        "eslint",
        "typecheck",
        "vitest",
        "next_build",
        "browser_desktop",
        "browser_mobile",
    ]
    frontend_body = FrontendDeliveryCreate(
        source_builder_run_id=frontend_run["run_id"],
        expected_context_version=7,
        workspace_manifest_hash=frontend_run["workspace_manifest_hash"],
        evidence=[
            FrontendVerificationEvidence(
                check=name,
                status="passed",
                summary=f"{name} passed",
                evidence_hash=hashlib.sha256(name.encode()).hexdigest(),
            )
            for name in frontend_checks
        ],
    )
    frontend_delivery_service = FrontendDeliveryService(runtime_settings)
    frontend_delivery = frontend_delivery_service.complete(
        project_id=project_id,
        body=frontend_body,
        idempotency_key=f"{owner}-frontend-delivery",
    )
    repeated_frontend_delivery = frontend_delivery_service.complete(
        project_id=project_id,
        body=frontend_body,
        idempotency_key=f"{owner}-frontend-delivery",
    )
    assert frontend_delivery["target_state"] == "mvp"
    assert frontend_delivery["context_version"] == 8
    assert frontend_delivery["verdict"] == "pass_with_known_issues"
    assert repeated_frontend_delivery["delivery_run_id"] == frontend_delivery["delivery_run_id"]
    assert repeated_frontend_delivery["idempotent"] is True
    with SessionLocal() as session:
        project = session.get(Project, project_id)
        mvp_pack = session.get(ContextPack, frontend_delivery["mvp_context_pack_id"])
        mvp_task = session.get(AgentTask, frontend_delivery["mvp_review_task_id"])
        assert project.state == "mvp"
        assert project.context_version == 8
        assert mvp_pack.policy["mode"] == "mvp_independent_acceptance"
        assert mvp_task.state == "ready"

    acceptance_checks = [
        "product_factory_control_plane",
        "sales_review_backend",
        "sales_review_frontend",
        "postgres_backup_restore",
        "browser_qa",
        "deepseek_conclusions",
        "deepseek_actions",
    ]
    acceptance_body = InternalAcceptanceCreate(
        mvp_review_task_id=frontend_delivery["mvp_review_task_id"],
        mvp_context_pack_id=frontend_delivery["mvp_context_pack_id"],
        expected_context_version=8,
        workspace_manifest_hash=frontend_run["workspace_manifest_hash"],
        evidence=[
            InternalAcceptanceEvidence(
                check=name,
                status="passed",
                summary=f"{name} passed",
                evidence_hash=hashlib.sha256(name.encode()).hexdigest(),
            )
            for name in acceptance_checks
        ],
    )
    acceptance_service = InternalAcceptanceService(runtime_settings)
    acceptance = acceptance_service.complete(
        project_id=project_id,
        body=acceptance_body,
        idempotency_key=f"{owner}-internal-acceptance",
    )
    repeated_acceptance = acceptance_service.complete(
        project_id=project_id,
        body=acceptance_body,
        idempotency_key=f"{owner}-internal-acceptance",
    )
    assert acceptance["target_state"] == "internal_acceptance"
    assert acceptance["context_version"] == 9
    assert acceptance["gate_type"] == "G5"
    assert acceptance["gate_status"] == "open"
    assert repeated_acceptance["acceptance_run_id"] == acceptance["acceptance_run_id"]
    assert repeated_acceptance["idempotent"] is True
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/gates/{acceptance['gate_id']}/decisions",
            json={
                "decision": "approve",
                "context_version": 9,
                "comment": "integration test G5 approval",
                "decided_by": owner,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["target_state"] == "seed_beta"
    assert response.json()["context_version"] == 10


def _seed_run(session, project_id: str, pack: ContextPack, agent_id: str) -> str:
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
    sequence = (
        session.scalar(select(func.max(Event.sequence)).where(Event.project_id == project_id)) or 0
    )
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
