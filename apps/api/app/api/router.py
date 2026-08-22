import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.adapters.codex_cli import smoke_codex_cli
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.request_logging import current_request_id
from app.domain.models import (
    AgentMembership,
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactEdge,
    ArtifactVersion,
    ClarificationRecord,
    ContextPack,
    ContextVersion,
    Event,
    Gate,
    GateDecision,
    IdempotencyRecord,
    Message,
    PermissionDecision,
    PermissionRequest,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
    RunStep,
    TaskDependency,
    ToolRun,
)
from app.domain.schemas import (
    AgentArtifactProposal,
    AgentMembershipRead,
    ArtifactContentRead,
    ArtifactVersionIndexRead,
    ArtifactVersionRead,
    ClarificationCreate,
    ClarificationRead,
    ContextPackCreate,
    ContextPackRead,
    ContextResourceRef,
    ContextVersionRead,
    DefinitionReviewCreate,
    DefinitionReviewerInputRead,
    DefinitionReviewRead,
    DefinitionSubmissionCreate,
    DefinitionSubmissionRead,
    EventRead,
    ExecutionRunRead,
    GateDecisionCreate,
    GateDecisionRead,
    GateOpenCreate,
    GateRead,
    GraphEdge,
    GraphNode,
    GraphRead,
    MessageCreate,
    MessageRead,
    PermissionDecisionCreate,
    PermissionRequestRead,
    ProjectBriefCreate,
    ProjectBriefCreateResult,
    ProjectBriefVersionRead,
    ProjectCreate,
    ProjectExecutionRead,
    ProjectRead,
    RunRead,
    RunResumeCreate,
    RunStepRead,
    RuntimeStatusRead,
    SessionCreate,
    SessionRead,
    TaskClaimCreate,
    TaskRead,
    ToolRunRead,
)
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact
from app.services.control_plane import (
    ControlPlaneError,
    validate_context_binding,
    validate_gate_artifact_kinds,
    validate_gate_open,
    validate_transition,
)
from app.services.definition_chain import (
    DefinitionChainError,
    reviewer_input,
    submit_definition,
    submit_definition_review,
)
from app.services.session_auth import (
    SessionTokenError,
    invite_code_matches,
    issue_session_token,
    verify_session_token,
)

router = APIRouter()
SESSION_COOKIE_NAME = "product_factory_session"


def api_error(code: str, user_message: str, http_status: int = 409) -> HTTPException:
    request_id = current_request_id() or f"req_{uuid4()}"
    return HTTPException(
        status_code=http_status,
        detail={
            "error": {
                "code": code,
                "message": user_message,
                "user_message": user_message,
                "retryable": False,
                "request_id": request_id,
            }
        },
    )


def advisory_xact_lock(session: Session, lock_key: str) -> None:
    """Serialize one deterministic control-plane scope for this transaction."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )


def next_sequence(session: Session, project_id: str) -> int:
    current = session.scalar(select(func.max(Event.sequence)).where(Event.project_id == project_id))
    return (current or 0) + 1


def append_event(session: Session, project_id: str, event_type: str, payload: dict) -> Event:
    advisory_xact_lock(session, f"project:{project_id}")
    event = Event(
        project_id=project_id,
        sequence=next_sequence(session, project_id),
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def input_hash(body: object) -> str:
    if hasattr(body, "model_dump"):
        body = body.model_dump(mode="json")  # type: ignore[attr-defined]
    value = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def add_idempotency(
    session: Session, *, scope: str, key: str, resource_id: str, body_hash: str
) -> None:
    session.add(
        IdempotencyRecord(
            scope=scope,
            key=key,
            resource_id=resource_id,
            input_hash=body_hash,
        )
    )


def get_idempotent_resource(
    session: Session, *, scope: str, key: str, body_hash: str
) -> IdempotencyRecord | None:
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )
    if existing and existing.input_hash != body_hash:
        raise api_error("IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同输入。")
    return existing


def create_context_version(
    session: Session,
    *,
    project: Project,
    stage: str,
    reason: str,
    gate_decision_id: str | None,
) -> ContextVersion:
    project.context_version += 1
    context = ContextVersion(
        project_id=project.id,
        version=project.context_version,
        stage=stage,
        approval_status="active",
        change_reason=reason,
        gate_decision_id=gate_decision_id,
        summary=reason,
    )
    session.add(context)
    session.flush()
    append_event(
        session,
        project.id,
        "context.updated",
        {"context_version": context.version, "stage": stage, "reason": reason},
    )
    return context


def brief_read(
    session: Session, version: ProjectBriefVersion
) -> ProjectBriefVersionRead:
    brief = session.get(ProjectBrief, version.brief_id)
    if brief is None:
        raise api_error("PROJECT_BRIEF_NOT_FOUND", "Project Brief 不存在。", 404)
    return ProjectBriefVersionRead(
        project_id=brief.project_id,
        **{
            field: getattr(version, field)
            for field in ProjectBriefVersionRead.model_fields
            if field != "project_id"
        },
    )


def context_pack_read(pack: ContextPack) -> ContextPackRead:
    refs = [ContextResourceRef.model_validate(item) for item in pack.references]
    primary = ContextResourceRef(
        resource_type=pack.primary_resource_type,
        resource_id=pack.primary_resource_id,
        version=pack.primary_resource_version,
        approval_status=pack.approval_status,
    )
    return ContextPackRead(
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


def validate_resource_ref(
    session: Session, *, project_id: str, resource: ContextResourceRef
) -> None:
    if resource.resource_type == "context_version":
        context = session.get(ContextVersion, resource.resource_id)
        if context is None or context.version != resource.version:
            raise api_error(
                "CONTEXT_RESOURCE_NOT_FOUND", "Context 引用的 ContextVersion 不存在。", 404
            )
        resource_project_id = context.project_id
        actual_status = "approved" if context.approval_status == "active" else "superseded"
    elif resource.resource_type == "project_brief":
        brief = session.get(ProjectBrief, resource.resource_id)
        version = session.scalar(
            select(ProjectBriefVersion).where(
                ProjectBriefVersion.brief_id == resource.resource_id,
                ProjectBriefVersion.version == resource.version,
            )
        )
        if brief is None or version is None:
            raise api_error("CONTEXT_RESOURCE_NOT_FOUND", "Context 引用的 Brief 版本不存在。", 404)
        resource_project_id = brief.project_id
        actual_status = version.approval_status
    else:
        artifact = session.get(Artifact, resource.resource_id)
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == resource.resource_id,
                ArtifactVersion.version == resource.version,
            )
        )
        if artifact is None or version is None:
            raise api_error("CONTEXT_RESOURCE_NOT_FOUND", "Context 引用的产物版本不存在。", 404)
        resource_project_id = artifact.project_id
        actual_status = version.approval_status
    try:
        validate_context_binding(
            project_id=project_id,
            resource_project_id=resource_project_id,
            expected_status=resource.approval_status,
            actual_status=actual_status,
        )
    except ControlPlaneError as error:
        raise api_error(error.code, error.user_message) from error


def create_context_pack_record(
    session: Session, *, project: Project, body: ContextPackCreate
) -> ContextPack:
    if body.context_version != project.context_version:
        raise api_error("STALE_CONTEXT", "Context Pack 必须绑定项目当前版本。")
    if body.stage != project.state:
        raise api_error("CONTEXT_STAGE_MISMATCH", "Context Pack 阶段与项目当前状态不一致。")
    validate_resource_ref(session, project_id=project.id, resource=body.primary_resource)
    for resource in body.required_resources:
        validate_resource_ref(session, project_id=project.id, resource=resource)
    context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project.id,
            ContextVersion.version == body.context_version,
            ContextVersion.stage == body.stage,
            ContextVersion.approval_status == "active",
        )
    )
    if context is None:
        raise api_error("CONTEXT_VERSION_NOT_FOUND", "精确 ContextVersion 不存在或未激活。", 404)
    pack = ContextPack(
        project_id=project.id,
        context_version_id=context.id,
        context_version=context.version,
        stage=body.stage,
        approval_status="approved",
        primary_resource_type=body.primary_resource.resource_type,
        primary_resource_id=body.primary_resource.resource_id,
        primary_resource_version=body.primary_resource.version,
        agent_id=body.recipient_agent_id,
        task=body.task,
        references=[item.model_dump(mode="json") for item in body.required_resources],
        policy=body.policy,
    )
    session.add(pack)
    session.flush()
    append_event(
        session,
        project.id,
        "context.pack_created",
        {
            "context_pack_id": pack.id,
            "context_version": pack.context_version,
            "stage": pack.stage,
            "recipient_agent_id": pack.agent_id,
            "primary_resource": body.primary_resource.model_dump(mode="json"),
        },
    )
    return pack


@router.get("/health")
def health(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> dict:
    session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "app_env": settings.APP_ENV,
        "database": "postgresql",
        "model_provider": settings.MODEL_PROVIDER,
        "model_configured": settings.model_ready,
    }


@router.get("/api/v1/runtime/status", response_model=RuntimeStatusRead)
def runtime_status(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> RuntimeStatusRead:
    session.execute(text("SELECT 1"))
    return RuntimeStatusRead(
        database="postgresql",
        artifact_root_configured=settings.ARTIFACT_ROOT.is_dir(),
        workspace_root_configured=settings.WORKSPACE_ROOT.is_dir(),
        model_provider=settings.MODEL_PROVIDER,
        model_configured=settings.model_ready,
        event_transport="sse_cursor",
        short_polling_degraded=True,
        codex=smoke_codex_cli(settings).model_dump(),
    )


@router.post("/api/v1/auth/session", response_model=SessionRead)
def create_session(
    body: SessionCreate,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> SessionRead:
    if not settings.session_auth_ready:
        raise api_error("AUTH_NOT_CONFIGURED", "登录尚未配置。", 503)
    if not invite_code_matches(body.invite_code, settings.INVITE_CODE_HASH):
        raise api_error("INVITE_CODE_INVALID", "邀请码无效。", 401)
    token, expires_at = issue_session_token(
        user_id="local-admin",
        secret=settings.resolve_session_secret(),
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.APP_ENV == "production",
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
        path="/",
    )
    return SessionRead(
        authenticated=True,
        user_id="local-admin",
        expires_at=expires_at,
        reason="active",
        auth_enforced=False,
    )


@router.get("/api/v1/me", response_model=SessionRead)
def get_me(
    request: Request, settings: Settings = Depends(get_settings)
) -> SessionRead:
    if not settings.session_auth_ready:
        return SessionRead(
            authenticated=False,
            user_id=None,
            expires_at=None,
            reason="auth_not_configured",
            auth_enforced=False,
        )
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return SessionRead(
            authenticated=False,
            user_id=None,
            expires_at=None,
            reason="missing",
            auth_enforced=False,
        )
    try:
        user_id, expires_at = verify_session_token(
            token, secret=settings.resolve_session_secret()
        )
    except SessionTokenError as exc:
        return SessionRead(
            authenticated=False,
            user_id=None,
            expires_at=None,
            reason=exc.reason,
            auth_enforced=False,
        )
    return SessionRead(
        authenticated=True,
        user_id=user_id,
        expires_at=expires_at,
        reason="active",
        auth_enforced=False,
    )


@router.delete("/api/v1/auth/session", response_model=SessionRead)
def delete_session(response: Response) -> SessionRead:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return SessionRead(
        authenticated=False,
        user_id=None,
        expires_at=None,
        reason="logged_out",
        auth_enforced=False,
    )


@router.post("/api/v1/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> Project:
    body_hash = input_hash(body)
    advisory_xact_lock(session, f"idempotency:project.create:{idempotency_key}")
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == "project.create",
            IdempotencyRecord.key == idempotency_key,
        )
    )
    if existing:
        if existing.input_hash != body_hash:
            raise api_error("IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同输入。")
        project = session.get(Project, existing.resource_id)
        if project is None:
            raise api_error("IDEMPOTENCY_ORPHAN", "幂等记录指向的项目不存在。", 500)
        return project

    project = Project(name=body.name, owner_user_id=body.owner_user_id)
    session.add(project)
    session.flush()
    context = ContextVersion(
        project_id=project.id,
        version=1,
        stage="alignment",
        approval_status="active",
        change_reason="project_created",
        summary="Initial alignment context",
    )
    membership = AgentMembership(
        project_id=project.id,
        agent_id="factory-lead",
        joined_context_version=1,
    )
    session.add_all([context, membership])
    session.flush()
    bootstrap_pack = ContextPack(
        project_id=project.id,
        context_version_id=context.id,
        context_version=1,
        stage="alignment",
        approval_status="approved",
        primary_resource_type="context_version",
        primary_resource_id=context.id,
        primary_resource_version=1,
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
    session.add(bootstrap_pack)
    session.flush()
    session.add(
        IdempotencyRecord(
            scope="project.create",
            key=idempotency_key,
            resource_id=project.id,
            input_hash=body_hash,
        )
    )
    append_event(session, project.id, "project.created", {"name": project.name})
    append_event(
        session,
        project.id,
        "agent.joined",
        {
            "agent_id": "factory-lead",
            "membership_id": membership.id,
            "context_version": 1,
        },
    )
    append_event(
        session,
        project.id,
        "context.pack_created",
        {
            "context_pack_id": bootstrap_pack.id,
            "context_version": 1,
            "stage": "alignment",
            "recipient_agent_id": "factory-lead",
            "primary_resource_type": "context_version",
            "primary_resource_id": context.id,
            "primary_resource_version": 1,
        },
    )
    session.commit()
    return project


@router.get("/api/v1/projects", response_model=list[ProjectRead])
def list_projects(
    owner_user_id: str = Query(default="local-admin"),
    session: Session = Depends(get_session),
) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .where(Project.owner_user_id == owner_user_id)
            .order_by(Project.updated_at.desc())
        )
    )


@router.get("/api/v1/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    return project


@router.post(
    "/api/v1/projects/{project_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    project_id: str, body: MessageCreate, session: Session = Depends(get_session)
) -> Message:
    advisory_xact_lock(session, f"project:{project_id}")
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing = session.scalar(
        select(Message).where(
            Message.project_id == project_id,
            Message.client_message_id == body.client_message_id,
        )
    )
    if existing:
        if existing.content != body.content:
            raise api_error("MESSAGE_ID_CONFLICT", "同一消息 ID 不能用于不同内容。")
        return existing
    message = Message(
        project_id=project_id,
        client_message_id=body.client_message_id,
        actor_type="user",
        actor_id=body.actor_id,
        content=body.content,
    )
    session.add(message)
    session.flush()
    append_event(session, project_id, "message.created", {"message_id": message.id})
    session.commit()
    return message


@router.get("/api/v1/projects/{project_id}/messages", response_model=list[MessageRead])
def list_messages(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[Message]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    return list(
        session.scalars(
            select(Message)
            .where(Message.project_id == project_id)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
        )
    )


@router.post(
    "/api/v1/projects/{project_id}/clarifications",
    response_model=ClarificationRead,
    status_code=status.HTTP_201_CREATED,
)
def record_clarification(
    project_id: str,
    body: ClarificationCreate,
    session: Session = Depends(get_session),
) -> ClarificationRecord:
    advisory_xact_lock(session, f"project:{project_id}")
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing = session.scalar(
        select(ClarificationRecord).where(
            ClarificationRecord.project_id == project_id,
            ClarificationRecord.client_clarification_id == body.client_clarification_id,
        )
    )
    if existing:
        comparable = {
            "question": existing.question,
            "answer": existing.answer,
            "scope_impact": existing.scope_impact,
            "expected_context_version": existing.context_version,
            "created_by": existing.created_by,
            "client_clarification_id": existing.client_clarification_id,
        }
        if input_hash(comparable) != input_hash(body):
            raise api_error(
                "CLARIFICATION_ID_CONFLICT",
                "同一 clarification ID 不能用于不同澄清内容。",
            )
        return existing
    if body.expected_context_version != project.context_version:
        raise api_error("STALE_CONTEXT", "澄清记录必须绑定项目当前 Context。")
    if project.state != "alignment":
        raise api_error("CLARIFICATION_STAGE_INVALID", "只允许在项目对齐阶段记录范围澄清。")
    clarification = ClarificationRecord(
        project_id=project_id,
        client_clarification_id=body.client_clarification_id,
        question=body.question,
        answer=body.answer,
        scope_impact=body.scope_impact,
        context_version=body.expected_context_version,
        created_by=body.created_by,
    )
    session.add(clarification)
    session.flush()
    append_event(
        session,
        project_id,
        "clarification.recorded",
        {
            "clarification_id": clarification.id,
            "context_version": clarification.context_version,
            "scope_impact": clarification.scope_impact,
        },
    )
    session.commit()
    return clarification


@router.get(
    "/api/v1/projects/{project_id}/clarifications",
    response_model=list[ClarificationRead],
)
def list_clarifications(
    project_id: str,
    context_version: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_session),
) -> list[ClarificationRecord]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    statement = select(ClarificationRecord).where(ClarificationRecord.project_id == project_id)
    if context_version is not None:
        statement = statement.where(ClarificationRecord.context_version == context_version)
    return list(session.scalars(statement.order_by(ClarificationRecord.created_at)))


@router.post(
    "/api/v1/projects/{project_id}/briefs",
    response_model=ProjectBriefCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_project_brief(
    project_id: str,
    body: ProjectBriefCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> ProjectBriefCreateResult:
    scope = f"project.brief:{project_id}"
    body_hash = input_hash(body)
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(session, f"idempotency:{scope}:{idempotency_key}")
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing_record = get_idempotent_resource(
        session, scope=scope, key=idempotency_key, body_hash=body_hash
    )
    if existing_record:
        version = session.get(ProjectBriefVersion, existing_record.resource_id)
        gate = session.scalar(
            select(Gate).where(
                Gate.project_id == project_id,
                Gate.gate_type == "G0",
                Gate.context_version == version.context_version if version else False,
            )
        )
        if version is None or gate is None:
            raise api_error("IDEMPOTENCY_ORPHAN", "幂等记录指向的 Brief/G0 不存在。", 500)
        return ProjectBriefCreateResult(
            brief=brief_read(session, version), gate=GateRead.model_validate(gate), idempotent=True
        )
    if project.state != "alignment":
        raise api_error("PROJECT_BRIEF_STAGE_INVALID", "Project Brief 只能在项目对齐阶段创建。")
    if project.context_version != body.expected_context_version:
        raise api_error("STALE_CONTEXT", "Project Brief 必须绑定项目当前 Context。")
    clarification_ids = set(body.source_clarification_ids)
    if clarification_ids:
        found = set(
            session.scalars(
                select(ClarificationRecord.id).where(
                    ClarificationRecord.project_id == project_id,
                    ClarificationRecord.id.in_(clarification_ids),
                    ClarificationRecord.context_version == project.context_version,
                )
            )
        )
        if found != clarification_ids:
            raise api_error(
                "CLARIFICATION_BINDING_INVALID",
                "Brief 引用了其他项目、其他 Context 或不存在的澄清记录。",
            )
    brief = session.scalar(select(ProjectBrief).where(ProjectBrief.project_id == project_id))
    if brief is None:
        brief = ProjectBrief(project_id=project_id, latest_version=0)
        session.add(brief)
        session.flush()
    if brief.latest_version != body.expected_previous_version:
        raise api_error("BRIEF_VERSION_CONFLICT", "Project Brief 前置版本已变化，请刷新。")
    if session.scalar(
        select(Gate).where(
            Gate.project_id == project_id,
            Gate.gate_type == "G0",
            Gate.status == "open",
        )
    ):
        raise api_error("GATE_ALREADY_OPEN", "当前已有待决定的 G0。")
    version = ProjectBriefVersion(
        brief_id=brief.id,
        version=brief.latest_version + 1,
        context_version=project.context_version,
        approval_status="draft",
        objective=body.objective,
        target_users=body.target_users,
        success_criteria=body.success_criteria,
        in_scope=body.in_scope,
        out_of_scope=body.out_of_scope,
        timeline=body.timeline,
        open_questions=body.open_questions,
        source_clarification_ids=body.source_clarification_ids,
        created_by=body.created_by,
    )
    brief.latest_version = version.version
    session.add(version)
    session.flush()
    gate = Gate(
        project_id=project_id,
        gate_type="G0",
        context_version=project.context_version,
        status="open",
        target_state="mrd",
        reason="批准 Project Brief、目标用户、成功标准、时间和不做范围。",
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
    add_idempotency(
        session,
        scope=scope,
        key=idempotency_key,
        resource_id=version.id,
        body_hash=body_hash,
    )
    append_event(
        session,
        project_id,
        "project_brief.created" if version.version == 1 else "project_brief.versioned",
        {
            "brief_id": brief.id,
            "brief_version_id": version.id,
            "version": version.version,
            "context_version": version.context_version,
        },
    )
    append_event(
        session,
        project_id,
        "gate.opened",
        {"gate_id": gate.id, "gate_type": "G0", "context_version": gate.context_version},
    )
    session.commit()
    return ProjectBriefCreateResult(
        brief=brief_read(session, version), gate=GateRead.model_validate(gate), idempotent=False
    )


@router.get(
    "/api/v1/projects/{project_id}/briefs/{version}",
    response_model=ProjectBriefVersionRead,
)
def get_project_brief_version(
    project_id: str, version: int, session: Session = Depends(get_session)
) -> ProjectBriefVersionRead:
    brief = session.scalar(select(ProjectBrief).where(ProjectBrief.project_id == project_id))
    if brief is None:
        raise api_error("PROJECT_BRIEF_NOT_FOUND", "Project Brief 不存在。", 404)
    brief_version = session.scalar(
        select(ProjectBriefVersion).where(
            ProjectBriefVersion.brief_id == brief.id,
            ProjectBriefVersion.version == version,
        )
    )
    if brief_version is None:
        raise api_error("PROJECT_BRIEF_VERSION_NOT_FOUND", "Project Brief 版本不存在。", 404)
    return brief_read(session, brief_version)


@router.get(
    "/api/v1/projects/{project_id}/context-versions/{version}",
    response_model=ContextVersionRead,
)
def get_context_version(
    project_id: str, version: int, session: Session = Depends(get_session)
) -> ContextVersion:
    context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project_id,
            ContextVersion.version == version,
        )
    )
    if context is None:
        raise api_error("CONTEXT_VERSION_NOT_FOUND", "ContextVersion 不存在。", 404)
    return context


@router.post(
    "/api/v1/projects/{project_id}/context-packs",
    response_model=ContextPackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_context_pack(
    project_id: str,
    body: ContextPackCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> ContextPackRead:
    scope = f"context.pack:{project_id}"
    body_hash = input_hash(body)
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(session, f"idempotency:{scope}:{idempotency_key}")
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing = get_idempotent_resource(
        session, scope=scope, key=idempotency_key, body_hash=body_hash
    )
    if existing:
        pack = session.get(ContextPack, existing.resource_id)
        if pack is None:
            raise api_error("IDEMPOTENCY_ORPHAN", "幂等记录指向的 Context Pack 不存在。", 500)
        return context_pack_read(pack)
    pack = create_context_pack_record(session, project=project, body=body)
    add_idempotency(
        session,
        scope=scope,
        key=idempotency_key,
        resource_id=pack.id,
        body_hash=body_hash,
    )
    session.commit()
    return context_pack_read(pack)


@router.get(
    "/api/v1/projects/{project_id}/context-packs/exact",
    response_model=ContextPackRead,
)
def get_exact_context_pack(
    project_id: str,
    stage: str = Query(min_length=1, max_length=64),
    context_version: int = Query(ge=1),
    resource_type: Literal["context_version", "project_brief", "artifact"] = Query(),
    resource_id: str = Query(min_length=1, max_length=36),
    resource_version: int = Query(ge=1),
    approval_status: Literal["approved"] = Query(default="approved"),
    recipient_agent_id: Literal["factory-lead", "ai-pm", "builder", "reviewer"] = Query(),
    session: Session = Depends(get_session),
) -> ContextPackRead:
    pack = session.scalar(
        select(ContextPack).where(
            ContextPack.project_id == project_id,
            ContextPack.stage == stage,
            ContextPack.context_version == context_version,
            ContextPack.primary_resource_type == resource_type,
            ContextPack.primary_resource_id == resource_id,
            ContextPack.primary_resource_version == resource_version,
            ContextPack.approval_status == approval_status,
            ContextPack.agent_id == recipient_agent_id,
        )
    )
    if pack is None:
        raise api_error(
            "CONTEXT_PACK_NOT_FOUND",
            "没有匹配项目、阶段、Context、资源、版本、批准状态和 Agent 的 Context Pack。",
            404,
        )
    return context_pack_read(pack)


@router.get("/api/v1/projects/{project_id}/events", response_model=list[EventRead])
def list_events(
    project_id: str,
    response: Response,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[Event]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    events = list(
        session.scalars(
            select(Event)
            .where(Event.project_id == project_id, Event.sequence > cursor)
            .order_by(Event.sequence)
            .limit(limit)
        )
    )
    response.headers["x-event-cursor"] = str(events[-1].sequence if events else cursor)
    response.headers["x-event-transport"] = "short-polling-degraded"
    return events


@router.get("/api/v1/projects/{project_id}/events/stream")
def stream_events(
    project_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2_000),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    events = list(
        session.scalars(
            select(Event)
            .where(Event.project_id == project_id, Event.sequence > cursor)
            .order_by(Event.sequence)
            .limit(limit)
        )
    )

    def event_source():
        for event in events:
            payload = EventRead.model_validate(event).model_dump(mode="json")
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.event_type}\n"
                f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
            )
        last_cursor = events[-1].sequence if events else cursor
        yield (
            "event: stream.cursor\n"
            f"data: {json.dumps({'cursor': last_cursor, 'continuous': True})}\n\n"
        )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Event-Cursor": str(events[-1].sequence if events else cursor),
            "X-Event-Stream-Mode": "snapshot-reconnect-foundation",
        },
    )


@router.get("/api/v1/projects/{project_id}/graph", response_model=GraphRead)
def get_graph(project_id: str, session: Session = Depends(get_session)) -> GraphRead:
    nodes = list(session.scalars(select(Artifact).where(Artifact.project_id == project_id)))
    edges = list(session.scalars(select(ArtifactEdge).where(ArtifactEdge.project_id == project_id)))
    return GraphRead(
        nodes=[GraphNode.model_validate(node) for node in nodes],
        edges=[GraphEdge.model_validate(edge) for edge in edges],
    )


@router.get("/api/v1/projects/{project_id}/tasks", response_model=list[TaskRead])
def list_tasks(project_id: str, session: Session = Depends(get_session)) -> list[AgentTask]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    return list(
        session.scalars(
            select(AgentTask)
            .where(AgentTask.project_id == project_id)
            .order_by(AgentTask.created_at, AgentTask.id)
        )
    )


@router.get(
    "/api/v1/projects/{project_id}/execution",
    response_model=ProjectExecutionRead,
)
def get_project_execution(
    project_id: str, session: Session = Depends(get_session)
) -> ProjectExecutionRead:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    memberships = list(
        session.scalars(
            select(AgentMembership)
            .where(AgentMembership.project_id == project_id)
            .order_by(AgentMembership.joined_at, AgentMembership.id)
        )
    )
    tasks = list(
        session.scalars(
            select(AgentTask)
            .where(AgentTask.project_id == project_id)
            .order_by(AgentTask.created_at, AgentTask.id)
        )
    )
    task_ids = [task.id for task in tasks]
    runs = (
        list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.task_id.in_(task_ids))
                .order_by(AgentRun.started_at, AgentRun.id)
            )
        )
        if task_ids
        else []
    )
    run_ids = [run.id for run in runs]
    steps = (
        list(
            session.scalars(
                select(RunStep)
                .where(RunStep.run_id.in_(run_ids))
                .order_by(RunStep.run_id, RunStep.step_index)
            )
        )
        if run_ids
        else []
    )
    steps_by_run: dict[str, list[RunStepRead]] = {}
    for step in steps:
        steps_by_run.setdefault(step.run_id, []).append(RunStepRead.model_validate(step))
    tool_runs = (
        list(
            session.scalars(
                select(ToolRun)
                .where(ToolRun.task_id.in_(task_ids))
                .order_by(ToolRun.created_at, ToolRun.id)
            )
        )
        if task_ids
        else []
    )
    return ProjectExecutionRead(
        memberships=[AgentMembershipRead.model_validate(item) for item in memberships],
        tasks=[TaskRead.model_validate(item) for item in tasks],
        runs=[
            ExecutionRunRead(
                id=run.id,
                task_id=run.task_id,
                attempt=run.attempt,
                state=run.state,
                input_hash=run.input_hash,
                turns_used=run.turns_used,
                retries_used=run.retries_used,
                started_at=run.started_at,
                completed_at=run.completed_at,
                steps=steps_by_run.get(run.id, []),
            )
            for run in runs
        ],
        tool_runs=[ToolRunRead.model_validate(item) for item in tool_runs],
    )


@router.post("/api/v1/tasks/{task_id}/claim", response_model=TaskRead)
def claim_task(
    task_id: str, body: TaskClaimCreate, session: Session = Depends(get_session)
) -> AgentTask:
    advisory_xact_lock(session, f"task:{task_id}")
    existing = session.get(AgentTask, task_id)
    if existing is None:
        raise api_error("TASK_NOT_FOUND", "执行任务不存在。", 404)
    if existing.state != "ready" or existing.claimed_by is not None:
        raise api_error("TASK_NOT_READY", "执行任务已被认领或当前不可运行。")
    blocked_dependencies = session.scalar(
        select(func.count())
        .select_from(TaskDependency)
        .join(AgentTask, TaskDependency.depends_on_task_id == AgentTask.id)
        .where(
            TaskDependency.task_id == task_id,
            AgentTask.state != "completed",
        )
    )
    if blocked_dependencies:
        raise api_error("TASK_DEPENDENCY_BLOCKED", "上游执行任务尚未完成。")
    task = session.scalar(
        update(AgentTask)
        .where(
            AgentTask.id == task_id,
            AgentTask.state == "ready",
            AgentTask.claimed_by.is_(None),
        )
        .values(state="running", claimed_by=body.worker_id)
        .returning(AgentTask)
    )
    if task is None:
        raise api_error("TASK_NOT_READY", "执行任务已被认领或当前不可运行。")
    append_event(
        session,
        task.project_id,
        "task.claimed",
        {"task_id": task.id, "worker_id": body.worker_id},
    )
    session.commit()
    return task


@router.get("/api/v1/runs/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    task = session.get(AgentTask, run.task_id) if run else None
    if run is None or task is None:
        raise api_error("RUN_NOT_FOUND", "Agent Run 不存在。", 404)
    steps = list(
        session.scalars(
            select(RunStep).where(RunStep.run_id == run.id).order_by(RunStep.step_index)
        )
    )
    return RunRead(
        id=run.id,
        task_id=task.id,
        project_id=task.project_id,
        attempt=run.attempt,
        state=run.state,
        input_hash=run.input_hash,
        resume_token=run.resume_token,
        turns_used=run.turns_used,
        retries_used=run.retries_used,
        started_at=run.started_at,
        completed_at=run.completed_at,
        steps=[RunStepRead.model_validate(step) for step in steps],
    )


@router.post("/api/v1/runs/{run_id}/resume")
def resume_run(
    run_id: str, body: RunResumeCreate, session: Session = Depends(get_session)
) -> dict:
    advisory_xact_lock(session, f"run:{run_id}")
    run = session.get(AgentRun, run_id)
    task = session.get(AgentTask, run.task_id) if run else None
    project = session.get(Project, task.project_id) if task else None
    if run is None or task is None or project is None:
        raise api_error("RUN_NOT_FOUND", "Agent Run 不存在。", 404)
    if run.resume_token != body.resume_token or run.input_hash != body.input_hash:
        raise api_error("RUN_RESUME_MISMATCH", "恢复令牌或输入版本不匹配。")
    if task.context_version != project.context_version:
        run.state = "stale"
        session.commit()
        raise api_error("STALE_CONTEXT", "Run 基于旧 Context，不能自动恢复。")
    if run.state in {"pending", "running"}:
        return {"run_id": run.id, "state": run.state, "idempotent": True}
    if run.state not in {"failed", "paused", "stale", "waiting", "waiting_for_human"}:
        raise api_error("RUN_NOT_RESUMABLE", "当前 Run 状态不可恢复。")
    unresolved_effect = session.scalar(
        select(RunStep).where(
            RunStep.run_id == run.id,
            RunStep.state.in_(["started", "running"]),
            RunStep.idempotency_key.is_not(None),
            RunStep.external_effect_confirmed.is_(False),
        )
    )
    if unresolved_effect is not None:
        raise api_error("SIDE_EFFECT_RECONCILIATION_REQUIRED", "外部副作用尚未对账，拒绝盲目重试。")
    run.state = "pending"
    run.completed_at = None
    append_event(
        session,
        project.id,
        "run.resumed",
        {"run_id": run.id, "task_id": task.id},
    )
    session.commit()
    return {"run_id": run.id, "state": run.state, "idempotent": False}


@router.post(
    "/api/v1/projects/{project_id}/definition-artifacts",
    response_model=ArtifactVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_definition_artifact(
    project_id: str,
    body: AgentArtifactProposal,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ArtifactVersion:
    scope = f"definition.artifact:{project_id}"
    body_hash = input_hash(body)
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(session, f"idempotency:{scope}:{idempotency_key}")
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing = get_idempotent_resource(
        session, scope=scope, key=idempotency_key, body_hash=body_hash
    )
    if existing:
        version = session.get(ArtifactVersion, existing.resource_id)
        if version is None:
            raise api_error("IDEMPOTENCY_ORPHAN", "幂等记录指向的产物版本不存在。", 500)
        return version
    if body.project_id != project_id:
        raise api_error("ARTIFACT_PROJECT_MISMATCH", "Agent 输出的 project_id 与 API 路径不一致。")
    if project.state != "mrd":
        raise api_error("ARTIFACT_STAGE_INVALID", "D5 定义产物只能在 MRD 阶段提交。")
    if project.context_version != body.context_version:
        raise api_error("STALE_CONTEXT", "Agent 产物基于旧 Context，禁止合并。")
    try:
        read_verified_artifact(settings.ARTIFACT_ROOT, body.content_ref, body.content_hash)
    except ArtifactStoreError as error:
        raise api_error("ARTIFACT_CONTENT_INVALID", str(error), 409) from error
    artifact = session.get(Artifact, body.artifact_id) if body.artifact_id else None
    if body.artifact_id and artifact is None:
        raise api_error("ARTIFACT_NOT_FOUND", "指定的产物不存在。", 404)
    if artifact is None:
        if body.expected_previous_version != 0:
            raise api_error("ARTIFACT_VERSION_CONFLICT", "新产物的前置版本必须为 0。")
        artifact = Artifact(
            project_id=project_id,
            title=body.title,
            kind=body.artifact_kind,
            stage="mrd",
            status="draft",
            latest_version=0,
            owner_agent="reviewer" if body.artifact_kind == "red_team_review" else "ai-pm",
        )
        session.add(artifact)
        session.flush()
    elif (
        artifact.project_id != project_id
        or artifact.kind != body.artifact_kind
        or artifact.stage != "mrd"
    ):
        raise api_error("ARTIFACT_BINDING_INVALID", "产物身份、类型或阶段不匹配。")
    if artifact.latest_version != body.expected_previous_version:
        raise api_error("ARTIFACT_VERSION_CONFLICT", "产物前置版本已变化，请刷新。")
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version=artifact.latest_version + 1,
        context_version=body.context_version,
        approval_status="draft",
        content_ref=body.content_ref,
        content_hash=body.content_hash,
        summary=body.summary,
        created_by="reviewer" if body.artifact_kind == "red_team_review" else "ai-pm",
    )
    artifact.latest_version = version.version
    artifact.title = body.title
    session.add(version)
    session.flush()
    add_idempotency(
        session,
        scope=scope,
        key=idempotency_key,
        resource_id=version.id,
        body_hash=body_hash,
    )
    append_event(
        session,
        project_id,
        "artifact.created" if version.version == 1 else "artifact.versioned",
        {
            "artifact_id": artifact.id,
            "artifact_version_id": version.id,
            "kind": artifact.kind,
            "version": version.version,
            "context_version": version.context_version,
            "approval_status": version.approval_status,
        },
    )
    session.commit()
    return version


@router.get(
    "/api/v1/artifacts/{artifact_id}/versions/{version}",
    response_model=ArtifactVersionRead,
)
def get_artifact_version(
    artifact_id: str, version: int, session: Session = Depends(get_session)
) -> ArtifactVersion:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise api_error("ARTIFACT_NOT_FOUND", "产物不存在。", 404)
    artifact_version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == version,
        )
    )
    if artifact_version is None:
        raise api_error("ARTIFACT_VERSION_NOT_FOUND", "产物版本不存在。", 404)
    return artifact_version


@router.get(
    "/api/v1/artifacts/{artifact_id}/versions",
    response_model=list[ArtifactVersionIndexRead],
)
def list_artifact_versions(
    artifact_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[ArtifactVersionIndexRead]:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise api_error("ARTIFACT_NOT_FOUND", "产物不存在。", 404)
    versions = list(
        session.scalars(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
            .order_by(ArtifactVersion.version.desc())
        )
    )
    result: list[ArtifactVersionIndexRead] = []
    for version in versions:
        try:
            read_verified_artifact(
                settings.ARTIFACT_ROOT, version.content_ref, version.content_hash
            )
            content_available = True
        except ArtifactStoreError:
            content_available = False
        result.append(
            ArtifactVersionIndexRead(
                artifact_id=version.artifact_id,
                version=version.version,
                context_version=version.context_version,
                approval_status=version.approval_status,
                content_hash=version.content_hash,
                summary=version.summary,
                created_by=version.created_by,
                created_at=version.created_at,
                content_available=content_available,
            )
        )
    return result


@router.get("/api/v1/artifacts/{artifact_id}/content", response_model=ArtifactContentRead)
def get_artifact_content(
    artifact_id: str,
    version: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ArtifactContentRead:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise api_error("ARTIFACT_NOT_FOUND", "产物不存在。", 404)
    requested_version = version or artifact.latest_version
    artifact_version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == requested_version,
        )
    )
    if artifact_version is None:
        raise api_error("ARTIFACT_VERSION_NOT_FOUND", "产物版本不存在。", 404)
    try:
        path, content = read_verified_artifact(
            settings.ARTIFACT_ROOT,
            artifact_version.content_ref,
            artifact_version.content_hash,
        )
    except ArtifactStoreError as error:
        raise api_error("ARTIFACT_CONTENT_INVALID", str(error), 409) from error
    safe_title = re.sub(r"[\\/:*?\"<>|]+", "-", artifact.title).strip(" .") or "artifact"
    content_type = "text/markdown" if path.suffix.lower() in {".md", ".markdown"} else "text/plain"
    return ArtifactContentRead(
        artifact_id=artifact.id,
        version=artifact_version.version,
        title=artifact.title,
        filename=f"{safe_title}{path.suffix.lower() or '.txt'}",
        content_type=content_type,
        content=content,
    )


@router.post(
    "/api/v1/projects/{project_id}/definition-submissions",
    response_model=DefinitionSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_definition_submission(
    project_id: str,
    body: DefinitionSubmissionCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DefinitionSubmissionRead:
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(
        session, f"idempotency:definition.submission:{project_id}:{idempotency_key}"
    )
    try:
        result = submit_definition(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except DefinitionChainError as error:
        raise api_error(error.code, str(error), error.http_status) from error
    session.commit()
    return result


@router.get(
    "/api/v1/projects/{project_id}/definition-submissions/{submission_id}/reviewer-input",
    response_model=DefinitionReviewerInputRead,
)
def get_definition_reviewer_input(
    project_id: str,
    submission_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DefinitionReviewerInputRead:
    try:
        return reviewer_input(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            submission_id=submission_id,
        )
    except DefinitionChainError as error:
        raise api_error(error.code, str(error), error.http_status) from error


@router.post(
    "/api/v1/projects/{project_id}/definition-submissions/{submission_id}/review",
    response_model=DefinitionReviewRead,
)
def create_definition_review(
    project_id: str,
    submission_id: str,
    body: DefinitionReviewCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DefinitionReviewRead:
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(
        session, f"idempotency:definition.review:{submission_id}:{idempotency_key}"
    )
    try:
        result = submit_definition_review(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            submission_id=submission_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except DefinitionChainError as error:
        raise api_error(error.code, str(error), error.http_status) from error
    session.commit()
    return result


@router.get("/api/v1/projects/{project_id}/gates", response_model=list[GateRead])
def list_gates(
    project_id: str,
    status_filter: Literal["open", "all"] = Query(default="open", alias="status"),
    session: Session = Depends(get_session),
) -> list[Gate]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    statement = select(Gate).where(Gate.project_id == project_id)
    if status_filter == "open":
        statement = statement.where(Gate.status == "open")
    return list(session.scalars(statement.order_by(Gate.opened_at, Gate.id)))


@router.get(
    "/api/v1/projects/{project_id}/gate-decisions",
    response_model=list[GateDecisionRead],
)
def list_gate_decisions(
    project_id: str, session: Session = Depends(get_session)
) -> list[GateDecisionRead]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    rows = session.execute(
        select(GateDecision, Gate)
        .join(Gate, GateDecision.gate_id == Gate.id)
        .where(Gate.project_id == project_id)
        .order_by(GateDecision.decided_at, GateDecision.id)
    ).all()
    return [
        GateDecisionRead(
            id=decision.id,
            gate_id=decision.gate_id,
            project_id=gate.project_id,
            gate_type=gate.gate_type,
            decision=decision.decision,
            comment=decision.comment,
            decided_by=decision.decided_by,
            context_version_before=decision.context_version_before,
            context_version_after=decision.context_version_after,
            target_state=decision.target_state,
            decided_at=decision.decided_at,
        )
        for decision, gate in rows
    ]


@router.post(
    "/api/v1/projects/{project_id}/gates",
    response_model=GateRead,
    status_code=status.HTTP_201_CREATED,
)
def open_gate(
    project_id: str,
    body: GateOpenCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> Gate:
    scope = f"gate.open:{project_id}"
    body_hash = input_hash(body)
    advisory_xact_lock(session, f"project:{project_id}")
    advisory_xact_lock(session, f"idempotency:{scope}:{idempotency_key}")
    project = session.get(Project, project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    existing = get_idempotent_resource(
        session, scope=scope, key=idempotency_key, body_hash=body_hash
    )
    if existing:
        gate = session.get(Gate, existing.resource_id)
        if gate is None:
            raise api_error("IDEMPOTENCY_ORPHAN", "幂等记录指向的 Gate 不存在。", 500)
        return gate
    if body.gate_type == "G0":
        raise api_error("G0_MANAGED_BY_BRIEF", "G0 只能由版本化 Project Brief 创建流程打开。")
    try:
        validate_gate_open(
            current_state=project.state,
            gate_type=body.gate_type,
            target_state=body.target_state,
            context_matches=project.context_version == body.context_version,
        )
    except ControlPlaneError as error:
        raise api_error(error.code, error.user_message) from error
    refs = [item.model_dump(mode="json") for item in body.impacted_artifact_refs]
    artifact_kinds: set[str] = set()
    for ref in body.impacted_artifact_refs:
        artifact = session.get(Artifact, ref.artifact_id)
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == ref.artifact_id,
                ArtifactVersion.version == ref.version,
            )
        )
        if artifact is None or version is None or artifact.project_id != project_id:
            raise api_error(
                "GATE_ARTIFACT_BINDING_INVALID",
                "Gate 引用了其他项目或不存在的产物版本。",
            )
        if artifact.stage != project.state or version.context_version != project.context_version:
            raise api_error(
                "GATE_ARTIFACT_CONTEXT_MISMATCH",
                "Gate 产物必须绑定当前项目阶段和 Context 版本。",
            )
        artifact_kinds.add(artifact.kind)
    try:
        validate_gate_artifact_kinds(body.gate_type, artifact_kinds)
    except ControlPlaneError as error:
        raise api_error(error.code, error.user_message) from error
    gate = Gate(
        project_id=project_id,
        gate_type=body.gate_type,
        context_version=body.context_version,
        status="open",
        target_state=body.target_state,
        reason=body.reason,
        impacted_artifact_refs=refs,
    )
    session.add(gate)
    session.flush()
    add_idempotency(
        session,
        scope=scope,
        key=idempotency_key,
        resource_id=gate.id,
        body_hash=body_hash,
    )
    append_event(
        session,
        project_id,
        "gate.opened",
        {
            "gate_id": gate.id,
            "gate_type": gate.gate_type,
            "context_version": gate.context_version,
            "target_state": gate.target_state,
            "impacted_artifact_refs": refs,
        },
    )
    session.commit()
    return gate


@router.get(
    "/api/v1/projects/{project_id}/permissions",
    response_model=list[PermissionRequestRead],
)
def list_permissions(
    project_id: str,
    status_filter: Literal["open", "all"] = Query(default="open", alias="status"),
    session: Session = Depends(get_session),
) -> list[PermissionRequestRead]:
    if session.get(Project, project_id) is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    statement = (
        select(PermissionRequest, AgentRun, AgentTask)
        .join(AgentRun, PermissionRequest.run_id == AgentRun.id)
        .join(AgentTask, AgentRun.task_id == AgentTask.id)
        .where(AgentTask.project_id == project_id)
    )
    if status_filter == "open":
        statement = statement.where(PermissionRequest.status == "open")
    rows = session.execute(
        statement.order_by(PermissionRequest.created_at, PermissionRequest.id)
    ).all()
    return [
        PermissionRequestRead(
            id=request.id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            tool_name=request.tool_name,
            input_hash=request.input_hash,
            risk_level=request.risk_level,
            reason=request.reason,
            redacted_parameters=request.redacted_parameters,
            context_version=task.context_version,
            status=request.status,
            expires_at=request.expires_at,
            created_at=request.created_at,
        )
        for request, run, task in rows
    ]


@router.post("/api/v1/gates/{gate_id}/decisions")
def decide_gate(
    gate_id: str, body: GateDecisionCreate, session: Session = Depends(get_session)
) -> dict:
    gate = session.get(Gate, gate_id)
    if gate is None:
        raise api_error("GATE_NOT_FOUND", "闸口不存在。", 404)
    advisory_xact_lock(session, f"project:{gate.project_id}")
    session.refresh(gate)
    existing = session.scalar(select(GateDecision).where(GateDecision.gate_id == gate_id))
    if existing:
        if (
            existing.decision != body.decision
            or existing.context_version_before != body.context_version
        ):
            raise api_error(
                "GATE_DECISION_CONFLICT", "该 Gate 已有不同的确定性决定，不能覆盖。"
            )
        return {
            "gate_id": gate_id,
            "decision": existing.decision,
            "context_version": existing.context_version_after,
            "target_state": existing.target_state,
            "idempotent": True,
        }
    if gate.status != "open":
        raise api_error("GATE_NOT_OPEN", "闸口当前不可决定。")

    project = session.get(Project, gate.project_id)
    if project is None:
        raise api_error("PROJECT_NOT_FOUND", "项目不存在。", 404)
    if (
        gate.context_version != body.context_version
        or project.context_version != body.context_version
    ):
        raise api_error("STALE_CONTEXT", "该 Gate 或项目已不在提交的 Context 版本。")
    if body.decision == "approve" and gate.target_state:
        try:
            validate_transition(project.state, gate.target_state, gate.gate_type)
        except ControlPlaneError as error:
            raise api_error(error.code, error.user_message) from error
        next_state = gate.target_state
    elif body.decision == "changes":
        next_state = project.state
    elif body.decision == "pause":
        project.paused_from_state = project.state
        next_state = "paused"
    elif body.decision == "kill":
        next_state = "killed"
    else:
        raise api_error("GATE_DECISION_INVALID", "该 Gate 决策与目标状态不兼容。")

    decision = GateDecision(
        gate_id=gate.id,
        decision=body.decision,
        comment=body.comment,
        decided_by=body.decided_by,
        context_version_before=project.context_version,
        context_version_after=project.context_version + 1,
        target_state=next_state,
    )
    session.add(decision)
    session.flush()
    previous_state = project.state
    previous_context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project.id,
            ContextVersion.version == project.context_version,
        )
    )
    if previous_context is None:
        raise api_error("CONTEXT_VERSION_NOT_FOUND", "Gate 所绑定的 ContextVersion 不存在。", 500)
    previous_context.approval_status = "superseded"
    project.state = next_state
    gate.status = {
        "approve": "approved",
        "changes": "changes_requested",
        "pause": "paused",
        "kill": "killed",
    }[body.decision]

    brief_resource: ContextResourceRef | None = None
    artifact_resources: list[ContextResourceRef] = []
    for ref in gate.impacted_artifact_refs:
        if ref.get("resource_type") == "project_brief":
            brief = session.get(ProjectBrief, ref["resource_id"])
            version = session.scalar(
                select(ProjectBriefVersion).where(
                    ProjectBriefVersion.brief_id == ref["resource_id"],
                    ProjectBriefVersion.version == ref["version"],
                )
            )
            if brief is None or version is None or brief.project_id != project.id:
                raise api_error("GATE_RESOURCE_MISSING", "G0 绑定的 Brief 版本不存在。", 500)
            version.approval_status = (
                "approved" if body.decision == "approve" else gate.status
            )
            brief_resource = ContextResourceRef(
                resource_type="project_brief",
                resource_id=brief.id,
                version=version.version,
                approval_status="approved",
            )
        elif "artifact_id" in ref:
            artifact = session.get(Artifact, ref["artifact_id"])
            version = session.scalar(
                select(ArtifactVersion).where(
                    ArtifactVersion.artifact_id == ref["artifact_id"],
                    ArtifactVersion.version == ref["version"],
                )
            )
            if artifact is None or version is None or artifact.project_id != project.id:
                raise api_error("GATE_RESOURCE_MISSING", "G1 绑定的产物版本不存在。", 500)
            version.approval_status = (
                "approved" if body.decision == "approve" else gate.status
            )
            artifact.status = version.approval_status
            if body.decision == "approve":
                artifact_resources.append(
                    ContextResourceRef(
                        resource_type="artifact",
                        resource_id=artifact.id,
                        version=version.version,
                        approval_status="approved",
                    )
                )

    context = create_context_version(
        session,
        project=project,
        stage=project.state,
        reason=f"{gate.gate_type}:{body.decision}",
        gate_decision_id=decision.id,
    )
    decision.context_version_after = context.version
    append_event(
        session,
        gate.project_id,
        "gate.decided",
        {
            "gate_id": gate.id,
            "gate_type": gate.gate_type,
            "decision": body.decision,
            "context_version_before": body.context_version,
            "context_version_after": context.version,
            "target_state": project.state,
        },
    )
    if project.state != previous_state:
        append_event(
            session,
            gate.project_id,
            "project.state_changed",
            {"from_state": previous_state, "state": project.state},
        )
    if body.decision == "approve" and gate.gate_type == "G0":
        if brief_resource is None:
            raise api_error("GATE_RESOURCE_MISSING", "G0 没有绑定 Project Brief。", 500)
        append_event(
            session,
            project.id,
            "project_brief.approved",
            {
                "brief_id": brief_resource.resource_id,
                "version": brief_resource.version,
                "context_version": context.version,
            },
        )
        pack = create_context_pack_record(
            session,
            project=project,
            body=ContextPackCreate(
                context_version=context.version,
                stage="mrd",
                recipient_agent_id="ai-pm",
                primary_resource=brief_resource,
                task="基于已批准 Project Brief 形成 Evidence Index、MRD 与 Red Team Review。",
                policy={
                    "allowed_capability_ids": ["CAP-02", "CAP-03"],
                    "forbidden_actions": [
                        "advance_project_state",
                        "approve_gate",
                        "read_secret_values",
                    ],
                },
            ),
        )
        membership = session.scalar(
            select(AgentMembership).where(
                AgentMembership.project_id == project.id,
                AgentMembership.agent_id == "ai-pm",
            )
        )
        if membership is None:
            session.add(
                AgentMembership(
                    project_id=project.id,
                    agent_id="ai-pm",
                    joined_context_version=context.version,
                )
            )
            append_event(
                session,
                project.id,
                "agent.joined",
                {
                    "agent_id": "ai-pm",
                    "context_pack_id": pack.id,
                    "context_version": context.version,
                    "responsibility": "Evidence/MRD/PRD definition",
                },
            )
    elif body.decision == "approve" and gate.gate_type == "G1":
        mrd_resources = [
            resource
            for resource in artifact_resources
            if session.get(Artifact, resource.resource_id).kind == "mrd"
        ]
        if len(mrd_resources) != 1:
            raise api_error("GATE_RESOURCE_MISSING", "G1 必须精确绑定一个 MRD 版本。", 500)
        create_context_pack_record(
            session,
            project=project,
            body=ContextPackCreate(
                context_version=context.version,
                stage="prd",
                recipient_agent_id="ai-pm",
                primary_resource=mrd_resources[0],
                required_resources=[r for r in artifact_resources if r != mrd_resources[0]],
                task="基于已批准 Evidence/MRD/Red Team Review 形成 PRD 与验收标准。",
                policy={
                    "allowed_capability_ids": ["CAP-04"],
                    "forbidden_actions": ["advance_project_state", "approve_gate"],
                },
            ),
        )
    session.commit()
    return {
        "gate_id": gate_id,
        "decision": body.decision,
        "context_version": context.version,
        "target_state": project.state,
        "idempotent": False,
    }


@router.post("/api/v1/permissions/{permission_id}/decisions")
def decide_permission(
    permission_id: str,
    body: PermissionDecisionCreate,
    session: Session = Depends(get_session),
) -> dict:
    request = session.get(PermissionRequest, permission_id)
    if request is None:
        raise api_error("PERMISSION_NOT_FOUND", "权限请求不存在。", 404)
    run = session.get(AgentRun, request.run_id)
    task = session.get(AgentTask, run.task_id) if run else None
    project = session.get(Project, task.project_id) if task else None
    if run is None or task is None or project is None:
        raise api_error("PERMISSION_SCOPE_MISSING", "权限请求关联的运行范围不存在。", 409)
    advisory_xact_lock(session, f"project:{project.id}")
    session.refresh(request)
    existing = session.scalar(
        select(PermissionDecision).where(
            PermissionDecision.permission_request_id == permission_id
        )
    )
    if existing:
        return {"permission_id": permission_id, "decision": existing.decision, "idempotent": True}
    if request.status != "open":
        raise api_error("PERMISSION_NOT_OPEN", "权限请求当前不可决定。")
    if request.expires_at is not None and request.expires_at <= datetime.now(UTC):
        request.status = "expired"
        session.commit()
        raise api_error("PERMISSION_EXPIRED", "权限请求已过期，请重新发起。")
    if task.context_version != project.context_version:
        request.status = "stale"
        session.commit()
        raise api_error("STALE_CONTEXT", "权限请求基于旧 Context，请重新发起。")
    if request.input_hash != body.input_hash:
        raise api_error("PERMISSION_INPUT_CHANGED", "工具参数已变化，原权限请求失效。")

    decision = PermissionDecision(
        permission_request_id=permission_id,
        decision=body.decision,
        input_hash=body.input_hash,
        decided_by=body.decided_by,
    )
    session.add(decision)
    request.status = "decided"
    append_event(
        session,
        project.id,
        "permission.decided",
        {"permission_id": permission_id, "decision": body.decision},
    )
    session.commit()
    return {"permission_id": permission_id, "decision": body.decision, "idempotent": False}


@router.get("/api/v1/demo/snapshot")
def demo_snapshot(settings: Settings = Depends(get_settings)) -> dict:
    if settings.APP_ENV != "development":
        raise api_error("DEMO_DISABLED", "Demo snapshot 仅在 development 可用。", 404)
    return {
        "mock": True,
        "project": {
            "id": "demo-project",
            "name": "销售复盘 Agent",
            "state": "mrd",
            "context_version": 2,
        },
        "events": [
            {"type": "project.created", "summary": "项目已创建"},
            {"type": "agent.joined", "summary": "AI PM 已入群（mock）"},
            {"type": "gate.opened", "summary": "G1 等待用户决定（mock）"},
        ],
        "graph": {
            "nodes": [
                {"id": "brief", "title": "Project Brief", "status": "approved"},
                {"id": "evidence", "title": "Evidence Index", "status": "draft"},
                {"id": "mrd", "title": "MRD", "status": "waiting_review"},
                {"id": "g1", "title": "G1", "status": "waiting_review"},
            ],
            "edges": [
                {"source": "brief", "target": "evidence"},
                {"source": "evidence", "target": "mrd"},
                {"source": "mrd", "target": "g1"},
            ],
        },
    }
