from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from parcel_shell.auth.cookies import verify_session_cookie
from parcel_shell.auth.sessions import bump, lookup
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.rbac.models import User

COOKIE_NAME = "parcel_session"


async def current_session(
    request: Request, db: AsyncSession = Depends(get_session)
) -> DbSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    secret = request.app.state.settings.session_secret
    session_id = verify_session_cookie(token, secret=secret)
    if session_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_session")
    s = await lookup(db, session_id)
    if s is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session_expired")
    await bump(db, s)
    return s


async def current_user(
    s: DbSession = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> User:
    u = await db.get(User, s.user_id)
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_unavailable")
    return u


def require_permission(name: str) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
    ) -> User:
        perms = await service.effective_permissions(db, user.id)
        if name not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")
        return user

    return _dep
