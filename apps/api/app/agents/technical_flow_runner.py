from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agents.outputs import BuilderTechnicalOutput, ReviewerTechnicalOutput
from app.main import app


def _require(response, expected: int) -> dict:
    body = response.json()
    if response.status_code != expected:
        error = body.get("error") or body.get("detail", {}).get("error") or {}
        raise RuntimeError(
            f"Technical flow failed: status={response.status_code}, code={error.get('code')}"
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


def run_technical_flow(
    *,
    project_id: str,
    context_pack_id: str,
    context_version: int,
) -> dict:
    with TestClient(app) as client:
        project = _require(client.get(f"/api/v1/projects/{project_id}"), 200)
        if (
            project["state"] != "tech_stack_confirmation"
            or project["context_version"] != context_version
        ):
            raise RuntimeError("Project is not at the approved technical context.")
        builder_run = _require(
            client.post(
                "/api/v1/agent-runtime/runs",
                json={
                    "context_pack_id": context_pack_id,
                    "user_input": (
                        "只生成技术定义文档，不写代码。输出必须包含且仅包含："
                        "1）Technical Adaptation；2）API Contract。严格继承 Context 中已批准的"
                        "User Flow、方案说明和 Solution Review，并继承项目冻结技术路线："
                        "Next.js 16.3.1、React 19.2.8、Tailwind 4.3.3、React Flow 12.11.3、"
                        "CopilotKit 1.68.1、AG-UI 0.0.58、FastAPI 0.141.1、Pydantic 2.13.4、"
                        "LangGraph 1.2.11、PostgreSQL 16.x、SQLAlchemy 2.0.52、Alembic 1.19.1、"
                        "Codex CLI Adapter。覆盖 Runtime/API/数据库边界、版本、数据与密钥、"
                        "成本、可观测性、迁移、失败处理、回退和验收证据。前端固定，不得提出"
                        "非必要前端改动。只引用 Context 中精确 artifact_ref 并在正文就近标注。"
                        "不得请求工具、不得调用 Codex/Git/测试/部署、不得批准 G4、不得推进状态。"
                    ),
                },
            ),
            200,
        )
        if builder_run["state"] != "succeeded" or builder_run["tool_calls_used"] != 0:
            return _failed_result(project_id, "builder", builder_run)
        builder_output = BuilderTechnicalOutput.model_validate(builder_run.get("output") or {})
        submission = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/technical-submissions",
                headers={"Idempotency-Key": f"technical-submission-{builder_run['run_id']}"},
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
                f"/api/v1/agent-runtime/projects/{project_id}/technical-submissions/"
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
        reviewer_output = ReviewerTechnicalOutput.model_validate(reviewer_run.get("output") or {})
        review = _require(
            client.post(
                f"/api/v1/agent-runtime/projects/{project_id}/technical-submissions/"
                f"{submission['submission_id']}/review",
                headers={"Idempotency-Key": f"technical-review-{reviewer_run['run_id']}"},
                json={
                    "source_run_id": reviewer_run["run_id"],
                    "context_pack_id": submission["reviewer_context_pack_id"],
                    "expected_context_version": context_version,
                    "verdict": reviewer_output.verdict,
                    "message": reviewer_output.message,
                    "findings": [
                        finding.model_dump(mode="json") for finding in reviewer_output.findings
                    ],
                    "review_artifact": reviewer_output.artifact_proposals[0].model_dump(
                        mode="json"
                    ),
                },
            ),
            200,
        )
        builder_snapshot = _require(client.get(f"/api/v1/runs/{builder_run['run_id']}"), 200)
        reviewer_snapshot = _require(client.get(f"/api/v1/runs/{reviewer_run['run_id']}"), 200)

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
        "technical_submission": submission,
        "reviewer": _run_evidence(reviewer_run, reviewer_snapshot),
        "review": {
            "verdict": review["verdict"],
            "status": review["status"],
            "technical_review": review["technical_review"],
            "known_issues": review["known_issues"],
        },
        "g4": review["gate"],
        "g4_decided": False,
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
    parser.add_argument("--context-pack-id", required=True)
    parser.add_argument("--context-version", type=int, required=True)
    args = parser.parse_args()
    result = run_technical_flow(
        project_id=args.project_id,
        context_pack_id=args.context_pack_id,
        context_version=args.context_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
