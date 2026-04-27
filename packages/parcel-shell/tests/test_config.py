# pyright: reportCallIssue=false
from __future__ import annotations

import pytest
from pydantic import ValidationError

from parcel_shell.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "PARCEL_SESSION_SECRET": "a" * 32,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
    }


def test_settings_loads_with_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.env == "dev"
    assert s.port == 8000
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_settings_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("PARCEL_SESSION_SECRET", "DATABASE_URL", "REDIS_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_rejects_non_asyncpg_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"DATABASE_URL": "postgresql://u:p@localhost/db"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_short_secret_ok_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"PARCEL_SESSION_SECRET": "short", "PARCEL_ENV": "dev"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.session_secret == "short"


def test_settings_short_secret_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"PARCEL_SESSION_SECRET": "short", "PARCEL_ENV": "prod"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings()


def test_public_base_url_default() -> None:
    settings = Settings.model_validate(
        {
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": "postgresql+asyncpg://x/y",
            "REDIS_URL": "redis://x:1",
        }
    )
    assert settings.public_base_url == "http://shell:8000"


def test_public_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARCEL_PUBLIC_BASE_URL", "http://localhost:8000")
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    settings = Settings()
    assert settings.public_base_url == "http://localhost:8000"
