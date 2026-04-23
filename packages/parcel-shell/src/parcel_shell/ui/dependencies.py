from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.cookies import verify_session_cookie
from parcel_shell.auth.dependencies import COOKIE_NAME as SESSION_COOKIE_NAME
from parcel_shell.auth.sessions import bump, lookup
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import User
from parcel_shell.ui.flash import COOKIE_NAME as FLASH_COOKIE_NAME
from parcel_shell.ui.flash import Flash, pack


class HTMLRedirect(Exception):
    """Raised by HTML-facing dependencies to signal a redirect.

    A FastAPI exception handler (installed in create_app) converts this into
    a 303 RedirectResponse at the edge of the request, keeping dep type
    signatures honest (-> User instead of User | Response).
    """

    def __init__(self, location: str, *, flash: Flash | None = None) -> None:
        self.location = location
        self.flash = flash


async def _try_current_user(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    secret = request.app.state.settings.session_secret
    sid = verify_session_cookie(token, secret=secret)
    if sid is None:
        return None
    s = await lookup(db, sid)
    if s is None:
        return None
    await bump(db, s)
    user = await db.get(User, s.user_id)
    if user is None or not user.is_active:
        return None
    return user


async def current_user_html(
    request: Request, db: AsyncSession = Depends(get_session)
) -> User:
    """HTML-route auth: redirect to /login?next=... on 401, otherwise return user."""
    user = await _try_current_user(request, db)
    if user is None:
        next_url = request.url.path
        if request.url.query:
            next_url += "?" + request.url.query
        raise HTMLRedirect(f"/login?next={quote_plus(next_url)}")
    return user


def html_require_permission(name: str) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: User = Depends(current_user_html),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        perms = await service.effective_permissions(db, user.id)
        if name not in perms:
            raise HTMLRedirect(
                "/",
                flash=Flash(kind="error", msg=f"You don't have permission: {name}"),
            )
        return user

    return _dep


def set_flash(response: Response, flash: Flash, *, secret: str) -> None:
    """Set the parcel_flash cookie on the given response."""
    response.set_cookie(
        key=FLASH_COOKIE_NAME,
        value=pack(flash, secret=secret),
        max_age=60,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
