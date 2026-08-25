from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.core.config import Settings


@dataclass(frozen=True)
class CodexCliSmoke:
    configured: bool
    executable: bool
    version: str | None
    exit_code: int | None
    checked_at: str
    error: str | None = None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceManifest:
    digest: str
    file_count: int
    total_bytes: int
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexCliExecution:
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    stdout_hash: str
    stderr_hash: str
    event_count: int
    final_message: str | None
    workspace_manifest: WorkspaceManifest
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.workspace_manifest.violations


class CodexCliExecutionError(ValueError):
    pass


_SAFE_PROJECT_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
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
_SECRET_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
_IGNORED_MANIFEST_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".pnpm-store",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
}
_SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
)
_SECRET_ASSIGNMENT = re.compile(
    rb"(?i)(?:api[_-]?key|secret|token)[ \t]*[:=][ \t]*['\"]?"
    rb"([A-Za-z0-9_./+=-]{16,})"
)
_SAFE_SECRET_MARKERS = (
    b"example",
    b"fake",
    b"minimum",
    b"placeholder",
    b"process.env.",
    b"random-secret",
    b"replace",
    b"test",
)


def smoke_codex_cli(settings: Settings, timeout_seconds: float = 5.0) -> CodexCliSmoke:
    """Run a read-only version probe without invoking a shell or project mutation."""
    checked_at = datetime.now(UTC).isoformat()
    if not settings.BUILDER_ENABLED:
        return CodexCliSmoke(
            configured=False,
            executable=False,
            version=None,
            exit_code=None,
            checked_at=checked_at,
            error="Builder is disabled by installation policy",
        )
    path = settings.CODEX_CLI_PATH
    if not path.is_file() or path.stat().st_mode & 0o111 == 0:
        return CodexCliSmoke(
            configured=True,
            executable=False,
            version=None,
            exit_code=None,
            checked_at=checked_at,
            error="CODEX_CLI_PATH is not executable",
        )
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            cwd=settings.WORKSPACE_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CodexCliSmoke(
            configured=True,
            executable=True,
            version=None,
            exit_code=None,
            checked_at=checked_at,
            error=type(error).__name__,
        )
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return CodexCliSmoke(
        configured=True,
        executable=True,
        version=output[0][:200] if output else None,
        exit_code=completed.returncode,
        checked_at=checked_at,
        error=None if completed.returncode == 0 else "Codex CLI version probe failed",
    )


def resolve_project_workspace(settings: Settings, project_id: str) -> Path:
    """Resolve exactly one UUID-named child under the approved workspace root."""
    try:
        canonical = str(UUID(project_id))
    except ValueError as error:
        raise CodexCliExecutionError("Project workspace identity must be a UUID.") from error
    if canonical != project_id or _SAFE_PROJECT_ID.fullmatch(project_id) is None:
        raise CodexCliExecutionError("Project workspace identity is not canonical.")
    root = settings.WORKSPACE_ROOT.resolve(strict=True)
    workspace = (root / project_id).resolve(strict=False)
    if workspace.parent != root:
        raise CodexCliExecutionError("Project workspace escapes WORKSPACE_ROOT.")
    workspace.mkdir(mode=0o700, parents=False, exist_ok=True)
    resolved = workspace.resolve(strict=True)
    if resolved.parent != root or not resolved.is_dir():
        raise CodexCliExecutionError("Project workspace is invalid.")
    return resolved


def execute_codex_cli(
    settings: Settings,
    *,
    project_id: str,
    prompt: str,
    output_schema: Path,
    timeout_seconds: float | None = None,
) -> CodexCliExecution:
    """Run Codex without a shell in one approved project workspace.

    Raw stdout/stderr are hashed in memory and never persisted by this adapter. The subprocess
    receives a small environment allowlist so application SecretRefs are not inherited.
    """
    if not prompt.strip() or len(prompt.encode("utf-8")) > 200_000:
        raise CodexCliExecutionError("Codex task prompt is empty or too large.")
    workspace = resolve_project_workspace(settings, project_id)
    schema = output_schema.resolve(strict=True)
    if not schema.is_relative_to(workspace) or not schema.is_file():
        raise CodexCliExecutionError("Codex output schema must be inside the project workspace.")
    command = [
        str(settings.CODEX_CLI_PATH),
        "exec",
        "--approve-for-me",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "-c",
        'shell_environment_policy.inherit="none"',
        "-C",
        str(workspace),
        "--output-schema",
        str(schema),
        "--color",
        "never",
        "--json",
        prompt,
    ]
    environment = {key: value for key, value in os.environ.items() if key in _SAFE_ENV_KEYS}
    started = time.monotonic()
    timed_out = False
    error: str | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            capture_output=True,
            check=False,
            text=False,
            timeout=timeout_seconds or settings.CODEX_TASK_TIMEOUT_SECONDS,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        error = "CODEX_TIMEOUT"
    except OSError as exc:
        exit_code = None
        stdout = b""
        stderr = b""
        error = f"CODEX_EXECUTION_{type(exc).__name__.upper()}"
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    final_message, event_count = _extract_final_message(stdout)
    manifest = build_workspace_manifest(settings, workspace)
    if manifest.violations and error is None:
        error = "WORKSPACE_POLICY_VIOLATION"
    elif exit_code not in {0, None} and error is None:
        error = "CODEX_NONZERO_EXIT"
    return CodexCliExecution(
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=duration_ms,
        stdout_hash=hashlib.sha256(stdout).hexdigest(),
        stderr_hash=hashlib.sha256(stderr).hexdigest(),
        event_count=event_count,
        final_message=final_message,
        workspace_manifest=manifest,
        error=error,
    )


def build_workspace_manifest(settings: Settings, workspace: Path) -> WorkspaceManifest:
    root = workspace.resolve(strict=True)
    records: list[str] = []
    violations: list[str] = []
    total_bytes = 0
    secret_values = _configured_secret_values(settings)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(part in _IGNORED_MANIFEST_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            violations.append(f"symlink:{relative}")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        total_bytes += len(data)
        digest = hashlib.sha256(data).hexdigest()
        records.append(f"{relative}\0{len(data)}\0{digest}")
        if path.name in _SECRET_FILE_NAMES:
            violations.append(f"secret-file:{relative}")
        if any(secret and secret in data for secret in secret_values):
            violations.append(f"configured-secret:{relative}")
        if any(pattern.search(data) for pattern in _SECRET_PATTERNS) or _has_secret_assignment(
            data
        ):
            violations.append(f"secret-pattern:{relative}")
        for forbidden_root in (settings.WORKSPACE_ROOT, settings.ARTIFACT_ROOT):
            if str(forbidden_root).encode() in data:
                violations.append(f"local-path:{relative}")
                break
        if b"/Users/" in data:
            violations.append(f"local-path:{relative}")
    manifest = "\n".join(records).encode("utf-8")
    return WorkspaceManifest(
        digest=hashlib.sha256(manifest).hexdigest(),
        file_count=len(records),
        total_bytes=total_bytes,
        violations=tuple(sorted(set(violations))),
    )


def _extract_final_message(stdout: bytes) -> tuple[str | None, int]:
    final_message: str | None = None
    event_count = 0
    for raw in stdout.splitlines():
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        event_count += 1
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str):
                final_message = text
        if isinstance(event, dict) and event.get("type") == "agent_message":
            text = event.get("text")
            if isinstance(text, str):
                final_message = text
    return final_message, event_count


def _configured_secret_values(settings: Settings) -> tuple[bytes, ...]:
    values: list[bytes] = []
    for candidate in (
        settings.DEEPSEEK_API_KEY,
        settings.BOCHA_API_KEY,
        settings.SESSION_SECRET,
    ):
        if candidate is None:
            continue
        value = candidate.get_secret_value()
        if value:
            values.append(value.encode("utf-8"))
    return tuple(values)


def _has_secret_assignment(data: bytes) -> bool:
    for match in _SECRET_ASSIGNMENT.finditer(data):
        candidate = match.group(1).lower()
        if any(marker in candidate for marker in _SAFE_SECRET_MARKERS):
            continue
        return True
    return False
