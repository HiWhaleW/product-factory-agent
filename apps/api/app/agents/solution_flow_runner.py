from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agents.outputs import BuilderSolutionOutput, ReviewerSolutionOutput
from app.main import app


def _require(response, expected: int) -> dict:
    body = response.json()
    if response.status_code != expected:
        error = body.get("error") or body.get("detail", {}).get("error") or {}
        raise RuntimeError(
            f"Solution flow failed: status={response.status_code}, code={error.get('code')}"
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


def run_solution_flow(
    *,
    project_id: str,
    context_pack_id: str,
    context_version: int,
) -> dict:
    with TestClient(app) as client:
        project = _require(client.get(f"/api/v1/projects/{project_id}"), 200)
        if (
            project["state"] != "solution_confirmation"
            or project["context_version"] != context_version
        ):
            raise RuntimeError("Project is not at the approved solution context.")
        builder_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": context_pack_id,
                    "user_input": (
                        "基于 Context Pack 中已批准的 PRD v1 与 PRD Review v1，只生成方案文档。"
                        "输出必须包含且仅包含：1）User Flow；2）方案说明。前端当前确认稿全部固定，"
                        "不得提出非必要前端改动；如存在无法复用的前端缺口，只列为需要用户另行确认"
                        "的问题，不在本次方案中修改。User Flow 要覆盖输入、生成、人工检查、导出/"
                        "回看、失败与空状态；方案说明要覆盖关键路径、状态、异常、可访问性、范围"
                        "影响和关键取舍。只引用 Context 中精确 artifact_ref，并在正文就近标注。"
                        "不得请求任何工具，不得写代码，不得调用 Codex/Git/测试/部署，不得选择"
                        "技术栈，不得批准 G3，不得推进项目状态。"
                    ),
                },
            ),
            200,
        )
        if builder_run["state"] != "succeeded" or builder_run["tool_calls_used"] != 0:
            return _failed_result(project_id, "builder", builder_run)
        builder_output = BuilderSolutionOutput.model_validate(builder_run.get("output") or {})
        submission = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions",
                headers={
                    "Idempotency-Key": f"solution-submission-{builder_run['run_id']}"
                },
                json={
                    "source_run_id": builder_run["run_id"],
                    "context_pack_id": context_pack_id,
                    "expected_context_version": context_version,
                    "artifact_proposals": [
                        proposal.model_dump(mode="json")
                        for proposal in builder_output.artifact_proposals
                    ],
                },
            ),
            201,
        )
        reviewer_input = _require(
            client.get(
                f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions/"
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
                builder_run_id=builder_run["run_id"],
                submission_id=submission["submission_id"],
            )
        reviewer_output = ReviewerSolutionOutput.model_validate(
            reviewer_run.get("output") or {}
        )
        review = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions/"
                f"{submission['submission_id']}/review",
                headers={"Idempotency-Key": f"solution-review-{reviewer_run['run_id']}"},
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
                    "review_artifact": reviewer_output.artifact_proposals[0].model_dump(
                        mode="json"
                    ),
                },
            ),
            200,
        )
        builder_snapshot = _require(
            client.get(f"/api/v1/runs/{builder_run['run_id']}"), 200
        )
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
        "frontend_changed": False,
        "codex_or_code_tools_used": False,
        "builder": _run_evidence(builder_run, builder_snapshot),
        "solution_submission": {
            "submission_id": submission["submission_id"],
            "user_flow": submission["user_flow"],
            "solution_design": submission["solution_design"],
            "reviewer_context_pack_id": submission["reviewer_context_pack_id"],
        },
        "reviewer": _run_evidence(reviewer_run, reviewer_snapshot),
        "review": {
            "verdict": review["verdict"],
            "status": review["status"],
            "solution_review": review["solution_review"],
            "known_issues": review["known_issues"],
        },
        "g3": review["gate"],
        "g3_decided": False,
        "development_started": False,
        "event_types": [event["event_type"] for event in events],
        "last_event_sequence": events[-1]["sequence"],
    }


def run_solution_review(
    *,
    project_id: str,
    submission_id: str,
    context_version: int,
) -> dict:
    """Retry only the clean review for an already persisted solution pair."""
    with TestClient(app) as client:
        project = _require(client.get(f"/api/v1/projects/{project_id}"), 200)
        if (
            project["state"] != "solution_confirmation"
            or project["context_version"] != context_version
        ):
            raise RuntimeError("Project is not at the approved solution context.")
        reviewer_input = _require(
            client.get(
                f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions/"
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
            return _failed_result(
                project_id,
                "reviewer",
                reviewer_run,
                submission_id=submission_id,
            )
        reviewer_output = ReviewerSolutionOutput.model_validate(
            reviewer_run.get("output") or {}
        )
        review = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/solution-submissions/"
                f"{submission_id}/review",
                headers={"Idempotency-Key": f"solution-review-{reviewer_run['run_id']}"},
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
                    "review_artifact": reviewer_output.artifact_proposals[0].model_dump(
                        mode="json"
                    ),
                },
            ),
            200,
        )
        reviewer_snapshot = _require(
            client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "project_state": project["state"],
        "context_version": context_version,
        "prompts_recorded": False,
        "model_outputs_recorded": False,
        "hidden_reasoning_recorded": False,
        "frontend_changed": False,
        "codex_or_code_tools_used": False,
        "solution_submission": {"submission_id": submission_id},
        "reviewer": _run_evidence(reviewer_run, reviewer_snapshot),
        "review": {
            "verdict": review["verdict"],
            "status": review["status"],
            "solution_review": review["solution_review"],
            "known_issues": review["known_issues"],
        },
        "g3": review["gate"],
        "g3_decided": False,
        "development_started": False,
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
        "frontend_changed": False,
        **extra,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--context-pack-id")
    parser.add_argument("--context-version", type=int, default=4)
    parser.add_argument("--submission-id")
    args = parser.parse_args()
    if args.submission_id:
        result = run_solution_review(
            project_id=args.project_id,
            submission_id=args.submission_id,
            context_version=args.context_version,
        )
    else:
        if not args.context_pack_id:
            parser.error("--context-pack-id is required unless --submission-id is provided")
        result = run_solution_flow(
            project_id=args.project_id,
            context_pack_id=args.context_pack_id,
            context_version=args.context_version,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
