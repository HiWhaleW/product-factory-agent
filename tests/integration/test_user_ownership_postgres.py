from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import (
    AgentRun,
    AgentTask,
    Event,
    IdempotencyRecord,
    Project,
    User,
    UserInvite,
)
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL database",
    ),
]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_invited_users_only_see_their_own_projects(monkeypatch) -> None:
    namespace = str(uuid4())
    code_a = f"user-a-{namespace}"
    code_b = f"user-b-{namespace}"
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        APP_ENV="test",
        INVITE_CODE_HASH="0" * 64,
        SESSION_TTL_SECONDS=300,
        session_auth_ready=True,
        resolve_session_secret=lambda: f"session-secret-{namespace}",
    )
    invite_ids: list[str] = []
    user_ids: list[str] = []
    project_ids: list[str] = []
    idempotency_keys = [f"{namespace}-a-project", f"{namespace}-b-project"]
    with SessionLocal.begin() as session:
        invite_a = UserInvite(
            code_hash=_hash(code_a),
            display_name="测试用户 A",
            role="user",
            status="active",
            max_uses=1,
        )
        invite_b = UserInvite(
            code_hash=_hash(code_b),
            display_name="测试用户 B",
            role="user",
            status="active",
            max_uses=1,
        )
        session.add_all([invite_a, invite_b])
        session.flush()
        invite_ids.extend([invite_a.id, invite_b.id])

    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)
    try:
        with TestClient(app) as client_a, TestClient(app) as client_b:
            login_a = client_a.post(
                "/api/v1/auth/session", json={"invite_code": code_a}
            )
            login_b = client_b.post(
                "/api/v1/auth/session", json={"invite_code": code_b}
            )
            assert login_a.status_code == 200, login_a.text
            assert login_b.status_code == 200, login_b.text
            user_a = login_a.json()
            user_b = login_b.json()
            user_ids.extend([user_a["user_id"], user_b["user_id"]])
            assert user_a["display_name"] == "测试用户 A"
            assert user_b["display_name"] == "测试用户 B"
            assert user_a["user_id"] != user_b["user_id"]

            assert client_a.get("/api/v1/projects").json() == []
            assert client_b.get("/api/v1/projects").json() == []

            created_a = client_a.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": idempotency_keys[0]},
                json={"name": "A 的项目"},
            )
            assert created_a.status_code == 201, created_a.text
            project_a = created_a.json()
            project_ids.append(project_a["id"])
            assert project_a["owner_user_id"] == user_a["user_id"]
            assert [item["id"] for item in client_a.get("/api/v1/projects").json()] == [
                project_a["id"]
            ]
            assert client_b.get("/api/v1/projects").json() == []
            assert client_b.get(f"/api/v1/projects/{project_a['id']}").status_code == 404
            assert client_b.get(f"/api/v1/projects/{project_a['id']}/graph").status_code == 404

            with SessionLocal.begin() as session:
                task = AgentTask(
                    project_id=project_a["id"],
                    assigned_agent="factory-lead",
                    title="删除保护测试",
                    state="running",
                    context_version=1,
                )
                session.add(task)
                session.flush()
                run = AgentRun(task_id=task.id, state="running", input_hash="d" * 64)
                session.add(run)
                session.flush()
                run_id = run.id

            blocked = client_a.request(
                "DELETE",
                f"/api/v1/projects/{project_a['id']}",
                json={"confirm_name": project_a["name"]},
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "PROJECT_RUN_ACTIVE"
            with SessionLocal.begin() as session:
                session.get(AgentRun, run_id).state = "failed"

            wrong_name = client_a.request(
                "DELETE",
                f"/api/v1/projects/{project_a['id']}",
                json={"confirm_name": "错误项目名"},
            )
            assert wrong_name.status_code == 409
            assert wrong_name.json()["error"]["code"] == "PROJECT_DELETE_CONFIRMATION_MISMATCH"
            foreign_delete = client_b.request(
                "DELETE",
                f"/api/v1/projects/{project_a['id']}",
                json={"confirm_name": project_a["name"]},
            )
            assert foreign_delete.status_code == 404

            removed = client_a.request(
                "DELETE",
                f"/api/v1/projects/{project_a['id']}",
                json={"confirm_name": project_a["name"]},
            )
            assert removed.status_code == 204, removed.text
            assert client_a.get("/api/v1/projects").json() == []
            assert client_a.get(f"/api/v1/projects/{project_a['id']}").status_code == 404
            with SessionLocal() as session:
                deleted_project = session.get(Project, project_a["id"])
                assert deleted_project is not None
                assert deleted_project.deleted_at is not None
                assert session.scalar(
                    select(Event).where(
                        Event.project_id == project_a["id"],
                        Event.event_type == "project.deleted",
                    )
                ) is not None

            trash_a = client_a.get("/api/v1/projects/trash")
            assert trash_a.status_code == 200, trash_a.text
            assert [item["id"] for item in trash_a.json()] == [project_a["id"]]
            assert trash_a.json()[0]["deleted_at"] is not None
            assert client_b.get("/api/v1/projects/trash").json() == []
            assert (
                client_b.post(f"/api/v1/projects/{project_a['id']}/restore").status_code
                == 404
            )

            restored = client_a.post(f"/api/v1/projects/{project_a['id']}/restore")
            assert restored.status_code == 200, restored.text
            assert restored.json()["id"] == project_a["id"]
            repeated_restore = client_a.post(
                f"/api/v1/projects/{project_a['id']}/restore"
            )
            assert repeated_restore.status_code == 200, repeated_restore.text
            assert client_a.get("/api/v1/projects/trash").json() == []
            assert [item["id"] for item in client_a.get("/api/v1/projects").json()] == [
                project_a["id"]
            ]
            assert client_a.get(f"/api/v1/projects/{project_a['id']}").status_code == 200
            with SessionLocal() as session:
                restored_project = session.get(Project, project_a["id"])
                assert restored_project is not None
                assert restored_project.deleted_at is None
                restored_events = list(
                    session.scalars(
                        select(Event).where(
                            Event.project_id == project_a["id"],
                            Event.event_type == "project.restored",
                        )
                    )
                )
                assert len(restored_events) == 1

            created_b = client_b.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": idempotency_keys[1]},
                json={"name": "B 的项目", "owner_user_id": user_a["user_id"]},
            )
            assert created_b.status_code == 403
            created_b = client_b.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": idempotency_keys[1]},
                json={"name": "B 的项目"},
            )
            assert created_b.status_code == 201, created_b.text
            project_b = created_b.json()
            project_ids.append(project_b["id"])
            assert project_b["owner_user_id"] == user_b["user_id"]
            assert [item["id"] for item in client_b.get("/api/v1/projects").json()] == [
                project_b["id"]
            ]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        with SessionLocal.begin() as session:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
            )
            if project_ids:
                session.execute(delete(Project).where(Project.id.in_(project_ids)))
            session.execute(delete(UserInvite).where(UserInvite.id.in_(invite_ids)))
            if user_ids:
                session.execute(delete(User).where(User.id.in_(user_ids)))
