from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from parcel_shell.ui.flash import COOKIE_NAME, unpack


class FlashMiddleware(BaseHTTPMiddleware):
    """Pop the parcel_flash cookie onto request.state; clear it in the response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        secret = request.app.state.settings.session_secret
        request.state.flash = unpack(token, secret=secret) if token else None
        response = await call_next(request)
        if token is not None:
            response.delete_cookie(COOKIE_NAME, path="/")
        return response
