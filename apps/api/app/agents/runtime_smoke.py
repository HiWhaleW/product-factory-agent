from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def _hash_json(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _require(response, expected: int):
    if response.status_code != expected:
        body = response.json()
        error = body.get("error") or {}
        raise RuntimeError(
            f"API smoke failed: status={response.status_code}, code={error.get('code')}"
        )
    return response.json()


def run_runtime_smoke() -> dict:
    nonce = uuid4().hex
    with TestClient(app) as client:
        project = _require(
            client.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": f"d5-runtime-{nonce}"},
                json={
                    "name": f"D5 Runtime Smoke {nonce[:8]}",
                    "owner_user_id": "d5-runtime-smoke",
                },
            ),
            201,
        )
        project_id = project["id"]
        brief_result = _require(
            client.post(
                f"/api/v1/projects/{project_id}/briefs",
                headers={"Idempotency-Key": f"d5-brief-{nonce}"},
                json={
                    "expected_context_version": 1,
                    "expected_previous_version": 0,
                    "objective": "验证产品工厂 D5 真实 Agent Runtime 的边界与恢复证据",
                    "target_users": ["产品工厂内部 Product Owner"],
                    "success_criteria": [
                        "真实 DeepSeek 输出通过严格 Schema",
                        "Run/Step/checkpoint 可从 PostgreSQL 与受控内容层恢复",
                    ],
                    "in_scope": ["Factory Lead 协调", "Reviewer 独立审查"],
                    "out_of_scope": ["Builder", "部署", "种子内测"],
                    "timeline": "D5 runtime smoke",
                    "open_questions": ["真实公开搜索 Adapter 尚未选型"],
                    "source_clarification_ids": [],
                    "created_by": "factory-lead",
                },
            ),
            201,
        )
        gate_id = brief_result["gate"]["id"]
        _require(
            client.post(
                f"/api/v1/gates/{gate_id}/decisions",
                json={
                    "decision": "approve",
                    "context_version": 1,
                    "comment": "批准 Runtime Smoke 的 G0 测试范围",
                },
            ),
            200,
        )
        brief = brief_result["brief"]
        resource = {
            "resource_type": "project_brief",
            "resource_id": brief["brief_id"],
            "version": brief["version"],
            "approval_status": "approved",
        }

        def create_pack(agent_id: str, task: str, capabilities: list[str]) -> dict:
            return _require(
                client.post(
                    f"/api/v1/projects/{project_id}/context-packs",
                    headers={"Idempotency-Key": f"d5-pack-{agent_id}-{nonce}"},
                    json={
                        "context_version": 2,
                        "stage": "mrd",
                        "recipient_agent_id": agent_id,
                        "primary_resource": resource,
                        "required_resources": [],
                        "task": task,
                        "policy": {
                            "allowed_capability_ids": capabilities,
                            "forbidden_actions": [
                                "advance_project_state",
                                "approve_gate",
                                "read_secret_values",
                            ],
                            "budget": {
                                "max_turns": 3,
                                "max_retries": 1,
                                "timeout_seconds": 120,
                                "max_tool_calls": 5,
                            },
                        },
                    },
                ),
                201,
            )

        lead_pack = create_pack(
            "factory-lead",
            "基于批准 Brief 说明当前状态、D5 边界和下一步；不得推进状态。",
            ["CAP-05", "CAP-06"],
        )
        reviewer_pack = create_pack(
            "reviewer",
            "用 clean-review Context 独立审查批准 Brief 的事实、范围和风险。",
            ["CAP-10"],
        )
        lead_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": lead_pack["id"],
                    "user_input": "请协调当前 D5 Runtime Smoke，但不要替用户做 Gate 决定。",
                },
            ),
            200,
        )
        reviewer_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": reviewer_pack["id"],
                    "user_input": "请独立审查批准 Brief，只输出可验证结论。",
                },
            ),
            200,
        )

        ai_pm_pack = _require(
            client.get(
                f"/api/v1/projects/{project_id}/context-packs/exact",
                params={
                    "context_version": 2,
                    "stage": "mrd",
                    "recipient_agent_id": "ai-pm",
                    "resource_type": "project_brief",
                    "resource_id": brief["brief_id"],
                    "resource_version": 1,
                },
            ),
            200,
        )
        ai_pm_response = client.post(
            "/api/v1/agent-runtime/runs",
            json={
                "context_pack_id": ai_pm_pack["id"],
                "user_input": "生成 Evidence Index 和 MRD。",
            },
        )
        if ai_pm_response.status_code != 503:
            raise RuntimeError("AI PM should fail closed without a real web_research adapter.")
        ai_pm_error = ai_pm_response.json()["error"]

        events = _require(client.get(f"/api/v1/projects/{project_id}/events?cursor=0"), 200)
        run_events = [event for event in events if event["event_type"].startswith("run.")]
        lead_snapshot = _require(client.get(f"/api/v1/runs/{lead_run['run_id']}"), 200)
        reviewer_snapshot = _require(client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "project_name": project["name"],
        "configured_model": "deepseek-chat",
        "prompts_recorded": False,
        "outputs_recorded": False,
        "runs": [
            {
                "agent_id": "factory-lead",
                "run_id": lead_run["run_id"],
                "state": lead_run["state"],
                "turns_used": lead_run["turns_used"],
                "retries_used": lead_run["retries_used"],
                "observed_model": lead_run["observed_model"],
                "usage": lead_run["usage"],
                "output_sha256": _hash_json(lead_run["output"]),
                "checkpoint_hash": lead_run["checkpoint_hash"],
                "journal_step_types": [step["step_type"] for step in lead_snapshot["steps"]],
            },
            {
                "agent_id": "reviewer",
                "run_id": reviewer_run["run_id"],
                "state": reviewer_run["state"],
                "turns_used": reviewer_run["turns_used"],
                "retries_used": reviewer_run["retries_used"],
                "observed_model": reviewer_run["observed_model"],
                "usage": reviewer_run["usage"],
                "output_sha256": _hash_json(reviewer_run["output"]),
                "checkpoint_hash": reviewer_run["checkpoint_hash"],
                "journal_step_types": [
                    step["step_type"] for step in reviewer_snapshot["steps"]
                ],
            },
        ],
        "ai_pm_fail_closed": {
            "status_code": ai_pm_response.status_code,
            "error_code": ai_pm_error["code"],
        },
        "cursor_evidence": {
            "run_event_count": len(run_events),
            "last_sequence": events[-1]["sequence"],
            "event_types": [event["event_type"] for event in run_events],
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_runtime_smoke(), ensure_ascii=False, indent=2))
