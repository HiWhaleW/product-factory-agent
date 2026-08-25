from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.codex_cli import (
    CodexCliExecution,
    execute_codex_cli,
    resolve_project_workspace,
)
from app.agents.builder_contracts import BuilderCodexOutput
from app.agents.outputs import BuilderOutput
from app.agents.registry import load_frozen_prompt
from app.core.config import Settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    Event,
    IdempotencyRecord,
    Project,
    RunStep,
    ToolRun,
)
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact


class BuilderRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class BuilderRuntimeService:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory

    def start(
        self,
        *,
        project_id: str,
        task_id: str,
        context_pack_id: str,
        expected_context_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not self.settings.BUILDER_ENABLED:
            raise BuilderRuntimeError(
                "BUILDER_DISABLED",
                "当前安装未启用受控开发工作区，Builder 不会执行。",
            )
        request_hash = self._request_hash(
            project_id=project_id,
            task_id=task_id,
            context_pack_id=context_pack_id,
            expected_context_version=expected_context_version,
        )
        scope = f"builder.run:{project_id}"
        with self.session_factory.begin() as session:
            self._advisory_lock(session, f"project:{project_id}")
            self._advisory_lock(session, f"idempotency:{scope}:{idempotency_key}")
            existing = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.input_hash != request_hash:
                    raise BuilderRuntimeError(
                        "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同的 Builder 输入。"
                    )
                run = session.get(AgentRun, existing.resource_id)
                if run is None:
                    raise BuilderRuntimeError(
                        "IDEMPOTENCY_ORPHAN", "Builder 幂等记录指向的 Run 不存在。"
                    )
                return self._read_result(session, run, idempotent=True)
            project, task, pack = self._validate_scope(
                session,
                project_id=project_id,
                task_id=task_id,
                context_pack_id=context_pack_id,
                expected_context_version=expected_context_version,
            )
            attempt = (
                session.scalar(
                    select(func.max(AgentRun.attempt)).where(AgentRun.task_id == task.id)
                )
                or 0
            ) + 1
            max_retries = int((pack.policy.get("budget") or {}).get("max_retries", 0))
            if attempt > max_retries + 1:
                raise BuilderRuntimeError(
                    "BUILDER_RETRY_BUDGET_EXHAUSTED", "Builder 重试次数已达到批准预算。"
                )
            run = AgentRun(
                task_id=task.id,
                attempt=attempt,
                state="running",
                input_hash=request_hash,
                retries_used=attempt - 1,
                started_at=datetime.now(UTC),
            )
            task.state = "running"
            task.claimed_by = "codex-builder-runtime"
            session.add(run)
            session.flush()
            session.add(
                IdempotencyRecord(
                    scope=scope,
                    key=idempotency_key,
                    resource_id=run.id,
                    input_hash=request_hash,
                )
            )
            self._add_step(
                session,
                run=run,
                step_type="runtime_start",
                state="completed",
                input_hash=request_hash,
                output_ref=f"context-pack://{pack.id}",
            )
            prepare_step = self._add_step(
                session,
                run=run,
                step_type="workspace_prepare",
                state="started",
                input_hash=request_hash,
                idempotency_key=f"builder-workspace:{run.id}",
            )
            self._append_event(
                session,
                project.id,
                "run.started",
                {
                    "run_id": run.id,
                    "task_id": task.id,
                    "agent_id": "builder",
                    "context_pack_id": pack.id,
                    "context_version": pack.context_version,
                    "executor": "codex_cli",
                },
            )
            run_id = run.id
            prepare_step_id = prepare_step.id

        try:
            workspace, schema_path, prompt, material_hash = self._materialize_context(
                project_id=project_id,
                context_pack_id=context_pack_id,
            )
            with self.session_factory.begin() as session:
                prepare_step = session.get(RunStep, prepare_step_id)
                run = session.get(AgentRun, run_id)
                task = session.get(AgentTask, task_id)
                if prepare_step is None or run is None or task is None:
                    raise BuilderRuntimeError("RUN_NOT_FOUND", "Builder Run 在准备阶段丢失。")
                prepare_step.state = "completed"
                prepare_step.output_ref = f"context-materials://{material_hash}"
                prepare_step.external_effect_confirmed = True
                tool_step = self._add_step(
                    session,
                    run=run,
                    step_type="codex_cli",
                    state="started",
                    input_hash=request_hash,
                    idempotency_key=f"codex_cli:{run.id}:1",
                )
                tool = ToolRun(
                    task_id=task.id,
                    run_id=run.id,
                    capability_id="CAP-08",
                    tool_name="codex_cli",
                    state="started",
                    input_hash=request_hash,
                    idempotency_key=f"codex_cli:{run.id}:1",
                )
                session.add(tool)
                session.flush()
                tool_step_id = tool_step.id
                tool_id = tool.id
                self._append_event(
                    session,
                    project_id,
                    "tool_run.started",
                    {
                        "tool_run_id": tool.id,
                        "run_id": run.id,
                        "task_id": task.id,
                        "tool_id": "codex_cli",
                        "workspace_scope": project_id,
                    },
                )
            execution = execute_codex_cli(
                self.settings,
                project_id=project_id,
                prompt=prompt,
                output_schema=schema_path,
            )
            return self._persist_execution(
                run_id=run_id,
                task_id=task_id,
                project_id=project_id,
                tool_step_id=tool_step_id,
                tool_id=tool_id,
                execution=execution,
            )
        except Exception as exc:
            if isinstance(exc, BuilderRuntimeError):
                error = exc
            else:
                error = BuilderRuntimeError(
                    "BUILDER_RUNTIME_FAILED", f"Builder Runtime 失败：{type(exc).__name__}"
                )
            self._persist_failure(
                run_id=run_id,
                task_id=task_id,
                project_id=project_id,
                error=error,
            )
            raise error from exc

    def _validate_scope(
        self,
        session: Session,
        *,
        project_id: str,
        task_id: str,
        context_pack_id: str,
        expected_context_version: int,
    ) -> tuple[Project, AgentTask, ContextPack]:
        project = session.get(Project, project_id)
        task = session.get(AgentTask, task_id)
        pack = session.get(ContextPack, context_pack_id)
        context = (
            session.scalar(
                select(ContextVersion).where(
                    ContextVersion.project_id == project_id,
                    ContextVersion.version == expected_context_version,
                    ContextVersion.approval_status == "active",
                )
            )
            if project is not None
            else None
        )
        if project is None or task is None or pack is None or context is None:
            raise BuilderRuntimeError("BUILDER_SCOPE_NOT_FOUND", "Builder 执行范围不存在。")
        if (
            project.state not in {"development_backend", "development_frontend"}
            or project.context_version != expected_context_version
            or task.project_id != project.id
            or task.assigned_agent != "builder"
            or task.context_version != expected_context_version
            or task.state not in {"ready", "failed"}
            or task.claimed_by not in {None, "codex-builder-runtime"}
            or pack.project_id != project.id
            or pack.context_version != expected_context_version
            or pack.stage != project.state
            or pack.agent_id != "builder"
            or pack.approval_status != "approved"
        ):
            raise BuilderRuntimeError("STALE_CONTEXT", "Builder Task 或 Context Pack 已失效。")
        if task.state == "failed":
            latest_run = session.scalar(
                select(AgentRun)
                .where(AgentRun.task_id == task.id)
                .order_by(AgentRun.attempt.desc())
            )
            unresolved_step = (
                session.scalar(
                    select(RunStep).where(
                        RunStep.run_id == latest_run.id,
                        RunStep.state.in_(["started", "running"]),
                        RunStep.external_effect_confirmed.is_(False),
                    )
                )
                if latest_run is not None
                else None
            )
            unresolved_tool = (
                session.scalar(
                    select(ToolRun).where(
                        ToolRun.run_id == latest_run.id,
                        ToolRun.state.in_(["started", "running"]),
                    )
                )
                if latest_run is not None
                else None
            )
            if (
                latest_run is None
                or latest_run.state != "failed"
                or latest_run.completed_at is None
                or unresolved_step is not None
                or unresolved_tool is not None
            ):
                raise BuilderRuntimeError(
                    "SIDE_EFFECT_RECONCILIATION_REQUIRED",
                    "上一次 Builder 外部副作用尚未对账，拒绝重试。",
                )
        policy = pack.policy
        required_forbidden = {
            "advance_project_state",
            "approve_gate",
            "git_push",
            "deploy_adapter",
            "workspace_delete",
            "read_secret_values",
        }
        backend_tools = {
            "codex_cli",
            "project_fs_read",
            "project_fs_write",
            "git_local",
            "test_runner",
        }
        frontend_tools = backend_tools | {"browser_qa"}
        expected_mode = {
            "development_backend": "backend_development",
            "development_frontend": "frontend_development",
        }[project.state]
        expected_tools = (
            backend_tools if project.state == "development_backend" else frontend_tools
        )
        if project.state == "development_frontend":
            required_forbidden.add("modify_product_factory_frontend")
        if (
            policy.get("mode") != expected_mode
            or policy.get("workspace_scope") != project.id
            or not required_forbidden.issubset(set(policy.get("forbidden_actions") or []))
            or set(policy.get("allowed_tools") or []) != expected_tools
        ):
            raise BuilderRuntimeError("BUILDER_POLICY_INVALID", "Builder 工具策略不完整。")
        return project, task, pack

    def _materialize_context(
        self, *, project_id: str, context_pack_id: str
    ) -> tuple[Path, Path, str, str]:
        with self.session_factory() as session:
            pack = session.get(ContextPack, context_pack_id)
            if pack is None:
                raise BuilderRuntimeError("CONTEXT_PACK_NOT_FOUND", "Builder Context Pack 不存在。")
            expected_kinds = {
                "development_backend": {
                    "api_contract",
                    "technical_adaptation",
                    "technical_review",
                },
                "development_frontend": {
                    "api_contract",
                    "backend_implementation",
                    "backend_review",
                    "backend_test_report",
                    "solution_design",
                    "user_flow",
                },
            }.get(pack.stage)
            if expected_kinds is None:
                raise BuilderRuntimeError(
                    "BUILDER_STAGE_INVALID", "当前阶段不支持 Codex Builder。"
                )
            refs = [
                (pack.primary_resource_id, pack.primary_resource_version),
                *[(item["resource_id"], item["version"]) for item in pack.references],
            ]
            materials: dict[str, str] = {}
            for artifact_id, version_number in refs:
                artifact = session.get(Artifact, artifact_id)
                version = session.scalar(
                    select(ArtifactVersion).where(
                        ArtifactVersion.artifact_id == artifact_id,
                        ArtifactVersion.version == version_number,
                    )
                )
                if (
                    artifact is None
                    or version is None
                    or artifact.project_id != project_id
                    or artifact.kind not in expected_kinds
                    or version.approval_status != "approved"
                ):
                    raise BuilderRuntimeError(
                        "BUILDER_MATERIAL_INVALID", "Builder 技术材料缺失或未批准。"
                    )
                try:
                    _, content = read_verified_artifact(
                        self.settings.ARTIFACT_ROOT,
                        version.content_ref,
                        version.content_hash,
                    )
                except ArtifactStoreError as exc:
                    raise BuilderRuntimeError(
                        "BUILDER_MATERIAL_INVALID", "Builder 技术材料完整性校验失败。"
                    ) from exc
                materials[artifact.kind] = content
        if set(materials) != expected_kinds:
            raise BuilderRuntimeError("BUILDER_MATERIAL_INVALID", "Builder 技术材料不完整。")
        workspace = resolve_project_workspace(self.settings, project_id)
        context_dir = workspace / ".product-factory" / f"context-v{pack.context_version}"
        context_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        filenames = {
            "api_contract": "API-Contract.md",
            "technical_adaptation": "Technical-Adaptation.md",
            "technical_review": "Technical-Review.md",
            "user_flow": "User-Flow.md",
            "solution_design": "Solution-Design.md",
            "backend_implementation": "Backend-Implementation.md",
            "backend_test_report": "Backend-Test-Report.md",
            "backend_review": "Backend-Review.md",
        }
        files = {filenames[kind]: materials[kind] for kind in sorted(materials)}
        frozen_prompt, prompt_hash = load_frozen_prompt("builder")
        schema_text = json.dumps(
            BuilderCodexOutput.model_json_schema(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        files["builder-output-v2.schema.json"] = schema_text
        files["CONTEXT.md"] = self._context_summary(pack, prompt_hash)
        for filename, content in files.items():
            self._write_exact(context_dir / filename, content)
        material_hash = hashlib.sha256(
            "\n".join(
                f"{name}:{hashlib.sha256(content.encode()).hexdigest()}"
                for name, content in sorted(files.items())
            ).encode()
        ).hexdigest()
        context_path = context_dir.relative_to(workspace).as_posix()
        prompt = self._builder_prompt(
            frozen_prompt,
            task=pack.task,
            stage=pack.stage,
            context_path=context_path,
        )
        return workspace, context_dir / "builder-output-v2.schema.json", prompt, material_hash

    @staticmethod
    def _context_summary(pack: ContextPack, prompt_hash: str) -> str:
        policy = {
            "allowed_tools": pack.policy.get("allowed_tools"),
            "forbidden_actions": pack.policy.get("forbidden_actions"),
            "mode": pack.policy.get("mode"),
            "workspace_scope": pack.policy.get("workspace_scope"),
        }
        return (
            "# Approved Builder Context\n\n"
            f"- Stage: `{pack.stage}`\n"
            f"- Context version: `{pack.context_version}`\n"
            f"- Frozen Builder Prompt SHA-256: `{prompt_hash}`\n"
            f"- Task: {pack.task}\n\n"
            "## Tool policy\n\n"
            f"```json\n{json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True)}\n```\n"
        )

    @staticmethod
    def _builder_prompt(
        frozen_prompt: str, *, task: str, stage: str, context_path: str
    ) -> str:
        if stage == "development_frontend":
            stage_instructions = (
                f"先读取 `{context_path}/` 下全部已批准材料和 `CONTEXT.md`。"
                "本阶段只实现当前项目自身前端，不修改产品工厂平台前端。"
                "使用冻结的 Next.js 16.3.1、React 19.2.8、Tailwind 4.3.3，连接当前工作区"
                "已核验的真实 FastAPI API；不得用 mock 数据放行。严格实现已批准的 User Flow、"
                "PRD 与 API Contract，完成 lint、typecheck、测试和 production build。"
            )
        else:
            stage_instructions = (
                f"先读取 `{context_path}/` 下全部已批准技术材料和 `CONTEXT.md`。"
                "本阶段只完成后端，不开发前端。为当前项目创建可独立运行的 "
                "FastAPI/PostgreSQL/Alembic 后端，完整实现已批准 API Contract，"
                "运行真实单元和集成测试。"
            )
        return (
            f"{frozen_prompt}\n\n"
            "# 本次已批准执行上下文\n\n"
            f"任务：{task}\n\n"
            "只读取当前项目工作区。"
            f"{stage_instructions}"
            "不得使用 mock 冒充数据库、模型或验收，不得 push、部署、删除工作区或读取密钥。\n\n"
            "权威架构澄清：DeepSeek Adapter 负责业务模型调用，LangGraph 负责 Agent Run 编排，"
            "Codex CLI Adapter 只负责本次代码实现。Technical Adaptation 中“业务模型调用经 "
            "Codex CLI Adapter 执行”的句子是已记录的文档表述问题，不得按该句实现。\n\n"
            "完成后输出严格符合 Builder JSON Schema 的 JSON；只报告实际运行结果，不输出隐藏思维链。"
        )

    @staticmethod
    def _write_exact(path: Path, content: str) -> None:
        data = content.encode("utf-8")
        if path.exists():
            if not path.is_file() or path.read_bytes() != data:
                raise BuilderRuntimeError(
                    "CONTEXT_MATERIAL_CONFLICT", "项目工作区已有不同的 Context 材料。"
                )
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def _persist_execution(
        self,
        *,
        run_id: str,
        task_id: str,
        project_id: str,
        tool_step_id: str,
        tool_id: str,
        execution: CodexCliExecution,
    ) -> dict[str, Any]:
        output: BuilderOutput | None = None
        output_error: str | None = None
        if execution.final_message:
            try:
                strict_output = BuilderCodexOutput.model_validate_json(execution.final_message)
                output = BuilderOutput.model_validate(strict_output.model_dump())
            except ValidationError:
                output_error = "BUILDER_OUTPUT_INVALID"
        else:
            output_error = "BUILDER_OUTPUT_MISSING"
        succeeded = execution.succeeded and output is not None
        error_code = execution.error or output_error
        result_ref = (
            f"codex-result://{execution.stdout_hash}?exit_code="
            f"{execution.exit_code if execution.exit_code is not None else 'none'}"
            f"&stderr={execution.stderr_hash}&events={execution.event_count}"
            f"&duration_ms={execution.duration_ms}"
        )
        with self.session_factory.begin() as session:
            run = session.get(AgentRun, run_id)
            task = session.get(AgentTask, task_id)
            tool_step = session.get(RunStep, tool_step_id)
            tool = session.get(ToolRun, tool_id)
            if run is None or task is None or tool_step is None or tool is None:
                raise BuilderRuntimeError("RUN_NOT_FOUND", "Builder 执行记录在完成阶段丢失。")
            tool_step.state = "completed" if succeeded else "failed"
            tool_step.output_ref = result_ref
            tool_step.external_effect_confirmed = True
            tool.state = tool_step.state
            tool.result_ref = result_ref
            manifest_ref = f"workspace-manifest://{execution.workspace_manifest.digest}"
            self._add_step(
                session,
                run=run,
                step_type="workspace_manifest",
                state="completed" if not execution.workspace_manifest.violations else "failed",
                input_hash=execution.workspace_manifest.digest,
                output_ref=manifest_ref,
                idempotency_key=f"workspace-manifest:{run.id}",
                external_effect_confirmed=True,
            )
            if output is not None:
                output_hash = hashlib.sha256(
                    output.model_dump_json().encode("utf-8")
                ).hexdigest()
                self._add_step(
                    session,
                    run=run,
                    step_type="builder_output",
                    state="completed",
                    input_hash=output_hash,
                    output_ref=f"builder-output://{output_hash}",
                    external_effect_confirmed=True,
                )
            run.state = "succeeded" if succeeded else "failed"
            run.turns_used = 1
            run.completed_at = datetime.now(UTC)
            task.state = "completed" if succeeded else "failed"
            self._append_event(
                session,
                project_id,
                "tool_run.completed" if succeeded else "tool_run.failed",
                {
                    "tool_run_id": tool.id,
                    "run_id": run.id,
                    "task_id": task.id,
                    "tool_id": "codex_cli",
                    "state": tool.state,
                    "exit_code": execution.exit_code,
                    "stdout_hash": execution.stdout_hash,
                    "stderr_hash": execution.stderr_hash,
                    "workspace_manifest_hash": execution.workspace_manifest.digest,
                    "workspace_file_count": execution.workspace_manifest.file_count,
                    "policy_violations": list(execution.workspace_manifest.violations),
                    "error_code": error_code,
                },
            )
            self._append_event(
                session,
                project_id,
                "run.completed" if succeeded else "run.failed",
                {
                    "run_id": run.id,
                    "task_id": task.id,
                    "state": run.state,
                    "error_code": error_code,
                },
            )
            result = self._read_result(session, run, idempotent=False)
            result.update(
                {
                    "exit_code": execution.exit_code,
                    "workspace_manifest_hash": execution.workspace_manifest.digest,
                    "workspace_file_count": execution.workspace_manifest.file_count,
                    "policy_violations": list(execution.workspace_manifest.violations),
                    "output": output.model_dump(mode="json") if output else None,
                    "error_code": error_code,
                }
            )
            return result

    def _persist_failure(
        self,
        *,
        run_id: str,
        task_id: str,
        project_id: str,
        error: BuilderRuntimeError,
    ) -> None:
        with self.session_factory.begin() as session:
            run = session.get(AgentRun, run_id)
            task = session.get(AgentTask, task_id)
            if run is None or task is None:
                return
            run.state = "failed"
            run.completed_at = datetime.now(UTC)
            task.state = "failed"
            running_steps = list(
                session.scalars(
                    select(RunStep).where(
                        RunStep.run_id == run.id,
                        RunStep.state.in_(["started", "running"]),
                    )
                )
            )
            for step in running_steps:
                step.state = "failed"
            running_tools = list(
                session.scalars(
                    select(ToolRun).where(
                        ToolRun.run_id == run.id,
                        ToolRun.state.in_(["started", "running"]),
                    )
                )
            )
            for tool in running_tools:
                tool.state = "failed"
            self._append_event(
                session,
                project_id,
                "run.failed",
                {
                    "run_id": run.id,
                    "task_id": task.id,
                    "state": "failed",
                    "error_code": error.code,
                },
            )

    @staticmethod
    def _request_hash(**payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _advisory_lock(session: Session, key: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": key},
        )

    @staticmethod
    def _add_step(
        session: Session,
        *,
        run: AgentRun,
        step_type: str,
        state: str,
        input_hash: str,
        output_ref: str | None = None,
        idempotency_key: str | None = None,
        external_effect_confirmed: bool = False,
    ) -> RunStep:
        current_index = session.scalar(
            select(func.max(RunStep.step_index)).where(RunStep.run_id == run.id)
        )
        next_index = 0 if current_index is None else current_index + 1
        step = RunStep(
            run_id=run.id,
            step_index=next_index,
            step_type=step_type,
            state=state,
            input_hash=input_hash,
            output_ref=output_ref,
            idempotency_key=idempotency_key,
            external_effect_confirmed=external_effect_confirmed,
        )
        session.add(step)
        session.flush()
        return step

    @staticmethod
    def _append_event(
        session: Session, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"project:{project_id}"},
        )
        sequence = (
            session.scalar(select(func.max(Event.sequence)).where(Event.project_id == project_id))
            or 0
        ) + 1
        event = Event(
            project_id=project_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
        )
        session.add(event)
        session.flush()

    @staticmethod
    def _read_result(session: Session, run: AgentRun, *, idempotent: bool) -> dict[str, Any]:
        task = session.get(AgentTask, run.task_id)
        if task is None:
            raise BuilderRuntimeError("RUN_NOT_FOUND", "Builder Task 不存在。")
        manifest = session.scalar(
            select(RunStep)
            .where(RunStep.run_id == run.id, RunStep.step_type == "workspace_manifest")
            .order_by(RunStep.step_index.desc())
        )
        tool = session.scalar(
            select(ToolRun).where(ToolRun.run_id == run.id, ToolRun.tool_name == "codex_cli")
        )
        return {
            "run_id": run.id,
            "task_id": task.id,
            "state": run.state,
            "context_version": task.context_version,
            "tool_run_id": tool.id if tool else None,
            "workspace_manifest_hash": (
                manifest.input_hash if manifest and manifest.output_ref else None
            ),
            "idempotent": idempotent,
        }
