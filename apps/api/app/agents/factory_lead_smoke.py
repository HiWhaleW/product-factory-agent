from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient

from app.adapters.deepseek import DeepSeekAdapter, DeepSeekSchemaError
from app.api.agent_router import get_factory_lead_service
from app.core.config import get_settings
from app.main import app
from app.services.factory_lead import FactoryLeadAlignmentService, FactoryLeadRuntimeService


class DiagnosticProvider:
    """Collect validation paths only; never retain provider content or Prompt text."""

    def __init__(self) -> None:
        self.adapter = DeepSeekAdapter.from_settings(get_settings())
        self.schema_issues: list[dict[str, object]] = []

    async def complete(self, messages, **kwargs):
        try:
            return await self.adapter.complete(messages, **kwargs)
        except DeepSeekSchemaError as error:
            cause = error.__cause__
            if hasattr(cause, "errors"):
                self.schema_issues.extend(
                    {
                        "loc": list(item.get("loc") or []),
                        "type": item.get("type"),
                    }
                    for item in cause.errors(include_input=False, include_url=False)
                )
            raise


def _require(response, expected: int = 200) -> dict:
    if response.status_code != expected:
        body = response.json()
        error = body.get("error") or {}
        raise RuntimeError(
            f"Factory Lead smoke failed: status={response.status_code}, "
            f"code={error.get('code')}, request_id={error.get('request_id')}"
        )
    return response.json()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _run_summary(result: dict, elapsed_ms: float) -> dict:
    return {
        "invocation_id": result["invocation_id"],
        "run_id": result.get("run_id"),
        "state": result["state"],
        "turns_used": result["turns_used"],
        "retries_used": result["retries_used"],
        "requested_model": result["requested_model"],
        "observed_model": result.get("observed_model"),
        "usage": result.get("usage") or {},
        "checkpoint_hash": result.get("checkpoint_hash"),
        "message_sha256": _hash_text(result.get("message") or ""),
        "message_length": len(result.get("message") or ""),
        "clarification_count": len(result.get("clarification_ids") or []),
        "brief_version_id": (result.get("brief") or {}).get("id"),
        "gate_id": (result.get("gate") or {}).get("id"),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def run_factory_lead_smoke() -> dict:
    nonce = uuid4().hex
    first_idea = "我要做一个帮助销售团队复盘客户沟通的 Agent。"
    complete_alignment = (
        "目标用户是 10-50 人 B2B 销售团队的销售主管；目标是把访谈纪要和跟进记录"
        "整理成可追溯的复盘结论。成功标准是每条结论有来源引用、主管 10 分钟内完成"
        "复盘，并明确下一步行动。范围包括材料汇总、结论生成和行动项；不包括自动外发、"
        "自动修改 CRM、部署或代替主管决策。D5 先完成定义链路，两周内做内部试用。"
    )
    endpoint_template = "/api/v1/agent-runtime/projects/{}/factory-lead/alignment-runs"
    provider = DiagnosticProvider()
    settings = get_settings()
    runtime = FactoryLeadRuntimeService(settings, provider=provider)
    service = FactoryLeadAlignmentService(settings, runtime=runtime)
    app.dependency_overrides[get_factory_lead_service] = lambda: service
    try:
        client_context = TestClient(app)
        client = client_context.__enter__()
        project = _require(
            client.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": f"factory-lead-smoke-project-{nonce}"},
                json={
                    "name": f"Factory Lead Smoke {nonce[:8]}",
                    "owner_user_id": "factory-lead-smoke",
                },
            ),
            201,
        )
        endpoint = endpoint_template.format(project["id"])
        first_started = perf_counter()
        first = _require(
            client.post(
                endpoint,
                headers={"Idempotency-Key": f"factory-lead-smoke-first-{nonce}"},
                json={
                    "expected_context_version": 1,
                    "expected_previous_brief_version": 0,
                    "client_message_id": f"factory-lead-smoke-message-first-{nonce}",
                    "content": first_idea,
                    "clarification_answers": [],
                },
            )
        )
        runs = [_run_summary(first, (perf_counter() - first_started) * 1000)]
        final = first
        if first["state"] == "clarification_required":
            second_started = perf_counter()
            final = _require(
                client.post(
                    endpoint,
                    headers={"Idempotency-Key": f"factory-lead-smoke-second-{nonce}"},
                    json={
                        "expected_context_version": 1,
                        "expected_previous_brief_version": 0,
                        "client_message_id": f"factory-lead-smoke-message-second-{nonce}",
                        "content": complete_alignment,
                        "clarification_answers": [
                            {
                                "clarification_id": clarification_id,
                                "answer": complete_alignment,
                            }
                            for clarification_id in first["clarification_ids"]
                        ],
                    },
                )
            )
            runs.append(_run_summary(final, (perf_counter() - second_started) * 1000))

        project_after = _require(client.get(f"/api/v1/projects/{project['id']}"))
        events = _require(client.get(f"/api/v1/projects/{project['id']}/events?cursor=0"))
        event_types = [event["event_type"] for event in events]
    finally:
        if "client_context" in locals():
            client_context.__exit__(None, None, None)
        app.dependency_overrides.pop(get_factory_lead_service, None)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project["id"],
        "evidence_contains_input": False,
        "evidence_contains_prompt": False,
        "evidence_contains_model_output": False,
        "runs": runs,
        "final_state": final["state"],
        "project_state_after_model": project_after["state"],
        "context_version_after_model": project_after["context_version"],
        "gate_opened": bool((final.get("gate") or {}).get("id")),
        "gate_approved": False,
        "schema_issues": provider.schema_issues,
        "event_cursor": events[-1]["sequence"],
        "event_types": event_types,
    }


if __name__ == "__main__":
    print(json.dumps(run_factory_lead_smoke(), ensure_ascii=False, indent=2))
