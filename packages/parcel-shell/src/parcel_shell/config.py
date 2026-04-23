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
