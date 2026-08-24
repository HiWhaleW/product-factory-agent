from __future__ import annotations

import hashlib
import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import UserProviderCredential

PROVIDER = "deepseek"


class UserCredentialError(ValueError):
    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True)
class CredentialStatus:
    configured: bool
    provider_name: str | None
    base_url: str | None
    model_name: str | None
    masked_hint: str | None
    updated_at: object | None
    internal_test_fallback: bool


@dataclass(frozen=True)
class ModelCredential:
    provider_name: str
    base_url: str
    model_name: str
    api_key: str


class UserSecretStore:
    """File-backed V1 secret store; PostgreSQL only receives opaque metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)

    def _directory(self, user_id: str) -> Path:
        safe_id = hashlib.sha256(user_id.encode()).hexdigest()
        return self.root / safe_id

    def _path(self, user_id: str) -> Path:
        return self._directory(user_id) / f"{PROVIDER}.key"

    def secret_ref(self, user_id: str) -> str:
        identity = hashlib.sha256(user_id.encode()).hexdigest()
        return f"user-secret://{identity}/{PROVIDER}"

    def write(self, user_id: str, api_key: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        directory = self._directory(user_id)
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        target = self._path(user_id)
        temporary = directory / f".{PROVIDER}.{uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(api_key)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    def read(self, user_id: str) -> str | None:
        path = self._path(user_id)
        if not path.is_file():
            return None
        if path.stat().st_mode & 0o077:
            raise UserCredentialError(
                "USER_API_KEY_PERMISSIONS_INVALID",
                "API Key 文件权限异常，请联系管理员后重试。",
            )
        value = path.read_text(encoding="utf-8")
        return value or None

    def delete(self, user_id: str) -> None:
        path = self._path(user_id)
        if path.exists():
            path.unlink()


def validate_api_key(api_key: str) -> str:
    if api_key != api_key.strip() or any(character.isspace() for character in api_key):
        raise UserCredentialError("USER_API_KEY_INVALID", "API Key 不能包含空格或换行。")
    if len(api_key) < 8 or len(api_key) > 512:
        raise UserCredentialError("USER_API_KEY_INVALID", "API Key 长度不正确。")
    return api_key


def validate_provider_config(
    provider_name: str, base_url: str, model_name: str
) -> tuple[str, str, str]:
    provider_name = provider_name.strip()
    model_name = model_name.strip()
    base_url = base_url.strip().rstrip("/")
    if not provider_name or not model_name:
        raise UserCredentialError(
            "USER_MODEL_CONFIG_INVALID", "接口名称和模型名不能为空。"
        )
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise UserCredentialError(
            "USER_MODEL_CONFIG_INVALID", "服务地址必须是公开可访问的 HTTPS 地址。"
        )
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UserCredentialError(
            "USER_MODEL_CONFIG_INVALID", "服务地址不能指向本机或内网。"
        )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UserCredentialError(
            "USER_MODEL_CONFIG_INVALID", "服务地址不能指向本机或内网。"
        )
    return provider_name, base_url, model_name


def credential_record(session: Session, user_id: str) -> UserProviderCredential | None:
    return session.scalar(
        select(UserProviderCredential).where(
            UserProviderCredential.user_id == user_id,
            UserProviderCredential.provider == PROVIDER,
        )
    )


def credential_status(
    session: Session, *, settings: Settings, user_id: str, role: str
) -> CredentialStatus:
    record = credential_record(session, user_id)
    available = False
    if record is not None:
        assert settings.USER_SECRET_ROOT is not None
        available = UserSecretStore(settings.USER_SECRET_ROOT).read(user_id) is not None
    return CredentialStatus(
        configured=available,
        provider_name=record.provider_name if available else None,
        base_url=record.base_url if available else None,
        model_name=record.model_name if available else None,
        masked_hint=record.masked_hint if available else None,
        updated_at=record.updated_at if record else None,
        internal_test_fallback=record is None and role == "admin" and settings.model_ready,
    )


def save_credential(
    session: Session,
    *,
    settings: Settings,
    user_id: str,
    provider_name: str,
    base_url: str,
    model_name: str,
    api_key: str,
) -> UserProviderCredential:
    api_key = validate_api_key(api_key)
    provider_name, base_url, model_name = validate_provider_config(
        provider_name, base_url, model_name
    )
    assert settings.USER_SECRET_ROOT is not None
    store = UserSecretStore(settings.USER_SECRET_ROOT)
    previous = store.read(user_id)
    store.write(user_id, api_key)
    try:
        record = credential_record(session, user_id)
        masked_hint = f"••••{api_key[-4:]}"
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()
        if record is None:
            record = UserProviderCredential(
                user_id=user_id,
                provider=PROVIDER,
                provider_name=provider_name,
                base_url=base_url,
                model_name=model_name,
                secret_ref=store.secret_ref(user_id),
                masked_hint=masked_hint,
                fingerprint=fingerprint,
            )
            session.add(record)
        else:
            record.provider_name = provider_name
            record.base_url = base_url
            record.model_name = model_name
            record.secret_ref = store.secret_ref(user_id)
            record.masked_hint = masked_hint
            record.fingerprint = fingerprint
        session.flush()
        return record
    except Exception:
        if previous is None:
            store.delete(user_id)
        else:
            store.write(user_id, previous)
        raise


def delete_credential(session: Session, *, settings: Settings, user_id: str) -> bool:
    record = credential_record(session, user_id)
    if record is None:
        return False
    assert settings.USER_SECRET_ROOT is not None
    store = UserSecretStore(settings.USER_SECRET_ROOT)
    previous = store.read(user_id)
    store.delete(user_id)
    try:
        session.delete(record)
        session.flush()
    except Exception:
        if previous is not None:
            store.write(user_id, previous)
        raise
    return True


def resolve_model_api_key(
    session: Session, *, settings: Settings, user_id: str, role: str
) -> str:
    record = credential_record(session, user_id)
    if record is not None:
        assert settings.USER_SECRET_ROOT is not None
        value = UserSecretStore(settings.USER_SECRET_ROOT).read(user_id)
        if value:
            return value
        raise UserCredentialError(
            "USER_API_KEY_UNAVAILABLE",
            "已保存的 API Key 暂时不可用，请在设置中重新添加。",
        )
    if role == "admin" and settings.model_ready:
        return settings.resolve_model_api_key()
    raise UserCredentialError(
        "USER_API_KEY_REQUIRED",
        "请先前往设置页添加专属于你的 API Key。",
    )


def resolve_model_credential(
    session: Session, *, settings: Settings, user_id: str, role: str
) -> ModelCredential:
    record = credential_record(session, user_id)
    if record is not None:
        api_key = resolve_model_api_key(
            session, settings=settings, user_id=user_id, role=role
        )
        return ModelCredential(
            provider_name=record.provider_name,
            base_url=record.base_url,
            model_name=record.model_name,
            api_key=api_key,
        )
    if role == "admin" and settings.model_ready:
        return ModelCredential(
            provider_name=settings.MODEL_PROVIDER,
            base_url=settings.MODEL_BASE_URL,
            model_name=settings.MODEL_NAME,
            api_key=settings.resolve_model_api_key(),
        )
    raise UserCredentialError(
        "USER_API_KEY_REQUIRED",
        "请先前往设置页添加专属于你的 API Key。",
    )
