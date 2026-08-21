from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agents.outputs import AiPmMrdOutput, ReviewerMrdOutput
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
            f"AI PM smoke failed: status={response.status_code}, code={error.get('code')}"
        )
    return response.json()


def run_ai_pm_research_smoke() -> dict:
    nonce = uuid4().hex
    with TestClient(app) as client:
        project = _require(
            client.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": f"d5-ai-pm-{nonce}"},
                json={
                    "name": f"D5 AI PM Research Smoke {nonce[:8]}",
                    "owner_user_id": "d5-runtime-smoke",
                },
            ),
            201,
        )
        project_id = project["id"]
        brief_result = _require(
            client.post(
                f"/api/v1/projects/{project_id}/briefs",
                headers={"Idempotency-Key": f"d5-ai-pm-brief-{nonce}"},
                json={
                    "expected_context_version": 1,
                    "expected_previous_version": 0,
                    "objective": "验证公开证据检索、Evidence Index 与 MRD 提案链路",
                    "target_users": ["企业内部产品负责人"],
                    "success_criteria": [
                        "真实博查结果进入受控 AI PM Run",
                        "模型输出通过严格 Schema 并携带 EvidenceRef",
                        "Permission/checkpoint/Journal 可审计恢复",
                    ],
                    "in_scope": ["AI PM Evidence Index 与 MRD 提案"],
                    "out_of_scope": ["真实产品 Gate 决定", "Builder", "部署"],
                    "timeline": "D5 isolated smoke fixture",
                    "open_questions": ["Provider 真实 429 尚未观察"],
                    "source_clarification_ids": [],
                    "created_by": "d5-smoke-fixture",
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
                    "comment": (
                        "仅批准隔离 smoke fixture 进入 mrd；不代表任何真实产品项目 G0。"
                    ),
                    "decided_by": "d5-smoke-operator",
                },
            ),
            200,
        )
        brief = brief_result["brief"]
        pack = _require(
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
        waiting = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": pack["id"],
                    "user_input": (
                        "2025-2026 中国企业采用 AI Agent 的市场需求、采购障碍、"
                        "可信可控需求与主要竞品；优先官方、原始报告与一手来源。"
                        "Evidence Index 必须逐条写出原始 EvidenceRef、标题、URL、"
                        "发布方/日期、支持的精确结论与局限；MRD 每个市场事实和"
                        "需求推导都在正文内就近引用原始 EvidenceRef，不使用 E1 别名。"
                        "严格区分已验证事实、假设和待访谈项，不得把待内测假设"
                        "写成已验证商业结论，不得推进项目状态。"
                    ),
                },
            ),
            200,
        )
        if (
            waiting["state"] != "waiting_human"
            or not waiting["permission_request_id"]
            or not waiting["permission_input_hash"]
        ):
            raise RuntimeError("AI PM smoke did not pause on a PermissionRequest.")

        _require(
            client.post(
                f"/api/v1/permissions/{waiting['permission_request_id']}/decisions",
                json={
                    "decision": "allow",
                    "input_hash": waiting["permission_input_hash"],
                    "decided_by": "d5-smoke-operator",
                },
            ),
            200,
        )
        completed = _require(
            client.post(f"/api/v1/agent-runtime/runs/{waiting['run_id']}/resume"),
            200,
        )
        if completed["state"] != "succeeded":
            raise RuntimeError(
                "AI PM smoke handed back after bounded retries: "
                f"state={completed['state']}, code={completed.get('error_code')}"
            )
        output = AiPmMrdOutput.model_validate(completed.get("output") or {})
        tool_results = completed.get("tool_results") or []
        definition = _require(
            client.post(
                f"/api/v1/projects/{project_id}/definition-submissions",
                headers={"Idempotency-Key": f"d5-definition-{nonce}"},
                json={
                    "source_run_id": completed["run_id"],
                    "context_pack_id": pack["id"],
                    "expected_context_version": 2,
                    "evidence_set_hash": _hash_json(tool_results),
                    "research_results": tool_results,
                    "artifact_proposals": [
                        {
                            "artifact_id": None,
                            "expected_previous_version": 0,
                            **proposal.model_dump(mode="json"),
                            "status": "waiting_review",
                        }
                        for proposal in output.artifact_proposals
                    ],
                },
            ),
            201,
        )
        reviewer_input = _require(
            client.get(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{definition['id']}/reviewer-input"
            ),
            200,
        )
        reviewer_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": definition["reviewer_context_pack_id"],
                    "user_input": reviewer_input["task"],
                },
            ),
            200,
        )
        if reviewer_run["state"] != "succeeded" or reviewer_run["tool_calls_used"] != 0:
            raise RuntimeError(
                "Reviewer smoke did not complete without external tools: "
                f"state={reviewer_run['state']}, code={reviewer_run.get('error_code')}"
            )
        reviewer_output = ReviewerMrdOutput.model_validate(reviewer_run.get("output") or {})
        red_team = reviewer_output.artifact_proposals[0]
        review = _require(
            client.post(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{definition['id']}/review",
                headers={"Idempotency-Key": f"d5-definition-review-{nonce}"},
                json={
                    "source_run_id": reviewer_run["run_id"],
                    "context_pack_id": definition["reviewer_context_pack_id"],
                    "expected_context_version": 2,
                    "verdict": reviewer_output.verdict,
                    "message": reviewer_output.message,
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in reviewer_output.findings
                    ],
                    "red_team_review": {
                        "artifact_id": None,
                        "expected_previous_version": 0,
                        "kind": "red_team_review",
                        "title": red_team.title,
                        "content": red_team.content,
                        "evidence_refs": red_team.evidence_refs,
                    },
                },
            ),
            200,
        )
        snapshot = _require(client.get(f"/api/v1/runs/{waiting['run_id']}"), 200)
        reviewer_snapshot = _require(
            client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200
        )
        gates = _require(client.get(f"/api/v1/projects/{project_id}/gates"), 200)
        events = _require(client.get(f"/api/v1/projects/{project_id}/events?cursor=0"), 200)

    proposals = [item.model_dump(mode="json") for item in output.artifact_proposals]
    evidence_refs = sorted(
        {
            ref
            for proposal in proposals
            for ref in proposal.get("evidence_refs") or []
            if isinstance(ref, str)
        }
    )
    step_evidence = [
        {
            "step_index": step["step_index"],
            "step_type": step["step_type"],
            "state": step["state"],
            "idempotency_key": step["idempotency_key"],
            "output_ref": step["output_ref"],
            "external_effect_confirmed": step["external_effect_confirmed"],
        }
        for step in snapshot["steps"]
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_only": True,
        "fixture_g0_is_not_product_approval": True,
        "provider": "bocha",
        "secret_ref": "BOCHA_API_KEY",
        "prompts_recorded": False,
        "search_bodies_recorded": False,
        "model_outputs_recorded": False,
        "project_id": project_id,
        "run_id": completed["run_id"],
        "permission_request_id": waiting["permission_request_id"],
        "initial_state": waiting["state"],
        "final_state": completed["state"],
        "turns_used": completed["turns_used"],
        "retries_used": completed["retries_used"],
        "research_retries_used": completed["research_retries_used"],
        "tool_calls_used": completed["tool_calls_used"],
        "requested_model": completed["requested_model"],
        "observed_model": completed["observed_model"],
        "usage": completed["usage"],
        "checkpoint_hash_before": waiting["checkpoint_hash"],
        "checkpoint_hash_after": completed["checkpoint_hash"],
        "output_sha256": _hash_json(output.model_dump(mode="json")),
        "artifact_proposal_count": len(proposals),
        "artifact_proposal_kinds": [proposal.get("kind") for proposal in proposals],
        "evidence_ref_count": len(evidence_refs),
        "evidence_ref_sha256": [_hash_json(ref) for ref in evidence_refs],
        "journal": step_evidence,
        "event_types": [event["event_type"] for event in events],
        "last_event_sequence": events[-1]["sequence"],
        "definition_submission": {
            "submission_id": definition["id"],
            "status_before_review": definition["status"],
            "evidence_set_hash": definition["evidence_set_hash"],
            "reviewer_context_pack_id": definition["reviewer_context_pack_id"],
            "artifact_refs": definition["artifact_refs"],
            "review_candidate_count": len(reviewer_input["artifacts"]),
            "review_candidate_content_recorded": False,
        },
        "reviewer": {
            "run_id": reviewer_run["run_id"],
            "state": reviewer_run["state"],
            "turns_used": reviewer_run["turns_used"],
            "retries_used": reviewer_run["retries_used"],
            "tool_calls_used": reviewer_run["tool_calls_used"],
            "requested_model": reviewer_run["requested_model"],
            "observed_model": reviewer_run["observed_model"],
            "usage": reviewer_run["usage"],
            "output_sha256": _hash_json(reviewer_output.model_dump(mode="json")),
            "checkpoint_hash": reviewer_run["checkpoint_hash"],
            "journal": [
                {
                    "step_index": step["step_index"],
                    "step_type": step["step_type"],
                    "state": step["state"],
                    "output_ref": step["output_ref"],
                }
                for step in reviewer_snapshot["steps"]
            ],
        },
        "definition_review": {
            "review_id": review["review_id"],
            "verdict": review["verdict"],
            "status": review["status"],
            "red_team_review": review["red_team_review"],
        },
        "g1_opened": bool(
            review.get("gate")
            and review["gate"]["gate_type"] == "G1"
            and review["gate"]["status"] == "open"
        ),
        "g1_decided": False,
        "open_gate_ids": [gate["id"] for gate in gates],
    }


if __name__ == "__main__":
    print(json.dumps(run_ai_pm_research_smoke(), ensure_ascii=False, indent=2))
