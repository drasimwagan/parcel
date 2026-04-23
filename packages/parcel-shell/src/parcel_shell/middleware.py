from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from parcel_shell.logging import request_id_var

HEADER_NAME = "X-Request-ID"

_log = structlog.get_logger("parcel_shell.middleware")


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(HEADER_NAME)
        request_id = incoming if incoming else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:  # noqa: BLE001
                _log.exception(
                    "shell.unhandled_exception",
                    error=str(exc),
                    request_id=request_id,
                )
                response = JSONResponse(
                    {"error": "internal_server_error", "request_id": request_id},
                    status_code=500,
                )
        finally:
            request_id_var.reset(token)
        response.headers[HEADER_NAME] = request_id
        return response
