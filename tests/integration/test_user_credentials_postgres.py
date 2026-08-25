from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import User, UserProviderCredential
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


def test_two_users_have_isolated_api_keys_and_responses_never_echo_them(
    monkeypatch, tmp_path
) -> None:
    namespace = str(uuid4())
    usernames = [f"credential-a-{namespace}", f"credential-b-{namespace}"]
    passwords = [f"password-a-{namespace}", f"password-b-{namespace}"]
    keys = [f"sk-a-{namespace}", f"sk-b-{namespace}"]
    research_keys = [f"bocha-a-{namespace}", f"bocha-b-{namespace}"]
    settings = SimpleNamespace(
        AUTH_ENFORCED=True,
        APP_ENV="test",
        SESSION_TTL_SECONDS=300,
        session_auth_ready=True,
        resolve_session_secret=lambda: f"session-secret-{namespace}",
        USER_SECRET_ROOT=tmp_path / "secrets",
        model_ready=True,
        resolve_model_api_key=lambda: "internal-key-must-not-reach-users",
    )
    user_ids: list[str] = []

    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("app.core.session_middleware.get_settings", lambda: settings)
    try:
        with TestClient(app) as client_a, TestClient(app) as client_b:
            logins = [
                client.post(
                    "/api/v1/auth/register",
                    json={
                        "username": username,
                        "display_name": f"API 用户 {index}",
                        "password": password,
                    },
                ).json()
                for index, (client, username, password) in enumerate(
                    [
                        (client_a, usernames[0], passwords[0]),
                        (client_b, usernames[1], passwords[1]),
                    ],
                    start=1,
                )
            ]
            user_ids.extend(login["user_id"] for login in logins)
            for client, key in [(client_a, keys[0]), (client_b, keys[1])]:
                response = client.put(
                    "/api/v1/me/provider-credentials/model-api",
                    json={
                        "provider_name": "测试接口",
                        "base_url": "https://models.example.com/v1",
                        "model_name": "test-model",
                        "api_key": key,
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["configured"] is True
                assert key not in response.text
                assert "internal-key-must-not-reach-users" not in response.text

            for client, key in [
                (client_a, research_keys[0]),
                (client_b, research_keys[1]),
            ]:
                response = client.put(
                    "/api/v1/me/provider-credentials/web-search",
                    json={
                        "provider_name": "博查",
                        "base_url": "https://api.bochaai.com/v1",
                        "api_key": key,
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["provider_name"] == "博查"
                assert key not in response.text

            with SessionLocal() as session:
                records = session.scalars(
                    select(UserProviderCredential).where(
                        UserProviderCredential.user_id.in_(user_ids)
                    )
                ).all()
                assert len(records) == 4
                serialized = repr([record.__dict__ for record in records])
                assert all(key not in serialized for key in keys)
                assert all(key not in serialized for key in research_keys)
                assert len({record.fingerprint for record in records}) == 4

            removed = client_a.delete("/api/v1/me/provider-credentials/model-api")
            assert removed.status_code == 200
            assert removed.json()["configured"] is False
            assert client_b.get(
                "/api/v1/me/provider-credentials/model-api"
            ).json()["configured"] is True
            removed_research = client_a.delete(
                "/api/v1/me/provider-credentials/web-search"
            )
            assert removed_research.status_code == 200
            assert removed_research.json()["configured"] is False
            assert client_b.get(
                "/api/v1/me/provider-credentials/web-search"
            ).json()["configured"] is True
    finally:
        app.dependency_overrides.pop(get_settings, None)
        with SessionLocal.begin() as session:
            if user_ids:
                session.execute(
                    delete(UserProviderCredential).where(
                        UserProviderCredential.user_id.in_(user_ids)
                    )
                )
            if user_ids:
                session.execute(delete(User).where(User.id.in_(user_ids)))
