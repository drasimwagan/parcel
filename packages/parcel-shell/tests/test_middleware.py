from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from parcel_shell.logging import configure_logging, request_id_var
from parcel_shell.middleware import RequestIdMiddleware


@pytest.fixture
def app() -> FastAPI:
    configure_logging(env="prod", level="INFO")
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/peek")
    async def peek() -> dict[str, str]:
        return {"request_id": request_id_var.get()}

    return app


async def test_middleware_echoes_provided_header(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/peek", headers={"X-Request-ID": "test-123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "test-123"
    assert r.json() == {"request_id": "test-123"}


async def test_middleware_generates_uuid_when_absent(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/peek")
    generated = r.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f-]{36}", generated)
    uuid.UUID(generated)
    assert r.json() == {"request_id": generated}
