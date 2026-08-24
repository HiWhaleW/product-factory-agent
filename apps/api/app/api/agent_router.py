from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.adapters.bocha import BochaAdapter
from app.adapters.deepseek import DeepSeekAdapter
from app.agents.prd_contracts import (
    PrdReviewCreate,
    PrdReviewerInputRead,
    PrdReviewRead,
    PrdSubmissionCreate,
    PrdSubmissionRead,
)
from app.agents.solution_contracts import (
    SolutionReviewCreate,
    SolutionReviewerInputRead,
    SolutionReviewRead,
    SolutionSubmissionCreate,
    SolutionSubmissionRead,
)
from app.agents.technical_contracts import (
    TechnicalReviewCreate,
    TechnicalReviewerInputRead,
    TechnicalReviewRead,
    TechnicalSubmissionCreate,
    TechnicalSubmissionRead,
)
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.request_logging import current_request_id
from app.domain.schemas import FactoryLeadAlignmentCreate, FactoryLeadAlignmentRead
from app.services.agent_runtime import (
    AgentRuntimeError,
    AgentRuntimeService,
    RuntimeExecutionResult,
)
from app.services.factory_lead import (
    FactoryLeadAlignmentError,
    FactoryLeadAlignmentService,
    FactoryLeadRuntimeService,
)
from app.services.prd_definition import (
    PrdDefinitionError,
    lock_prd_scope,
    prd_reviewer_input,
    submit_prd,
    submit_prd_review,
)
from app.services.solution_definition import (
    lock_solution_scope,
    solution_reviewer_input,
    submit_solution,
    submit_solution_review,
)
from app.services.technical_definition import (
    lock_technical_scope,
    submit_technical_definition,
    submit_technical_review,
    technical_reviewer_input,
)
from app.services.user_credentials import UserCredentialError, resolve_model_credential


class AgentRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_pack_id: str = Field(min_length=1, max_length=36)
    user_input: str = Field(min_length=1, max_length=50_000)


def _request_provider(
    request: Request, session: Session, settings: Settings
) -> tuple[DeepSeekAdapter, str]:
    user_id = getattr(request.state, "user_id", "local-admin")
    role = getattr(request.state, "user_role", "admin")
    try:
        credential = resolve_model_credential(
            session,
            settings=settings,
            user_id=user_id,
            role=role,
        )
    except UserCredentialError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": error.code,
                    "message": error.user_message,
                    "user_message": error.user_message,
                    "retryable": False,
                    "request_id": current_request_id() or "req_user_credential",
                }
            },
        ) from error
    return DeepSeekAdapter.from_api_key(
        settings,
        credential.api_key,
        model=credential.model_name,
        base_url=credential.base_url,
    ), user_id


def get_agent_runtime(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AgentRuntimeService:
    provider, user_id = _request_provider(request, session, settings)
    research_provider = (
        BochaAdapter.from_settings(settings) if settings.web_research_ready else None
    )
    return AgentRuntimeService(
        settings,
        provider=provider,
        research_provider=research_provider,
        owner_user_id=user_id,
    )


def get_factory_lead_service(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FactoryLeadAlignmentService:
    provider, user_id = _request_provider(request, session, settings)
    runtime = FactoryLeadRuntimeService(
        settings,
        provider=provider,
        owner_user_id=user_id,
    )
    return FactoryLeadAlignmentService(settings, runtime=runtime)


def runtime_error(error: AgentRuntimeError) -> HTTPException:
    unavailable = {
        "WEB_RESEARCH_ADAPTER_UNAVAILABLE",
        "CHECKPOINT_UNAVAILABLE",
        "CHECKPOINT_INVALID",
    }
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE if error.code in unavailable else 409
    return HTTPException(
        status_code=http_status,
        detail={
            "error": {
                "code": error.code,
                "message": str(error),
                "user_message": str(error),
                "retryable": error.retryable,
                "request_id": current_request_id() or "req_agent_runtime",
            }
        },
    )


def prd_error(error: PrdDefinitionError) -> HTTPException:
    return HTTPException(
        status_code=error.http_status,
        detail={
            "error": {
                "code": error.code,
                "message": str(error),
                "user_message": str(error),
                "retryable": False,
                "request_id": current_request_id() or "req_prd_definition",
            }
        },
    )


router = APIRouter(prefix="/api/v1/agent-runtime", tags=["agent-runtime"])


@router.post(
    "/projects/{project_id}/factory-lead/alignment-runs",
    response_model=FactoryLeadAlignmentRead,
)
async def start_factory_lead_alignment(
    project_id: str,
    body: FactoryLeadAlignmentCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    service: FactoryLeadAlignmentService = Depends(get_factory_lead_service),
) -> FactoryLeadAlignmentRead:
    try:
        return await service.start(
            project_id=project_id,
            body=body,
            idempotency_key=idempotency_key,
        )
    except FactoryLeadAlignmentError as error:
        raise HTTPException(
            status_code=error.http_status,
            detail={
                "error": {
                    "code": error.code,
                    "message": str(error),
                    "user_message": str(error),
                    "retryable": error.retryable,
                    "request_id": current_request_id() or "req_factory_lead",
                }
            },
        ) from error


@router.post("/runs", response_model=RuntimeExecutionResult)
async def start_agent_run(
    body: AgentRunStart,
    runtime: AgentRuntimeService = Depends(get_agent_runtime),
) -> RuntimeExecutionResult:
    try:
        return await runtime.start(
            context_pack_id=body.context_pack_id,
            user_input=body.user_input,
        )
    except AgentRuntimeError as error:
        raise runtime_error(error) from error


@router.post("/runs/{run_id}/resume", response_model=RuntimeExecutionResult)
async def resume_agent_run(
    run_id: str,
    runtime: AgentRuntimeService = Depends(get_agent_runtime),
) -> RuntimeExecutionResult:
    try:
        return await runtime.resume_permission(run_id)
    except AgentRuntimeError as error:
        raise runtime_error(error) from error


@router.post(
    "/projects/{project_id}/prd-submissions",
    response_model=PrdSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prd_submission(
    project_id: str,
    body: PrdSubmissionCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PrdSubmissionRead:
    try:
        lock_prd_scope(session, project_id, idempotency_key)
        result = submit_prd(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result


@router.get(
    "/projects/{project_id}/prd-submissions/{submission_id}/reviewer-input",
    response_model=PrdReviewerInputRead,
)
def get_prd_reviewer_input(
    project_id: str,
    submission_id: str,
    session: Session = Depends(get_session),
) -> PrdReviewerInputRead:
    try:
        return prd_reviewer_input(
            session,
            project_id=project_id,
            submission_id=submission_id,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error


@router.post(
    "/projects/{project_id}/prd-submissions/{submission_id}/review",
    response_model=PrdReviewRead,
)
def create_prd_review(
    project_id: str,
    submission_id: str,
    body: PrdReviewCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PrdReviewRead:
    try:
        lock_prd_scope(session, project_id, idempotency_key)
        result = submit_prd_review(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            submission_id=submission_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result


@router.post(
    "/projects/{project_id}/solution-submissions",
    response_model=SolutionSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_solution_submission(
    project_id: str,
    body: SolutionSubmissionCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SolutionSubmissionRead:
    try:
        lock_solution_scope(session, project_id, idempotency_key)
        result = submit_solution(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result


@router.get(
    "/projects/{project_id}/solution-submissions/{submission_id}/reviewer-input",
    response_model=SolutionReviewerInputRead,
)
def get_solution_reviewer_input(
    project_id: str,
    submission_id: str,
    session: Session = Depends(get_session),
) -> SolutionReviewerInputRead:
    try:
        return solution_reviewer_input(
            session,
            project_id=project_id,
            submission_id=submission_id,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error


@router.post(
    "/projects/{project_id}/solution-submissions/{submission_id}/review",
    response_model=SolutionReviewRead,
)
def create_solution_review(
    project_id: str,
    submission_id: str,
    body: SolutionReviewCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SolutionReviewRead:
    try:
        lock_solution_scope(session, project_id, idempotency_key)
        result = submit_solution_review(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            submission_id=submission_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result


@router.post(
    "/projects/{project_id}/technical-submissions",
    response_model=TechnicalSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_technical_submission(
    project_id: str,
    body: TechnicalSubmissionCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TechnicalSubmissionRead:
    try:
        lock_technical_scope(session, project_id, idempotency_key)
        result = submit_technical_definition(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result


@router.get(
    "/projects/{project_id}/technical-submissions/{submission_id}/reviewer-input",
    response_model=TechnicalReviewerInputRead,
)
def get_technical_reviewer_input(
    project_id: str,
    submission_id: str,
    session: Session = Depends(get_session),
) -> TechnicalReviewerInputRead:
    try:
        return technical_reviewer_input(
            session,
            project_id=project_id,
            submission_id=submission_id,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error


@router.post(
    "/projects/{project_id}/technical-submissions/{submission_id}/review",
    response_model=TechnicalReviewRead,
)
def create_technical_review(
    project_id: str,
    submission_id: str,
    body: TechnicalReviewCreate,
    idempotency_key: str = Header(min_length=8, max_length=200, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TechnicalReviewRead:
    try:
        lock_technical_scope(session, project_id, idempotency_key)
        result = submit_technical_review(
            session,
            artifact_root=settings.ARTIFACT_ROOT,
            project_id=project_id,
            submission_id=submission_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except PrdDefinitionError as error:
        raise prd_error(error) from error
    session.commit()
    return result
