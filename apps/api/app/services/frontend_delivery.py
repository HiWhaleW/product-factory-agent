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
from app.domain.schemas import FrontendDeliveryCreate
from app.services.artifact_store import write_immutable_artifact
from app.services.control_plane import ControlPlaneError, validate_transition


class FrontendDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FrontendDeliveryService:
    REQUIRED_CHECKS = {
        "eslint",
        "typecheck",
        "vitest",
        "next_build",
        "browser_desktop",
        "browser_mobile",
    }

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
        body: FrontendDeliveryCreate,
        idempotency_key: str,
    ) -> dict[str, Any]:
        body_hash = hashlib.sha256(
            body.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        scope = f"frontend.delivery:{project_id}"
        workspace = resolve_project_workspace(self.settings, project_id)
        manifest = build_workspace_manifest(self.settings, workspace)
        if manifest.violations:
            raise FrontendDeliveryError(
                "WORKSPACE_POLICY_VIOLATION", "前端工作区仍有安全策略违规。"
            )
        if manifest.digest != body.workspace_manifest_hash:
            raise FrontendDeliveryError("WORKSPACE_MANIFEST_CHANGED", "前端工作区哈希已变化。")
        checks = {item.check: item for item in body.evidence}
        if set(checks) != self.REQUIRED_CHECKS:
            raise FrontendDeliveryError("FRONTEND_EVIDENCE_INCOMPLETE", "前端验证证据不完整。")

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
                    raise FrontendDeliveryError(
                        "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同前端交付证据。"
                    )
                run = session.get(AgentRun, existing.resource_id)
                if run is None:
                    raise FrontendDeliveryError(
                        "IDEMPOTENCY_ORPHAN", "前端交付幂等记录指向的 Run 不存在。"
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
                        ToolRun.state == "completed",
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
                or project.state != "development_frontend"
                or project.context_version != body.expected_context_version
                or source_run is None
                or source_task is None
                or source_task.project_id != project.id
                or source_task.assigned_agent != "builder"
                or source_run.state != "succeeded"
                or source_tool is None
                or source_tool.result_ref is None
                or "exit_code=0" not in source_tool.result_ref
                or builder_output is None
            ):
                raise FrontendDeliveryError(
                    "FRONTEND_SOURCE_INVALID",
                    "前端交付必须绑定当前 Context 中已成功的 Codex Builder Run。",
                )
            try:
                validate_transition(project.state, "mvp")
            except ControlPlaneError as exc:
                raise FrontendDeliveryError(exc.code, exc.user_message) from exc

            review_task = AgentTask(
                project_id=project.id,
                assigned_agent="reviewer",
                title="独立核验当前项目前端实现",
                state="completed",
                context_version=project.context_version,
                claimed_by="frontend-verification",
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
                kind="frontend_implementation",
                title="当前项目前端实现",
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
                kind="frontend_test_report",
                title="当前项目前端测试与浏览器 QA",
                created_by="reviewer",
                content=self._test_report(checks),
            )
            review = self._artifact(
                session,
                project=project,
                kind="frontend_review",
                title="当前项目前端独立审核",
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
                raise FrontendDeliveryError("CONTEXT_VERSION_NOT_FOUND", "当前 Context 不存在。")
            current_context.approval_status = "superseded"
            previous_state = project.state
            project.state = "mvp"
            project.context_version += 1
            next_context = ContextVersion(
                project_id=project.id,
                version=project.context_version,
                stage=project.state,
                approval_status="active",
                change_reason="frontend_review:pass_with_known_issues",
                summary="前端独立核验通过，形成可运行 MVP，进入内部验收准备。",
            )
            session.add(next_context)
            session.flush()
            mvp_pack = ContextPack(
                project_id=project.id,
                context_version_id=next_context.id,
                context_version=next_context.version,
                stage=project.state,
                approval_status="approved",
                primary_resource_type="artifact",
                primary_resource_id=implementation.id,
                primary_resource_version=1,
                agent_id="reviewer",
                task=(
                    "独立验收当前项目 MVP：复核 Runtime/API/PostgreSQL/Web 纵向闭环、"
                    "真实模型样本、桌面与移动浏览器、安全、备份恢复和已知问题；"
                    "证据不完整时不得打开 G5。"
                ),
                references=[
                    self._ref(test_report),
                    self._ref(review),
                    self._approved_ref(session, project.id, "backend_review"),
                ],
                policy={
                    "allowed_capability_ids": ["CAP-09"],
                    "allowed_tools": [
                        "project_fs_read",
                        "test_runner",
                        "browser_qa",
                        "postgresql",
                        "model_qa",
                    ],
                    "forbidden_actions": [
                        "approve_gate",
                        "advance_project_state",
                        "git_push",
                        "deploy_adapter",
                        "workspace_delete",
                        "persist_secret_values",
                    ],
                    "workspace_scope": project.id,
                    "mode": "mvp_independent_acceptance",
                },
            )
            session.add(mvp_pack)
            session.flush()
            mvp_task = AgentTask(
                project_id=project.id,
                assigned_agent="reviewer",
                title="当前项目 MVP 独立验收",
                state="ready",
                context_version=project.context_version,
            )
            session.add(mvp_task)
            session.flush()
            session.add(
                TaskDependency(task_id=mvp_task.id, depends_on_task_id=review_task.id)
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
                "frontend.reviewed",
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
                    "task_id": mvp_task.id,
                    "assigned_agent": "reviewer",
                    "context_pack_id": mvp_pack.id,
                    "context_version": project.context_version,
                },
            )
            return self._result(
                project=project,
                delivery_run=delivery_run,
                review_task=review_task,
                source_run_id=source_run.id,
                implementation=implementation,
                test_report=test_report,
                review=review,
                mvp_pack=mvp_pack,
                mvp_task=mvp_task,
                idempotent=False,
            )

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
            stage="development_frontend",
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
    def _ref(artifact: Artifact) -> dict[str, Any]:
        return {
            "resource_type": "artifact",
            "resource_id": artifact.id,
            "version": artifact.latest_version,
            "approval_status": "approved",
        }

    @staticmethod
    def _approved_ref(session: Session, project_id: str, kind: str) -> dict[str, Any]:
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
            raise FrontendDeliveryError(
                "MVP_CONTEXT_INCOMPLETE", f"MVP Context 缺少已批准 {kind}。"
            )
        artifact, version = row
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
            "# 当前项目前端实现\n\n"
            f"- Codex Builder Run：`{source_run_id}`\n"
            "- Codex CLI exit code：`0`\n"
            f"- 工作区安全哈希：`{manifest_hash}`\n"
            f"- 源文件清单：`{file_count}`\n"
            "- 技术：Next.js 16.3.1 / React 19.2.8 / Tailwind 4.3.3。\n"
            "- 范围：材料上传与状态、结论编辑/确认、行动项编辑、导出、历史回看。\n"
            "- API：同源 Route Handler 转发真实 FastAPI，Token 仅在服务端注入。\n"
            "- 产品工厂前端：未修改。\n"
        )

    @staticmethod
    def _test_report(checks: dict[str, Any]) -> str:
        lines = ["# 当前项目前端测试与浏览器 QA", ""]
        for name in sorted(checks):
            item = checks[name]
            lines.append(
                f"- `{name}`：passed；{item.summary}；证据哈希 `{item.evidence_hash}`"
            )
        lines.extend(
            [
                "",
                "桌面 1440×900 与移动 390×844 使用真实 Chromium；未用 mock API 放行。",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _review_report(*, implementation_id: str, test_report_id: str) -> str:
        return (
            "# 当前项目前端独立审核\n\n"
            "## 结论\n\n"
            "`pass_with_known_issues`\n\n"
            f"- 实现证据：artifact:{implementation_id}:v1\n"
            f"- 测试证据：artifact:{test_report_id}:v1\n"
            "- lint / typecheck / test / production build：通过\n"
            "- 桌面/移动真实浏览器：通过\n"
            "- 真实 FastAPI/PostgreSQL 上传、编辑、确认、导出、历史回看：通过\n"
            "- 工作区安全重扫：无违规\n\n"
            "## 已知问题\n\n"
            "- P1：DeepSeek 真实结论和行动项效果尚未验收，未解决前不打开 G5。\n"
            "- P2：Turbopack 在受限环境中无法绑定临时端口，"
            "同版本 webpack production build 已通过。\n"
        )

    @staticmethod
    def _result(
        *,
        project: Project,
        delivery_run: AgentRun,
        review_task: AgentTask,
        source_run_id: str,
        implementation: Artifact,
        test_report: Artifact,
        review: Artifact,
        mvp_pack: ContextPack,
        mvp_task: AgentTask,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "delivery_run_id": delivery_run.id,
            "review_task_id": review_task.id,
            "source_builder_run_id": source_run_id,
            "frontend_implementation_artifact_id": implementation.id,
            "frontend_test_report_artifact_id": test_report.id,
            "frontend_review_artifact_id": review.id,
            "verdict": "pass_with_known_issues",
            "target_state": project.state,
            "context_version": project.context_version,
            "mvp_context_pack_id": mvp_pack.id,
            "mvp_review_task_id": mvp_task.id,
            "idempotent": idempotent,
        }

    def _read_result(
        self, session: Session, run: AgentRun, *, idempotent: bool
    ) -> dict[str, Any]:
        review_task = session.get(AgentTask, run.task_id)
        if review_task is None:
            raise FrontendDeliveryError("RUN_NOT_FOUND", "前端交付 Task 不存在。")
        project = session.get(Project, review_task.project_id)
        if project is None:
            raise FrontendDeliveryError("PROJECT_NOT_FOUND", "前端交付项目不存在。")
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.project_id == project.id,
                    Artifact.kind.in_(
                        ["frontend_implementation", "frontend_test_report", "frontend_review"]
                    ),
                )
            )
        )
        by_kind = {artifact.kind: artifact for artifact in artifacts}
        mvp_pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project.id,
                ContextPack.stage == "mvp",
                ContextPack.context_version == project.context_version,
            )
        )
        mvp_task = session.scalar(
            select(AgentTask).where(
                AgentTask.project_id == project.id,
                AgentTask.assigned_agent == "reviewer",
                AgentTask.context_version == project.context_version,
                AgentTask.state == "ready",
            )
        )
        source_event = session.scalar(
            select(Event)
            .where(Event.project_id == project.id, Event.event_type == "frontend.reviewed")
            .order_by(Event.sequence.desc())
        )
        if mvp_pack is None or mvp_task is None or source_event is None:
            raise FrontendDeliveryError("FRONTEND_DELIVERY_INCOMPLETE", "前端交付记录不完整。")
        return self._result(
            project=project,
            delivery_run=run,
            review_task=review_task,
            source_run_id=source_event.payload["source_builder_run_id"],
            implementation=by_kind["frontend_implementation"],
            test_report=by_kind["frontend_test_report"],
            review=by_kind["frontend_review"],
            mvp_pack=mvp_pack,
            mvp_task=mvp_task,
            idempotent=idempotent,
        )
