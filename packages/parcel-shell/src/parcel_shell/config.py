from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "staging", "prod"] = Field(default="dev", alias="PARCEL_ENV")
    host: str = Field(default="0.0.0.0", alias="PARCEL_HOST")  # noqa: S104
    port: int = Field(default=8000, alias="PARCEL_PORT")
    session_secret: str = Field(alias="PARCEL_SESSION_SECRET")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="PARCEL_LOG_LEVEL")

    # Phase 7b — AI generator. None of these are strictly required to boot:
    # the generator endpoint returns 503 until a provider is configured.
    ai_provider: Literal["api", "cli"] = Field(default="api", alias="PARCEL_AI_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-7", alias="PARCEL_ANTHROPIC_MODEL")

    # Phase 10c — SMTP for the SendEmail workflow action. All optional;
    # SendEmail raises at run time if smtp_host is None.
    smtp_host: str | None = Field(default=None, alias="PARCEL_SMTP_HOST")
    smtp_port: int = Field(default=587, alias="PARCEL_SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="PARCEL_SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="PARCEL_SMTP_PASSWORD")
    smtp_from_address: str | None = Field(default=None, alias="PARCEL_SMTP_FROM_ADDRESS")

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must start with 'postgresql+asyncpg://'")
        return v

    @model_validator(mode="after")
    def _enforce_secret_length(self) -> Settings:
        if self.env != "dev" and len(self.session_secret) < 32:
            raise ValueError(
                "PARCEL_SESSION_SECRET must be at least 32 chars when env is not 'dev'"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # BaseSettings populates required fields from env vars at runtime; pyright can't see that.
    return Settings()  # pyright: ignore[reportCallIssue]
