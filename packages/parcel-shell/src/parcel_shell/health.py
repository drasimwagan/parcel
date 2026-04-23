from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import Request

router = APIRouter(prefix="/health", tags=["health"])

_TIMEOUT_SECONDS = 5.0


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


async def _check_db(engine: Any) -> str:
    try:
        async def _run() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_run(), timeout=_TIMEOUT_SECONDS)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


async def _check_redis(redis: Any) -> str:
    try:
        await asyncio.wait_for(redis.ping(), timeout=_TIMEOUT_SECONDS)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    redis = request.app.state.redis
    db_status, redis_status = await asyncio.gather(
        _check_db(engine), _check_redis(redis)
    )
    checks = {"db": db_status, "redis": redis_status}
    if all(v == "ok" for v in checks.values()):
        return JSONResponse({"status": "ok", "checks": checks})
    return JSONResponse({"status": "degraded", "checks": checks}, status_code=503)
