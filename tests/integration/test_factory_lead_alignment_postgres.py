from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from app.adapters.deepseek import DeepSeekResponse, DeepSeekUsage
from app.api.agent_router import get_factory_lead_service
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import ContextPack, FactoryLeadInvocation, Gate, Project, ProjectBriefVersion
from app.main import app
from app.services.factory_lead import FactoryLeadAlignmentService, FactoryLeadRuntimeService
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
    def __init__(self, outputs: list[dict], *, delay: float = 0) -> None:
        self.outputs = outputs
        self.delay = delay
        self.calls = 0
        self._lock = Lock()

    async def complete(self, messages, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        with self._lock:
            index = self.calls
            self.calls += 1
        output = self.outputs[index]
        model = kwargs["response_model"]
        validated = model.model_validate(output)
        return DeepSeekResponse(
            model="deepseek-alignment-test",
            content=None,
            finish_reason="stop",
            usage=DeepSeekUsage(prompt_tokens=31, completion_tokens=47, total_tokens=78),
            structured_output=validated.model_dump(mode="json"),
        )


def clarification_output() -> dict:
    return {
        "message": "先确认目标用户和成功标准。",
        "identity_event": None,
        "tool_request": None,
        "artifact_proposals": [],
        "clarification_proposals": [
            {"question": "首要用户是销售主管吗？", "scope_impact": "user"},
            {"question": "成功是否以复盘结论可追溯为准？", "scope_impact": "success"},
        ],
        "project_brief": None,
        "gate_request": None,
        "transition_proposal": None,
        "open_questions": [],
    }


def brief_output() -> dict:
    return {
        "message": "已形成 Project Brief 候选，请决定 G0。",
        "identity_event": None,
        "tool_request": None,
        "artifact_proposals": [],
        "clarification_proposals": [],
        "project_brief": {
            "objective": "帮助销售主管形成有证据引用的复盘结论",
            "target_users": ["销售主管"],
            "success_criteria": ["每条结论可追溯到输入证据"],
            "in_scope": ["销售材料汇总", "复盘结论生成"],
            "out_of_scope": ["自动外发", "自动修改 CRM"],
            "timeline": "先完成 D5 定义链路",
            "open_questions": [],
        },
        "gate_request": None,
        "transition_proposal": None,
        "open_questions": ["是否由 Product Owner 在 G0 确认试用范围？"],
    }


@pytest.fixture
def project_id() -> str:
    owner = f"factory-lead-it-{uuid4()}"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": owner},
            json={"name": "Factory Lead alignment", "owner_user_id": owner},
        )
    assert response.status_code == 201, response.text
    value = response.json()["id"]
    yield value
    with SessionLocal.begin() as session:
        session.execute(delete(Project).where(Project.id == value))


def install_service(provider: FakeProvider) -> None:
    settings = get_settings()
    runtime = FactoryLeadRuntimeService(settings, provider=provider)
    service = FactoryLeadAlignmentService(settings, runtime=runtime)
    app.dependency_overrides[get_factory_lead_service] = lambda: service


def request_body(*, suffix: str, answers: list[dict] | None = None) -> dict:
    return {
        "expected_context_version": 1,
        "expected_previous_brief_version": 0,
        "client_message_id": f"alignment-{suffix}",
        "content": "我要做一个销售复盘 Agent。",
        "clarification_answers": answers or [],
    }


def endpoint(project_id: str) -> str:
    return f"/api/v1/agent-runtime/projects/{project_id}/factory-lead/alignment-runs"


def test_project_has_exact_factory_lead_bootstrap_context(project_id: str) -> None:
    with SessionLocal() as session:
        pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project_id,
                ContextPack.stage == "alignment",
                ContextPack.agent_id == "factory-lead",
            )
        )
    assert pack is not None
    assert pack.primary_resource_type == "context_version"
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/projects/{project_id}/context-packs/exact",
            params={
                "stage": "alignment",
                "context_version": 1,
                "resource_type": "context_version",
                "resource_id": pack.primary_resource_id,
                "resource_version": 1,
                "recipient_agent_id": "factory-lead",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == pack.id


def test_factory_lead_clarification_is_model_call_idempotent(project_id: str) -> None:
    provider = FakeProvider([clarification_output()])
    install_service(provider)
    body = request_body(suffix="clarify")
    try:
        with TestClient(app) as client:
            first = client.post(
                endpoint(project_id), headers={"Idempotency-Key": "clarify-once"}, json=body
            )
            repeated = client.post(
                endpoint(project_id), headers={"Idempotency-Key": "clarify-once"}, json=body
            )
        assert first.status_code == repeated.status_code == 200
        assert first.json()["state"] == "clarification_required"
        assert len(first.json()["clarification_ids"]) == 2
        assert repeated.json()["idempotent"] is True
        assert repeated.json()["invocation_id"] == first.json()["invocation_id"]
        assert provider.calls == 1
    finally:
        app.dependency_overrides.pop(get_factory_lead_service, None)


def test_concurrent_factory_lead_double_click_charges_once(project_id: str) -> None:
    provider = FakeProvider([clarification_output()], delay=0.2)
    install_service(provider)
    barrier = Barrier(2)
    body = request_body(suffix="concurrent")

    def post_once() -> tuple[int, dict]:
        barrier.wait()
        with TestClient(app) as client:
            response = client.post(
                endpoint(project_id),
                headers={"Idempotency-Key": "concurrent-once"},
                json=body,
            )
        return response.status_code, response.json()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: post_once(), range(2)))
        assert [status for status, _ in responses] == [200, 200]
        assert {payload["state"] for _, payload in responses} <= {
            "running",
            "clarification_required",
        }
        assert provider.calls == 1
        with SessionLocal() as session:
            invocations = list(
                session.scalars(
                    select(FactoryLeadInvocation).where(
                        FactoryLeadInvocation.project_id == project_id
                    )
                )
            )
        assert len(invocations) == 1
    finally:
        app.dependency_overrides.pop(get_factory_lead_service, None)


def test_answers_create_brief_and_g0_but_do_not_advance_state(project_id: str) -> None:
    provider = FakeProvider([clarification_output(), brief_output()])
    install_service(provider)
    try:
        with TestClient(app) as client:
            first = client.post(
                endpoint(project_id),
                headers={"Idempotency-Key": "alignment-first"},
                json=request_body(suffix="first"),
            )
            assert first.status_code == 200, first.text
            clarification_ids = first.json()["clarification_ids"]
            second = client.post(
                endpoint(project_id),
                headers={"Idempotency-Key": "alignment-second"},
                json=request_body(
                    suffix="second",
                    answers=[
                        {"clarification_id": clarification_ids[0], "answer": "是，销售主管。"},
                        {
                            "clarification_id": clarification_ids[1],
                            "answer": "是，结论必须可追溯。",
                        },
                    ],
                ),
            )
            project_before = client.get(f"/api/v1/projects/{project_id}")
        assert second.status_code == 200, second.text
        result = second.json()
        assert result["state"] == "waiting_g0"
        assert result["brief"]["approval_status"] == "draft"
        assert result["gate"]["gate_type"] == "G0"
        assert project_before.json()["state"] == "alignment"
        assert provider.calls == 2
        with SessionLocal() as session:
            version = session.get(ProjectBriefVersion, result["brief"]["id"])
            gate = session.get(Gate, result["gate"]["id"])
        assert version is not None
        assert set(version.source_clarification_ids) == set(clarification_ids)
        assert gate is not None and gate.status == "open"
    finally:
        app.dependency_overrides.pop(get_factory_lead_service, None)
