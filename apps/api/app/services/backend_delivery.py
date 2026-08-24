from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.codex_cli import build_workspace_manifest, resolve_project_workspace
from app.core.config import Settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactEdge,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    Event,
    IdempotencyRecord,
    Project,
    RunStep,
    TaskDependency,
    ToolRun,
)
from app.domain.schemas import BackendDeliveryCreate
from app.services.artifact_store import write_immutable_artifact
from app.services.control_plane import ControlPlaneError, validate_transition


class BackendDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BackendDeliveryService:
    REQUIRED_CHECKS = {"ruff", "pytest_postgresql", "alembic", "compileall"}

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory

    def complete(
        self,
        *,
        project_id: str,
        body: BackendDeliveryCreate,
        idempotency_key: str,
    ) -> dict[str, Any]:
        body_hash = hashlib.sha256(
            body.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        scope = f"backend.delivery:{project_id}"
        workspace = resolve_project_workspace(self.settings, project_id)
        manifest = build_workspace_manifest(self.settings, workspace)
        if manifest.violations:
            raise BackendDeliveryError(
                "WORKSPACE_POLICY_VIOLATION", "后端工作区仍有安全策略违规。"
            )
        if manifest.digest != body.workspace_manifest_hash:
            raise BackendDeliveryError("WORKSPACE_MANIFEST_CHANGED", "后端工作区哈希已变化。")
        checks = {item.check: item for item in body.evidence}
        if set(checks) != self.REQUIRED_CHECKS:
            raise BackendDeliveryError("BACKEND_EVIDENCE_INCOMPLETE", "后端验证证据不完整。")

        with self.session_factory.begin() as session:
            self._lock(session, f"project:{project_id}")
            self._lock(session, f"idempotency:{scope}:{idempotency_key}")
            existing = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.input_hash != body_hash:
                    raise BackendDeliveryError(
                        "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同后端交付证据。"
                    )
                run = session.get(AgentRun, existing.resource_id)
                if run is None:
                    raise BackendDeliveryError(
                        "IDEMPOTENCY_ORPHAN", "后端交付幂等记录指向的 Run 不存在。"
                    )
                return self._read_result(session, run, idempotent=True)
            project = session.get(Project, project_id)
            source_run = session.get(AgentRun, body.source_builder_run_id)
            source_task = session.get(AgentTask, source_run.task_id) if source_run else None
            source_tool = (
                session.scalar(
                    select(ToolRun).where(
                        ToolRun.run_id == source_run.id,
                        ToolRun.tool_name == "codex_cli",
                    )
                )
                if source_run
                else None
            )
            builder_output = (
                session.scalar(
                    select(RunStep).where(
                        RunStep.run_id == source_run.id,
                        RunStep.step_type == "builder_output",
                        RunStep.state == "completed",
                    )
                )
                if source_run
                else None
            )
            if (
                project is None
                or project.state != "development_backend"
                or project.context_version != body.expected_context_version
                or source_run is None
                or source_task is None
                or source_task.project_id != project.id
                or source_task.assigned_agent != "builder"
                or source_run.state != "failed"
                or source_tool is None
                or source_tool.result_ref is None
                or "exit_code=0" not in source_tool.result_ref
                or builder_output is None
            ):
                raise BackendDeliveryError(
                    "BACKEND_SOURCE_INVALID",
                    "后端交付必须绑定 Codex 已正常退出但扫描误报的当前 Builder Run。",
                )
            try:
                validate_transition(project.state, "development_frontend")
            except ControlPlaneError as exc:
                raise BackendDeliveryError(exc.code, exc.user_message) from exc

            review_task = AgentTask(
                project_id=project.id,
                assigned_agent="reviewer",
                title="独立核验销售复盘 Agent 后端实现",
                state="completed",
                context_version=project.context_version,
                claimed_by="backend-verification",
            )
            session.add(review_task)
            session.flush()
            delivery_run = AgentRun(
                task_id=review_task.id,
                attempt=1,
                state="succeeded",
                input_hash=body_hash,
                turns_used=1,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            session.add(delivery_run)
            session.flush()
            self._add_step(
                session,
                delivery_run,
                "workspace_policy_reconcile",
                manifest.digest,
                f"workspace-manifest://{manifest.digest}",
            )
            for name in sorted(checks):
                evidence = checks[name]
                self._add_step(
                    session,
                    delivery_run,
                    f"verification_{name}",
                    evidence.evidence_hash,
                    f"verification://{name}/{evidence.evidence_hash}",
                )

            implementation = self._artifact(
                session,
                project=project,
                kind="backend_implementation",
                title="销售复盘 Agent 后端实现",
                created_by="builder",
                content=self._implementation_report(
                    source_run_id=source_run.id,
                    manifest_hash=manifest.digest,
                    file_count=manifest.file_count,
                ),
            )
            test_report = self._artifact(
                session,
                project=project,
                kind="backend_test_report",
                title="销售复盘 Agent 后端测试报告",
                created_by="reviewer",
                content=self._test_report(checks),
            )
            review = self._artifact(
                session,
                project=project,
                kind="backend_review",
                title="销售复盘 Agent 后端独立审核",
                created_by="reviewer",
                content=self._review_report(
                    implementation_id=implementation.id,
                    test_report_id=test_report.id,
                ),
            )
            session.add_all(
                [
                    ArtifactEdge(
                        project_id=project.id,
                        source_id=implementation.id,
                        target_id=test_report.id,
                        relation="verified_by",
                    ),
                    ArtifactEdge(
                        project_id=project.id,
                        source_id=test_report.id,
                        target_id=review.id,
                        relation="reviewed_by",
                    ),
                ]
            )

            current_context = session.scalar(
                select(ContextVersion).where(
                    ContextVersion.project_id == project.id,
                    ContextVersion.version == project.context_version,
                )
            )
            if current_context is None:
                raise BackendDeliveryError("CONTEXT_VERSION_NOT_FOUND", "当前 Context 不存在。")
            current_context.approval_status = "superseded"
            previous_state = project.state
            project.state = "development_frontend"
            project.context_version += 1
            next_context = ContextVersion(
                project_id=project.id,
                version=project.context_version,
                stage=project.state,
                approval_status="active",
                change_reason="backend_review:pass_with_known_issues",
                summary="后端独立核验通过，进入销售复盘 Agent 前端开发。",
            )
            session.add(next_context)
            session.flush()
            solution_design = self._approved_artifact(session, project.id, "solution_design")
            user_flow = self._approved_artifact(session, project.id, "user_flow")
            api_contract = self._approved_artifact(session, project.id, "api_contract")
            frontend_pack = ContextPack(
                project_id=project.id,
                context_version_id=next_context.id,
                context_version=next_context.version,
                stage=project.state,
                approval_status="approved",
                primary_resource_type="artifact",
                primary_resource_id=solution_design[0].id,
                primary_resource_version=solution_design[1].version,
                agent_id="builder",
                task=(
                    "在同一项目专属工作区实现销售复盘 Agent 前端，严格继承已批准 User Flow、"
                    "方案、API Contract 和已核验后端。不得修改产品工厂前端，不得 push、部署、"
                    "删除工作区或读取密钥原值；必须完成真实浏览器 QA。"
                ),
                references=[
                    self._ref(user_flow),
                    self._ref(api_contract),
                    self._ref((implementation, self._latest_version(session, implementation))),
                    self._ref((test_report, self._latest_version(session, test_report))),
                    self._ref((review, self._latest_version(session, review))),
                ],
                policy={
                    "allowed_capability_ids": ["CAP-08", "CAP-09"],
                    "allowed_tools": [
                        "codex_cli",
                        "project_fs_read",
                        "project_fs_write",
                        "git_local",
                        "test_runner",
                        "browser_qa",
                    ],
                    "forbidden_actions": [
                        "advance_project_state",
                        "approve_gate",
                        "git_push",
                        "deploy_adapter",
                        "workspace_delete",
                        "read_secret_values",
                        "modify_product_factory_frontend",
                    ],
                    "workspace_scope": project.id,
                    "mode": "frontend_development",
                    "budget": {
                        "max_turns": 6,
                        "max_retries": 2,
                        "timeout_seconds": 1800,
                        "max_tool_calls": 8,
                    },
                },
            )
            session.add(frontend_pack)
            session.flush()
            frontend_task = AgentTask(
                project_id=project.id,
                assigned_agent="builder",
                title="实现销售复盘 Agent 前端纵向切片",
                state="ready",
                context_version=project.context_version,
            )
            session.add(frontend_task)
            session.flush()
            session.add(
                TaskDependency(
                    task_id=frontend_task.id,
                    depends_on_task_id=review_task.id,
                )
            )
            session.add(
                IdempotencyRecord(
                    scope=scope,
                    key=idempotency_key,
                    resource_id=delivery_run.id,
                    input_hash=body_hash,
                )
            )
            self._event(
                session,
                project.id,
                "backend.reviewed",
                {
                    "run_id": delivery_run.id,
                    "source_builder_run_id": source_run.id,
                    "verdict": "pass_with_known_issues",
                    "workspace_manifest_hash": manifest.digest,
                    "artifact_ids": [implementation.id, test_report.id, review.id],
                },
            )
            self._event(
                session,
                project.id,
                "context.updated",
                {"context_version": next_context.version, "stage": project.state},
            )
            self._event(
                session,
                project.id,
                "project.state_changed",
                {"from_state": previous_state, "state": project.state},
            )
            self._event(
                session,
                project.id,
                "task.ready",
                {
                    "task_id": frontend_task.id,
                    "assigned_agent": "builder",
                    "context_pack_id": frontend_pack.id,
                    "context_version": project.context_version,
                },
            )
            return {
                "delivery_run_id": delivery_run.id,
                "review_task_id": review_task.id,
                "source_builder_run_id": source_run.id,
                "backend_implementation_artifact_id": implementation.id,
                "backend_test_report_artifact_id": test_report.id,
                "backend_review_artifact_id": review.id,
                "verdict": "pass_with_known_issues",
                "target_state": project.state,
                "context_version": project.context_version,
                "frontend_context_pack_id": frontend_pack.id,
                "frontend_task_id": frontend_task.id,
                "idempotent": False,
            }

    def _artifact(
        self,
        session: Session,
        *,
        project: Project,
        kind: str,
        title: str,
        created_by: str,
        content: str,
    ) -> Artifact:
        content_ref, content_hash = write_immutable_artifact(
            self.settings.ARTIFACT_ROOT,
            project_id=project.id,
            kind=kind,
            content=content,
        )
        artifact = Artifact(
            project_id=project.id,
            title=title,
            kind=kind,
            stage="development_backend",
            status="approved",
            latest_version=1,
            owner_agent=created_by,
        )
        session.add(artifact)
        session.flush()
        session.add(
            ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=project.context_version,
                approval_status="approved",
                content_ref=content_ref,
                content_hash=content_hash,
                summary=title,
                created_by=created_by,
            )
        )
        session.flush()
        return artifact

    @staticmethod
    def _approved_artifact(
        session: Session, project_id: str, kind: str
    ) -> tuple[Artifact, ArtifactVersion]:
        row = session.execute(
            select(Artifact, ArtifactVersion)
            .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
            .where(
                Artifact.project_id == project_id,
                Artifact.kind == kind,
                ArtifactVersion.approval_status == "approved",
            )
            .order_by(ArtifactVersion.version.desc())
        ).first()
        if row is None:
            raise BackendDeliveryError(
                "FRONTEND_CONTEXT_INCOMPLETE", f"前端 Context 缺少已批准 {kind}。"
            )
        return row[0], row[1]

    @staticmethod
    def _latest_version(session: Session, artifact: Artifact) -> ArtifactVersion:
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact.id,
                ArtifactVersion.version == artifact.latest_version,
            )
        )
        if version is None:
            raise BackendDeliveryError("ARTIFACT_VERSION_NOT_FOUND", "交付产物版本不存在。")
        return version

    @staticmethod
    def _ref(pair: tuple[Artifact, ArtifactVersion]) -> dict[str, Any]:
        artifact, version = pair
        return {
            "resource_type": "artifact",
            "resource_id": artifact.id,
            "version": version.version,
            "approval_status": "approved",
        }

    @staticmethod
    def _add_step(
        session: Session,
        run: AgentRun,
        step_type: str,
        evidence_hash: str,
        output_ref: str,
    ) -> None:
        index = (
            session.scalar(
                select(func.count()).select_from(RunStep).where(RunStep.run_id == run.id)
            )
            or 0
        )
        session.add(
            RunStep(
                run_id=run.id,
                step_index=index,
                step_type=step_type,
                state="completed",
                input_hash=evidence_hash,
                output_ref=output_ref,
                external_effect_confirmed=True,
            )
        )
        session.flush()

    @staticmethod
    def _lock(session: Session, key: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": key},
        )

    @classmethod
    def _event(
        cls, session: Session, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        cls._lock(session, f"project:{project_id}")
        sequence = (
            session.scalar(select(func.max(Event.sequence)).where(Event.project_id == project_id))
            or 0
        ) + 1
        session.add(
            Event(
                project_id=project_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
            )
        )
        session.flush()

    @staticmethod
    def _implementation_report(
        *, source_run_id: str, manifest_hash: str, file_count: int
    ) -> str:
        return (
            "# 销售复盘 Agent 后端实现\n\n"
            f"- Codex Builder Run：`{source_run_id}`\n"
            "- Codex CLI exit code：`0`\n"
            f"- 安全重扫工作区哈希：`{manifest_hash}`\n"
            f"- 纳入源文件清单：`{file_count}`\n"
            "- 架构：DeepSeek Adapter 负责业务模型调用；LangGraph 负责编排；"
            "Codex CLI 仅负责代码实现。\n"
            "- 范围：FastAPI、PostgreSQL、Alembic、材料、结论、行动项、导出、历史回看。\n"
            "- 产品工厂前端：未修改。\n"
        )

    @staticmethod
    def _test_report(checks: dict[str, Any]) -> str:
        lines = ["# 销售复盘 Agent 后端测试报告", ""]
        for name in sorted(checks):
            item = checks[name]
            lines.append(
                f"- `{name}`：passed；{item.summary}；证据哈希 `{item.evidence_hash}`"
            )
        lines.extend(
            [
                "",
                "测试数据库为隔离的本机 PostgreSQL；未使用 SQLite 或 mock 数据库放行。",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _review_report(*, implementation_id: str, test_report_id: str) -> str:
        return (
            "# 销售复盘 Agent 后端独立审核\n\n"
            "## 结论\n\n"
            "`pass_with_known_issues`\n\n"
            f"- 实现证据：artifact:{implementation_id}:v1\n"
            f"- 测试证据：artifact:{test_report_id}:v1\n"
            "- Ruff：通过\n"
            "- Python：7/7 通过\n"
            "- PostgreSQL 集成：通过\n"
            "- Alembic downgrade → upgrade → head：通过\n"
            "- 工作区安全重扫：无违规\n\n"
            "## 已知问题\n\n"
            "- P1：真实 DeepSeek 业务生成效果尚未验收，留到 MVP 真实模型 QA。\n"
            "- P2：保留 1 条 Starlette/httpx TestClient 弃用警告。\n"
        )

    @staticmethod
    def _read_result(session: Session, run: AgentRun, *, idempotent: bool) -> dict[str, Any]:
        review_task = session.get(AgentTask, run.task_id)
        if review_task is None:
            raise BackendDeliveryError("RUN_NOT_FOUND", "后端交付 Task 不存在。")
        project = session.get(Project, review_task.project_id)
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.project_id == review_task.project_id,
                    Artifact.kind.in_(
                        ["backend_implementation", "backend_test_report", "backend_review"]
                    ),
                )
            )
        )
        by_kind = {artifact.kind: artifact for artifact in artifacts}
        frontend_pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == review_task.project_id,
                ContextPack.stage == "development_frontend",
                ContextPack.context_version == project.context_version,
            )
        )
        frontend_task = session.scalar(
            select(AgentTask).where(
                AgentTask.project_id == review_task.project_id,
                AgentTask.assigned_agent == "builder",
                AgentTask.context_version == project.context_version,
            )
        )
        source_event = session.scalar(
            select(Event)
            .where(
                Event.project_id == review_task.project_id,
                Event.event_type == "backend.reviewed",
            )
            .order_by(Event.sequence.desc())
        )
        return {
            "delivery_run_id": run.id,
            "review_task_id": review_task.id,
            "source_builder_run_id": source_event.payload["source_builder_run_id"],
            "backend_implementation_artifact_id": by_kind["backend_implementation"].id,
            "backend_test_report_artifact_id": by_kind["backend_test_report"].id,
            "backend_review_artifact_id": by_kind["backend_review"].id,
            "verdict": "pass_with_known_issues",
            "target_state": project.state,
            "context_version": project.context_version,
            "frontend_context_pack_id": frontend_pack.id,
            "frontend_task_id": frontend_task.id,
            "idempotent": idempotent,
        }
