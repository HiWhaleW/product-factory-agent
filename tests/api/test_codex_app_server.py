from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest
from app.adapters.codex_app_server import (
    CODEX_APP_SERVER_CLI_VERSION,
    CodexAppServerClient,
    CodexAppServerProtocolError,
    CodexAppServerRequestError,
    CodexAppServerTimeout,
    CodexAppServerVersionError,
    verify_codex_app_server_schema,
)


def make_fake_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "codex"
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            import time

            VERSION = {CODEX_APP_SERVER_CLI_VERSION!r}
            mode = os.environ.get("FAKE_CODEX_MODE", "happy")

            if sys.argv[1:] == ["--version"]:
                print("codex-cli 0.0.0" if mode == "version-mismatch" else VERSION)
                raise SystemExit(0)
            if sys.argv[1:] != ["app-server", "--listen", "stdio://"]:
                raise SystemExit(64)

            def receive():
                line = sys.stdin.readline()
                if not line:
                    raise SystemExit(0)
                return json.loads(line)

            def send(message):
                print(json.dumps(message, separators=(",", ":")), flush=True)

            initialize = receive()
            if mode == "invalid-json":
                print("not-json", flush=True)
                raise SystemExit(0)
            if mode == "timeout":
                time.sleep(60)
                raise SystemExit(0)
            if mode == "request-error":
                send({{"id": initialize["id"], "error": {{"code": 7001, "message": "nope"}}}})
                raise SystemExit(0)
            if mode == "server-request":
                send({{
                    "id": "approval-1",
                    "method": "item/commandExecution/requestApproval",
                    "params": {{}},
                }})
                denial = receive()
                if denial.get("error", {{}}).get("code") != -32601:
                    raise SystemExit(65)
            send({{"id": initialize["id"], "result": {{"userAgent": "fake"}}}})
            initialized = receive()
            if initialized.get("method") != "initialized":
                raise SystemExit(66)

            thread_start = receive()
            if thread_start.get("method") != "thread/start":
                raise SystemExit(67)
            send({{
                "id": thread_start["id"],
                "result": {{
                    "thread": {{"id": "thread-1"}},
                    "model": "fake",
                    "modelProvider": "fake",
                    "cwd": thread_start["params"]["cwd"],
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": {{"type": "readOnly"}},
                }},
            }})

            turn_start = receive()
            if turn_start.get("method") != "turn/start":
                raise SystemExit(68)
            send({{"id": turn_start["id"], "result": {{"turn": {{"id": "turn-1"}}}}}})

            if mode == "interrupt":
                interrupt = receive()
                if interrupt.get("method") != "turn/interrupt":
                    raise SystemExit(69)
                send({{"id": interrupt["id"], "result": {{}}}})
                send({{
                    "method": "turn/completed",
                    "params": {{
                        "threadId": "thread-1",
                        "turn": {{"id": "turn-1", "status": "interrupted", "items": []}},
                    }},
                }})
            else:
                item = {{"id": "item-1", "type": "agentMessage", "text": "E1_FIXTURE_OK"}}
                send({{
                    "method": "turn/started",
                    "params": {{
                        "threadId": "thread-1",
                        "turn": {{"id": "turn-1", "status": "inProgress", "items": []}},
                    }},
                }})
                send({{
                    "method": "item/started",
                    "params": {{
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "item": item,
                        "startedAtMs": 1,
                    }},
                }})
                send({{
                    "method": "item/completed",
                    "params": {{
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "item": item,
                        "completedAtMs": 2,
                    }},
                }})
                send({{
                    "method": "turn/completed",
                    "params": {{
                        "threadId": "thread-1",
                        "turn": {{"id": "turn-1", "status": "completed", "items": [item]}},
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


def make_client(
    tmp_path: Path,
    codex_path: Path,
    *,
    mode: str = "happy",
    request_timeout_seconds: float = 2,
) -> CodexAppServerClient:
    return CodexAppServerClient(
        codex_path,
        cwd=tmp_path,
        environment={"FAKE_CODEX_MODE": mode},
        request_timeout_seconds=request_timeout_seconds,
        shutdown_timeout_seconds=0.2,
    )


def test_pinned_schema_hash_and_e1_definitions() -> None:
    info = verify_codex_app_server_schema()

    schema = json.loads(info.path.read_text(encoding="utf-8"))
    assert info.title == "CodexAppServerProtocolV2"
    assert info.sha256 == "9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9"
    assert {
        "InitializeParams",
        "ThreadStartParams",
        "TurnStartParams",
        "TurnInterruptParams",
        "ItemStartedNotification",
        "ItemCompletedNotification",
        "TurnCompletedNotification",
    } <= schema["definitions"].keys()


def test_thread_turn_item_lifecycle_and_process_reaping(tmp_path: Path) -> None:
    client = make_client(tmp_path, make_fake_codex(tmp_path))

    with client:
        process_id = client.process_id
        thread_id = client.start_thread()
        turn = client.run_turn(thread_id, "Return the fixture result.")

        assert process_id is not None
        assert thread_id == "thread-1"
        assert turn.turn_id == "turn-1"
        assert turn.status == "completed"
        assert turn.final_text == "E1_FIXTURE_OK"
        assert [event.method for event in turn.events] == [
            "turn/started",
            "item/started",
            "item/completed",
            "turn/completed",
        ]

    assert client.is_running is False
    assert client.returncode == 0
    assert client.used_forceful_shutdown is False


def test_interrupt_waits_for_terminal_turn_event(tmp_path: Path) -> None:
    client = make_client(tmp_path, make_fake_codex(tmp_path), mode="interrupt")

    with client:
        thread_id = client.start_thread()
        turn_id = client.start_turn(thread_id, "Wait until interrupted.")
        client.interrupt_turn(thread_id, turn_id)
        turn = client.wait_for_turn(thread_id, turn_id)

    assert turn.status == "interrupted"
    assert turn.final_text is None
    assert client.returncode == 0


def test_unhandled_server_request_is_denied_by_default(tmp_path: Path) -> None:
    client = make_client(tmp_path, make_fake_codex(tmp_path), mode="server-request")

    with client:
        client.start_thread()
        turn = client.run_turn("thread-1", "Return the fixture result.")

    assert turn.status == "completed"
    assert client.server_requests == (
        {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {},
        },
    )


def test_version_mismatch_fails_before_app_server_start(tmp_path: Path) -> None:
    client = make_client(tmp_path, make_fake_codex(tmp_path), mode="version-mismatch")

    with pytest.raises(CodexAppServerVersionError, match="version mismatch"):
        client.start()

    assert client.process_id is None


@pytest.mark.parametrize(
    ("mode", "error_type"),
    [
        ("request-error", CodexAppServerRequestError),
        ("invalid-json", CodexAppServerProtocolError),
        ("timeout", CodexAppServerTimeout),
    ],
)
def test_initialize_failures_close_and_reap_process(
    tmp_path: Path,
    mode: str,
    error_type: type[Exception],
) -> None:
    client = make_client(
        tmp_path,
        make_fake_codex(tmp_path),
        mode=mode,
        request_timeout_seconds=0.5,
    )

    with pytest.raises(error_type):
        client.start()

    assert client.is_running is False
    assert client.returncode is not None


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_CODEX_APP_SERVER_INTEGRATION") != "1",
    reason="requires an authenticated real Codex app-server binary",
)
def test_real_codex_app_server_turn_and_process_reaping(tmp_path: Path) -> None:
    codex_path = Path(os.environ["CODEX_APP_SERVER_INTEGRATION_BINARY"])
    client = CodexAppServerClient(
        codex_path,
        cwd=tmp_path,
        request_timeout_seconds=30,
        shutdown_timeout_seconds=10,
    )

    with client:
        process_id = client.process_id
        thread_id = client.start_thread(
            ephemeral=True,
            approval_policy="never",
            sandbox="read-only",
        )
        turn = client.run_turn(
            thread_id,
            "Reply with exactly E1_APP_SERVER_OK and do not call any tools.",
            timeout_seconds=180,
        )

        assert process_id is not None
        assert turn.status == "completed"
        assert turn.final_text == "E1_APP_SERVER_OK"

    assert client.is_running is False
    assert client.returncode == 0
    assert client.used_forceful_shutdown is False
