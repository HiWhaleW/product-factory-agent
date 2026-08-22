from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.deepseek import DeepSeekAdapter
from app.agents.checkpoint import CheckpointArchive, CheckpointArchiveError
from app.agents.context import ApprovedContextPack, ContextBoundaryError
from app.agents.graph import ModelProvider, ResearchProvider, build_agent_graph
from app.agents.registry import require_d5_agent
from app.core.config import Settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    DefinitionSubmission,
    Event,
    PermissionDecision,
    PermissionRequest,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
    RunStep,
    ToolRun,
)
from app.domain.schemas import ContextPackRead, ContextResourceRef
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact


class AgentRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RuntimeExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    state: str
    turns_used: int
    retries_used: int
    research_retries_used: int = 0
    tool_calls_used: int = 0
    requested_model: str
    observed_model: str | None = None
    usage: dict[str, Any] = {}
    output: dict[str, Any] | None = None
    tool_results: list[dict[str, Any]] = []
    error_code: str | None = None
    permission_request_id: str | None = None
    permission_input_hash: str | None = None
    checkpoint_hash: str | None = None


@dataclass(frozen=True)
class LoadedPack:
    pack: ApprovedContextPack
    agent_id: str
    approved_materials: list[dict[str, Any]]
    review_candidates: list[dict[str, Any]]


class AgentRuntimeService:
    def __init__(
        self,
        settings: Settings,
        *,
        provider: ModelProvider | None = None,
        research_provider: ResearchProvider | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
        available_tool_ids: frozenset[str] = frozenset(),
    ) -> None:
        self.settings = settings
        self.provider = provider or DeepSeekAdapter.from_settings(settings)
        self.research_provider = research_provider
        self.session_factory = session_factory
        self.available_tool_ids = available_tool_ids | (
            frozenset({"web_research"}) if research_provider is not None else frozenset()
        )
        self.archive = CheckpointArchive(settings.ARTIFACT_ROOT)

    async def start(
        self,
        *,
        context_pack_id: str,
        user_input: str,
    ) -> RuntimeExecutionResult:
        self._reject_secret_like_input(user_input)
        with self.session_factory.begin() as session:
            loaded = self._load_approved_pack(session, context_pack_id)
            definition = require_d5_agent(loaded.agent_id, loaded.pack.stage)
            self._check_tool_preconditions(loaded.pack)
            input_hash = self._input_hash(loaded.pack, user_input, definition.prompt_version)
            task = AgentTask(
                project_id=loaded.pack.project_id,
                assigned_agent=definition.id,
                title=loaded.pack.task[:240],
                state="running",
                context_version=loaded.pack.context_version,
                claimed_by="agent-runtime",
            )
            session.add(task)
            session.flush()
            run = AgentRun(
                task_id=task.id,
                state="running",
                input_hash=input_hash,
                started_at=datetime.now(UTC),
            )
            session.add(run)
            session.flush()
            self._add_step(
                session,
                run_id=run.id,
                step_type="runtime_start",
                state="completed",
                input_hash=input_hash,
            )
            self._append_event(
                session,
                loaded.pack.project_id,
                "run.started",
                {
                    "run_id": run.id,
                    "task_id": task.id,
                    "agent_id": definition.id,
                    "context_pack_id": loaded.pack.id,
                    "context_version": loaded.pack.context_version,
                    "requested_model": self.settings.MODEL_NAME,
                },
            )
            run_id, task_id = run.id, task.id

        saver = InMemorySaver()
        graph = build_agent_graph(
            self.provider,
            checkpointer=saver,
            research_provider=self.research_provider,
        )
        config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": loaded.pack.budget.max_turns * 3 + 5,
        }
        initial = {
            "run_id": run_id,
            "agent_id": definition.id,
            "stage": loaded.pack.stage,
            "context_pack": loaded.pack.model_dump(mode="json"),
            "approved_materials": loaded.approved_materials,
            "review_candidates": loaded.review_candidates,
            "user_input": user_input,
            "turns_used": 0,
            "retries_used": 0,
            "tool_calls_used": 0,
            "research_retries_used": 0,
            "tool_results": [],
            "status": "queued",
        }
        try:
            async with asyncio.timeout(loaded.pack.budget.timeout_seconds):
                result = await graph.ainvoke(initial, config)
        except TimeoutError:
            result = {
                **initial,
                "status": "waiting_human",
                "error_code": "AGENT_RUN_TIMEOUT",
            }
        return self._persist_result(
            run_id=run_id,
            task_id=task_id,
            project_id=loaded.pack.project_id,
            result=result,
            saver=saver,
            config=config,
        )

    async def resume_permission(self, run_id: str) -> RuntimeExecutionResult:
        with self.session_factory() as session:
            run = session.get(AgentRun, run_id)
            task = session.get(AgentTask, run.task_id) if run else None
            project = session.get(Project, task.project_id) if task else None
            if run is None or task is None or project is None:
                raise AgentRuntimeError("RUN_NOT_FOUND", "Agent Run does not exist.")
            if task.context_version != project.context_version:
                raise AgentRuntimeError("STALE_CONTEXT", "Run Context is stale.")
            unresolved = session.scalar(
                select(RunStep).where(
                    RunStep.run_id == run.id,
                    RunStep.state.in_(["started", "running"]),
                    RunStep.idempotency_key.is_not(None),
                    RunStep.external_effect_confirmed.is_(False),
                )
            )
            if unresolved is not None:
                raise AgentRuntimeError(
                    "SIDE_EFFECT_RECONCILIATION_REQUIRED",
                    "External side effect must be reconciled before resume.",
                )
            permission = session.scalar(
                select(PermissionRequest)
                .where(PermissionRequest.run_id == run.id)
                .order_by(PermissionRequest.created_at.desc())
            )
            decision = (
                session.scalar(
                    select(PermissionDecision).where(
                        PermissionDecision.permission_request_id == permission.id
                    )
                )
                if permission
                else None
            )
            if permission is None or decision is None:
                raise AgentRuntimeError(
                    "PERMISSION_DECISION_REQUIRED", "Permission must be decided before resume."
                )
            checkpoint = session.scalar(
                select(RunStep)
                .where(RunStep.run_id == run.id, RunStep.step_type == "checkpoint")
                .order_by(RunStep.step_index.desc())
            )
            if checkpoint is None or checkpoint.output_ref is None:
                raise AgentRuntimeError("CHECKPOINT_UNAVAILABLE", "Durable checkpoint is missing.")
            project_id, task_id = project.id, task.id

        saver = InMemorySaver()
        base_config = {"configurable": {"thread_id": run_id}}
        try:
            restored_config = self.archive.restore(
                saver,
                base_config,
                relative_path=checkpoint.output_ref,
                expected_hash=checkpoint.input_hash,
            )
        except CheckpointArchiveError as exc:
            raise AgentRuntimeError("CHECKPOINT_INVALID", str(exc)) from exc
        with self.session_factory.begin() as session:
            run = session.get(AgentRun, run_id)
            task = session.get(AgentTask, task_id)
            if run is None or task is None:
                raise AgentRuntimeError("RUN_NOT_FOUND", "Run disappeared before resume.")
            run.state = "running"
            task.state = "running"
            self._add_step(
                session,
                run_id=run_id,
                step_type="resume",
                state="completed",
                input_hash=checkpoint.input_hash,
                output_ref=checkpoint.output_ref,
                idempotency_key=f"resume:{run_id}:{checkpoint.input_hash}",
                external_effect_confirmed=True,
            )
            self._append_event(
                session,
                project_id,
                "run.resumed",
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "checkpoint_hash": checkpoint.input_hash,
                },
            )
        graph = build_agent_graph(
            self.provider,
            checkpointer=saver,
            research_provider=self.research_provider,
        )
        resumed = await graph.ainvoke(
            Command(resume={"decision": "allow" if decision.decision == "allow" else "deny"}),
            restored_config,
        )
        return self._persist_result(
            run_id=run_id,
            task_id=task_id,
            project_id=project_id,
            result=resumed,
            saver=saver,
            config=restored_config,
        )

    def _persist_result(
        self,
        *,
        run_id: str,
        task_id: str,
        project_id: str,
        result: dict[str, Any],
        saver: InMemorySaver,
        config: dict[str, Any],
    ) -> RuntimeExecutionResult:
        relative_path, checkpoint_hash = self.archive.save(saver, config)
        interrupts = result.get("__interrupt__") or ()
        interrupted = bool(interrupts)
        state = "waiting_human" if interrupted else result.get("status", "failed")
        permission_id = None
        permission_hash = None
        with self.session_factory.begin() as session:
            run = session.get(AgentRun, run_id)
            task = session.get(AgentTask, task_id)
            if run is None or task is None:
                raise AgentRuntimeError("RUN_NOT_FOUND", "Run disappeared during persistence.")
            tool_steps = session.scalar(
                select(func.count())
                .select_from(RunStep)
                .where(RunStep.run_id == run_id, RunStep.step_type == "tool")
            ) or 0
            tool_calls_used = int(result.get("tool_calls_used") or 0)
            tool_results = result.get("tool_results") or []
            tool_output_hash = (
                hashlib.sha256(
                    json.dumps(tool_results, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
                if tool_results
                else None
            )
            for attempt in range(tool_steps, tool_calls_used):
                final_attempt = attempt == tool_calls_used - 1
                completed = final_attempt and tool_output_hash is not None
                step = self._add_step(
                    session,
                    run_id=run_id,
                    step_type="tool",
                    state="completed" if completed else "failed",
                    input_hash=run.input_hash,
                    output_ref=(
                        f"evidence-set://{tool_output_hash}" if completed else None
                    ),
                    idempotency_key=f"web_research:{run_id}:{attempt + 1}",
                    external_effect_confirmed=completed,
                )
                tool_run = ToolRun(
                    task_id=task_id,
                    run_id=run_id,
                    capability_id="CAP-02",
                    tool_name="web_research",
                    state=step.state,
                    input_hash=step.input_hash,
                    idempotency_key=step.idempotency_key,
                    result_ref=step.output_ref,
                )
                session.add(tool_run)
                session.flush()
                self._append_event(
                    session,
                    project_id,
                    "tool_run.completed" if completed else "tool_run.failed",
                    {
                        "tool_run_id": tool_run.id,
                        "run_id": run_id,
                        "task_id": task_id,
                        "tool_id": tool_run.tool_name,
                        "state": tool_run.state,
                        "idempotency_key": tool_run.idempotency_key,
                        "result_ref": tool_run.result_ref,
                    },
                )
            model_steps = session.scalar(
                select(func.count())
                .select_from(RunStep)
                .where(RunStep.run_id == run_id, RunStep.step_type == "model")
            ) or 0
            turns_used = int(result.get("turns_used") or 0)
            for attempt in range(model_steps, turns_used):
                final_attempt = attempt == turns_used - 1
                self._add_step(
                    session,
                    run_id=run_id,
                    step_type="model",
                    state=(
                        "completed"
                        if final_attempt and result.get("observed_model")
                        else "failed"
                    ),
                    input_hash=run.input_hash,
                    output_ref=(
                        f"model://{result['observed_model']}"
                        if final_attempt and result.get("observed_model")
                        else None
                    ),
                )
            self._add_step(
                session,
                run_id=run_id,
                step_type="checkpoint",
                state="completed",
                input_hash=checkpoint_hash,
                output_ref=relative_path,
                idempotency_key=f"checkpoint:{checkpoint_hash}",
                external_effect_confirmed=True,
            )
            if interrupted:
                value = interrupts[0].value
                permission_hash = hashlib.sha256(
                    json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()
                permission = PermissionRequest(
                    run_id=run_id,
                    tool_name=str(value.get("tool_id") or "unknown"),
                    input_hash=permission_hash,
                    risk_level="high",
                    reason=str(value.get("reason") or ""),
                    redacted_parameters=dict(value.get("parameters") or {}),
                    status="open",
                )
                session.add(permission)
                session.flush()
                permission_id = permission.id
                self._append_event(
                    session,
                    project_id,
                    "permission.opened",
                    {
                        "permission_id": permission.id,
                        "run_id": run_id,
                        "tool_id": permission.tool_name,
                        "input_hash": permission.input_hash,
                    },
                )
            run.state = state
            run.turns_used = int(result.get("turns_used") or run.turns_used)
            research_retries = int(result.get("research_retries_used") or 0)
            run.retries_used = int(result.get("retries_used") or 0) + research_retries
            task.state = {
                "succeeded": "completed",
                "waiting_human": "waiting_human",
            }.get(state, "failed")
            if state in {"succeeded", "failed"}:
                run.completed_at = datetime.now(UTC)
            event_type = {
                "succeeded": "run.completed",
                "waiting_human": "run.waiting",
            }.get(state, "run.failed")
            self._append_event(
                session,
                project_id,
                event_type,
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "state": state,
                    "error_code": result.get("error_code"),
                    "checkpoint_hash": checkpoint_hash,
                    "observed_model": result.get("observed_model"),
                    "usage": result.get("usage") or {},
                },
            )
        return RuntimeExecutionResult(
            run_id=run_id,
            task_id=task_id,
            state=state,
            turns_used=int(result.get("turns_used") or 0),
            retries_used=int(result.get("retries_used") or 0),
            research_retries_used=int(result.get("research_retries_used") or 0),
            tool_calls_used=int(result.get("tool_calls_used") or 0),
            requested_model=self.settings.MODEL_NAME,
            observed_model=result.get("observed_model"),
            usage=result.get("usage") or {},
            output=result.get("output"),
            tool_results=result.get("tool_results") or [],
            error_code=result.get("error_code"),
            permission_request_id=permission_id,
            permission_input_hash=permission_hash,
            checkpoint_hash=checkpoint_hash,
        )

    def _load_approved_pack(self, session: Session, pack_id: str) -> LoadedPack:
        pack = session.get(ContextPack, pack_id)
        project = session.get(Project, pack.project_id) if pack else None
        context = (
            session.scalar(
                select(ContextVersion).where(
                    ContextVersion.id == pack.context_version_id,
                    ContextVersion.approval_status == "active",
                )
            )
            if pack
            else None
        )
        if pack is None or project is None or context is None:
            raise AgentRuntimeError("CONTEXT_PACK_NOT_FOUND", "Approved Context Pack is missing.")
        if (
            pack.approval_status != "approved"
            or pack.context_version != project.context_version
            or pack.stage != project.state
        ):
            raise AgentRuntimeError("STALE_CONTEXT", "Context Pack is not current and approved.")
        primary = ContextResourceRef(
            resource_type=pack.primary_resource_type,
            resource_id=pack.primary_resource_id,
            version=pack.primary_resource_version,
            approval_status="approved",
        )
        refs = [ContextResourceRef.model_validate(item) for item in pack.references]
        materials = [
            self._load_resource_material(session, project.id, resource)
            for resource in [primary, *refs]
        ]
        review_candidates = self._load_review_candidates(
            session,
            project=project,
            pack=pack,
        )
        read = ContextPackRead(
            id=pack.id,
            project_id=pack.project_id,
            context_version=pack.context_version,
            stage=pack.stage,
            approval_status=pack.approval_status,
            recipient_agent_id=pack.agent_id,
            primary_resource=primary,
            required_resources=refs,
            task=pack.task,
            policy=pack.policy,
            created_at=pack.created_at,
        )
        try:
            approved = ApprovedContextPack.from_control_plane(read)
        except (ContextBoundaryError, ValueError) as exc:
            raise AgentRuntimeError("CONTEXT_BOUNDARY_INVALID", str(exc)) from exc
        return LoadedPack(
            pack=approved,
            agent_id=pack.agent_id,
            approved_materials=materials,
            review_candidates=review_candidates,
        )

    def _load_review_candidates(
        self,
        session: Session,
        *,
        project: Project,
        pack: ContextPack,
    ) -> list[dict[str, Any]]:
        """Load only the draft artifacts bound by definition-review/v1.

        These inputs are intentionally separate from approved Context resources: they are
        immutable review candidates, not approved facts or project state.
        """
        if pack.agent_id != "reviewer":
            return []
        input_contract = pack.policy.get("input_contract")
        if input_contract == "prd-review/v1":
            return self._load_prd_review_candidate(
                session,
                project=project,
                pack=pack,
            )
        if input_contract != "definition-review/v1":
            raise AgentRuntimeError(
                "REVIEW_INPUT_CONTRACT_INVALID",
                "Reviewer Context Pack is missing the deterministic review input contract.",
            )
        submission_id = pack.policy.get("definition_submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            raise AgentRuntimeError(
                "REVIEW_INPUT_UNAVAILABLE",
                "Reviewer Context Pack is not bound to a DefinitionSubmission.",
            )
        submission = session.get(DefinitionSubmission, submission_id)
        if (
            submission is None
            or submission.project_id != project.id
            or submission.reviewer_context_pack_id != pack.id
            or submission.context_version != project.context_version
            or submission.status != "waiting_reviewer"
        ):
            raise AgentRuntimeError(
                "REVIEW_INPUT_STALE",
                "Definition review candidates are missing, stale, or no longer reviewable.",
            )
        candidates = (
            (submission.evidence_artifact_id, submission.evidence_artifact_version),
            (submission.mrd_artifact_id, submission.mrd_artifact_version),
        )
        loaded: list[dict[str, Any]] = []
        for artifact_id, version_number in candidates:
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
                or artifact.project_id != project.id
                or artifact.kind not in {"evidence_index", "mrd"}
                or version.context_version != project.context_version
                or version.approval_status != "draft"
            ):
                raise AgentRuntimeError(
                    "REVIEW_INPUT_INVALID",
                    "Definition review candidate identity or version is invalid.",
                )
            try:
                _, content = read_verified_artifact(
                    self.settings.ARTIFACT_ROOT,
                    version.content_ref,
                    version.content_hash,
                )
            except ArtifactStoreError as exc:
                raise AgentRuntimeError(
                    "REVIEW_INPUT_INVALID",
                    "Definition review candidate failed integrity checks.",
                ) from exc
            self._reject_secret_like_input(content)
            loaded.append(
                {
                    "resource_type": "review_candidate_artifact",
                    "review_status": "waiting_reviewer",
                    "submission_id": submission.id,
                    "resource_id": artifact.id,
                    "version": version.version,
                    "kind": artifact.kind,
                    "title": artifact.title,
                    "evidence_refs": submission.evidence_refs,
                    "content": content,
                    "content_hash": version.content_hash,
                }
            )
        return loaded

    def _load_prd_review_candidate(
        self,
        session: Session,
        *,
        project: Project,
        pack: ContextPack,
    ) -> list[dict[str, Any]]:
        candidate = pack.policy.get("review_candidate")
        if not isinstance(candidate, dict):
            raise AgentRuntimeError(
                "REVIEW_INPUT_UNAVAILABLE",
                "Reviewer Context Pack is not bound to a PRD candidate.",
            )
        artifact_id = candidate.get("artifact_id")
        version_number = candidate.get("version")
        expected_hash = candidate.get("content_hash")
        artifact = session.get(Artifact, artifact_id) if isinstance(artifact_id, str) else None
        version = (
            session.scalar(
                select(ArtifactVersion).where(
                    ArtifactVersion.artifact_id == artifact_id,
                    ArtifactVersion.version == version_number,
                )
            )
            if artifact is not None and isinstance(version_number, int)
            else None
        )
        if (
            artifact is None
            or version is None
            or artifact.project_id != project.id
            or artifact.kind != "prd"
            or artifact.stage != "prd"
            or version.context_version != project.context_version
            or version.approval_status != "draft"
            or version.content_hash != expected_hash
        ):
            raise AgentRuntimeError(
                "REVIEW_INPUT_STALE",
                "PRD review candidate is missing, stale, or no longer reviewable.",
            )
        try:
            _, content = read_verified_artifact(
                self.settings.ARTIFACT_ROOT,
                version.content_ref,
                version.content_hash,
            )
        except ArtifactStoreError as exc:
            raise AgentRuntimeError(
                "REVIEW_INPUT_INVALID",
                "PRD review candidate failed integrity checks.",
            ) from exc
        self._reject_secret_like_input(content)
        artifact_ref = f"artifact:{artifact.id}:v{version.version}"
        return [
            {
                "resource_type": "review_candidate_artifact",
                "review_status": "waiting_reviewer",
                "resource_id": artifact.id,
                "version": version.version,
                "kind": artifact.kind,
                "title": artifact.title,
                "artifact_ref": artifact_ref,
                "evidence_refs": list(candidate.get("evidence_refs") or []),
                "content": content,
                "content_hash": version.content_hash,
            }
        ]

    def _load_resource_material(
        self, session: Session, project_id: str, ref: ContextResourceRef
    ) -> dict[str, Any]:
        if ref.resource_type == "project_brief":
            resource = session.get(ProjectBrief, ref.resource_id)
            version = session.scalar(
                select(ProjectBriefVersion).where(
                    ProjectBriefVersion.brief_id == ref.resource_id,
                    ProjectBriefVersion.version == ref.version,
                )
            )
        else:
            resource = session.get(Artifact, ref.resource_id)
            version = session.scalar(
                select(ArtifactVersion).where(
                    ArtifactVersion.artifact_id == ref.resource_id,
                    ArtifactVersion.version == ref.version,
                )
            )
        if (
            resource is None
            or version is None
            or resource.project_id != project_id
            or version.approval_status != "approved"
        ):
            raise AgentRuntimeError(
                "CONTEXT_RESOURCE_INVALID", "Context resource is missing, stale, or unapproved."
            )
        if ref.resource_type == "project_brief":
            return {
                "resource_type": "project_brief",
                "resource_id": resource.id,
                "version": version.version,
                "objective": version.objective,
                "target_users": version.target_users,
                "success_criteria": version.success_criteria,
                "in_scope": version.in_scope,
                "out_of_scope": version.out_of_scope,
                "timeline": version.timeline,
                "open_questions": version.open_questions,
            }
        try:
            _, content = read_verified_artifact(
                self.settings.ARTIFACT_ROOT,
                version.content_ref,
                version.content_hash,
            )
        except ArtifactStoreError as exc:
            raise AgentRuntimeError(
                "CONTEXT_ARTIFACT_INVALID", "Approved Artifact content failed integrity checks."
            ) from exc
        self._reject_secret_like_input(content)
        return {
            "resource_type": "artifact",
            "resource_id": resource.id,
            "version": version.version,
            "kind": resource.kind,
            "title": resource.title,
            "artifact_ref": f"artifact:{resource.id}:v{version.version}",
            "content": content,
            "content_hash": version.content_hash,
        }

    def _check_tool_preconditions(self, pack: ApprovedContextPack) -> None:
        if (
            pack.recipient_agent_id == "ai-pm"
            and pack.stage == "mrd"
            and "CAP-02" in pack.allowed_capability_ids
            and "web_research" not in self.available_tool_ids
        ):
            raise AgentRuntimeError(
                "WEB_RESEARCH_ADAPTER_UNAVAILABLE",
                "Evidence/MRD cannot run without a real public research adapter.",
            )

    @staticmethod
    def _reject_secret_like_input(user_input: str) -> None:
        markers = (
            r"\bsk-[A-Za-z0-9_-]{16,}\b",
            r"(?i)\b(api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S+",
        )
        if any(re.search(pattern, user_input) for pattern in markers):
            raise AgentRuntimeError(
                "SENSITIVE_INPUT_REJECTED", "Move secret values to a local SecretRef."
            )

    @staticmethod
    def _input_hash(pack: ApprovedContextPack, user_input: str, prompt_version: str) -> str:
        payload = {
            "context_pack": pack.model_dump(mode="json"),
            "user_input": user_input,
            "prompt_version": prompt_version,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def _add_step(
        session: Session,
        *,
        run_id: str,
        step_type: str,
        state: str,
        input_hash: str,
        output_ref: str | None = None,
        idempotency_key: str | None = None,
        external_effect_confirmed: bool = False,
    ) -> RunStep:
        current = session.scalar(
            select(func.max(RunStep.step_index)).where(RunStep.run_id == run_id)
        )
        step = RunStep(
            run_id=run_id,
            step_index=(current if current is not None else -1) + 1,
            step_type=step_type,
            state=state,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            output_ref=output_ref,
            external_effect_confirmed=external_effect_confirmed,
        )
        session.add(step)
        session.flush()
        return step

    @staticmethod
    def _append_event(
        session: Session, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> Event:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"project:{project_id}"},
        )
        sequence = session.scalar(
            select(func.max(Event.sequence)).where(Event.project_id == project_id)
        )
        event = Event(
            project_id=project_id,
            sequence=(sequence or 0) + 1,
            event_type=event_type,
            payload=payload,
        )
        session.add(event)
        session.flush()
        return event
