from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str = "development"
    DATABASE_URL: str
    ARTIFACT_ROOT: Path
    WORKSPACE_ROOT: Path
    USER_SECRET_ROOT: Path | None = None

    MODEL_PROVIDER: str = "deepseek"
    MODEL_NAME: str = ""
    MODEL_BASE_URL: str = ""
    MODEL_API_KEY_REF: str = "DEEPSEEK_API_KEY"
    DEEPSEEK_API_KEY: SecretStr | None = Field(default=None, repr=False, exclude=True)

    WEB_RESEARCH_PROVIDER: str = "bocha"
    WEB_RESEARCH_BASE_URL: str = "https://api.bochaai.com/v1"
    WEB_RESEARCH_API_KEY_REF: str = "BOCHA_API_KEY"
    WEB_RESEARCH_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=120)
    BOCHA_API_KEY: SecretStr | None = Field(default=None, repr=False, exclude=True)

    CODEX_CLI_PATH: Path
    CODEX_MAX_CONCURRENT_RUNS: int = Field(default=1, ge=1, le=4)
    CODEX_TASK_TIMEOUT_SECONDS: int = Field(default=1800, ge=30, le=7200)
    AGENT_MAX_TURNS_PER_RUN: int = Field(default=12, ge=1, le=50)
    AGENT_MAX_RETRIES_PER_RUN: int = Field(default=2, ge=0, le=5)
    RUN_HEARTBEAT_TIMEOUT_SECONDS: int = Field(default=90, ge=15, le=600)

    INVITE_CODE_HASH: str = ""
    SESSION_SECRET: SecretStr | None = Field(default=None, repr=False, exclude=True)
    SESSION_TTL_SECONDS: int = Field(default=28_800, ge=300, le=604_800)
    AUTH_ENFORCED: bool = False
    EVENT_STREAM_POLL_INTERVAL_SECONDS: float = Field(default=0.5, ge=0.1, le=5)
    EVENT_STREAM_HEARTBEAT_SECONDS: int = Field(default=15, ge=5, le=60)

    @field_validator("DATABASE_URL")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL; runtime fallback is forbidden")
        return value

    @field_validator("MODEL_PROVIDER")
    @classmethod
    def require_deepseek(cls, value: str) -> str:
        if value != "deepseek":
            raise ValueError("V1 MODEL_PROVIDER is frozen to deepseek")
        return value

    @field_validator("ARTIFACT_ROOT", "WORKSPACE_ROOT", "CODEX_CLI_PATH", "USER_SECRET_ROOT")
    @classmethod
    def require_absolute_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        if not value.is_absolute():
            raise ValueError("runtime paths must be absolute")
        return value.resolve(strict=False)

    @model_validator(mode="after")
    def validate_runtime_paths(self) -> "Settings":
        if self.USER_SECRET_ROOT is None:
            self.USER_SECRET_ROOT = (self.ARTIFACT_ROOT.parent / "secrets").resolve(
                strict=False
            )
        if self.ARTIFACT_ROOT == self.WORKSPACE_ROOT:
            raise ValueError("ARTIFACT_ROOT and WORKSPACE_ROOT must be different directories")
        if not self.ARTIFACT_ROOT.is_dir():
            raise ValueError("ARTIFACT_ROOT must be an existing directory")
        if not self.WORKSPACE_ROOT.is_dir():
            raise ValueError("WORKSPACE_ROOT must be an existing directory")
        if not self.CODEX_CLI_PATH.is_file():
            raise ValueError("CODEX_CLI_PATH must point to an existing file")
        if self.CODEX_CLI_PATH.stat().st_mode & 0o111 == 0:
            raise ValueError("CODEX_CLI_PATH must be executable")
        if self.APP_ENV == "production" and not self.AUTH_ENFORCED:
            raise ValueError("AUTH_ENFORCED must be true in production")
        if self.AUTH_ENFORCED and not self.session_auth_ready:
            raise ValueError(
                "AUTH_ENFORCED requires INVITE_CODE_HASH and SESSION_SECRET"
            )
        return self

    @property
    def model_ready(self) -> bool:
        return bool(
            self.MODEL_NAME
            and self.MODEL_BASE_URL
            and self.MODEL_API_KEY_REF == "DEEPSEEK_API_KEY"
            and self.DEEPSEEK_API_KEY
            and self.DEEPSEEK_API_KEY.get_secret_value()
        )

    def resolve_model_api_key(self) -> str:
        if self.MODEL_API_KEY_REF != "DEEPSEEK_API_KEY":
            raise ValueError("V1 only allows the DEEPSEEK_API_KEY SecretRef")
        if self.DEEPSEEK_API_KEY is None or not self.DEEPSEEK_API_KEY.get_secret_value():
            raise ValueError("configured DeepSeek SecretRef has no value")
        return self.DEEPSEEK_API_KEY.get_secret_value()

    @property
    def web_research_ready(self) -> bool:
        return bool(
            self.WEB_RESEARCH_PROVIDER == "bocha"
            and self.WEB_RESEARCH_BASE_URL
            and self.WEB_RESEARCH_API_KEY_REF == "BOCHA_API_KEY"
            and self.BOCHA_API_KEY
            and self.BOCHA_API_KEY.get_secret_value()
        )

    def resolve_web_research_api_key(self) -> str:
        if self.WEB_RESEARCH_API_KEY_REF != "BOCHA_API_KEY":
            raise ValueError("D5 only allows the BOCHA_API_KEY SecretRef")
        if self.BOCHA_API_KEY is None or not self.BOCHA_API_KEY.get_secret_value():
            raise ValueError("configured Bocha SecretRef has no value")
        return self.BOCHA_API_KEY.get_secret_value()

    @property
    def session_auth_ready(self) -> bool:
        return bool(
            len(self.INVITE_CODE_HASH) == 64
            and self.SESSION_SECRET
            and self.SESSION_SECRET.get_secret_value()
        )

    def resolve_session_secret(self) -> str:
        if self.SESSION_SECRET is None or not self.SESSION_SECRET.get_secret_value():
            raise ValueError("SESSION_SECRET is not configured")
        return self.SESSION_SECRET.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
