from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CODEX_APP_SERVER_CLI_VERSION = "codex-cli 0.149.0-alpha.4.3"
CODEX_APP_SERVER_SCHEMA_SHA256 = (
    "9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9"
)
CODEX_APP_SERVER_SCHEMA_FILENAME = (
    "codex_app_server_protocol.0.149.0-alpha.4.3.v2.json"
)

_CLIENT_NAME = "product_factory_agent"
_CLIENT_TITLE = "Product Factory Agent"
_CLIENT_VERSION = "0.1.0"
_MAX_PROTOCOL_LINE_BYTES = 8 * 1024 * 1024
_SAFE_ENV_KEYS = {
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TMPDIR",
}
_EOF = object()


class CodexAppServerError(RuntimeError):
    """Base error for the pinned Codex app-server protocol client."""


class CodexAppServerVersionError(CodexAppServerError):
    pass


class CodexAppServerProtocolError(CodexAppServerError):
    pass


class CodexAppServerTimeout(CodexAppServerError):
    pass


class CodexAppServerRequestError(CodexAppServerError):
    def __init__(self, method: str, error: Mapping[str, Any]) -> None:
        self.method = method
        self.code = error.get("code")
        self.data = error.get("data")
        message = str(error.get("message") or "Unknown app-server request error")
        super().__init__(f"{method} failed: {message}")


@dataclass(frozen=True)
class CodexAppServerSchemaInfo:
    path: Path
    sha256: str
    title: str


@dataclass(frozen=True)
class CodexAppServerEvent:
    method: str
    params: dict[str, Any]


@dataclass(frozen=True)
class CodexAppServerTurn:
    thread_id: str
    turn_id: str
    status: str
    items: tuple[dict[str, Any], ...]
    events: tuple[CodexAppServerEvent, ...]

    @property
    def final_text(self) -> str | None:
        for item in reversed(self.items):
            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                return item["text"]
        return None


ServerRequestHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


def codex_app_server_schema_path() -> Path:
    return Path(__file__).with_name("schemas") / CODEX_APP_SERVER_SCHEMA_FILENAME


def verify_codex_app_server_schema() -> CodexAppServerSchemaInfo:
    schema_path = codex_app_server_schema_path().resolve(strict=True)
    data = schema_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != CODEX_APP_SERVER_SCHEMA_SHA256:
        raise CodexAppServerProtocolError("Pinned app-server schema hash does not match.")
    try:
        schema = json.loads(data)
    except json.JSONDecodeError as error:
        raise CodexAppServerProtocolError("Pinned app-server schema is invalid JSON.") from error
    title = schema.get("title")
    definitions = schema.get("definitions")
    required = {
        "InitializeParams",
        "ThreadStartParams",
        "ThreadStartResponse",
        "TurnStartParams",
        "TurnStartResponse",
        "TurnInterruptParams",
        "ItemStartedNotification",
        "ItemCompletedNotification",
        "TurnCompletedNotification",
    }
    if title != "CodexAppServerProtocolV2" or not isinstance(definitions, dict):
        raise CodexAppServerProtocolError("Pinned app-server schema has the wrong bundle type.")
    if not required.issubset(definitions):
        raise CodexAppServerProtocolError("Pinned app-server schema is missing E1 methods.")
    return CodexAppServerSchemaInfo(path=schema_path, sha256=digest, title=title)


class CodexAppServerClient:
    """Synchronous stdio JSON-RPC client for one pinned Codex app-server process.

    The client owns the subprocess, performs exactly one initialize handshake, keeps all
    protocol traffic in memory, and always waits on process shutdown so child processes are
    reaped. It does not persist product Runs, Artifacts, permissions, or user provider config.
    """

    def __init__(
        self,
        codex_path: Path,
        *,
        cwd: Path,
        expected_version: str = CODEX_APP_SERVER_CLI_VERSION,
        request_timeout_seconds: float = 15.0,
        shutdown_timeout_seconds: float = 5.0,
        server_request_handler: ServerRequestHandler | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        resolved_codex = codex_path.resolve(strict=True)
        resolved_cwd = cwd.resolve(strict=True)
        if not resolved_codex.is_file() or resolved_codex.stat().st_mode & 0o111 == 0:
            raise CodexAppServerError("Codex app-server binary is not executable.")
        if not resolved_cwd.is_dir():
            raise CodexAppServerError("Codex app-server cwd must be a directory.")
        if request_timeout_seconds <= 0 or shutdown_timeout_seconds <= 0:
            raise ValueError("App-server timeouts must be positive.")
        self.codex_path = resolved_codex
        self.cwd = resolved_cwd
        self.expected_version = expected_version
        self.request_timeout_seconds = request_timeout_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.server_request_handler = server_request_handler
        base_environment = {
            key: value for key, value in os.environ.items() if key in _SAFE_ENV_KEYS
        }
        if environment is not None:
            base_environment.update(environment)
        self._environment = base_environment
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[object] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=100)
        self._events: list[CodexAppServerEvent] = []
        self._turn_events: dict[tuple[str, str], list[CodexAppServerEvent]] = {}
        self._pending_responses: dict[int | str, dict[str, Any]] = {}
        self._server_requests: list[dict[str, Any]] = []
        self._next_request_id = 1
        self._request_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._initialized = False
        self._closed = False
        self._returncode: int | None = None
        self._used_forceful_shutdown = False

    @property
    def process_id(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def returncode(self) -> int | None:
        if self._process is not None and self._process.poll() is not None:
            return self._process.returncode
        return self._returncode

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def used_forceful_shutdown(self) -> bool:
        return self._used_forceful_shutdown

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_tail)

    @property
    def events(self) -> tuple[CodexAppServerEvent, ...]:
        return tuple(self._events)

    @property
    def server_requests(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._server_requests)

    def __enter__(self) -> CodexAppServerClient:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def start(self) -> CodexAppServerClient:
        if self._process is not None:
            raise CodexAppServerError("Codex app-server client has already been started.")
        verify_codex_app_server_schema()
        actual_version = self._probe_version()
        if actual_version != self.expected_version:
            raise CodexAppServerVersionError(
                f"Codex version mismatch: expected {self.expected_version!r}, "
                f"received {actual_version!r}."
            )
        try:
            self._process = subprocess.Popen(
                [str(self.codex_path), "app-server", "--listen", "stdio://"],
                cwd=self.cwd,
                env=self._environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self._reader_thread = threading.Thread(
                target=self._read_stdout,
                name="codex-app-server-stdout",
                daemon=True,
            )
            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                name="codex-app-server-stderr",
                daemon=True,
            )
            self._reader_thread.start()
            self._stderr_thread.start()
            self.initialize()
        except Exception:
            self.close()
            raise
        return self

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            raise CodexAppServerProtocolError("App-server connection is already initialized.")
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": _CLIENT_NAME,
                    "title": _CLIENT_TITLE,
                    "version": _CLIENT_VERSION,
                }
            },
        )
        self.notify("initialized", {})
        self._initialized = True
        return result

    def start_thread(
        self,
        *,
        ephemeral: bool = True,
        approval_policy: str = "never",
        sandbox: str = "read-only",
    ) -> str:
        self._require_initialized()
        if approval_policy not in {"untrusted", "on-request", "never"}:
            raise ValueError("Unsupported app-server approval policy.")
        if sandbox not in {"read-only", "workspace-write", "danger-full-access"}:
            raise ValueError("Unsupported app-server sandbox mode.")
        result = self.request(
            "thread/start",
            {
                "cwd": str(self.cwd),
                "ephemeral": ephemeral,
                "approvalPolicy": approval_policy,
                "sandbox": sandbox,
            },
        )
        thread = result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexAppServerProtocolError("thread/start returned no thread id.")
        return thread_id

    def start_turn(
        self,
        thread_id: str,
        text: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        self._require_initialized()
        if not thread_id:
            raise ValueError("Thread id is required.")
        if not text.strip() or len(text.encode("utf-8")) > 200_000:
            raise ValueError("Turn text is empty or too large.")
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": text}],
        }
        if output_schema is not None:
            params["outputSchema"] = output_schema
        result = self.request("turn/start", params)
        turn = result.get("turn")
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexAppServerProtocolError("turn/start returned no turn id.")
        return turn_id

    def run_turn(
        self,
        thread_id: str,
        text: str,
        *,
        timeout_seconds: float | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> CodexAppServerTurn:
        turn_id = self.start_turn(thread_id, text, output_schema=output_schema)
        return self.wait_for_turn(thread_id, turn_id, timeout_seconds=timeout_seconds)

    def wait_for_turn(
        self,
        thread_id: str,
        turn_id: str,
        *,
        timeout_seconds: float | None = None,
    ) -> CodexAppServerTurn:
        self._require_initialized()
        timeout = timeout_seconds or self.request_timeout_seconds
        deadline = time.monotonic() + timeout
        key = (thread_id, turn_id)
        completed = self._completed_turn(key)
        while completed is None:
            message = self._next_message(deadline, f"turn {turn_id}")
            self._route_message(message)
            completed = self._completed_turn(key)
        return completed

    def interrupt_turn(self, thread_id: str, turn_id: str) -> None:
        self._require_initialized()
        self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self._process is None or self._process.poll() is not None:
            raise CodexAppServerError("Codex app-server process is not running.")
        timeout = timeout_seconds or self.request_timeout_seconds
        with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            self._send({"method": method, "id": request_id, "params": dict(params or {})})
            deadline = time.monotonic() + timeout
            while True:
                pending = self._pending_responses.pop(request_id, None)
                message = pending or self._next_message(deadline, method)
                if message.get("id") == request_id and "method" not in message:
                    error = message.get("error")
                    if isinstance(error, dict):
                        raise CodexAppServerRequestError(method, error)
                    result = message.get("result")
                    if not isinstance(result, dict):
                        raise CodexAppServerProtocolError(
                            f"{method} returned a non-object result."
                        )
                    return result
                self._route_message(message)

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._send({"method": method, "params": dict(params or {})})

    def close(self) -> None:
        process = self._process
        if process is None or self._closed:
            return
        self._closed = True
        if process.stdin is not None and not process.stdin.closed:
            with suppress(OSError):
                process.stdin.close()
        if process.poll() is None:
            try:
                process.wait(timeout=self.shutdown_timeout_seconds)
            except subprocess.TimeoutExpired:
                self._used_forceful_shutdown = True
                process.terminate()
                try:
                    process.wait(timeout=self.shutdown_timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self.shutdown_timeout_seconds)
        self._returncode = process.returncode
        for worker in (self._reader_thread, self._stderr_thread):
            if worker is not None:
                worker.join(timeout=self.shutdown_timeout_seconds)

    def _probe_version(self) -> str:
        try:
            completed = subprocess.run(
                [str(self.codex_path), "--version"],
                cwd=self.cwd,
                env=self._environment,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.request_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CodexAppServerVersionError("Codex version probe failed.") from error
        output = (completed.stdout or completed.stderr).strip().splitlines()
        version = output[0].strip() if output else ""
        if completed.returncode != 0 or not version:
            raise CodexAppServerVersionError("Codex version probe returned no version.")
        return version

    def _send(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexAppServerError("Codex app-server process is not writable.")
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _MAX_PROTOCOL_LINE_BYTES:
            raise CodexAppServerProtocolError("Outgoing app-server message is too large.")
        try:
            with self._write_lock:
                process.stdin.write(f"{encoded}\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise CodexAppServerError("Codex app-server stdin closed unexpectedly.") from error

    def _next_message(self, deadline: float, operation: str) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CodexAppServerTimeout(f"Timed out waiting for {operation}.")
        try:
            message = self._messages.get(timeout=remaining)
        except queue.Empty as error:
            raise CodexAppServerTimeout(f"Timed out waiting for {operation}.") from error
        if message is _EOF:
            returncode = self._process.poll() if self._process is not None else None
            detail = self._stderr_tail[-1] if self._stderr_tail else "no stderr"
            raise CodexAppServerError(
                f"Codex app-server closed during {operation} (exit={returncode}): {detail}"
            )
        if isinstance(message, Exception):
            raise message
        if not isinstance(message, dict):
            raise CodexAppServerProtocolError("App-server emitted a non-object message.")
        return message

    def _route_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if isinstance(method, str):
            params = message.get("params")
            if not isinstance(params, dict):
                raise CodexAppServerProtocolError(f"{method} notification has invalid params.")
            if "id" in message:
                self._handle_server_request(message["id"], method, params)
                return
            event = CodexAppServerEvent(method=method, params=params)
            self._events.append(event)
            thread_id = params.get("threadId")
            turn_id = params.get("turnId")
            if not isinstance(turn_id, str):
                turn = params.get("turn")
                turn_id = turn.get("id") if isinstance(turn, dict) else None
            if isinstance(thread_id, str) and isinstance(turn_id, str):
                self._turn_events.setdefault((thread_id, turn_id), []).append(event)
            return
        response_id = message.get("id")
        if isinstance(response_id, (int, str)):
            self._pending_responses[response_id] = message
            return
        raise CodexAppServerProtocolError("App-server message has no method or id.")

    def _handle_server_request(
        self, request_id: int | str, method: str, params: dict[str, Any]
    ) -> None:
        request = {"id": request_id, "method": method, "params": params}
        self._server_requests.append(request)
        if self.server_request_handler is None:
            self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Product Factory E1 client does not approve server requests.",
                    },
                }
            )
            return
        try:
            result = self.server_request_handler(method, params)
        except Exception as error:
            self._send(
                {
                    "id": request_id,
                    "error": {"code": -32000, "message": type(error).__name__},
                }
            )
            return
        if not isinstance(result, dict):
            raise CodexAppServerProtocolError("Server request handler must return an object.")
        self._send({"id": request_id, "result": result})

    def _completed_turn(self, key: tuple[str, str]) -> CodexAppServerTurn | None:
        events = self._turn_events.get(key, [])
        completed_event = next(
            (event for event in reversed(events) if event.method == "turn/completed"), None
        )
        if completed_event is None:
            return None
        turn = completed_event.params.get("turn")
        status = turn.get("status") if isinstance(turn, dict) else None
        if not isinstance(status, str):
            raise CodexAppServerProtocolError("turn/completed has no status.")
        items: list[dict[str, Any]] = []
        for event in events:
            if event.method != "item/completed":
                continue
            item = event.params.get("item")
            if isinstance(item, dict):
                items.append(item)
        return CodexAppServerTurn(
            thread_id=key[0],
            turn_id=key[1],
            status=status,
            items=tuple(items),
            events=tuple(events),
        )

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise CodexAppServerProtocolError("App-server connection is not initialized.")

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._messages.put(CodexAppServerProtocolError("App-server stdout is unavailable."))
            return
        try:
            for raw_line in process.stdout:
                if len(raw_line.encode("utf-8")) > _MAX_PROTOCOL_LINE_BYTES:
                    self._messages.put(
                        CodexAppServerProtocolError("Incoming app-server message is too large.")
                    )
                    return
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._messages.put(
                        CodexAppServerProtocolError("App-server emitted invalid JSON.")
                    )
                    return
                self._messages.put(message)
        except (OSError, UnicodeError) as error:
            self._messages.put(
                CodexAppServerProtocolError(
                    f"App-server stdout failed: {type(error).__name__}."
                )
            )
        finally:
            self._messages.put(_EOF)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        try:
            for raw_line in process.stderr:
                line = raw_line.strip()
                if line:
                    self._stderr_tail.append(line[:1000])
        except (OSError, UnicodeError):
            return
