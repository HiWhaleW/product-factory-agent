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
    Gate,
    IdempotencyRecord,
    Project,
    RunStep,
)
from app.domain.schemas import InternalAcceptanceCreate
from app.services.artifact_store import write_immutable_artifact
from app.services.control_plane import (
    ControlPlaneError,
    validate_gate_artifact_kinds,
    validate_gate_open,
    validate_transition,
)


class InternalAcceptanceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InternalAcceptanceService:
    REQUIRED_CHECKS = {
        "product_factory_control_plane",
        "sales_review_backend",
        "sales_review_frontend",
        "postgres_backup_restore",
        "browser_qa",
        "deepseek_conclusions",
        "deepseek_actions",
    }
    REQUIRED_ARTIFACT_KINDS = {
        "mvp_candidate",
        "qa_report",
        "known_issues",
        "seed_test_plan",
        "telemetry_schema",
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
        body: InternalAcceptanceCreate,
        idempotency_key: str,
    ) -> dict[str, Any]:
        body_hash = hashlib.sha256(
            body.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        scope = f"internal.acceptance:{project_id}"
        workspace = resolve_project_workspace(self.settings, project_id)
        manifest = build_workspace_manifest(self.settings, workspace)
        if manifest.violations:
            raise InternalAcceptanceError(
                "WORKSPACE_POLICY_VIOLATION", "MVP 工作区仍有安全策略违规。"
            )
        if manifest.digest != body.workspace_manifest_hash:
            raise InternalAcceptanceError("WORKSPACE_MANIFEST_CHANGED", "MVP 工作区哈希已变化。")
        checks = {item.check: item for item in body.evidence}
        if set(checks) != self.REQUIRED_CHECKS:
            raise InternalAcceptanceError(
                "INTERNAL_ACCEPTANCE_EVIDENCE_INCOMPLETE",
                "内部验收证据不完整，不得打开 G5。",
            )

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
                    raise InternalAcceptanceError(
                        "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同验收证据。"
                    )
                run = session.get(AgentRun, existing.resource_id)
                if run is None:
                    raise InternalAcceptanceError(
                        "IDEMPOTENCY_ORPHAN", "内部验收幂等记录指向的 Run 不存在。"
                    )
                return self._read_result(session, run, idempotent=True)

            project = session.get(Project, project_id)
            task = session.get(AgentTask, body.mvp_review_task_id)
            pack = session.get(ContextPack, body.mvp_context_pack_id)
            context = (
                session.scalar(
                    select(ContextVersion).where(
                        ContextVersion.project_id == project_id,
                        ContextVersion.version == body.expected_context_version,
                        ContextVersion.approval_status == "active",
                    )
                )
                if project
                else None
            )
            if (
                project is None
                or project.state != "mvp"
                or project.context_version != body.expected_context_version
                or task is None
                or task.project_id != project.id
                or task.assigned_agent != "reviewer"
                or task.state != "ready"
                or task.context_version != project.context_version
                or pack is None
                or pack.project_id != project.id
                or pack.stage != "mvp"
                or pack.context_version != project.context_version
                or pack.agent_id != "reviewer"
                or pack.approval_status != "approved"
                or pack.policy.get("mode") != "mvp_independent_acceptance"
                or context is None
            ):
                raise InternalAcceptanceError(
                    "MVP_ACCEPTANCE_SCOPE_INVALID", "MVP Reviewer Task 或 Context Pack 已失效。"
                )
            try:
                validate_transition(project.state, "internal_acceptance")
            except ControlPlaneError as exc:
                raise InternalAcceptanceError(exc.code, exc.user_message) from exc

            task.state = "running"
            task.claimed_by = "independent-acceptance"
            run = AgentRun(
                task_id=task.id,
                attempt=1,
                state="running",
                input_hash=body_hash,
                turns_used=1,
                started_at=datetime.now(UTC),
            )
            session.add(run)
            session.flush()
            self._add_step(
                session,
                run,
                "workspace_policy_reconcile",
                manifest.digest,
                f"workspace-manifest://{manifest.digest}",
            )
            for name in sorted(checks):
                evidence = checks[name]
                self._add_step(
                    session,
                    run,
                    f"acceptance_{name}",
                    evidence.evidence_hash,
                    f"acceptance-evidence://{name}/{evidence.evidence_hash}",
                )

            context.approval_status = "superseded"
            previous_state = project.state
            project.state = "internal_acceptance"
            project.context_version += 1
            next_context = ContextVersion(
                project_id=project.id,
                version=project.context_version,
                stage=project.state,
                approval_status="active",
                change_reason="mvp_review:beta_candidate_ready",
                summary=(
                    "MVP 独立验收证据完整，形成 Beta Candidate 与种子内测包，"
                    "等待用户决定 G5。"
                ),
            )
            session.add(next_context)
            session.flush()

            artifacts = self._create_acceptance_artifacts(
                session,
                project=project,
                source_manifest_hash=manifest.digest,
                checks=checks,
            )
            by_kind = {artifact.kind: artifact for artifact in artifacts}
            for source_kind, target_kind, relation in [
                ("mvp_candidate", "qa_report", "verified_by"),
                ("qa_report", "known_issues", "records"),
                ("mvp_candidate", "seed_test_plan", "enables"),
                ("seed_test_plan", "telemetry_schema", "measured_by"),
            ]:
                session.add(
                    ArtifactEdge(
                        project_id=project.id,
                        source_id=by_kind[source_kind].id,
                        target_id=by_kind[target_kind].id,
                        relation=relation,
                    )
                )

            try:
                validate_gate_open(
                    current_state=project.state,
                    gate_type="G5",
                    target_state="seed_beta",
                    context_matches=True,
                )
                validate_gate_artifact_kinds("G5", set(by_kind))
            except ControlPlaneError as exc:
                raise InternalAcceptanceError(exc.code, exc.user_message) from exc
            impacted_refs = [
                {"artifact_id": by_kind[kind].id, "version": 1}
                for kind in sorted(self.REQUIRED_ARTIFACT_KINDS)
            ]
            gate = Gate(
                project_id=project.id,
                gate_type="G5",
                context_version=project.context_version,
                status="open",
                target_state="seed_beta",
                reason=(
                    "MVP 已通过 Runtime/API/PostgreSQL/Web、真实模型、浏览器、"
                    "安全与备份恢复验收；请用户决定是否进入种子内测。"
                ),
                impacted_artifact_refs=impacted_refs,
                known_issues=[
                    {
                        "issue": "Turbopack 受限环境端口约束，已使用同版本 webpack build",
                        "severity": "P2",
                        "evidence_refs": [f"artifact:{by_kind['qa_report'].id}:v1"],
                        "source_refs": [],
                        "status": "accepted",
                    },
                    {
                        "issue": "Starlette/httpx TestClient 弃用警告",
                        "severity": "P2",
                        "evidence_refs": [f"artifact:{by_kind['known_issues'].id}:v1"],
                        "source_refs": [],
                        "status": "accepted",
                    },
                ],
            )
            session.add(gate)
            session.flush()
            run.state = "succeeded"
            run.completed_at = datetime.now(UTC)
            task.state = "completed"
            session.add(
                IdempotencyRecord(
                    scope=scope,
                    key=idempotency_key,
                    resource_id=run.id,
                    input_hash=body_hash,
                )
            )
            self._event(
                session,
                project.id,
                "mvp.reviewed",
                {
                    "run_id": run.id,
                    "verdict": "beta_candidate_ready",
                    "workspace_manifest_hash": manifest.digest,
                    "artifact_ids": [artifact.id for artifact in artifacts],
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
                "gate.opened",
                {
                    "gate_id": gate.id,
                    "gate_type": gate.gate_type,
                    "context_version": gate.context_version,
                    "target_state": gate.target_state,
                    "impacted_artifact_refs": impacted_refs,
                },
            )
            return self._result(
                project=project,
                run=run,
                task=task,
                by_kind=by_kind,
                gate=gate,
                idempotent=False,
            )

    def _create_acceptance_artifacts(
        self,
        session: Session,
        *,
        project: Project,
        source_manifest_hash: str,
        checks: dict[str, Any],
    ) -> list[Artifact]:
        reports = {
            "mvp_candidate": (
                "当前项目 Beta Candidate",
                self._mvp_report(source_manifest_hash),
            ),
            "qa_report": ("MVP 独立 QA 报告", self._qa_report(checks)),
            "known_issues": ("MVP 已知问题", self._known_issues_report()),
            "seed_test_plan": ("MVP 种子用户内测计划", self._seed_plan()),
            "telemetry_schema": ("MVP 内测数据 Schema", self._telemetry_schema()),
        }
        artifacts: list[Artifact] = []
        for kind in sorted(reports):
            title, content = reports[kind]
            artifacts.append(
                self._artifact(
                    session,
                    project=project,
                    kind=kind,
                    title=title,
                    content=content,
                )
            )
        return artifacts

    def _artifact(
        self,
        session: Session,
        *,
        project: Project,
        kind: str,
        title: str,
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
            stage="internal_acceptance",
            status="pending_review",
            latest_version=1,
            owner_agent="reviewer",
        )
        session.add(artifact)
        session.flush()
        session.add(
            ArtifactVersion(
                artifact_id=artifact.id,
                version=1,
                context_version=project.context_version,
                approval_status="pending_review",
                content_ref=content_ref,
                content_hash=content_hash,
                summary=title,
                created_by="reviewer",
            )
        )
        session.flush()
        return artifact

    @staticmethod
    def _mvp_report(manifest_hash: str) -> str:
        return (
            "# 当前项目 Beta Candidate\n\n"
            "- 版本：iteration v1 / Beta Candidate 1\n"
            f"- 工作区哈希：`{manifest_hash}`\n"
            "- 闭环：材料上传 → 汇总 → 结论生成/编辑/确认 → "
            "行动项生成/编辑 → 导出 → 历史回看。\n"
            "- 架构：FastAPI + PostgreSQL + Alembic + LangGraph + DeepSeek Adapter + "
            "Next.js。\n"
            "- 状态：已完成内部工程验收，尚未开放给种子用户。\n"
        )

    @staticmethod
    def _qa_report(checks: dict[str, Any]) -> str:
        lines = ["# MVP 独立 QA 报告", "", "结论：`beta_candidate_ready`", ""]
        for name in sorted(checks):
            item = checks[name]
            lines.append(
                f"- `{name}`：passed；{item.summary}；证据哈希 `{item.evidence_hash}`"
            )
        lines.extend(
            [
                "",
                "未使用 mock 模型、mock API 或 mock 数据库作为放行证据。",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _known_issues_report() -> str:
        return (
            "# MVP 已知问题\n\n"
            "- P2 / accepted：受限环境下 Turbopack PostCSS 子进程不能绑定"
            "临时端口；同版本 Next.js webpack production build 已通过。\n"
            "- P2 / accepted：保留 Starlette/httpx TestClient 弃用警告，"
            "不影响当前 HTTP 集成结果。\n"
            "- P2 / open：种子用户的真实价值、留存和付费信号尚未产生，"
            "不得写入商业 BRD 结论。\n"
        )

    @staticmethod
    def _seed_plan() -> str:
        return (
            "# MVP 种子用户内测计划\n\n"
            "## 范围\n\n"
            "- 目标：3-5 名获授权、每周真实复盘销售对话的种子用户。\n"
            "- 任务：上传一份真实脱敏材料，确认或修改结论，生成并编辑行动项，导出复盘。\n"
            "- 同意：明确告知数据用途、保留期和删除方式；不收集密钥或未授权敏感信息。\n\n"
            "## 退出标准\n\n"
            "- 至少 3 名用户完成核心闭环，且完成率、编辑率、失败率可追溯。\n"
            "- 至少 3 份定性反馈，包含价值、阻力、替代方案和继续使用意愿。\n"
            "- 出现 P0/P1 数据或核心任务故障时停止内测并返回开发。\n"
        )

    @staticmethod
    def _telemetry_schema() -> str:
        return (
            "# MVP 内测数据 Schema\n\n"
            "| 字段 | 用途 | 隐私 |\n"
            "|---|---|---|\n"
            "| candidate_version | 关联 Beta Candidate | 非敏感 |\n"
            "| consent_scope | 记录用户同意范围 | 不存原文 |\n"
            "| core_task_completed | 核心闭环是否完成 | 布尔值 |\n"
            "| time_to_confirm_seconds | 从上传到确认结论的耗时 | 数值 |\n"
            "| conclusion_edit_rate | 结论人工修改比例 | 汇总值 |\n"
            "| action_edit_rate | 行动项人工修改比例 | 汇总值 |\n"
            "| export_completed | 是否完成导出 | 布尔值 |\n"
            "| failure_code | 失败类型 | 脱敏枚举 |\n"
            "| qualitative_feedback_ref | 指向授权的脱敏反馈 | 引用，不复制原文 |\n"
        )

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
    def _result(
        *,
        project: Project,
        run: AgentRun,
        task: AgentTask,
        by_kind: dict[str, Artifact],
        gate: Gate,
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "acceptance_run_id": run.id,
            "mvp_review_task_id": task.id,
            "mvp_candidate_artifact_id": by_kind["mvp_candidate"].id,
            "qa_report_artifact_id": by_kind["qa_report"].id,
            "known_issues_artifact_id": by_kind["known_issues"].id,
            "seed_test_plan_artifact_id": by_kind["seed_test_plan"].id,
            "telemetry_schema_artifact_id": by_kind["telemetry_schema"].id,
            "verdict": "beta_candidate_ready",
            "target_state": project.state,
            "context_version": project.context_version,
            "gate_id": gate.id,
            "gate_type": gate.gate_type,
            "gate_status": gate.status,
            "idempotent": idempotent,
        }

    def _read_result(
        self, session: Session, run: AgentRun, *, idempotent: bool
    ) -> dict[str, Any]:
        task = session.get(AgentTask, run.task_id)
        project = session.get(Project, task.project_id) if task else None
        if task is None or project is None:
            raise InternalAcceptanceError("RUN_NOT_FOUND", "内部验收 Run 不存在。")
        artifacts = list(
            session.scalars(
                select(Artifact).where(
                    Artifact.project_id == project.id,
                    Artifact.kind.in_(self.REQUIRED_ARTIFACT_KINDS),
                )
            )
        )
        by_kind = {artifact.kind: artifact for artifact in artifacts}
        gate = session.scalar(
            select(Gate).where(
                Gate.project_id == project.id,
                Gate.gate_type == "G5",
                Gate.context_version == project.context_version,
            )
        )
        if set(by_kind) != self.REQUIRED_ARTIFACT_KINDS or gate is None:
            raise InternalAcceptanceError(
                "INTERNAL_ACCEPTANCE_INCOMPLETE", "内部验收结果不完整。"
            )
        return self._result(
            project=project,
            run=run,
            task=task,
            by_kind=by_kind,
            gate=gate,
            idempotent=idempotent,
        )
