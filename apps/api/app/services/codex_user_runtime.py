from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.adapters.codex_app_server import (
    CODEX_APP_SERVER_CLI_VERSION,
    CodexAppServerClient,
    CodexAppServerError,
    CodexAppServerRequestError,
    CodexAppServerTimeout,
    CodexAppServerVersionError,
)
from app.core.config import Settings
from app.services.user_credentials import (
    UserCredentialError,
    credential_record,
    credential_status,
    resolve_model_credential,
)

CODEX_PROVIDER_ENV_KEY = "PRODUCT_FACTORY_CODEX_PROVIDER_API_KEY"
CODEX_PROVIDER_ID = "product_factory_user"
CODEX_USER_CONFIG_FORMAT = "product-factory-codex-user-v1"
_REPORT_FILENAME = "compatibility-report.json"
_CONFIG_FILENAME = "config.toml"
_MAX_REPORT_BYTES = 64 * 1024

CompatibilityStatus = Literal[
    "not_configured", "untested", "compatible", "partial", "incompatible"
]


@dataclass(frozen=True)
class CodexCapabilityChecks:
    app_server: bool
    responses_api: bool
    streaming: bool
    structured_output: bool
    tool_calling: bool
    secret_isolation: bool


@dataclass(frozen=True)
class CodexRuntimeCapability:
    configured: bool
    compatibility: CompatibilityStatus
    config_version: str | None
    checked_at: str | None
    checks: CodexCapabilityChecks
    error_code: str | None = None
    user_message: str | None = None


class CodexUserRuntimeError(RuntimeError):
    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


def _empty_checks() -> CodexCapabilityChecks:
    return CodexCapabilityChecks(
        app_server=False,
        responses_api=False,
        streaming=False,
        structured_output=False,
        tool_calling=False,
        secret_isolation=False,
    )


def _atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def user_codex_home(settings: Settings, user_id: str) -> Path:
    assert settings.CODEX_USER_HOME_ROOT is not None
    root = settings.CODEX_USER_HOME_ROOT.resolve(strict=False)
    identity = hashlib.sha256(user_id.encode()).hexdigest()
    home = root / identity
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    home.mkdir(mode=0o700, exist_ok=True)
    os.chmod(home, 0o700)
    return home


def codex_config_version(
    *,
    provider_name: str,
    base_url: str,
    model_name: str,
    fingerprint: str,
) -> str:
    canonical = json.dumps(
        {
            "format": CODEX_USER_CONFIG_FORMAT,
            "codex_version": CODEX_APP_SERVER_CLI_VERSION,
            "provider_name": provider_name,
            "base_url": base_url,
            "model_name": model_name,
            "credential_fingerprint": fingerprint,
            "wire_api": "responses",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def prepare_user_codex_config(
    session: Session,
    *,
    settings: Settings,
    user_id: str,
    role: str,
) -> tuple[Path, str, str]:
    credential = resolve_model_credential(
        session, settings=settings, user_id=user_id, role=role
    )
    version = codex_config_version(
        provider_name=credential.provider_name,
        base_url=credential.base_url,
        model_name=credential.model_name,
        fingerprint=credential.fingerprint,
    )
    home = user_codex_home(settings, user_id)
    config = "\n".join(
        [
            f"# {CODEX_USER_CONFIG_FORMAT}",
            f"# config-version: {version}",
            f"model = {_toml_string(credential.model_name)}",
            f"model_provider = {_toml_string(CODEX_PROVIDER_ID)}",
            'approval_policy = "never"',
            'sandbox_mode = "read-only"',
            "",
            f"[model_providers.{CODEX_PROVIDER_ID}]",
            f"name = {_toml_string(credential.provider_name)}",
            f"base_url = {_toml_string(credential.base_url)}",
            f"env_key = {_toml_string(CODEX_PROVIDER_ENV_KEY)}",
            'wire_api = "responses"',
            "requires_openai_auth = false",
            "request_max_retries = 0",
            "stream_max_retries = 0",
            "",
            "[shell_environment_policy]",
            'inherit = "none"',
            'include_only = ["HOME", "PATH"]',
            "ignore_default_excludes = false",
            "",
            "[analytics]",
            "enabled = false",
            "",
        ]
    )
    if credential.api_key in config:
        raise CodexUserRuntimeError(
            "CODEX_SECRET_ISOLATION_FAILED",
            "Codex 用户配置未能安全生成，请勿继续运行。",
        )
    _atomic_write(home / _CONFIG_FILENAME, config)
    return home, version, credential.api_key


def _report_path(home: Path) -> Path:
    return home / _REPORT_FILENAME


def _read_current_report(home: Path, config_version: str) -> CodexRuntimeCapability | None:
    path = _report_path(home)
    if not path.is_file() or path.stat().st_size > _MAX_REPORT_BYTES:
        return None
    if path.stat().st_mode & 0o077:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("config_version") != config_version:
            return None
        return CodexRuntimeCapability(
            configured=True,
            compatibility=payload["compatibility"],
            config_version=config_version,
            checked_at=payload.get("checked_at"),
            checks=CodexCapabilityChecks(**payload["checks"]),
            error_code=payload.get("error_code"),
            user_message=payload.get("user_message"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def codex_runtime_capability_status(
    session: Session,
    *,
    settings: Settings,
    user_id: str,
    role: str,
) -> CodexRuntimeCapability:
    status = credential_status(
        session, settings=settings, user_id=user_id, role=role
    )
    if not status.configured:
        return CodexRuntimeCapability(
            configured=False,
            compatibility="not_configured",
            config_version=None,
            checked_at=None,
            checks=_empty_checks(),
            user_message="请先添加大模型 API，再检测 Codex 兼容性。",
        )
    record = credential_record(session, user_id)
    if record is None:
        raise CodexUserRuntimeError(
            "CODEX_CREDENTIAL_METADATA_MISSING", "模型 API 配置不完整，请重新添加。"
        )
    version = codex_config_version(
        provider_name=record.provider_name,
        base_url=record.base_url,
        model_name=record.model_name,
        fingerprint=record.fingerprint,
    )
    home = user_codex_home(settings, user_id)
    report = _read_current_report(home, version)
    if report is not None:
        return report
    return CodexRuntimeCapability(
        configured=True,
        compatibility="untested",
        config_version=version,
        checked_at=None,
        checks=_empty_checks(),
        user_message="API 已保存，尚未执行 Codex 兼容性检测。",
    )


def _safe_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, CodexAppServerVersionError):
        return "CODEX_VERSION_MISMATCH", "当前 Codex 版本与产品固定版本不一致。"
    if isinstance(error, CodexAppServerTimeout):
        return "CODEX_PROVIDER_TIMEOUT", "模型接口响应超时，请检查服务状态后重试。"
    if isinstance(error, CodexAppServerRequestError):
        return (
            "CODEX_PROVIDER_REQUEST_FAILED",
            "模型接口拒绝了 Codex 请求，请检查地址、模型和 Key。",
        )
    if isinstance(error, CodexAppServerError):
        return "CODEX_APP_SERVER_FAILED", "Codex 运行时未能完成兼容性检测。"
    return "CODEX_COMPATIBILITY_FAILED", "兼容性检测失败，请检查模型接口配置。"


def _persist_report(home: Path, report: CodexRuntimeCapability) -> None:
    payload = asdict(report)
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    _atomic_write(_report_path(home), serialized)


def run_codex_compatibility_check(
    session: Session,
    *,
    settings: Settings,
    user_id: str,
    role: str,
) -> CodexRuntimeCapability:
    try:
        home, version, api_key = prepare_user_codex_config(
            session, settings=settings, user_id=user_id, role=role
        )
    except UserCredentialError:
        raise
    workspace = home / "compatibility-workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    os.chmod(workspace, 0o700)
    marker = workspace / "capability-marker.txt"
    marker_value = f"E2_TOOL_{uuid4().hex}"
    _atomic_write(marker, marker_value)
    checks = _empty_checks()
    checked_at = datetime.now(UTC).isoformat()
    try:
        with CodexAppServerClient(
            settings.CODEX_CLI_PATH,
            cwd=workspace,
            request_timeout_seconds=min(
                30, settings.CODEX_COMPATIBILITY_TIMEOUT_SECONDS
            ),
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
            structured_turn = client.run_turn(
                thread_id,
                "Return a JSON object whose message field is exactly E2_CODEX_COMPATIBILITY_OK. "
                "Do not call tools.",
                timeout_seconds=settings.CODEX_COMPATIBILITY_TIMEOUT_SECONDS,
                output_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["message"],
                    "properties": {
                        "message": {
                            "type": "string",
                            "const": "E2_CODEX_COMPATIBILITY_OK",
                        }
                    },
                },
            )
            structured = False
            if structured_turn.final_text:
                try:
                    structured = json.loads(structured_turn.final_text) == {
                        "message": "E2_CODEX_COMPATIBILITY_OK"
                    }
                except json.JSONDecodeError:
                    structured = False
            streaming = any(
                event.method == "item/agentMessage/delta"
                for event in structured_turn.events
            )
            tool_turn = client.run_turn(
                thread_id,
                "Use the shell tool to read capability-marker.txt, then reply with only the "
                "file contents. Do not guess the contents.",
                timeout_seconds=settings.CODEX_COMPATIBILITY_TIMEOUT_SECONDS,
            )
            tool_calling = (
                any(item.get("type") == "commandExecution" for item in tool_turn.items)
                and tool_turn.final_text == marker_value
            )
            checks = CodexCapabilityChecks(
                app_server=True,
                responses_api=structured_turn.status == "completed",
                streaming=streaming,
                structured_output=structured,
                tool_calling=tool_calling,
                secret_isolation=api_key
                not in (home / _CONFIG_FILENAME).read_text(encoding="utf-8"),
            )
        essential = (
            checks.app_server
            and checks.responses_api
            and checks.streaming
            and checks.structured_output
        )
        compatibility: CompatibilityStatus = (
            "compatible" if essential and checks.tool_calling else "partial"
        )
        report = CodexRuntimeCapability(
            configured=True,
            compatibility=compatibility,
            config_version=version,
            checked_at=checked_at,
            checks=checks,
            user_message=(
                "Codex 兼容性检测通过。"
                if compatibility == "compatible"
                else "模型接口可完成 Turn，但部分 Codex 能力未通过。"
            ),
        )
    except CodexAppServerError as error:
        code, user_message = _safe_failure(error)
        report = CodexRuntimeCapability(
            configured=True,
            compatibility="incompatible",
            config_version=version,
            checked_at=checked_at,
            checks=checks,
            error_code=code,
            user_message=user_message,
        )
    finally:
        if marker.exists():
            marker.unlink()
    _persist_report(home, report)
    return report
