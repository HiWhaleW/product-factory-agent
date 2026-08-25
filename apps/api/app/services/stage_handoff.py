from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.agents.outputs import (
    AiPmMrdOutput,
    AiPmPrdOutput,
    BuilderSolutionOutput,
    BuilderTechnicalOutput,
    ReviewerMrdOutput,
    ReviewerPrdOutput,
    ReviewerSolutionOutput,
    ReviewerTechnicalOutput,
)
from app.agents.prd_contracts import PrdReviewCreate, PrdSubmissionCreate
from app.agents.solution_contracts import SolutionReviewCreate, SolutionSubmissionCreate
from app.agents.technical_contracts import TechnicalReviewCreate, TechnicalSubmissionCreate
from app.core.config import Settings
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    ContextPack,
    Event,
    Message,
    PermissionRequest,
    Project,
)
from app.domain.schemas import (
    DefinitionArtifactProposal,
    DefinitionReviewCreate,
    DefinitionSubmissionCreate,
    RedTeamReviewProposal,
    WebResearchEvidenceSet,
)
from app.services.agent_runtime import AgentRuntimeError, AgentRuntimeService
from app.services.definition_chain import (
    DefinitionChainError,
    reviewer_input,
    submit_definition,
    submit_definition_review,
)
from app.services.prd_definition import prd_reviewer_input, submit_prd, submit_prd_review
from app.services.solution_definition import (
    solution_reviewer_input,
    submit_solution,
    submit_solution_review,
)
from app.services.technical_definition import (
    submit_technical_definition,
    submit_technical_review,
    technical_reviewer_input,
)


class StageHandoffError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class StageHandoffRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    context_pack_id: str
    context_version: int
    agent_id: str
    task: str
    run_id: str
    task_id: str
    state: str
    permission_request_id: str | None = None
    permission_input_hash: str | None = None
    idempotent: bool


class StageContinuationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    run_id: str
    state: str
    error_code: str | None = None
    definition_submission_id: str | None = None
    reviewer_run_id: str | None = None
    review_id: str | None = None
    gate_id: str | None = None


class StageHandoffService:
    """Connect an approved Context Pack to real delegated Agent work.

    The model still cannot mutate project state. This service records the Factory
    Lead delegation, starts the exact Context-bound Runtime, then submits successful
    MRD output through the deterministic definition/review control plane.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        runtime: AgentRuntimeService | None,
        session_factory: sessionmaker[Session],
        owner_user_id: str | None,
    ) -> None:
        self.settings = settings
        self.runtime = runtime
        self.session_factory = session_factory
        self.owner_user_id = owner_user_id

    def record_delegation(self, context_pack_id: str) -> None:
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, context_pack_id)
            self._lock_project(session, project.id)
            self._record_delegation(session, project=project, pack=pack)

    def record_start_blocked(self, context_pack_id: str, message: str) -> None:
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, context_pack_id)
            self._record_message(
                session,
                project_id=project.id,
                client_message_id=f"handoff:{context_pack_id}:configuration-blocked",
                actor_id="factory-lead",
                content=(
                    f"任务已经交给 {self._agent_label(pack.agent_id)}，"
                    "但当前账户的服务还没有配置完成："
                    f"{message}。请先前往设置页补齐；项目仍停留在当前阶段。"
                ),
            )
            already_recorded = any(
                event.payload.get("context_pack_id") == pack.id
                for event in session.scalars(
                    select(Event).where(
                        Event.project_id == project.id,
                        Event.event_type == "task.delegation_blocked",
                    )
                )
            )
            if not already_recorded:
                self._append_event(
                    session,
                    project.id,
                    "task.delegation_blocked",
                    {
                        "context_pack_id": pack.id,
                        "recipient_agent_id": pack.agent_id,
                        "reason_code": "MODEL_CREDENTIAL_REQUIRED",
                    },
                )

    async def start(self, context_pack_id: str) -> StageHandoffRead:
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, context_pack_id)
            self._lock_project(session, project.id)
            existing = self._existing_run_for_pack(session, project.id, pack.id)
            if existing is not None:
                run, task = existing
                permission = self._latest_permission(session, run.id)
                return StageHandoffRead(
                    project_id=project.id,
                    context_pack_id=pack.id,
                    context_version=pack.context_version,
                    agent_id=pack.agent_id,
                    task=pack.task,
                    run_id=run.id,
                    task_id=task.id,
                    state=run.state,
                    permission_request_id=(permission.id if permission else None),
                    permission_input_hash=(permission.input_hash if permission else None),
                    idempotent=True,
                )
            self._record_delegation(session, project=project, pack=pack)
            runtime_input = self._runtime_input(session, project=project, pack=pack)
            project_id = project.id
            agent_id = pack.agent_id
            stage = pack.stage
            context_version = pack.context_version
            task_text = pack.task

        if self.runtime is None:
            raise StageHandoffError(
                "MODEL_RUNTIME_UNAVAILABLE",
                "Agent Runtime is unavailable for this handoff.",
                http_status=503,
            )
        try:
            result = await self.runtime.start(
                context_pack_id=context_pack_id,
                user_input=runtime_input,
            )
        except AgentRuntimeError as error:
            with self.session_factory.begin() as session:
                missing_research = error.code == "WEB_RESEARCH_ADAPTER_UNAVAILABLE"
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"handoff:{context_pack_id}:failed",
                    actor_id="factory-lead",
                    content=(
                        f"任务已经交给 {self._agent_label(agent_id)}，"
                        "但当前网络搜索服务还不能用于项目。"
                        "请先前往设置页添加或检查厂商，"
                        "项目仍停留在当前阶段。"
                        if missing_research
                        else (
                            f"{self._agent_label(agent_id)} 暂时没能开始这项任务。"
                            "请检查设置后重试，项目仍停留在当前阶段。"
                        )
                    ),
                )
                self._append_event(
                    session,
                    project_id,
                    "task.delegation_blocked" if missing_research else "task.delegation_failed",
                    {
                        "context_pack_id": context_pack_id,
                        "recipient_agent_id": agent_id,
                        (
                            "reason_code" if missing_research else "error_code"
                        ): (
                            "USER_RESEARCH_CREDENTIAL_REQUIRED"
                            if missing_research
                            else error.code
                        ),
                    },
                )
            raise

        later_stage_completed = False
        if result.state == "succeeded" and stage in {
            "prd",
            "solution_confirmation",
            "tech_stack_confirmation",
        }:
            await self._continue_later_definition_stage(
                pack_id=context_pack_id,
                run_id=result.run_id,
                output=result.output or {},
            )
            later_stage_completed = True

        with self.session_factory.begin() as session:
            if result.state == "waiting_human" and result.permission_request_id:
                content = (
                    "我已收到任务和相关项目资料，正在开展市场研究。"
                    "使用你配置的网络搜索服务可能产生费用，"
                    "请你决定是否允许这一次搜索。"
                )
            elif result.state == "succeeded" and later_stage_completed:
                content = None
            elif result.state == "succeeded":
                content = self._output_message(result.output) or (
                    "我已根据当前项目资料完成任务，正在整理结果。"
                )
            else:
                content = (
                    "我已读取相关项目资料，但这次处理没有完成。"
                    "记录已保留，项目仍停留在当前阶段。"
                )
            if content is not None:
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"handoff:{context_pack_id}:ack:{result.run_id}",
                    actor_id=agent_id,
                    content=content,
                )

        return StageHandoffRead(
            project_id=project_id,
            context_pack_id=context_pack_id,
            context_version=context_version,
            agent_id=agent_id,
            task=task_text,
            run_id=result.run_id,
            task_id=result.task_id,
            state=result.state,
            permission_request_id=result.permission_request_id,
            permission_input_hash=result.permission_input_hash,
            idempotent=False,
        )

    async def resume_and_continue(self, run_id: str) -> StageContinuationRead:
        if self.runtime is None:
            raise StageHandoffError(
                "MODEL_RUNTIME_UNAVAILABLE",
                "Agent Runtime is unavailable for this handoff.",
                http_status=503,
            )
        result = await self.runtime.resume_permission(run_id)
        with self.session_factory.begin() as session:
            pack, project = self._pack_for_run(session, run_id)
            pack_id = pack.id
            agent_id = pack.agent_id
            stage = pack.stage
            project_id = project.id
            if result.state != "succeeded":
                message = (
                    "本次工具使用未获允许，任务已停止；我没有调用工具，也没有生成或提交产物。"
                    if result.error_code == "PERMISSION_DENIED"
                    else (
                        "本次处理没有完成，运行记录已经保留。"
                        "项目仍停留在当前阶段，请检查设置后重试。"
                    )
                )
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"run:{run_id}:result",
                    actor_id=agent_id,
                    content=message,
                )
                return StageContinuationRead(
                    project_id=project_id,
                    run_id=run_id,
                    state=result.state,
                    error_code=result.error_code,
                )

        if agent_id != "ai-pm" or stage != "mrd":
            with self.session_factory.begin() as session:
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"run:{run_id}:result",
                    actor_id=agent_id,
                    content=self._output_message(result.output) or "任务执行完成。",
                )
            return StageContinuationRead(
                project_id=project_id,
                run_id=run_id,
                state=result.state,
            )

        return await self._continue_mrd(
            pack_id=pack_id,
            ai_pm_run_id=run_id,
            output=result.output or {},
            tool_results=result.tool_results,
        )

    async def _continue_mrd(
        self,
        *,
        pack_id: str,
        ai_pm_run_id: str,
        output: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> StageContinuationRead:
        ai_pm_output = AiPmMrdOutput.model_validate(output)
        research_results = [WebResearchEvidenceSet.model_validate(item) for item in tool_results]
        evidence_hash = hashlib.sha256(
            json.dumps(tool_results, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        with self.session_factory.begin() as session:
            current_pack, current_project = self._require_current_pack(session, pack_id)
            self._lock_project(session, current_project.id)
            proposals: list[DefinitionArtifactProposal] = []
            for proposal in ai_pm_output.artifact_proposals:
                existing = session.scalar(
                    select(Artifact).where(
                        Artifact.project_id == current_project.id,
                        Artifact.stage == "mrd",
                        Artifact.kind == proposal.kind,
                    )
                )
                proposals.append(
                    DefinitionArtifactProposal(
                        artifact_id=existing.id if existing else None,
                        expected_previous_version=existing.latest_version if existing else 0,
                        **proposal.model_dump(mode="json"),
                    )
                )
            submission_body = DefinitionSubmissionCreate(
                source_run_id=ai_pm_run_id,
                context_pack_id=current_pack.id,
                expected_context_version=current_project.context_version,
                evidence_set_hash=evidence_hash,
                research_results=research_results,
                artifact_proposals=proposals,
            )
            submission = submit_definition(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=current_project.id,
                idempotency_key=f"stage-definition-{ai_pm_run_id}",
                body=submission_body,
            )
            reviewer_pack = session.get(ContextPack, submission.reviewer_context_pack_id)
            if reviewer_pack is None:
                raise StageHandoffError(
                    "REVIEWER_CONTEXT_MISSING",
                    "Reviewer Context Pack was not created.",
                    http_status=500,
                )
            self._record_message(
                session,
                project_id=current_project.id,
                client_message_id=f"run:{ai_pm_run_id}:result",
                actor_id="ai-pm",
                content=ai_pm_output.message,
            )
            self._record_delegation(
                session,
                project=current_project,
                pack=reviewer_pack,
            )
            reviewer_task = reviewer_input(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=current_project.id,
                submission_id=submission.id,
            ).task
            project_id = current_project.id
            context_version = current_project.context_version

        reviewer_run = await self.runtime.start(
            context_pack_id=submission.reviewer_context_pack_id,
            user_input=reviewer_task,
        )
        if reviewer_run.state != "succeeded":
            with self.session_factory.begin() as session:
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"run:{reviewer_run.run_id}:result",
                    actor_id="reviewer",
                    content=(
                        "我已读取独立 Reviewer Context，但审查没有成功完成。"
                        f"错误：{reviewer_run.error_code or reviewer_run.state}。G1 不会打开。"
                    ),
                )
            return StageContinuationRead(
                project_id=project_id,
                run_id=ai_pm_run_id,
                state=reviewer_run.state,
                error_code=reviewer_run.error_code,
                definition_submission_id=submission.id,
                reviewer_run_id=reviewer_run.run_id,
            )

        reviewer_output = ReviewerMrdOutput.model_validate(reviewer_run.output or {})
        red_team = reviewer_output.artifact_proposals[0]
        with self.session_factory.begin() as session:
            current_project = session.get(Project, project_id)
            if current_project is None:
                raise StageHandoffError(
                    "PROJECT_NOT_FOUND", "Project no longer exists.", http_status=404
                )
            existing_review = session.scalar(
                select(Artifact).where(
                    Artifact.project_id == project_id,
                    Artifact.stage == "mrd",
                    Artifact.kind == "red_team_review",
                )
            )
            review = submit_definition_review(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project_id,
                submission_id=submission.id,
                idempotency_key=f"stage-review-{reviewer_run.run_id}",
                body=DefinitionReviewCreate(
                    source_run_id=reviewer_run.run_id,
                    context_pack_id=submission.reviewer_context_pack_id,
                    expected_context_version=context_version,
                    verdict=reviewer_output.verdict,
                    message=reviewer_output.message,
                    findings=[
                        finding.model_dump(mode="json") for finding in reviewer_output.findings
                    ],
                    red_team_review=RedTeamReviewProposal(
                        artifact_id=existing_review.id if existing_review else None,
                        expected_previous_version=(
                            existing_review.latest_version if existing_review else 0
                        ),
                        title=red_team.title,
                        content=red_team.content,
                        evidence_refs=red_team.evidence_refs,
                    ),
                ),
            )
            self._record_message(
                session,
                project_id=project_id,
                client_message_id=f"run:{reviewer_run.run_id}:result",
                actor_id="reviewer",
                content=reviewer_output.message,
            )
            if review.gate is not None:
                lead_message = (
                    "Reviewer 已完成独立审查，Evidence Index、MRD 与 Red Team Review "
                    "已提交。G1 已打开，等待你决定；我不会代替你批准。"
                )
            else:
                lead_message = (
                    "Reviewer 要求修改，本轮没有打开 G1。我会保留反馈和运行记录，"
                    "后续修订必须继续基于当前 Context。"
                )
            self._record_message(
                session,
                project_id=project_id,
                client_message_id=f"review:{review.review_id}:lead-summary",
                actor_id="factory-lead",
                content=lead_message,
            )
            gate_id = review.gate.id if review.gate else None

        return StageContinuationRead(
            project_id=project_id,
            run_id=ai_pm_run_id,
            state="succeeded",
            definition_submission_id=submission.id,
            reviewer_run_id=reviewer_run.run_id,
            review_id=review.review_id,
            gate_id=gate_id,
        )

    async def _continue_later_definition_stage(
        self,
        *,
        pack_id: str,
        run_id: str,
        output: dict[str, Any],
    ) -> None:
        with self.session_factory() as session:
            pack, _ = self._require_current_pack(session, pack_id)
            stage = pack.stage
            agent_id = pack.agent_id
        if stage == "prd" and agent_id == "ai-pm":
            await self._continue_prd(pack_id=pack_id, run_id=run_id, output=output)
            return
        if stage == "solution_confirmation" and agent_id == "builder":
            await self._continue_solution(pack_id=pack_id, run_id=run_id, output=output)
            return
        if stage == "tech_stack_confirmation" and agent_id == "builder":
            await self._continue_technical(pack_id=pack_id, run_id=run_id, output=output)
            return
        raise StageHandoffError(
            "STAGE_HANDOFF_UNSUPPORTED",
            f"No deterministic continuation is registered for {agent_id}/{stage}.",
        )

    async def _continue_prd(
        self, *, pack_id: str, run_id: str, output: dict[str, Any]
    ) -> None:
        ai_pm_output = AiPmPrdOutput.model_validate(output)
        proposal = ai_pm_output.artifact_proposals[0]
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, pack_id)
            existing = self._stage_artifact(session, project.id, "prd", "prd")
            body = PrdSubmissionCreate.model_validate(
                {
                    "source_run_id": run_id,
                    "context_pack_id": pack.id,
                    "expected_context_version": project.context_version,
                    "artifact_proposal": {
                        "artifact_id": existing.id if existing else None,
                        "expected_previous_version": existing.latest_version if existing else 0,
                        **proposal.model_dump(mode="json"),
                    },
                }
            )
            submission = submit_prd(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project.id,
                idempotency_key=f"stage-prd-{run_id}",
                body=body,
            )
            reviewer_pack = session.get(ContextPack, submission.reviewer_context_pack_id)
            if reviewer_pack is None:
                raise StageHandoffError(
                    "REVIEWER_CONTEXT_MISSING", "Reviewer Context Pack was not created."
                )
            reviewer_task = prd_reviewer_input(
                session,
                project_id=project.id,
                submission_id=submission.submission_id,
            ).task
            self._record_message(
                session,
                project_id=project.id,
                client_message_id=f"run:{run_id}:result",
                actor_id="ai-pm",
                content=ai_pm_output.message,
            )
            self._record_delegation(session, project=project, pack=reviewer_pack)
            project_id = project.id
            context_version = project.context_version

        reviewer_run = await self._start_reviewer(
            project_id=project_id,
            context_pack_id=submission.reviewer_context_pack_id,
            task=reviewer_task,
        )
        if reviewer_run.state != "succeeded":
            return
        reviewer_output = ReviewerPrdOutput.model_validate(reviewer_run.output or {})
        review_proposal = reviewer_output.artifact_proposals[0]
        with self.session_factory.begin() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise StageHandoffError("PROJECT_NOT_FOUND", "Project no longer exists.")
            existing_review = self._stage_artifact(
                session, project_id, "prd", "prd_review"
            )
            review = submit_prd_review(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project_id,
                submission_id=submission.submission_id,
                idempotency_key=f"stage-prd-review-{reviewer_run.run_id}",
                body=PrdReviewCreate.model_validate(
                    {
                        "source_run_id": reviewer_run.run_id,
                        "context_pack_id": submission.reviewer_context_pack_id,
                        "expected_context_version": context_version,
                        "verdict": reviewer_output.verdict,
                        "message": reviewer_output.message,
                        "findings": [
                            finding.model_dump(mode="json")
                            for finding in reviewer_output.findings
                        ],
                        "review_artifact": {
                            "artifact_id": existing_review.id if existing_review else None,
                            "expected_previous_version": (
                                existing_review.latest_version if existing_review else 0
                            ),
                            **review_proposal.model_dump(mode="json"),
                        },
                    }
                ),
            )
            self._record_review_result(
                session,
                project=project,
                reviewer_run_id=reviewer_run.run_id,
                reviewer_message=reviewer_output.message,
                gate_id=review.gate.id if review.gate else None,
                next_gate="G2",
            )

    async def _continue_solution(
        self, *, pack_id: str, run_id: str, output: dict[str, Any]
    ) -> None:
        builder_output = BuilderSolutionOutput.model_validate(output)
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, pack_id)
            proposals = []
            for proposal in builder_output.artifact_proposals:
                existing = self._stage_artifact(
                    session, project.id, "solution_confirmation", proposal.kind
                )
                proposals.append(
                    {
                        "artifact_id": existing.id if existing else None,
                        "expected_previous_version": existing.latest_version if existing else 0,
                        **proposal.model_dump(mode="json"),
                    }
                )
            submission = submit_solution(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project.id,
                idempotency_key=f"stage-solution-{run_id}",
                body=SolutionSubmissionCreate(
                    source_run_id=run_id,
                    context_pack_id=pack.id,
                    expected_context_version=project.context_version,
                    artifact_proposals=proposals,
                ),
            )
            reviewer_pack = session.get(ContextPack, submission.reviewer_context_pack_id)
            if reviewer_pack is None:
                raise StageHandoffError(
                    "REVIEWER_CONTEXT_MISSING", "Reviewer Context Pack was not created."
                )
            reviewer_task = solution_reviewer_input(
                session,
                project_id=project.id,
                submission_id=submission.submission_id,
            ).task
            self._record_message(
                session,
                project_id=project.id,
                client_message_id=f"run:{run_id}:result",
                actor_id="builder",
                content=builder_output.message,
            )
            self._record_delegation(session, project=project, pack=reviewer_pack)
            project_id = project.id
            context_version = project.context_version

        reviewer_run = await self._start_reviewer(
            project_id=project_id,
            context_pack_id=submission.reviewer_context_pack_id,
            task=reviewer_task,
        )
        if reviewer_run.state != "succeeded":
            return
        reviewer_output = ReviewerSolutionOutput.model_validate(reviewer_run.output or {})
        review_proposal = reviewer_output.artifact_proposals[0]
        with self.session_factory.begin() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise StageHandoffError("PROJECT_NOT_FOUND", "Project no longer exists.")
            existing_review = self._stage_artifact(
                session, project_id, "solution_confirmation", "solution_review"
            )
            review = submit_solution_review(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project_id,
                submission_id=submission.submission_id,
                idempotency_key=f"stage-solution-review-{reviewer_run.run_id}",
                body=SolutionReviewCreate.model_validate(
                    {
                        "source_run_id": reviewer_run.run_id,
                        "context_pack_id": submission.reviewer_context_pack_id,
                        "expected_context_version": context_version,
                        "verdict": reviewer_output.verdict,
                        "message": reviewer_output.message,
                        "findings": [
                            finding.model_dump(mode="json")
                            for finding in reviewer_output.findings
                        ],
                        "review_artifact": {
                            "artifact_id": existing_review.id if existing_review else None,
                            "expected_previous_version": (
                                existing_review.latest_version if existing_review else 0
                            ),
                            **review_proposal.model_dump(mode="json"),
                        },
                    }
                ),
            )
            self._record_review_result(
                session,
                project=project,
                reviewer_run_id=reviewer_run.run_id,
                reviewer_message=reviewer_output.message,
                gate_id=review.gate.id if review.gate else None,
                next_gate="G3",
            )

    async def _continue_technical(
        self, *, pack_id: str, run_id: str, output: dict[str, Any]
    ) -> None:
        builder_output = BuilderTechnicalOutput.model_validate(output)
        with self.session_factory.begin() as session:
            pack, project = self._require_current_pack(session, pack_id)
            proposals = []
            for proposal in builder_output.artifact_proposals:
                existing = self._stage_artifact(
                    session, project.id, "tech_stack_confirmation", proposal.kind
                )
                proposals.append(
                    {
                        "artifact_id": existing.id if existing else None,
                        "expected_previous_version": existing.latest_version if existing else 0,
                        **proposal.model_dump(mode="json"),
                    }
                )
            submission = submit_technical_definition(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project.id,
                idempotency_key=f"stage-technical-{run_id}",
                body=TechnicalSubmissionCreate(
                    source_run_id=run_id,
                    context_pack_id=pack.id,
                    expected_context_version=project.context_version,
                    artifact_proposals=proposals,
                ),
            )
            reviewer_pack = session.get(ContextPack, submission.reviewer_context_pack_id)
            if reviewer_pack is None:
                raise StageHandoffError(
                    "REVIEWER_CONTEXT_MISSING", "Reviewer Context Pack was not created."
                )
            reviewer_task = technical_reviewer_input(
                session,
                project_id=project.id,
                submission_id=submission.submission_id,
            ).task
            self._record_message(
                session,
                project_id=project.id,
                client_message_id=f"run:{run_id}:result",
                actor_id="builder",
                content=builder_output.message,
            )
            self._record_delegation(session, project=project, pack=reviewer_pack)
            project_id = project.id
            context_version = project.context_version

        reviewer_run = await self._start_reviewer(
            project_id=project_id,
            context_pack_id=submission.reviewer_context_pack_id,
            task=reviewer_task,
        )
        if reviewer_run.state != "succeeded":
            return
        reviewer_output = ReviewerTechnicalOutput.model_validate(reviewer_run.output or {})
        review_proposal = reviewer_output.artifact_proposals[0]
        with self.session_factory.begin() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise StageHandoffError("PROJECT_NOT_FOUND", "Project no longer exists.")
            existing_review = self._stage_artifact(
                session, project_id, "tech_stack_confirmation", "technical_review"
            )
            review = submit_technical_review(
                session,
                artifact_root=self.settings.ARTIFACT_ROOT,
                project_id=project_id,
                submission_id=submission.submission_id,
                idempotency_key=f"stage-technical-review-{reviewer_run.run_id}",
                body=TechnicalReviewCreate.model_validate(
                    {
                        "source_run_id": reviewer_run.run_id,
                        "context_pack_id": submission.reviewer_context_pack_id,
                        "expected_context_version": context_version,
                        "verdict": reviewer_output.verdict,
                        "message": reviewer_output.message,
                        "findings": [
                            finding.model_dump(mode="json")
                            for finding in reviewer_output.findings
                        ],
                        "review_artifact": {
                            "artifact_id": existing_review.id if existing_review else None,
                            "expected_previous_version": (
                                existing_review.latest_version if existing_review else 0
                            ),
                            **review_proposal.model_dump(mode="json"),
                        },
                    }
                ),
            )
            self._record_review_result(
                session,
                project=project,
                reviewer_run_id=reviewer_run.run_id,
                reviewer_message=reviewer_output.message,
                gate_id=review.gate.id if review.gate else None,
                next_gate="G4",
            )

    async def _start_reviewer(
        self, *, project_id: str, context_pack_id: str, task: str
    ):
        if self.runtime is None:
            raise StageHandoffError(
                "MODEL_RUNTIME_UNAVAILABLE", "Reviewer Runtime is unavailable."
            )
        result = await self.runtime.start(context_pack_id=context_pack_id, user_input=task)
        if result.state != "succeeded":
            with self.session_factory.begin() as session:
                self._record_message(
                    session,
                    project_id=project_id,
                    client_message_id=f"run:{result.run_id}:result",
                    actor_id="reviewer",
                    content=(
                        "我已读取独立 Reviewer Context，但审查没有成功完成。"
                        f"错误：{result.error_code or result.state}。下一 Gate 不会打开。"
                    ),
                )
        return result

    def _record_review_result(
        self,
        session: Session,
        *,
        project: Project,
        reviewer_run_id: str,
        reviewer_message: str,
        gate_id: str | None,
        next_gate: str,
    ) -> None:
        self._record_message(
            session,
            project_id=project.id,
            client_message_id=f"run:{reviewer_run_id}:result",
            actor_id="reviewer",
            content=reviewer_message,
        )
        lead_message = (
            f"Reviewer 已完成独立审查，{next_gate} 已打开并等待你决定；我不会代替你批准。"
            if gate_id
            else (
                f"Reviewer 要求修改，本轮没有打开 {next_gate}。反馈和运行记录已保留，"
                "后续修订仍须基于当前 Context。"
            )
        )
        self._record_message(
            session,
            project_id=project.id,
            client_message_id=f"review:{reviewer_run_id}:lead-summary",
            actor_id="factory-lead",
            content=lead_message,
        )

    @staticmethod
    def _stage_artifact(
        session: Session, project_id: str, stage: str, kind: str
    ) -> Artifact | None:
        return session.scalar(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.stage == stage,
                Artifact.kind == kind,
            )
        )

    def _require_current_pack(
        self, session: Session, context_pack_id: str
    ) -> tuple[ContextPack, Project]:
        pack = session.get(ContextPack, context_pack_id)
        project = session.get(Project, pack.project_id) if pack else None
        if pack is None or project is None or project.deleted_at is not None:
            raise StageHandoffError(
                "CONTEXT_PACK_NOT_FOUND", "Context Pack does not exist.", http_status=404
            )
        if self.owner_user_id is not None and project.owner_user_id != self.owner_user_id:
            raise StageHandoffError(
                "CONTEXT_PACK_NOT_FOUND", "Context Pack does not exist.", http_status=404
            )
        if (
            pack.approval_status != "approved"
            or pack.context_version != project.context_version
            or pack.stage != project.state
        ):
            raise StageHandoffError("STALE_CONTEXT", "Context Pack is not current and approved.")
        return pack, project

    def _pack_for_run(self, session: Session, run_id: str) -> tuple[ContextPack, Project]:
        run = session.get(AgentRun, run_id)
        task = session.get(AgentTask, run.task_id) if run else None
        if run is None or task is None:
            raise StageHandoffError("RUN_NOT_FOUND", "Agent Run does not exist.", http_status=404)
        events = session.scalars(
            select(Event)
            .where(Event.project_id == task.project_id, Event.event_type == "run.started")
            .order_by(Event.sequence.desc())
        )
        event = next((item for item in events if item.payload.get("run_id") == run_id), None)
        pack_id = event.payload.get("context_pack_id") if event else None
        if not isinstance(pack_id, str):
            raise StageHandoffError(
                "RUN_CONTEXT_BINDING_INVALID", "Run has no Context Pack binding."
            )
        return self._require_current_pack(session, pack_id)

    def _existing_run_for_pack(
        self, session: Session, project_id: str, context_pack_id: str
    ) -> tuple[AgentRun, AgentTask] | None:
        events = session.scalars(
            select(Event)
            .where(Event.project_id == project_id, Event.event_type == "run.started")
            .order_by(Event.sequence.desc())
        )
        event = next(
            (item for item in events if item.payload.get("context_pack_id") == context_pack_id),
            None,
        )
        run_id = event.payload.get("run_id") if event else None
        run = session.get(AgentRun, run_id) if isinstance(run_id, str) else None
        task = session.get(AgentTask, run.task_id) if run else None
        if run is not None and run.state == "failed":
            blocked_events = session.scalars(
                select(Event)
                .where(
                    Event.project_id == project_id,
                    Event.event_type == "task.delegation_blocked",
                )
                .order_by(Event.sequence.desc())
            )
            retryable_block = next(
                (
                    item
                    for item in blocked_events
                    if item.payload.get("context_pack_id") == context_pack_id
                    and item.payload.get("reason_code")
                    == "USER_RESEARCH_CREDENTIAL_REQUIRED"
                ),
                None,
            )
            if retryable_block is not None:
                return None
        return (run, task) if run is not None and task is not None else None

    @staticmethod
    def _latest_permission(session: Session, run_id: str) -> PermissionRequest | None:
        return session.scalar(
            select(PermissionRequest)
            .where(PermissionRequest.run_id == run_id)
            .order_by(PermissionRequest.created_at.desc())
        )

    def _record_delegation(
        self, session: Session, *, project: Project, pack: ContextPack
    ) -> None:
        resource_label = {
            "project_brief": "已确认的项目目标、用户和范围",
            "artifact": "已确认的上一阶段产物",
        }.get(pack.primary_resource_type, "已确认的项目资料")
        content = (
            f"{self._agent_label(pack.agent_id)}，现在把阶段任务交给你。\n"
            f"任务：{pack.task}\n"
            f"已提供资料：{resource_label}。\n"
            "工作边界：只使用完成任务必需的资料；不得读取密钥、越过项目范围，"
            "也不得代替用户确认阶段。\n"
            "请基于这些资料开始工作。"
        )
        self._record_message(
            session,
            project_id=project.id,
            client_message_id=f"handoff:{pack.id}:assignment",
            actor_id="factory-lead",
            content=content,
        )
        exists = next(
            (
                event
                for event in session.scalars(
                    select(Event).where(
                        Event.project_id == project.id,
                        Event.event_type == "task.delegated",
                    )
                )
                if event.payload.get("context_pack_id") == pack.id
            ),
            None,
        )
        if exists is None:
            self._append_event(
                session,
                project.id,
                "task.delegated",
                {
                    "delegated_by": "factory-lead",
                    "recipient_agent_id": pack.agent_id,
                    "context_pack_id": pack.id,
                    "context_version": pack.context_version,
                    "stage": pack.stage,
                    "task": pack.task,
                    "primary_resource": {
                        "resource_type": pack.primary_resource_type,
                        "resource_id": pack.primary_resource_id,
                        "version": pack.primary_resource_version,
                        "approval_status": "approved",
                    },
                    "allowed_capability_ids": list(
                        pack.policy.get("allowed_capability_ids") or []
                    ),
                    "forbidden_actions": list(pack.policy.get("forbidden_actions") or []),
                },
            )

    def _runtime_input(self, session: Session, *, project: Project, pack: ContextPack) -> str:
        if pack.agent_id == "ai-pm" and pack.stage == "mrd":
            objective = ""
            if pack.primary_resource_type == "project_brief":
                from app.domain.models import ProjectBriefVersion

                version = session.scalar(
                    select(ProjectBriefVersion).where(
                        ProjectBriefVersion.brief_id == pack.primary_resource_id,
                        ProjectBriefVersion.version == pack.primary_resource_version,
                    )
                )
                objective = version.objective if version else ""
            query_parts = [project.name, objective, "目标用户 需求 市场 竞品"]
            query = " ".join(part.strip() for part in query_parts if part.strip())[:1800]
            return (
                f"Research query: {query}\n{pack.task}\n"
                "先用公开一手资料建立可追溯 Evidence Index，再形成 MRD。"
                "区分事实、推断、假设和待访谈项；不得自动推进 Gate。"
            )
        return pack.task

    def _record_message(
        self,
        session: Session,
        *,
        project_id: str,
        client_message_id: str,
        actor_id: str,
        content: str,
    ) -> Message:
        existing = session.scalar(
            select(Message).where(
                Message.project_id == project_id,
                Message.client_message_id == client_message_id,
            )
        )
        if existing is not None:
            return existing
        message = Message(
            project_id=project_id,
            client_message_id=client_message_id[:100],
            actor_type="agent",
            actor_id=actor_id,
            content=content,
        )
        session.add(message)
        session.flush()
        self._append_event(
            session,
            project_id,
            "message.created",
            {"message_id": message.id, "actor_id": actor_id},
        )
        return message

    @staticmethod
    def _output_message(output: dict[str, Any] | None) -> str | None:
        value = (output or {}).get("message")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _agent_label(agent_id: str) -> str:
        return {
            "ai-pm": "AI PM",
            "reviewer": "Reviewer",
            "builder": "Builder",
        }.get(agent_id, agent_id)

    @staticmethod
    def _lock_project(session: Session, project_id: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"project:{project_id}"},
        )

    @classmethod
    def _append_event(
        cls, session: Session, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> Event:
        cls._lock_project(session, project_id)
        current = session.scalar(
            select(func.max(Event.sequence)).where(Event.project_id == project_id)
        )
        event = Event(
            project_id=project_id,
            sequence=(current or 0) + 1,
            event_type=event_type,
            payload=payload,
        )
        session.add(event)
        session.flush()
        return event


__all__ = [
    "StageContinuationRead",
    "StageHandoffError",
    "StageHandoffRead",
    "StageHandoffService",
    "DefinitionChainError",
]
