from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from parcel_shell.app import create_app
from parcel_shell.config import Settings


@pytest.fixture
def settings(migrations_applied: str) -> Settings:
    return Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": migrations_applied,
            "REDIS_URL": "redis://localhost:1",
            "PARCEL_LOG_LEVEL": "INFO",
        }
    )


async def test_create_app_returns_fastapi(settings: Settings) -> None:
    app = create_app(settings=settings)
    assert app.title


async def test_lifespan_attaches_and_disposes_state(settings: Settings) -> None:
    app = create_app(settings=settings)
    async with LifespanManager(app):
        assert isinstance(app.state.engine, AsyncEngine)
        assert app.state.sessionmaker is not None
        assert app.state.redis is not None


async def test_live_endpoint_via_factory(settings: Settings) -> None:
    app = create_app(settings=settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        r = await c.get("/health/live")
    assert r.status_code == 200


async def test_unhandled_exception_returns_500_with_request_id(
    settings: Settings,
) -> None:
    app = create_app(settings=settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    async with (
        LifespanManager(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://t",
        ) as c,
    ):
        r = await c.get("/boom", headers={"X-Request-ID": "rid-9"})
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_server_error"
    assert body["request_id"] == "rid-9"
    assert r.headers["x-request-id"] == "rid-9"
