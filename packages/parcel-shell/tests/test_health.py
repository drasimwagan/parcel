from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from parcel_shell.health import router as health_router


class _FakeRedisOk:
    async def ping(self) -> bool:
        return True


class _FakeRedisFail:
    async def ping(self) -> bool:
        raise RuntimeError("boom")


def _make_app(engine: AsyncEngine | None, redis: Any) -> FastAPI:
    app = FastAPI()
    app.state.engine = engine
    app.state.redis = redis
    app.include_router(health_router)
    return app


async def test_live_always_ok() -> None:
    app = _make_app(engine=None, redis=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_ok_when_deps_up(engine: AsyncEngine) -> None:
    app = _make_app(engine=engine, redis=_FakeRedisOk())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"db": "ok", "redis": "ok"}


async def test_ready_503_when_redis_down(engine: AsyncEngine) -> None:
    app = _make_app(engine=engine, redis=_FakeRedisFail())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"].startswith("error:")


async def test_ready_503_when_db_down() -> None:
    class _BadEngine:
        def connect(self) -> Any:
            raise RuntimeError("db down")

    app = _make_app(engine=_BadEngine(), redis=_FakeRedisOk())  # type: ignore[arg-type]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["db"].startswith("error:")
    assert body["checks"]["redis"] == "ok"
