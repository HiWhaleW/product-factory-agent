from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.request_logging import current_request_id
from app.domain.models import (
    AgentRun,
    AgentTask,
    Artifact,
    Gate,
    PermissionRequest,
    Project,
)
from app.services.session_auth import SessionTokenError, verify_session_token
from app.services.user_identity import UserIdentityError, get_active_user

SESSION_COOKIE_NAME = "product_factory_session"
PUBLIC_PATHS = {
    "/health",
    "/api/v1/auth/session",
    "/api/v1/auth/register",
    "/api/v1/me",
    "/docs",
    "/redoc",
    "/openapi.json",
}


@dataclass(frozen=True)
class RequestUser:
    id: str
    display_name: str
    role: str


class RequestScopeError(ValueError):
    def __init__(self, code: str, user_message: str, status_code: int) -> None:
        self.code = code
        self.user_message = user_message
        self.status_code = status_code
        super().__init__(user_message)


def _resource_project(session, path: str) -> Project | None:
    match = re.match(r"^/api/v1/projects/([^/]+)", path)
    if match:
        return session.get(Project, match.group(1))
    match = re.match(r"^/api/v1/agent-runtime/projects/([^/]+)", path)
    if match:
        return session.get(Project, match.group(1))
    match = re.match(r"^/api/v1/artifacts/([^/]+)", path)
    if match:
        artifact = session.get(Artifact, match.group(1))
        return session.get(Project, artifact.project_id) if artifact else None
    match = re.match(r"^/api/v1/tasks/([^/]+)", path)
    if match:
        task = session.get(AgentTask, match.group(1))
        return session.get(Project, task.project_id) if task else None
    match = re.match(r"^/api/v1/runs/([^/]+)", path)
    if match:
        run = session.get(AgentRun, match.group(1))
        task = session.get(AgentTask, run.task_id) if run else None
        return session.get(Project, task.project_id) if task else None
    match = re.match(r"^/api/v1/gates/([^/]+)", path)
    if match:
        gate = session.get(Gate, match.group(1))
        return session.get(Project, gate.project_id) if gate else None
    match = re.match(r"^/api/v1/permissions/([^/]+)", path)
    if match:
        permission = session.get(PermissionRequest, match.group(1))
        run = session.get(AgentRun, permission.run_id) if permission else None
        task = session.get(AgentTask, run.task_id) if run else None
        return session.get(Project, task.project_id) if task else None
    return None


def resolve_authenticated_scope(user_id: str, path: str) -> RequestUser:
    try:
        with SessionLocal() as session:
            user = get_active_user(session, user_id)
            project = _resource_project(session, path)
            restore_path = re.fullmatch(r"/api/v1/projects/[^/]+/restore", path) is not None
            if project is not None and project.deleted_at is not None and not restore_path:
                raise RequestScopeError("RESOURCE_NOT_FOUND", "资源不存在。", 404)
            if project is not None and project.owner_user_id != user.id:
                raise RequestScopeError("RESOURCE_NOT_FOUND", "资源不存在。", 404)
            if path == "/api/v1/demo/snapshot" and user.role != "admin":
                raise RequestScopeError("RESOURCE_NOT_FOUND", "资源不存在。", 404)
            return RequestUser(user.id, user.display_name, user.role)
    except RequestScopeError:
        raise
    except UserIdentityError as error:
        raise RequestScopeError(error.code, error.user_message, 401) from error
    except Exception as error:
        raise RequestScopeError(
            "IDENTITY_SERVICE_UNAVAILABLE", "身份服务暂不可用，请稍后重试。", 503
        ) from error


def auth_error(code: str, user_message: str, status_code: int) -> JSONResponse:
    request_id = current_request_id() or f"req_{uuid4()}"
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": user_message,
                "user_message": user_message,
                "retryable": False,
                "request_id": request_id,
            }
        },
    )


async def enforce_session_auth(request: Request, call_next) -> Response:
    settings = get_settings()
    request.state.auth_enforced = settings.AUTH_ENFORCED
    request.state.user_id = "local-admin"
    if not settings.AUTH_ENFORCED or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return auth_error("AUTH_REQUIRED", "请先登录后再访问造物工场。", 401)
    try:
        user_id, _ = verify_session_token(token, secret=settings.resolve_session_secret())
    except SessionTokenError as error:
        code = "SESSION_EXPIRED" if error.reason == "expired" else "SESSION_INVALID"
        message = (
            "登录已过期，请重新登录。"
            if error.reason == "expired"
            else "登录状态无效，请重新登录。"
        )
        return auth_error(code, message, 401)
    try:
        user = resolve_authenticated_scope(user_id, request.url.path)
    except RequestScopeError as error:
        return auth_error(error.code, error.user_message, error.status_code)
    request.state.user_id = user.id
    request.state.user_display_name = user.display_name
    request.state.user_role = user.role
    return await call_next(request)
