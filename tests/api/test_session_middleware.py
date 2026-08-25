from types import SimpleNamespace

from app.core.session_middleware import (
    SESSION_COOKIE_NAME,
    RequestScopeError,
    RequestUser,
    _resource_project,
    enforce_session_auth,
)
from app.domain.models import Project
from app.services.session_auth import issue_session_token
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_protected_api_fails_closed_without_session(monkeypatch) -> None:
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        resolve_session_secret=lambda: "test-session-secret",
    )
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)
    protected = FastAPI()
    protected.middleware("http")(enforce_session_auth)

    @protected.get("/api/v1/protected")
    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(protected) as client:
        response = client.get("/api/v1/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_valid_http_only_session_can_access_protected_api(monkeypatch) -> None:
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        resolve_session_secret=lambda: "test-session-secret",
    )
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.core.session_middleware.resolve_authenticated_scope",
        lambda user_id, path: RequestUser(user_id, "内部管理员", "admin"),
    )
    protected = FastAPI()
    protected.middleware("http")(enforce_session_auth)

    @protected.get("/api/v1/protected")
    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    token, _ = issue_session_token(
        user_id="local-admin", secret="test-session-secret", ttl_seconds=300
    )
    with TestClient(protected) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/api/v1/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_valid_session_cannot_cross_project_scope(monkeypatch) -> None:
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        resolve_session_secret=lambda: "test-session-secret",
    )
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)

    def deny_other_project(user_id: str, path: str) -> RequestUser:
        assert user_id == "user-a"
        assert path == "/api/v1/projects/project-b"
        raise RequestScopeError("RESOURCE_NOT_FOUND", "资源不存在。", 404)

    monkeypatch.setattr(
        "app.core.session_middleware.resolve_authenticated_scope", deny_other_project
    )
    protected = FastAPI()
    protected.middleware("http")(enforce_session_auth)

    @protected.get("/api/v1/projects/project-b")
    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    token, _ = issue_session_token(
        user_id="user-a", secret="test-session-secret", ttl_seconds=300
    )
    with TestClient(protected) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/api/v1/projects/project-b")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_agent_runtime_project_routes_use_the_same_owner_scope(monkeypatch) -> None:
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        resolve_session_secret=lambda: "test-session-secret",
    )
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)

    def deny_other_project(user_id: str, path: str) -> RequestUser:
        assert user_id == "user-a"
        assert path == "/api/v1/agent-runtime/projects/project-b/prd-submissions"
        raise RequestScopeError("RESOURCE_NOT_FOUND", "资源不存在。", 404)

    monkeypatch.setattr(
        "app.core.session_middleware.resolve_authenticated_scope", deny_other_project
    )
    protected = FastAPI()
    protected.middleware("http")(enforce_session_auth)

    @protected.post("/api/v1/agent-runtime/projects/project-b/prd-submissions")
    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    token, _ = issue_session_token(
        user_id="user-a", secret="test-session-secret", ttl_seconds=300
    )
    with TestClient(protected) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.post(
            "/api/v1/agent-runtime/projects/project-b/prd-submissions"
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_agent_runtime_project_path_resolves_its_project() -> None:
    calls: list[tuple[object, str]] = []

    class SessionStub:
        def get(self, model, resource_id):
            calls.append((model, resource_id))
            return "project-record"

    resolved = _resource_project(
        SessionStub(), "/api/v1/agent-runtime/projects/project-a/prd-submissions"
    )

    assert resolved == "project-record"
    assert calls == [(Project, "project-a")]
