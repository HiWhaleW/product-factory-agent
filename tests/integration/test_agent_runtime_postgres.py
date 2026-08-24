from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from app.adapters.bocha import BochaSearchResponse, BochaSearchResult
from app.adapters.deepseek import DeepSeekResponse, DeepSeekUsage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import (
    ContextPack,
    ContextVersion,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
    RunStep,
)
from app.main import app
from app.services.agent_runtime import AgentRuntimeError, AgentRuntimeService
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL database",
    ),
]


class FakeProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def complete(self, messages, **kwargs):
        output = self.outputs[self.calls]
        self.calls += 1
        model = kwargs["response_model"]
        validated = model.model_validate(output)
        return DeepSeekResponse(
            model="deepseek-integration-double",
            content=None,
            finish_reason="stop",
            usage=DeepSeekUsage(prompt_tokens=11, completion_tokens=12, total_tokens=23),
            structured_output=validated.model_dump(mode="json"),
        )


class FakeResearchProvider:
    def __init__(self, response: BochaSearchResponse):
        self.response = response
        self.calls = 0

    async def search(self, query, **kwargs):
        self.calls += 1
        return self.response


def factory_output(*, ask_permission: bool = False) -> dict:
    return {
        "message": "项目对齐结果",
        "identity_event": None,
        "tool_request": (
            {
                "tool_id": "send_email",
                "reason": "外发摘要",
                "parameters": {"recipient": "redacted@example.invalid"},
                "side_effect": "external-write",
            }
            if ask_permission
            else None
        ),
        "artifact_proposals": [],
        "gate_request": None,
        "transition_proposal": None,
        "open_questions": [],
    }


def ai_pm_output() -> dict:
    evidence_ref = f"bocha:web:{'b' * 64}"
    return {
        "message": "已形成 Evidence Index 候选。",
        "artifact_proposals": [
            {
                "kind": "evidence_index",
                "title": "Evidence Index",
                "content": f"可追溯市场证据：{evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": [],
                "status": "waiting_review",
            },
            {
                "kind": "mrd",
                "title": "MRD",
                "content": f"可追溯市场需求草案：{evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": [],
                "status": "waiting_review",
            }
        ],
        "verified_fact_proposals": [],
        "open_questions": [],
        "transition_proposal": None,
    }


def research_response() -> BochaSearchResponse:
    return BochaSearchResponse(
        provider_request_id="bocha-integration-1",
        query="AI Agent 市场需求",
        total_estimated_matches=10,
        results=[
            BochaSearchResult(
                evidence_ref=f"bocha:web:{'b' * 64}",
                title="官方市场报告",
                url="https://example.com/official-report",
                summary="官方摘要",
            )
        ],
    )


@pytest.fixture
def runtime_context_pack() -> tuple[str, str]:
    owner = f"runtime-it-{uuid4()}"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": owner},
            json={"name": "Runtime integration", "owner_user_id": owner},
        )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    with SessionLocal.begin() as session:
        project = session.get(Project, project_id)
        context = session.scalar(
            select(ContextVersion).where(
                ContextVersion.project_id == project_id,
                ContextVersion.version == project.context_version,
            )
        )
        brief = ProjectBrief(project_id=project_id, latest_version=1)
        session.add(brief)
        session.flush()
        session.add(
            ProjectBriefVersion(
                brief_id=brief.id,
                version=1,
                context_version=project.context_version,
                approval_status="approved",
                objective="验证真实 Run Journal",
                target_users=["产品负责人"],
                success_criteria=["可恢复"],
                in_scope=["runtime"],
                out_of_scope=["deploy"],
                timeline="D5",
                open_questions=[],
                source_clarification_ids=[],
                created_by="factory-lead",
            )
        )
        pack = ContextPack(
            project_id=project_id,
            context_version_id=context.id,
            context_version=project.context_version,
            stage=project.state,
            approval_status="approved",
            primary_resource_type="project_brief",
            primary_resource_id=brief.id,
            primary_resource_version=1,
            agent_id="factory-lead",
            task="验证 Factory Lead 有界运行。",
            references=[],
            policy={
                "allowed_capability_ids": ["CAP-01"],
                "forbidden_actions": ["advance_project_state", "approve_gate"],
                "budget": {"max_turns": 3, "max_retries": 1, "timeout_seconds": 30},
            },
        )
        session.add(pack)
        session.flush()
        pack_id = pack.id
    yield project_id, pack_id
    with SessionLocal.begin() as session:
        session.execute(delete(Project).where(Project.id == project_id))


@pytest.fixture
def ai_pm_context_pack() -> tuple[str, str]:
    owner = f"ai-pm-runtime-it-{uuid4()}"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": owner},
            json={"name": "AI PM runtime integration", "owner_user_id": owner},
        )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    with SessionLocal.begin() as session:
        project = session.get(Project, project_id)
        context = session.scalar(
            select(ContextVersion).where(
                ContextVersion.project_id == project_id,
                ContextVersion.version == project.context_version,
            )
        )
        project.state = "mrd"
        context.stage = "mrd"
        brief = ProjectBrief(project_id=project_id, latest_version=1)
        session.add(brief)
        session.flush()
        session.add(
            ProjectBriefVersion(
                brief_id=brief.id,
                version=1,
                context_version=project.context_version,
                approval_status="approved",
                objective="验证 AI PM 可追溯证据链",
                target_users=["产品负责人"],
                success_criteria=["证据带 URL"],
                in_scope=["evidence_index", "mrd"],
                out_of_scope=["prd"],
                timeline="D5",
                open_questions=[],
                source_clarification_ids=[],
                created_by="factory-lead",
            )
        )
        pack = ContextPack(
            project_id=project_id,
            context_version_id=context.id,
            context_version=project.context_version,
            stage="mrd",
            approval_status="approved",
            primary_resource_type="project_brief",
            primary_resource_id=brief.id,
            primary_resource_version=1,
            agent_id="ai-pm",
            task="搜索市场证据并生成 Evidence Index 候选。",
            references=[],
            policy={
                "allowed_capability_ids": ["CAP-02", "CAP-12"],
                "forbidden_actions": ["advance_project_state", "approve_gate"],
                "budget": {
                    "max_turns": 3,
                    "max_retries": 1,
                    "timeout_seconds": 30,
                    "max_tool_calls": 3,
                },
            },
        )
        session.add(pack)
        session.flush()
        pack_id = pack.id
    yield project_id, pack_id
    with SessionLocal.begin() as session:
        session.execute(delete(Project).where(Project.id == project_id))


def test_runtime_persists_run_step_checkpoint_and_cursor_event(runtime_context_pack) -> None:
    project_id, pack_id = runtime_context_pack
    provider = FakeProvider([factory_output()])
    service = AgentRuntimeService(get_settings(), provider=provider)

    result = asyncio.run(service.start(context_pack_id=pack_id, user_input="做销售复盘 Agent"))

    assert result.state == "succeeded"
    assert result.observed_model == "deepseek-integration-double"
    assert result.checkpoint_hash
    with SessionLocal() as session:
        steps = list(
            session.scalars(
                select(RunStep).where(RunStep.run_id == result.run_id).order_by(RunStep.step_index)
            )
        )
        assert [step.step_type for step in steps] == [
            "runtime_start",
            "model",
            "checkpoint",
        ]
        assert steps[-1].input_hash == result.checkpoint_hash
        events = session.execute(
            select(Project.id).where(Project.id == project_id)
        ).all()
        assert events


def test_permission_resume_restores_checkpoint_in_new_service(runtime_context_pack) -> None:
    _, pack_id = runtime_context_pack
    first_provider = FakeProvider([factory_output(ask_permission=True)])
    first_service = AgentRuntimeService(get_settings(), provider=first_provider)
    waiting = asyncio.run(
        first_service.start(context_pack_id=pack_id, user_input="将结果邮件发给团队")
    )
    assert waiting.state == "waiting_human"
    assert waiting.permission_request_id

    with TestClient(app) as client:
        decision = client.post(
            f"/api/v1/permissions/{waiting.permission_request_id}/decisions",
            json={
                "decision": "deny",
                "input_hash": waiting.permission_input_hash,
                "decided_by": "local-admin",
            },
        )
    assert decision.status_code == 200, decision.text

    fresh_provider = FakeProvider([])
    fresh_service = AgentRuntimeService(get_settings(), provider=fresh_provider)
    resumed = asyncio.run(fresh_service.resume_permission(waiting.run_id))
    assert resumed.state == "failed"
    assert resumed.error_code == "PERMISSION_DENIED"
    assert fresh_provider.calls == 0


def test_resume_fails_closed_before_unknown_external_side_effect(runtime_context_pack) -> None:
    _, pack_id = runtime_context_pack
    service = AgentRuntimeService(
        get_settings(), provider=FakeProvider([factory_output(ask_permission=True)])
    )
    waiting = asyncio.run(service.start(context_pack_id=pack_id, user_input="外发摘要"))
    with SessionLocal.begin() as session:
        last_index = session.scalar(
            select(RunStep.step_index)
            .where(RunStep.run_id == waiting.run_id)
            .order_by(RunStep.step_index.desc())
        )
        session.add(
            RunStep(
                run_id=waiting.run_id,
                step_index=last_index + 1,
                step_type="tool",
                state="running",
                idempotency_key=f"effect-{uuid4()}",
                input_hash="9" * 64,
                external_effect_confirmed=False,
            )
        )
    with pytest.raises(AgentRuntimeError, match="reconciled") as error:
        asyncio.run(service.resume_permission(waiting.run_id))
    assert error.value.code == "SIDE_EFFECT_RECONCILIATION_REQUIRED"


def test_ai_pm_bocha_permission_resume_persists_tool_journal(ai_pm_context_pack) -> None:
    _, pack_id = ai_pm_context_pack
    initial_research = FakeResearchProvider(research_response())
    initial_service = AgentRuntimeService(
        get_settings(),
        provider=FakeProvider([ai_pm_output()]),
        research_provider=initial_research,
    )

    waiting = asyncio.run(
        initial_service.start(
            context_pack_id=pack_id,
            user_input="搜索 AI Agent 产品市场需求和替代方案",
        )
    )
    assert waiting.state == "waiting_human"
    assert waiting.permission_request_id
    assert waiting.tool_calls_used == 0
    assert initial_research.calls == 0

    with TestClient(app) as client:
        decision = client.post(
            f"/api/v1/permissions/{waiting.permission_request_id}/decisions",
            json={
                "decision": "allow",
                "input_hash": waiting.permission_input_hash,
                "decided_by": "local-admin",
            },
        )
    assert decision.status_code == 200, decision.text

    fresh_model = FakeProvider([ai_pm_output()])
    fresh_research = FakeResearchProvider(research_response())
    fresh_service = AgentRuntimeService(
        get_settings(),
        provider=fresh_model,
        research_provider=fresh_research,
    )
    completed = asyncio.run(fresh_service.resume_permission(waiting.run_id))

    assert completed.state == "succeeded"
    assert completed.tool_calls_used == 1
    assert completed.tool_results[0]["provider"] == "bocha"
    assert fresh_research.calls == fresh_model.calls == 1
    with SessionLocal() as session:
        steps = list(
            session.scalars(
                select(RunStep)
                .where(RunStep.run_id == completed.run_id)
                .order_by(RunStep.step_index)
            )
        )
    assert [step.step_type for step in steps] == [
        "runtime_start",
        "checkpoint",
        "resume",
        "tool",
        "model",
        "checkpoint",
    ]
    assert steps[2].output_ref == steps[1].output_ref
    assert steps[2].external_effect_confirmed is True
    assert steps[3].output_ref.startswith("evidence-set://")
    assert steps[3].external_effect_confirmed is True
