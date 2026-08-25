from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agents.outputs import AiPmPrdOutput, ReviewerPrdOutput
from app.main import app


def _require(response, expected: int) -> dict:
    body = response.json()
    if response.status_code != expected:
        error = body.get("error") or {}
        raise RuntimeError(
            f"PRD flow failed: status={response.status_code}, code={error.get('code')}"
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


def run_prd_flow(
    *,
    project_id: str,
    context_pack_id: str,
    context_version: int,
    prd_artifact_id: str | None = None,
    prd_expected_previous_version: int = 0,
    review_artifact_id: str | None = None,
    review_expected_previous_version: int = 0,
) -> dict:
    with TestClient(app) as client:
        project = _require(client.get(f"/api/v1/projects/{project_id}"), 200)
        if project["state"] != "prd" or project["context_version"] != context_version:
            raise RuntimeError("Project is not at the approved PRD context.")

        ai_pm_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": context_pack_id,
                    "user_input": (
                        "基于 Context Pack 中已批准的 MRD v2、Evidence Index v2 与 Red Team "
                        "Review v2，生成当前项目的真实 PRD。继承 G1 范围，不重新发散；"
                        "V1 核心能力不超过 3 项。PRD 必须覆盖：核心用户闭环、做/不做、状态与"
                        "边界、非技术用户可操作验收、北极星和反指标；AI 功能须写清模型任务、"
                        "输入输出、数据闭环、自动与人工评测、失败兜底。继续保留 Context "
                        "中尚未关闭的已知问题，不得替换成固定示范项目的问题。"
                        "只引用 Context 中的原始 EvidenceRef 或 artifact_ref，并将引用就近写入"
                        "正文。不得批准 G2、推进状态、启动 Builder、调用搜索或写外部系统。"
                    ),
                },
            ),
            200,
        )
        if ai_pm_run["state"] != "succeeded":
            return _failed_result(project_id, "ai_pm", ai_pm_run)
        ai_pm_output = AiPmPrdOutput.model_validate(ai_pm_run.get("output") or {})
        proposal = ai_pm_output.artifact_proposals[0]
        submission = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/prd-submissions",
                headers={"Idempotency-Key": f"prd-submission-{ai_pm_run['run_id']}"},
                json={
                    "source_run_id": ai_pm_run["run_id"],
                    "context_pack_id": context_pack_id,
                    "expected_context_version": context_version,
                    "artifact_proposal": {
                        "artifact_id": prd_artifact_id,
                        "expected_previous_version": prd_expected_previous_version,
                        **proposal.model_dump(mode="json"),
                    },
                },
            ),
            201,
        )
        reviewer_input = _require(
            client.get(
                f"/api/v1/agent-runtime/projects/{project_id}/prd-submissions/"
                f"{submission['submission_id']}/reviewer-input"
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
            return _failed_result(
                project_id,
                "reviewer",
                reviewer_run,
                ai_pm_run_id=ai_pm_run["run_id"],
                submission_id=submission["submission_id"],
            )
        reviewer_output = ReviewerPrdOutput.model_validate(
            reviewer_run.get("output") or {}
        )
        review_proposal = reviewer_output.artifact_proposals[0]
        review = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/prd-submissions/"
                f"{submission['submission_id']}/review",
                headers={"Idempotency-Key": f"prd-review-{reviewer_run['run_id']}"},
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
                    "review_artifact": {
                        "artifact_id": review_artifact_id,
                        "expected_previous_version": review_expected_previous_version,
                        **review_proposal.model_dump(mode="json"),
                    },
                },
            ),
            200,
        )
        ai_pm_snapshot = _require(client.get(f"/api/v1/runs/{ai_pm_run['run_id']}"), 200)
        reviewer_snapshot = _require(
            client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200
        )
        events = _require(
            client.get(f"/api/v1/projects/{project_id}/events", params={"cursor": 0}),
            200,
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "project_state": project["state"],
        "context_version": context_version,
        "context_pack_id": context_pack_id,
        "prompts_recorded": False,
        "model_outputs_recorded": False,
        "hidden_reasoning_recorded": False,
        "ai_pm": _run_evidence(ai_pm_run, ai_pm_snapshot),
        "prd_submission": {
            "submission_id": submission["submission_id"],
            "prd": submission["prd"],
            "reviewer_context_pack_id": submission["reviewer_context_pack_id"],
        },
        "reviewer": _run_evidence(reviewer_run, reviewer_snapshot),
        "review": {
            "verdict": review["verdict"],
            "status": review["status"],
            "prd_review": review["prd_review"],
            "known_issues": review["known_issues"],
        },
        "g2": review["gate"],
        "g2_decided": False,
        "builder_started": False,
        "event_types": [event["event_type"] for event in events],
        "last_event_sequence": events[-1]["sequence"],
    }


def _run_evidence(run: dict, snapshot: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "state": run["state"],
        "turns_used": run["turns_used"],
        "retries_used": run["retries_used"],
        "tool_calls_used": run["tool_calls_used"],
        "requested_model": run["requested_model"],
        "observed_model": run["observed_model"],
        "usage": run["usage"],
        "checkpoint_hash": run["checkpoint_hash"],
        "journal": _journal(snapshot),
    }


def _failed_result(project_id: str, role: str, run: dict, **extra: str) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "state": run["state"],
        "failed_role": role,
        "run_id": run["run_id"],
        "error_code": run["error_code"],
        "prompts_recorded": False,
        "model_outputs_recorded": False,
        **extra,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--context-pack-id", required=True)
    parser.add_argument("--context-version", type=int, default=3)
    parser.add_argument("--prd-artifact-id")
    parser.add_argument("--prd-expected-previous-version", type=int, default=0)
    parser.add_argument("--review-artifact-id")
    parser.add_argument("--review-expected-previous-version", type=int, default=0)
    args = parser.parse_args()
    result = run_prd_flow(
        project_id=args.project_id,
        context_pack_id=args.context_pack_id,
        context_version=args.context_version,
        prd_artifact_id=args.prd_artifact_id,
        prd_expected_previous_version=args.prd_expected_previous_version,
        review_artifact_id=args.review_artifact_id,
        review_expected_previous_version=args.review_expected_previous_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
