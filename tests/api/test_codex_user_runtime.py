from __future__ import annotations

import json
import os
import textwrap
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.adapters.codex_app_server import CodexAppServerClient
from app.domain.models import User, UserProviderCredential
from app.services.codex_user_runtime import (
    CODEX_PROVIDER_ENV_KEY,
    codex_runtime_capability_status,
    prepare_user_codex_config,
    run_codex_compatibility_check,
    user_codex_home,
)
from app.services.user_credentials import save_credential
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    UserProviderCredential.__table__.create(engine)
    session = Session(engine)
    session.add_all(
        [
            User(
                id=user_id,
                username=user_id,
                password_hash=f"disabled${user_id}",
                display_name=user_id,
                role="user",
                status="active",
            )
            for user_id in ("user-a", "user-b")
        ]
    )
    session.commit()
    return session


def make_fake_codex(tmp_path: Path, *, version_mismatch: bool = False) -> Path:
    executable = tmp_path / ("codex-mismatch" if version_mismatch else "codex")
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from pathlib import Path

            expected_version = "codex-cli 0.149.0-alpha.4.3"
            if sys.argv[1:] == ["--version"]:
                print("codex-cli 0.0.0" if {version_mismatch!r} else expected_version)
                raise SystemExit(0)
            if sys.argv[1:] != ["app-server", "--listen", "stdio://"]:
                raise SystemExit(64)

            home = Path(os.environ["CODEX_HOME"])
            secret = os.environ["{CODEX_PROVIDER_ENV_KEY}"]
            config = (home / "config.toml").read_text(encoding="utf-8")
            if secret in config or "{CODEX_PROVIDER_ENV_KEY}" not in config:
                raise SystemExit(65)

            def receive():
                line = sys.stdin.readline()
                if not line:
                    raise SystemExit(0)
                return json.loads(line)

            def send(message):
                print(json.dumps(message, separators=(",", ":")), flush=True)

            initialize = receive()
            send({{"id": initialize["id"], "result": {{"userAgent": "fake-e2"}}}})
            if receive().get("method") != "initialized":
                raise SystemExit(66)
            thread_start = receive()
            send({{
                "id": thread_start["id"],
                "result": {{
                    "thread": {{"id": "thread-e2"}},
                    "model": "test-model",
                    "modelProvider": "product_factory_user",
                    "cwd": thread_start["params"]["cwd"],
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": {{"type": "readOnly"}},
                }},
            }})

            first_turn = receive()
            send({{"id": first_turn["id"], "result": {{"turn": {{"id": "turn-1"}}}}}})
            send({{
                "method": "item/agentMessage/delta",
                "params": {{
                    "threadId": "thread-e2",
                    "turnId": "turn-1",
                    "itemId": "agent-1",
                    "delta": "E2",
                }},
            }})
            structured_text = json.dumps({{"message": "E2_CODEX_COMPATIBILITY_OK"}})
            structured_item = {{
                "id": "agent-1",
                "type": "agentMessage",
                "text": structured_text,
            }}
            send({{
                "method": "item/completed",
                "params": {{
                    "threadId": "thread-e2",
                    "turnId": "turn-1",
                    "item": structured_item,
                    "completedAtMs": 1,
                }},
            }})
            send({{
                "method": "turn/completed",
                "params": {{
                    "threadId": "thread-e2",
                    "turn": {{"id": "turn-1", "status": "completed", "items": [structured_item]}},
                }},
            }})

            second_turn = receive()
            send({{"id": second_turn["id"], "result": {{"turn": {{"id": "turn-2"}}}}}})
            marker = Path("capability-marker.txt").read_text(encoding="utf-8")
            command_item = {{"id": "command-1", "type": "commandExecution", "status": "completed"}}
            agent_item = {{"id": "agent-2", "type": "agentMessage", "text": marker}}
            for item in (command_item, agent_item):
                send({{
                    "method": "item/completed",
                    "params": {{
                        "threadId": "thread-e2",
                        "turnId": "turn-2",
                        "item": item,
                        "completedAtMs": 2,
                    }},
                }})
            send({{
                "method": "turn/completed",
                "params": {{
                    "threadId": "thread-e2",
                    "turn": {{
                        "id": "turn-2",
                        "status": "completed",
                        "items": [command_item, agent_item],
                    }},
                }},
            }})
            for _line in sys.stdin:
                pass
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def runtime_settings(tmp_path: Path, codex_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        USER_SECRET_ROOT=tmp_path / "secrets",
        CODEX_USER_HOME_ROOT=tmp_path / "codex-users",
        CODEX_CLI_PATH=codex_path,
        CODEX_COMPATIBILITY_TIMEOUT_SECONDS=5,
    )


def save_user_credential(
    session: Session,
    settings: SimpleNamespace,
    user_id: str,
    api_key: str,
) -> None:
    save_credential(
        session,
        settings=settings,
        user_id=user_id,
        provider_name="用户模型服务",
        base_url="https://models.example.com/v1",
        model_name="test-model",
        api_key=api_key,
    )
    session.commit()


def test_user_codex_config_is_isolated_versioned_and_secret_free(tmp_path: Path) -> None:
    session = make_session()
    settings = runtime_settings(tmp_path, make_fake_codex(tmp_path))
    api_key = "user-a-secret-key-1234"
    save_user_credential(session, settings, "user-a", api_key)

    home, config_version, resolved_key = prepare_user_codex_config(
        session,
        settings=settings,
        user_id="user-a",
        role="user",
    )

    config_path = home / "config.toml"
    config_text = config_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(config_text)
    assert resolved_key == api_key
    assert api_key not in config_text
    assert parsed["model"] == "test-model"
    assert parsed["model_provider"] == "product_factory_user"
    assert parsed["model_providers"]["product_factory_user"]["env_key"] == (
        CODEX_PROVIDER_ENV_KEY
    )
    assert parsed["shell_environment_policy"]["include_only"] == ["HOME", "PATH"]
    assert config_version in config_text
    assert config_path.stat().st_mode & 0o077 == 0
    assert user_codex_home(settings, "user-a") != user_codex_home(settings, "user-b")


def test_compatibility_check_proves_streaming_tools_and_secret_isolation(
    tmp_path: Path,
) -> None:
    session = make_session()
    settings = runtime_settings(tmp_path, make_fake_codex(tmp_path))
    api_key = "user-a-secret-key-5678"
    save_user_credential(session, settings, "user-a", api_key)

    report = run_codex_compatibility_check(
        session,
        settings=settings,
        user_id="user-a",
        role="user",
    )

    assert report.compatibility == "compatible"
    assert report.checks.app_server is True
    assert report.checks.responses_api is True
    assert report.checks.streaming is True
    assert report.checks.structured_output is True
    assert report.checks.tool_calling is True
    assert report.checks.secret_isolation is True
    report_path = user_codex_home(settings, "user-a") / "compatibility-report.json"
    assert api_key not in report_path.read_text(encoding="utf-8")
    assert report_path.stat().st_mode & 0o077 == 0
    assert codex_runtime_capability_status(
        session,
        settings=settings,
        user_id="user-a",
        role="user",
    ) == report


def test_credential_change_invalidates_report_without_crossing_users(tmp_path: Path) -> None:
    session = make_session()
    settings = runtime_settings(tmp_path, make_fake_codex(tmp_path))
    save_user_credential(session, settings, "user-a", "user-a-secret-key-0001")
    save_user_credential(session, settings, "user-b", "user-b-secret-key-0002")
    first = run_codex_compatibility_check(
        session, settings=settings, user_id="user-a", role="user"
    )

    save_user_credential(session, settings, "user-a", "user-a-secret-key-0003")
    changed = codex_runtime_capability_status(
        session, settings=settings, user_id="user-a", role="user"
    )
    untouched = codex_runtime_capability_status(
        session, settings=settings, user_id="user-b", role="user"
    )

    assert changed.compatibility == "untested"
    assert changed.config_version != first.config_version
    assert untouched.compatibility == "untested"
    assert untouched.config_version not in {first.config_version, changed.config_version}


def test_version_mismatch_returns_safe_report_without_secret(tmp_path: Path) -> None:
    session = make_session()
    settings = runtime_settings(
        tmp_path,
        make_fake_codex(tmp_path, version_mismatch=True),
    )
    api_key = "user-a-secret-key-9999"
    save_user_credential(session, settings, "user-a", api_key)

    report = run_codex_compatibility_check(
        session, settings=settings, user_id="user-a", role="user"
    )

    assert report.compatibility == "incompatible"
    assert report.error_code == "CODEX_VERSION_MISMATCH"
    assert api_key not in json.dumps(report.__dict__, default=str)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_CODEX_APP_SERVER_INTEGRATION") != "1",
    reason="requires the pinned real Codex app-server binary",
)
def test_real_codex_accepts_generated_user_provider_config(tmp_path: Path) -> None:
    session = make_session()
    settings = runtime_settings(
        tmp_path,
        Path(os.environ["CODEX_APP_SERVER_INTEGRATION_BINARY"]),
    )
    save_user_credential(session, settings, "user-a", "non-production-test-key")
    home, _, api_key = prepare_user_codex_config(
        session, settings=settings, user_id="user-a", role="user"
    )

    with CodexAppServerClient(
        settings.CODEX_CLI_PATH,
        cwd=tmp_path,
        request_timeout_seconds=30,
        shutdown_timeout_seconds=10,
        environment={
            "CODEX_HOME": str(home),
            CODEX_PROVIDER_ENV_KEY: api_key,
        },
    ) as client:
        thread_id = client.start_thread(
            ephemeral=True,
            approval_policy="never",
            sandbox="read-only",
        )

        assert thread_id

    assert client.is_running is False
    assert client.returncode == 0
    assert client.used_forceful_shutdown is False
