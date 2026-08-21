from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

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


def smoke_codex_cli(settings: Settings, timeout_seconds: float = 5.0) -> CodexCliSmoke:
    """Run a read-only version probe without invoking a shell or project mutation."""
    checked_at = datetime.now(UTC).isoformat()
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
