from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.agents.outputs import FactoryLeadOutput
from app.core.config import Settings
from app.core.database import SessionLocal
from app.domain.models import (
    ClarificationRecord,
    ContextPack,
    ContextVersion,
    Event,
    FactoryLeadInvocation,
    Gate,
    Message,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
)
from app.domain.schemas import (
    FactoryLeadAlignmentCreate,
    FactoryLeadAlignmentRead,
    GateRead,
    ProjectBriefVersionRead,
)
from app.services.agent_runtime import (
    AgentRuntimeError,
    AgentRuntimeService,
    RuntimeExecutionResult,
)
from app.services.control_plane import (
    ControlPlaneError,
    validate_gate_open,
    validate_transition,
)


class FactoryLeadAlignmentError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int = 409,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class FactoryLeadRuntimeService(AgentRuntimeService):
    """Alignment-only extension without modifying the parallel Agent Runtime file."""

    def _load_resource_material(
        self, session: Session, project_id: str, ref
    ) -> dict[str, Any]:
        if ref.resource_type != "context_version":
            return super()._load_resource_material(session, project_id, ref)
        context = session.get(ContextVersion, ref.resource_id)
        if (
            context is None
            or context.project_id != project_id
            or context.version != ref.version
            or context.stage != "alignment"
            or context.approval_status != "active"
        ):
            raise AgentRuntimeError(
                "CONTEXT_RESOURCE_INVALID",
                "Factory Lead bootstrap ContextVersion is missing, stale, or inactive.",
            )
        return {
            "resource_type": "context_version",
            "resource_id": context.id,
            "version": context.version,
            "stage": context.stage,
            "summary": context.summary,
        }


class FactoryLeadAlignmentService:
    def __init__(
        self,
        settings: Settings,
        *,
        runtime: FactoryLeadRuntimeService | None = None,
        session_factory: sessionmaker[Session] = SessionLocal,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.runtime = runtime or FactoryLeadRuntimeService(
            settings, session_factory=session_factory
        )

    async def start(
        self,
        *,
        project_id: str,
        body: FactoryLeadAlignmentCreate,
        idempotency_key: str,
    ) -> FactoryLeadAlignmentRead:
        request_hash = self._stable_hash(body.model_dump(mode="json"))
        with self.session_factory.begin() as session:
            self._lock(session, f"project:{project_id}")
            self._lock(session, f"factory-lead:{project_id}:{idempotency_key}")
            project = session.get(Project, project_id)
            if project is None:
                raise FactoryLeadAlignmentError(
                    "PROJECT_NOT_FOUND", "项目不存在。", http_status=404
                )
            existing = session.scalar(
                select(FactoryLeadInvocation).where(
                    FactoryLeadInvocation.project_id == project_id,
                    FactoryLeadInvocation.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.input_hash != request_hash:
                    raise FactoryLeadAlignmentError(
                        "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同的 Factory Lead 输入。"
                    )
                return self._read_result(session, existing, idempotent=True)
            self._validate_alignment(project, body.expected_context_version)
            message = self._record_user_message(session, project, body)
            self._apply_answers(session, project, body)
            pack = self._ensure_bootstrap_pack(session, project)
            invocation = FactoryLeadInvocation(
                project_id=project.id,
                idempotency_key=idempotency_key,
                input_hash=request_hash,
                context_version=project.context_version,
                status="running",
                result_summary={
                    "context_pack_id": pack.id,
                    "user_message_id": message.id,
                },
            )
            session.add(invocation)
            session.flush()
            self._append_event(
                session,
                project.id,
                "factory_lead.invocation.started",
                {
                    "invocation_id": invocation.id,
                    "context_pack_id": pack.id,
                    "context_version": project.context_version,
                },
            )
            invocation_id = invocation.id
            pack_id = pack.id
            model_input = self._model_input(session, project, body)

        try:
            runtime_result = await self.runtime.start(
                context_pack_id=pack_id,
                user_input=json.dumps(model_input, ensure_ascii=False, separators=(",", ":")),
            )
        except AgentRuntimeError as error:
            self._mark_failed(invocation_id, error.code)
            raise FactoryLeadAlignmentError(
                error.code, str(error), retryable=error.retryable
            ) from error

        try:
            return self._apply_runtime_result(
                invocation_id=invocation_id,
                body=body,
                runtime_result=runtime_result,
            )
        except FactoryLeadAlignmentError as error:
            self._mark_failed(invocation_id, error.code)
            raise

    def _apply_runtime_result(
        self,
        *,
        invocation_id: str,
        body: FactoryLeadAlignmentCreate,
        runtime_result: RuntimeExecutionResult,
    ) -> FactoryLeadAlignmentRead:
        with self.session_factory.begin() as session:
            invocation = session.get(FactoryLeadInvocation, invocation_id)
            if invocation is None:
                raise FactoryLeadAlignmentError(
                    "INVOCATION_NOT_FOUND", "Factory Lead 调用记录不存在。", http_status=500
                )
            self._lock(session, f"project:{invocation.project_id}")
            project = session.get(Project, invocation.project_id)
            if project is None:
                raise FactoryLeadAlignmentError(
                    "PROJECT_NOT_FOUND", "项目不存在。", http_status=404
                )
            context_pack_id = str(invocation.result_summary.get("context_pack_id") or "")
            invocation.run_id = runtime_result.run_id
            if runtime_result.state != "succeeded" or runtime_result.output is None:
                invocation.status = "failed"
                invocation.error_code = runtime_result.error_code or "FACTORY_LEAD_RUN_FAILED"
                invocation.completed_at = datetime.now(UTC)
                invocation.result_summary = {
                    **self._runtime_summary(runtime_result),
                    "context_pack_id": context_pack_id,
                }
                self._append_event(
                    session,
                    project.id,
                    "factory_lead.invocation.failed",
                    {
                        "invocation_id": invocation.id,
                        "run_id": runtime_result.run_id,
                        "error_code": invocation.error_code,
                    },
                )
                return self._read_result(session, invocation, idempotent=False)
            if (
                project.state != "alignment"
                or project.context_version != invocation.context_version
            ):
                invocation.status = "failed"
                invocation.error_code = "STALE_CONTEXT"
                invocation.completed_at = datetime.now(UTC)
                invocation.result_summary = {
                    **self._runtime_summary(runtime_result),
                    "context_pack_id": context_pack_id,
                }
                return self._read_result(session, invocation, idempotent=False)
            try:
                output = FactoryLeadOutput.model_validate(runtime_result.output)
            except ValidationError as error:
                invocation.status = "failed"
                invocation.error_code = "FACTORY_LEAD_OUTPUT_INVALID"
                invocation.completed_at = datetime.now(UTC)
                invocation.result_summary = {
                    **self._runtime_summary(runtime_result),
                    "context_pack_id": context_pack_id,
                }
                raise FactoryLeadAlignmentError(
                    "FACTORY_LEAD_OUTPUT_INVALID",
                    "Factory Lead 输出未通过稳定 Schema。",
                ) from error

            proposals = (
                list(output.clarification_proposals)
                if output.project_brief is None
                else []
            )
            if not proposals and output.open_questions and output.project_brief is None:
                from app.agents.outputs import ClarificationProposal

                proposals = [
                    ClarificationProposal(question=question, scope_impact="none")
                    for question in output.open_questions[:3]
                ]
            message_content = output.message.strip()
            if proposals:
                questions = "\n".join(
                    f"{index}. {proposal.question}"
                    for index, proposal in enumerate(proposals, start=1)
                )
                message_content = f"{message_content}\n\n请回答以下问题：\n{questions}"

            agent_message = Message(
                project_id=project.id,
                client_message_id=f"factory-lead:{runtime_result.run_id}",
                actor_type="agent",
                actor_id="factory-lead",
                content=message_content,
            )
            session.add(agent_message)
            session.flush()
            self._append_event(
                session,
                project.id,
                "message.created",
                {
                    "message_id": agent_message.id,
                    "actor_type": "agent",
                    "actor_id": "factory-lead",
                    "run_id": runtime_result.run_id,
                },
            )

            clarification_ids: list[str] = []
            for index, proposal in enumerate(proposals):
                clarification = ClarificationRecord(
                    project_id=project.id,
                    client_clarification_id=f"factory-lead:{runtime_result.run_id}:{index}",
                    question=proposal.question,
                    answer=None,
                    scope_impact=proposal.scope_impact,
                    context_version=project.context_version,
                    created_by="factory-lead",
                )
                session.add(clarification)
                session.flush()
                clarification_ids.append(clarification.id)
                self._append_event(
                    session,
                    project.id,
                    "clarification.recorded",
                    {
                        "clarification_id": clarification.id,
                        "context_version": project.context_version,
                        "scope_impact": clarification.scope_impact,
                        "answer_status": "pending",
                        "run_id": runtime_result.run_id,
                    },
                )

            brief_version: ProjectBriefVersion | None = None
            gate: Gate | None = None
            if output.project_brief is not None:
                brief_version, gate = self._apply_brief(
                    session=session,
                    project=project,
                    body=body,
                    output=output,
                    run_id=runtime_result.run_id,
                )
            if clarification_ids:
                state = "clarification_required"
            elif brief_version is not None and gate is not None:
                state = "waiting_g0"
            else:
                invocation.status = "failed"
                invocation.error_code = "FACTORY_LEAD_OUTPUT_NO_ACTION"
                invocation.completed_at = datetime.now(UTC)
                invocation.result_summary = {
                    **self._runtime_summary(runtime_result),
                    "context_pack_id": context_pack_id,
                    "message_id": agent_message.id,
                }
                return self._read_result(session, invocation, idempotent=False)

            invocation.status = "completed"
            invocation.error_code = None
            invocation.completed_at = datetime.now(UTC)
            invocation.result_summary = {
                **self._runtime_summary(runtime_result),
                "context_pack_id": context_pack_id,
                "state": state,
                "message_id": agent_message.id,
                "clarification_ids": clarification_ids,
                "brief_version_id": brief_version.id if brief_version else None,
                "gate_id": gate.id if gate else None,
            }
            self._append_event(
                session,
                project.id,
                "factory_lead.invocation.completed",
                {
                    "invocation_id": invocation.id,
                    "run_id": runtime_result.run_id,
                    "state": state,
                    "clarification_ids": clarification_ids,
                    "brief_version_id": brief_version.id if brief_version else None,
                    "gate_id": gate.id if gate else None,
                },
            )
            return self._read_result(session, invocation, idempotent=False)

    def _apply_brief(
        self,
        *,
        session: Session,
        project: Project,
        body: FactoryLeadAlignmentCreate,
        output: FactoryLeadOutput,
        run_id: str,
    ) -> tuple[ProjectBriefVersion, Gate]:
        proposal = output.project_brief
        if proposal is None:
            raise FactoryLeadAlignmentError(
                "FACTORY_LEAD_OUTPUT_INVALID", "Factory Lead 没有提交 Project Brief 候选。"
            )
        gate_request = output.gate_request
        transition = output.transition_proposal
        if gate_request is not None and gate_request.context_version != project.context_version:
            raise FactoryLeadAlignmentError(
                "STALE_CONTEXT", "Factory Lead 的 G0 建议没有绑定当前 Context。"
            )
        if transition is not None and (
            transition.context_version != project.context_version
            or transition.from_state != project.state
        ):
            raise FactoryLeadAlignmentError(
                "STALE_CONTEXT", "Factory Lead 的状态建议没有绑定当前 Context。"
            )
        try:
            validate_gate_open(
                current_state=project.state,
                gate_type="G0",
                target_state="mrd",
                context_matches=True,
            )
            validate_transition(project.state, "mrd", "G0")
        except ControlPlaneError as error:
            raise FactoryLeadAlignmentError(error.code, error.user_message) from error
        pending = session.scalar(
            select(func.count())
            .select_from(ClarificationRecord)
            .where(
                ClarificationRecord.project_id == project.id,
                ClarificationRecord.context_version == project.context_version,
                ClarificationRecord.answer.is_(None),
            )
        )
        if pending:
            raise FactoryLeadAlignmentError(
                "CLARIFICATION_ANSWERS_REQUIRED",
                "仍有未回答的范围澄清，不能生成 G0 候选。",
            )
        brief = session.scalar(
            select(ProjectBrief).where(ProjectBrief.project_id == project.id)
        )
        if brief is None:
            brief = ProjectBrief(project_id=project.id, latest_version=0)
            session.add(brief)
            session.flush()
        if brief.latest_version != body.expected_previous_brief_version:
            raise FactoryLeadAlignmentError(
                "BRIEF_VERSION_CONFLICT", "Project Brief 前置版本已变化，请刷新。"
            )
        open_gate = session.scalar(
            select(Gate).where(
                Gate.project_id == project.id,
                Gate.gate_type == "G0",
                Gate.status == "open",
            )
        )
        if open_gate is not None:
            raise FactoryLeadAlignmentError("GATE_ALREADY_OPEN", "当前已有待决定的 G0。")
        source_ids = list(
            session.scalars(
                select(ClarificationRecord.id).where(
                    ClarificationRecord.project_id == project.id,
                    ClarificationRecord.context_version == project.context_version,
                    ClarificationRecord.answer.is_not(None),
                )
            )
        )
        version = ProjectBriefVersion(
            brief_id=brief.id,
            version=brief.latest_version + 1,
            context_version=project.context_version,
            approval_status="draft",
            objective=proposal.objective,
            target_users=proposal.target_users,
            success_criteria=proposal.success_criteria,
            in_scope=proposal.in_scope,
            out_of_scope=proposal.out_of_scope,
            timeline=proposal.timeline,
            open_questions=list(
                dict.fromkeys(
                    [
                        *proposal.open_questions,
                        *(item.question for item in output.clarification_proposals),
                        *output.open_questions,
                    ]
                )
            ),
            source_clarification_ids=source_ids,
            created_by="factory-lead",
        )
        brief.latest_version = version.version
        session.add(version)
        session.flush()
        gate = Gate(
            project_id=project.id,
            gate_type="G0",
            context_version=project.context_version,
            status="open",
            target_state="mrd",
            reason=(
                gate_request.reason
                if gate_request is not None
                else "批准 Project Brief、目标用户、成功标准、时间和不做范围。"
            ),
            impacted_artifact_refs=[
                {
                    "resource_type": "project_brief",
                    "resource_id": brief.id,
                    "version": version.version,
                }
            ],
        )
        session.add(gate)
        session.flush()
        self._append_event(
            session,
            project.id,
            "project_brief.created" if version.version == 1 else "project_brief.versioned",
            {
                "brief_id": brief.id,
                "brief_version_id": version.id,
                "version": version.version,
                "context_version": version.context_version,
                "source_run_id": run_id,
            },
        )
        self._append_event(
            session,
            project.id,
            "gate.opened",
            {
                "gate_id": gate.id,
                "gate_type": "G0",
                "context_version": gate.context_version,
                "source_run_id": run_id,
            },
        )
        return version, gate

    def _record_user_message(
        self, session: Session, project: Project, body: FactoryLeadAlignmentCreate
    ) -> Message:
        existing = session.scalar(
            select(Message).where(
                Message.project_id == project.id,
                Message.client_message_id == body.client_message_id,
            )
        )
        if existing is not None:
            if existing.content != body.content or existing.actor_type != "user":
                raise FactoryLeadAlignmentError(
                    "MESSAGE_ID_CONFLICT", "同一消息 ID 不能用于不同内容。"
                )
            return existing
        message = Message(
            project_id=project.id,
            client_message_id=body.client_message_id,
            actor_type="user",
            actor_id=project.owner_user_id,
            content=body.content,
        )
        session.add(message)
        session.flush()
        self._append_event(
            session,
            project.id,
            "message.created",
            {"message_id": message.id, "actor_type": "user"},
        )
        return message

    def _apply_answers(
        self, session: Session, project: Project, body: FactoryLeadAlignmentCreate
    ) -> None:
        for item in body.clarification_answers:
            clarification = session.get(ClarificationRecord, item.clarification_id)
            if (
                clarification is None
                or clarification.project_id != project.id
                or clarification.context_version != project.context_version
            ):
                raise FactoryLeadAlignmentError(
                    "CLARIFICATION_BINDING_INVALID",
                    "澄清回答引用了其他项目、其他 Context 或不存在的问题。",
                )
            if clarification.answer is not None:
                if clarification.answer != item.answer:
                    raise FactoryLeadAlignmentError(
                        "CLARIFICATION_ANSWER_CONFLICT", "同一澄清问题不能覆盖为不同回答。"
                    )
                continue
            clarification.answer = item.answer
            self._append_event(
                session,
                project.id,
                "clarification.answered",
                {
                    "clarification_id": clarification.id,
                    "context_version": clarification.context_version,
                },
            )

    def _ensure_bootstrap_pack(self, session: Session, project: Project) -> ContextPack:
        context = session.scalar(
            select(ContextVersion).where(
                ContextVersion.project_id == project.id,
                ContextVersion.version == project.context_version,
                ContextVersion.stage == "alignment",
                ContextVersion.approval_status == "active",
            )
        )
        if context is None:
            raise FactoryLeadAlignmentError(
                "CONTEXT_VERSION_NOT_FOUND", "当前 alignment ContextVersion 不存在。"
            )
        pack = session.scalar(
            select(ContextPack).where(
                ContextPack.project_id == project.id,
                ContextPack.context_version == project.context_version,
                ContextPack.stage == "alignment",
                ContextPack.agent_id == "factory-lead",
                ContextPack.primary_resource_type == "context_version",
                ContextPack.primary_resource_id == context.id,
                ContextPack.primary_resource_version == context.version,
                ContextPack.approval_status == "approved",
            )
        )
        if pack is not None:
            return pack
        pack = ContextPack(
            project_id=project.id,
            context_version_id=context.id,
            context_version=context.version,
            stage="alignment",
            approval_status="approved",
            primary_resource_type="context_version",
            primary_resource_id=context.id,
            primary_resource_version=context.version,
            agent_id="factory-lead",
            task="澄清用户输入并生成 Project Brief/G0 候选；不得批准 Gate 或推进状态。",
            references=[],
            policy={
                "allowed_capability_ids": ["CAP-01", "CAP-05", "CAP-06"],
                "forbidden_actions": [
                    "advance_project_state",
                    "approve_gate",
                    "read_secret_values",
                ],
                "budget": {
                    "max_turns": 3,
                    "max_retries": 1,
                    "timeout_seconds": 120,
                    "max_tool_calls": 0,
                },
            },
        )
        session.add(pack)
        session.flush()
        self._append_event(
            session,
            project.id,
            "context.pack_created",
            {
                "context_pack_id": pack.id,
                "context_version": context.version,
                "stage": "alignment",
                "recipient_agent_id": "factory-lead",
                "primary_resource_type": "context_version",
            },
        )
        return pack

    def _model_input(
        self, session: Session, project: Project, body: FactoryLeadAlignmentCreate
    ) -> dict[str, Any]:
        clarifications = list(
            session.scalars(
                select(ClarificationRecord)
                .where(
                    ClarificationRecord.project_id == project.id,
                    ClarificationRecord.context_version == project.context_version,
                )
                .order_by(ClarificationRecord.created_at, ClarificationRecord.id)
            )
        )
        return {
            "project_id": project.id,
            "stage": project.state,
            "context_version": project.context_version,
            "current_user_input": body.content,
            "clarifications": [
                {
                    "clarification_id": item.id,
                    "question": item.question,
                    "answer": item.answer,
                    "scope_impact": item.scope_impact,
                }
                for item in clarifications
            ],
            "instruction": (
                "最多提出 3 个真正改变范围的问题；信息足够时生成结构化 Project Brief、"
                "G0 请求和仅供确定性状态机校验的 TransitionProposal。"
            ),
        }

    def _read_result(
        self, session: Session, invocation: FactoryLeadInvocation, *, idempotent: bool
    ) -> FactoryLeadAlignmentRead:
        summary = invocation.result_summary or {}
        message_id = summary.get("message_id")
        brief_version_id = summary.get("brief_version_id")
        gate_id = summary.get("gate_id")
        message = session.get(Message, message_id) if message_id else None
        brief_version = (
            session.get(ProjectBriefVersion, brief_version_id) if brief_version_id else None
        )
        gate = session.get(Gate, gate_id) if gate_id else None
        state = summary.get("state")
        if invocation.status == "running":
            state = "running"
        elif invocation.status == "failed" or state not in {
            "clarification_required",
            "waiting_g0",
        }:
            state = "failed"
        return FactoryLeadAlignmentRead(
            invocation_id=invocation.id,
            idempotent=idempotent,
            state=state,
            context_version=invocation.context_version,
            context_pack_id=str(summary.get("context_pack_id") or ""),
            run_id=invocation.run_id,
            task_id=summary.get("task_id"),
            message_id=message.id if message else None,
            message=message.content if message else "",
            clarification_ids=list(summary.get("clarification_ids") or []),
            brief=self._brief_read(session, brief_version) if brief_version else None,
            gate=GateRead.model_validate(gate) if gate else None,
            turns_used=int(summary.get("turns_used") or 0),
            retries_used=int(summary.get("retries_used") or 0),
            requested_model=str(summary.get("requested_model") or self.settings.MODEL_NAME),
            observed_model=summary.get("observed_model"),
            usage=summary.get("usage") or {},
            checkpoint_hash=summary.get("checkpoint_hash"),
            error_code=invocation.error_code,
        )

    @staticmethod
    def _brief_read(
        session: Session, version: ProjectBriefVersion
    ) -> ProjectBriefVersionRead:
        brief = session.get(ProjectBrief, version.brief_id)
        if brief is None:
            raise FactoryLeadAlignmentError(
                "PROJECT_BRIEF_NOT_FOUND", "Project Brief 不存在。", http_status=500
            )
        return ProjectBriefVersionRead(
            project_id=brief.project_id,
            **{
                field: getattr(version, field)
                for field in ProjectBriefVersionRead.model_fields
                if field != "project_id"
            },
        )

    def _mark_failed(self, invocation_id: str, error_code: str) -> None:
        with self.session_factory.begin() as session:
            invocation = session.get(FactoryLeadInvocation, invocation_id)
            if invocation is None:
                return
            invocation.status = "failed"
            invocation.error_code = error_code
            invocation.completed_at = datetime.now(UTC)

    @staticmethod
    def _runtime_summary(result: RuntimeExecutionResult) -> dict[str, Any]:
        return {
            "run_id": result.run_id,
            "task_id": result.task_id,
            "turns_used": result.turns_used,
            "retries_used": result.retries_used,
            "requested_model": result.requested_model,
            "observed_model": result.observed_model,
            "usage": result.usage,
            "checkpoint_hash": result.checkpoint_hash,
        }

    @staticmethod
    def _validate_alignment(project: Project, expected_context_version: int) -> None:
        if project.state != "alignment":
            raise FactoryLeadAlignmentError(
                "FACTORY_LEAD_STAGE_INVALID", "Factory Lead 对齐运行只允许在 alignment 阶段。"
            )
        if project.context_version != expected_context_version:
            raise FactoryLeadAlignmentError(
                "STALE_CONTEXT", "Factory Lead 输入必须绑定项目当前 Context。"
            )

    @staticmethod
    def _stable_hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _lock(session: Session, key: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": key},
        )

    def _append_event(
        self, session: Session, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> Event:
        self._lock(session, f"project:{project_id}")
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
