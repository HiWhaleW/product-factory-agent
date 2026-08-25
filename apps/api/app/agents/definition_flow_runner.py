from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agents.outputs import AiPmMrdOutput, ReviewerMrdOutput
from app.main import app


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _require(response, expected: int) -> dict:
    body = response.json()
    if response.status_code != expected:
        error = body.get("error") or {}
        raise RuntimeError(
            f"Definition flow failed: status={response.status_code}, "
            f"code={error.get('code')}"
        )
    return body


def _journal(snapshot: dict) -> list[dict]:
    return [
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


def run_definition_flow(
    *,
    project_id: str,
    brief_id: str,
    context_version: int,
    brief_version: int,
    allow_web_research: bool,
    evidence_artifact_id: str | None,
    mrd_artifact_id: str | None,
    red_team_artifact_id: str | None,
    expected_previous_version: int,
) -> dict:
    with TestClient(app) as client:
        project = _require(client.get(f"/api/v1/projects/{project_id}"), 200)
        if project["state"] != "mrd" or project["context_version"] != context_version:
            raise RuntimeError("Project is not at the approved MRD context.")

        pack = _require(
            client.get(
                f"/api/v1/projects/{project_id}/context-packs/exact",
                params={
                    "context_version": context_version,
                    "stage": "mrd",
                    "recipient_agent_id": "ai-pm",
                    "resource_type": "project_brief",
                    "resource_id": brief_id,
                    "resource_version": brief_version,
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
                        "读取 Context Pack 中当前项目的目标用户、问题、范围与待验证假设，"
                        "据此形成精确研究查询；不得替换成固定行业或示范项目。优先官方、"
                        "原始报告和一手来源。Evidence Index 逐条包含原始 EvidenceRef、标题、URL、"
                        "发布方/日期、支持的精确结论、段落/章节或可用的时间戳定位"
                        "与局限。MRD 中的市场事实和需求推导就近引用原始 "
                        "EvidenceRef。严格区分已验证事实、假设和待访谈项；不得把"
                        "搜索摘要写成全文证据，不得自动外发、修改外部系统、部署、"
                        "代替用户决策或推进项目状态。对 Reviewer 第一轮反馈做明确修订："
                        "只有直接支持当前项目关键结论的来源才能标为直接证据；其他来源必须"
                        "标为背景或假设。若搜索结果无法提供段落/时间戳，必须如实"
                        "标注为未验证，并将原文定位与 5–8 名目标用户访谈列为 G1 "
                        "后续条件，不得伪造定位。发布方或日期缺失时标注未知。"
                    ),
                },
            ),
            200,
        )
        if waiting["state"] != "waiting_human":
            raise RuntimeError("AI PM did not stop for web research permission.")
        if not allow_web_research:
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "state": "waiting_human",
                "run_id": waiting["run_id"],
                "permission_request_id": waiting["permission_request_id"],
                "checkpoint_hash": waiting["checkpoint_hash"],
            }

        _require(
            client.post(
                f"/api/v1/permissions/{waiting['permission_request_id']}/decisions",
                json={
                    "decision": "allow",
                    "input_hash": waiting["permission_input_hash"],
                    "decided_by": "local-admin",
                },
            ),
            200,
        )
        ai_pm_run = _require(
            client.post(f"/api/v1/agent-runtime/runs/{waiting['run_id']}/resume"),
            200,
        )
        if ai_pm_run["state"] != "succeeded":
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "state": ai_pm_run["state"],
                "run_id": ai_pm_run["run_id"],
                "error_code": ai_pm_run["error_code"],
                "checkpoint_hash_before": waiting["checkpoint_hash"],
                "checkpoint_hash_after": ai_pm_run["checkpoint_hash"],
            }

        ai_pm_output = AiPmMrdOutput.model_validate(ai_pm_run.get("output") or {})
        tool_results = ai_pm_run.get("tool_results") or []
        submission = _require(
            client.post(
                f"/api/v1/projects/{project_id}/definition-submissions",
                headers={"Idempotency-Key": f"product-definition-{ai_pm_run['run_id']}"},
                json={
                    "source_run_id": ai_pm_run["run_id"],
                    "context_pack_id": pack["id"],
                    "expected_context_version": context_version,
                    "evidence_set_hash": _hash_json(tool_results),
                    "research_results": tool_results,
                    "artifact_proposals": [
                        {
                            "artifact_id": (
                                evidence_artifact_id
                                if proposal.kind == "evidence_index"
                                else mrd_artifact_id
                            ),
                            "expected_previous_version": expected_previous_version,
                            **proposal.model_dump(mode="json"),
                            "status": "waiting_review",
                        }
                        for proposal in ai_pm_output.artifact_proposals
                    ],
                },
            ),
            201,
        )
        reviewer_input = _require(
            client.get(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{submission['id']}/reviewer-input"
            ),
            200,
        )
        reviewer_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": submission["reviewer_context_pack_id"],
                    "user_input": reviewer_input["task"],
                },
            ),
            200,
        )
        if reviewer_run["state"] != "succeeded" or reviewer_run["tool_calls_used"] != 0:
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "state": reviewer_run["state"],
                "ai_pm_run_id": ai_pm_run["run_id"],
                "reviewer_run_id": reviewer_run["run_id"],
                "error_code": reviewer_run["error_code"],
            }

        reviewer_output = ReviewerMrdOutput.model_validate(reviewer_run.get("output") or {})
        red_team = reviewer_output.artifact_proposals[0]
        review = _require(
            client.post(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{submission['id']}/review",
                headers={"Idempotency-Key": f"product-review-{reviewer_run['run_id']}"},
                json={
                    "source_run_id": reviewer_run["run_id"],
                    "context_pack_id": submission["reviewer_context_pack_id"],
                    "expected_context_version": context_version,
                    "verdict": reviewer_output.verdict,
                    "message": reviewer_output.message,
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in reviewer_output.findings
                    ],
                    "red_team_review": {
                        "artifact_id": red_team_artifact_id,
                        "expected_previous_version": expected_previous_version,
                        "kind": "red_team_review",
                        "title": red_team.title,
                        "content": red_team.content,
                        "evidence_refs": red_team.evidence_refs,
                    },
                },
            ),
            200,
        )
        ai_pm_snapshot = _require(client.get(f"/api/v1/runs/{ai_pm_run['run_id']}"), 200)
        reviewer_snapshot = _require(
            client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200
        )
        gates = _require(
            client.get(f"/api/v1/projects/{project_id}/gates", params={"status": "open"}),
            200,
        )
        events = _require(
            client.get(f"/api/v1/projects/{project_id}/events", params={"cursor": 0}),
            200,
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "project_state": project["state"],
        "context_version": project["context_version"],
        "context_pack_id": pack["id"],
        "prompts_recorded": False,
        "search_bodies_recorded": False,
        "model_outputs_recorded": False,
        "permission": {
            "request_id": waiting["permission_request_id"],
            "decision": "allow",
            "separate_from_gate": True,
        },
        "ai_pm": {
            "run_id": ai_pm_run["run_id"],
            "state": ai_pm_run["state"],
            "turns_used": ai_pm_run["turns_used"],
            "retries_used": ai_pm_run["retries_used"],
            "research_retries_used": ai_pm_run["research_retries_used"],
            "tool_calls_used": ai_pm_run["tool_calls_used"],
            "requested_model": ai_pm_run["requested_model"],
            "observed_model": ai_pm_run["observed_model"],
            "usage": ai_pm_run["usage"],
            "checkpoint_hash_before": waiting["checkpoint_hash"],
            "checkpoint_hash_after": ai_pm_run["checkpoint_hash"],
            "journal": _journal(ai_pm_snapshot),
        },
        "definition_submission": {
            "id": submission["id"],
            "status": submission["status"],
            "artifact_refs": submission["artifact_refs"],
            "reviewer_context_pack_id": submission["reviewer_context_pack_id"],
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
            "journal": _journal(reviewer_snapshot),
        },
        "review": {
            "id": review["review_id"],
            "verdict": review["verdict"],
            "status": review["status"],
            "message": reviewer_output.message,
            "findings": [
                {
                    "severity": finding.severity,
                    "title": finding.title,
                    "impact": finding.impact,
                    "recommended_fix": finding.recommended_fix,
                }
                for finding in reviewer_output.findings
            ],
        },
        "g1_open": next(
            (
                {
                    "id": gate["id"],
                    "status": gate["status"],
                    "context_version": gate["context_version"],
                    "target_state": gate["target_state"],
                    "impacted_artifact_refs": gate["impacted_artifact_refs"],
                }
                for gate in gates
                if gate["gate_type"] == "G1"
            ),
            None,
        ),
        "g1_decided": False,
        "event_types": [event["event_type"] for event in events],
        "last_event_sequence": events[-1]["sequence"],
    }


def retry_reviewer_flow(
    *,
    project_id: str,
    submission_id: str,
    context_version: int,
    red_team_artifact_id: str,
    expected_previous_version: int,
) -> dict:
    """Retry only the clean-context Reviewer after a fail-closed provider error."""
    with TestClient(app) as client:
        reviewer_input = _require(
            client.get(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{submission_id}/reviewer-input"
            ),
            200,
        )
        reviewer_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": reviewer_input["reviewer_context_pack_id"],
                    "user_input": reviewer_input["task"],
                },
            ),
            200,
        )
        if reviewer_run["state"] != "succeeded" or reviewer_run["tool_calls_used"] != 0:
            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "project_id": project_id,
                "submission_id": submission_id,
                "state": reviewer_run["state"],
                "reviewer_run_id": reviewer_run["run_id"],
                "error_code": reviewer_run["error_code"],
            }
        reviewer_output = ReviewerMrdOutput.model_validate(reviewer_run.get("output") or {})
        red_team = reviewer_output.artifact_proposals[0]
        review = _require(
            client.post(
                f"/api/v1/projects/{project_id}/definition-submissions/"
                f"{submission_id}/review",
                headers={"Idempotency-Key": f"product-review-{reviewer_run['run_id']}"},
                json={
                    "source_run_id": reviewer_run["run_id"],
                    "context_pack_id": reviewer_input["reviewer_context_pack_id"],
                    "expected_context_version": context_version,
                    "verdict": reviewer_output.verdict,
                    "message": reviewer_output.message,
                    "findings": [
                        finding.model_dump(mode="json")
                        for finding in reviewer_output.findings
                    ],
                    "red_team_review": {
                        "artifact_id": red_team_artifact_id,
                        "expected_previous_version": expected_previous_version,
                        "kind": "red_team_review",
                        "title": red_team.title,
                        "content": red_team.content,
                        "evidence_refs": red_team.evidence_refs,
                    },
                },
            ),
            200,
        )
        snapshot = _require(client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200)
        events = _require(
            client.get(f"/api/v1/projects/{project_id}/events", params={"cursor": 0}),
            200,
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "submission_id": submission_id,
        "prompts_recorded": False,
        "model_outputs_recorded": False,
        "reviewer": {
            "run_id": reviewer_run["run_id"],
            "state": reviewer_run["state"],
            "turns_used": reviewer_run["turns_used"],
            "retries_used": reviewer_run["retries_used"],
            "tool_calls_used": reviewer_run["tool_calls_used"],
            "requested_model": reviewer_run["requested_model"],
            "observed_model": reviewer_run["observed_model"],
            "usage": reviewer_run["usage"],
            "journal": _journal(snapshot),
        },
        "review": {
            "id": review["review_id"],
            "verdict": review["verdict"],
            "status": review["status"],
            "message": reviewer_output.message,
            "findings": [
                {
                    "severity": finding.severity,
                    "title": finding.title,
                    "impact": finding.impact,
                    "recommended_fix": finding.recommended_fix,
                }
                for finding in reviewer_output.findings
            ],
            "red_team_review": review["red_team_review"],
            "gate": review["gate"],
        },
        "g1_decided": False,
        "last_event_sequence": events[-1]["sequence"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--brief-id", required=True)
    parser.add_argument("--context-version", type=int, default=2)
    parser.add_argument("--brief-version", type=int, default=1)
    parser.add_argument("--allow-web-research", action="store_true")
    parser.add_argument("--evidence-artifact-id")
    parser.add_argument("--mrd-artifact-id")
    parser.add_argument("--red-team-artifact-id")
    parser.add_argument("--expected-previous-version", type=int, default=0)
    parser.add_argument("--retry-reviewer-submission-id")
    args = parser.parse_args()
    if args.retry_reviewer_submission_id:
        if not args.red_team_artifact_id:
            parser.error("--red-team-artifact-id is required for Reviewer retry")
        result = retry_reviewer_flow(
            project_id=args.project_id,
            submission_id=args.retry_reviewer_submission_id,
            context_version=args.context_version,
            red_team_artifact_id=args.red_team_artifact_id,
            expected_previous_version=args.expected_previous_version,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(
        json.dumps(
            run_definition_flow(
                project_id=args.project_id,
                brief_id=args.brief_id,
                context_version=args.context_version,
                brief_version=args.brief_version,
                allow_web_research=args.allow_web_research,
                evidence_artifact_id=args.evidence_artifact_id,
                mrd_artifact_id=args.mrd_artifact_id,
                red_team_artifact_id=args.red_team_artifact_id,
                expected_previous_version=args.expected_previous_version,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
