from pathlib import Path

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def settings_values(tmp_path: Path) -> dict[str, object]:
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    artifact_root.mkdir()
    workspace_root.mkdir()
    codex_path = tmp_path / "codex"
    codex_path.touch(mode=0o700)
    return {
        "DATABASE_URL": "postgresql+psycopg://user:password@127.0.0.1:5432/database",
        "ARTIFACT_ROOT": artifact_root,
        "WORKSPACE_ROOT": workspace_root,
        "CODEX_CLI_PATH": codex_path,
    }


def test_runtime_configuration_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "ARTIFACT_ROOT", "WORKSPACE_ROOT", "CODEX_CLI_PATH"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    missing = {item["loc"][0] for item in error.value.errors() if item["type"] == "missing"}
    assert missing == {"DATABASE_URL", "ARTIFACT_ROOT", "WORKSPACE_ROOT", "CODEX_CLI_PATH"}


def test_runtime_paths_must_be_absolute_and_exist(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    values["ARTIFACT_ROOT"] = Path("relative-artifacts")

    with pytest.raises(ValidationError, match="runtime paths must be absolute"):
        Settings(_env_file=None, **values)


def test_artifact_and_workspace_roots_must_be_separate(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    values["WORKSPACE_ROOT"] = values["ARTIFACT_ROOT"]

    with pytest.raises(ValidationError, match="must be different directories"):
        Settings(_env_file=None, **values)


def test_codex_path_must_be_executable(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    codex_path = tmp_path / "not-executable-codex"
    codex_path.touch(mode=0o600)
    values["CODEX_CLI_PATH"] = codex_path

    with pytest.raises(ValidationError, match="must be executable"):
        Settings(_env_file=None, **values)


def test_valid_d3_runtime_configuration_loads(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, **settings_values(tmp_path))

    assert settings.MODEL_PROVIDER == "deepseek"
    assert settings.ARTIFACT_ROOT.is_absolute()
    assert settings.WORKSPACE_ROOT.is_absolute()
    assert tmp_path / "codex-users" == settings.CODEX_USER_HOME_ROOT
    assert settings.BUILDER_ENABLED is True


def test_codex_user_home_must_not_overlap_other_runtime_roots(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    values["CODEX_USER_HOME_ROOT"] = values["WORKSPACE_ROOT"]

    with pytest.raises(ValidationError, match="storage roots must be different"):
        Settings(_env_file=None, **values)


def test_builder_can_be_explicitly_disabled(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        **settings_values(tmp_path),
        BUILDER_ENABLED=False,
    )

    assert settings.BUILDER_ENABLED is False


def test_production_requires_auth_enforcement(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    values["APP_ENV"] = "production"

    with pytest.raises(ValidationError, match="AUTH_ENFORCED must be true in production"):
        Settings(_env_file=None, **values)


def test_auth_enforcement_requires_session_secret(tmp_path: Path) -> None:
    values = settings_values(tmp_path)
    values.update(
        {
            "AUTH_ENFORCED": True,
            "SESSION_SECRET": None,
        }
    )

    with pytest.raises(ValidationError, match="AUTH_ENFORCED requires"):
        Settings(_env_file=None, **values)
