from collections.abc import Generator

from app.api.router import router
from app.core.config import get_settings
from app.core.database import get_session
from app.services.codex_user_runtime import (
    CodexCapabilityChecks,
    CodexRuntimeCapability,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def capability() -> CodexRuntimeCapability:
    return CodexRuntimeCapability(
        configured=True,
        compatibility="compatible",
        config_version="a" * 64,
        checked_at="2026-08-27T14:00:00+00:00",
        checks=CodexCapabilityChecks(
            app_server=True,
            responses_api=True,
            streaming=True,
            structured_output=True,
            tool_calling=True,
            secret_isolation=True,
        ),
        user_message="Codex 兼容性检测通过。",
    )


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def session_override() -> Generator[object, None, None]:
        yield object()

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: object()
    return app


def test_codex_runtime_status_is_user_scoped_and_secret_free(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_status(session, *, settings, user_id, role):
        calls.append((user_id, role))
        return capability()

    monkeypatch.setattr(
        "app.api.router.codex_runtime_capability_status", fake_status
    )

    with TestClient(make_app()) as client:
        response = client.get("/api/v1/me/codex-runtime")

    assert response.status_code == 200
    assert response.json()["compatibility"] == "compatible"
    assert response.json()["checks"]["streaming"] is True
    assert "api_key" not in response.text.lower()
    assert "secret-key" not in response.text
    assert calls == [("local-admin", "admin")]


def test_codex_runtime_check_returns_capability_report_without_runtime_details(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_check(session, *, settings, user_id, role):
        calls.append((user_id, role))
        return capability()

    monkeypatch.setattr("app.api.router.run_codex_compatibility_check", fake_check)

    with TestClient(make_app()) as client:
        response = client.post("/api/v1/me/codex-runtime/compatibility")

    assert response.status_code == 200
    assert response.json()["runtime"] == "codex_app_server"
    assert set(response.json()) == {
        "runtime",
        "configured",
        "compatibility",
        "config_version",
        "checked_at",
        "checks",
        "error_code",
        "user_message",
    }
    assert "stderr" not in response.text
    assert "environment" not in response.text
    assert calls == [("local-admin", "admin")]
