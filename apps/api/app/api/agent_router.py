from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.adapters.bocha import BochaAdapter
from app.agents.prd_contracts import (
    PrdReviewCreate,
    PrdReviewerInputRead,
    PrdReviewRead,
    PrdSubmissionCreate,
    PrdSubmissionRead,
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
)
from app.services.prd_definition import (
    PrdDefinitionError,
    lock_prd_scope,
    prd_reviewer_input,
    submit_prd,
    submit_prd_review,
)


class AgentRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_pack_id: str = Field(min_length=1, max_length=36)
    user_input: str = Field(min_length=1, max_length=50_000)


@lru_cache
def runtime_service() -> AgentRuntimeService:
    settings = get_settings()
    research_provider = (
        BochaAdapter.from_settings(settings) if settings.web_research_ready else None
    )
    return AgentRuntimeService(settings, research_provider=research_provider)


def get_agent_runtime() -> AgentRuntimeService:
    return runtime_service()


@lru_cache
def factory_lead_service() -> FactoryLeadAlignmentService:
    return FactoryLeadAlignmentService(get_settings())


def get_factory_lead_service() -> FactoryLeadAlignmentService:
    return factory_lead_service()


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
