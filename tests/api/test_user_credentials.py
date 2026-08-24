from types import SimpleNamespace

import pytest
from app.domain.models import User, UserProviderCredential
from app.services.user_credentials import (
    UserCredentialError,
    UserSecretStore,
    credential_status,
    delete_credential,
    resolve_model_api_key,
    resolve_model_credential,
    save_credential,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def session_with_user() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    UserProviderCredential.__table__.create(engine)
    session = Session(engine)
    session.add(User(id="user-a", display_name="用户 A", role="user", status="active"))
    session.commit()
    return session


def settings(secret_root, *, fallback: str | None = None):
    return SimpleNamespace(
        USER_SECRET_ROOT=secret_root,
        model_ready=fallback is not None,
        resolve_model_api_key=lambda: fallback,
    )


def test_user_api_key_is_file_backed_and_database_only_has_metadata(tmp_path) -> None:
    session = session_with_user()
    value = "test-user-secret-value-1234"
    configured = settings(tmp_path / "secrets")

    record = save_credential(
        session,
        settings=configured,
        user_id="user-a",
        provider_name="兼容接口",
        base_url="https://models.example.com/v1",
        model_name="reasoner-v1",
        api_key=value,
    )
    session.commit()

    stored = session.scalar(select(UserProviderCredential))
    assert stored is not None
    assert record.masked_hint == "••••1234"
    assert value not in repr(stored.__dict__)
    assert value not in stored.secret_ref
    assert resolve_model_api_key(
        session, settings=configured, user_id="user-a", role="user"
    ) == value
    resolved = resolve_model_credential(
        session, settings=configured, user_id="user-a", role="user"
    )
    assert resolved.provider_name == "兼容接口"
    assert resolved.base_url == "https://models.example.com/v1"
    assert resolved.model_name == "reasoner-v1"
    secret_file = next((tmp_path / "secrets").glob("*/deepseek.key"))
    assert secret_file.stat().st_mode & 0o077 == 0

    delete_credential(session, settings=configured, user_id="user-a")
    session.commit()
    assert not secret_file.exists()
    assert credential_status(
        session, settings=configured, user_id="user-a", role="user"
    ).configured is False


def test_only_admin_can_use_internal_environment_fallback(tmp_path) -> None:
    session = session_with_user()
    configured = settings(tmp_path / "secrets", fallback="internal-test-only")

    assert resolve_model_api_key(
        session, settings=configured, user_id="user-a", role="admin"
    ) == "internal-test-only"
    with pytest.raises(UserCredentialError, match="请先前往设置页") as error:
        resolve_model_api_key(
            session, settings=configured, user_id="user-a", role="user"
        )
    assert error.value.code == "USER_API_KEY_REQUIRED"


def test_secret_store_rejects_loose_file_permissions(tmp_path) -> None:
    store = UserSecretStore(tmp_path / "secrets")
    store.write("user-a", "test-secure-key")
    secret_file = next((tmp_path / "secrets").glob("*/deepseek.key"))
    secret_file.chmod(0o644)

    with pytest.raises(UserCredentialError) as error:
        store.read("user-a")
    assert error.value.code == "USER_API_KEY_PERMISSIONS_INVALID"


@pytest.mark.parametrize(
    "base_url",
    ["http://models.example.com/v1", "https://localhost/v1", "https://127.0.0.1/v1"],
)
def test_provider_config_rejects_insecure_or_local_endpoints(tmp_path, base_url) -> None:
    session = session_with_user()
    with pytest.raises(UserCredentialError) as error:
        save_credential(
            session,
            settings=settings(tmp_path / "secrets"),
            user_id="user-a",
            provider_name="测试接口",
            base_url=base_url,
            model_name="test-model",
            api_key="test-secure-api-key",
        )
    assert error.value.code == "USER_MODEL_CONFIG_INVALID"
