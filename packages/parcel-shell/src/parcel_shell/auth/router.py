from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth import sessions as sess
from parcel_shell.auth.cookies import sign_session_id, verify_session_cookie
from parcel_shell.auth.dependencies import COOKIE_NAME, current_user
from parcel_shell.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RoleSummary,
    UserSummary,
)
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import User

_log = structlog.get_logger("parcel_shell.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


async def _me_payload(db: AsyncSession, user: User) -> MeResponse:
    perms = await service.effective_permissions(db, user.id)
    return MeResponse(
        user=UserSummary(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
        roles=[RoleSummary(id=r.id, name=r.name) for r in user.roles],
        permissions=sorted(perms),
    )


def _apply_cookie(response: Response, *, request: Request, session_id: uuid.UUID) -> None:
    secret = request.app.state.settings.session_secret
    env = request.app.state.settings.env
    token = sign_session_id(session_id, secret=secret)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(env != "dev"),
        samesite="lax",
        path="/",
    )


async def _classify_login_failure(db: AsyncSession, email: str) -> str:
    row = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if row is None:
        return "no_user"
    if not row.is_active:
        return "inactive"
    return "bad_password"


@router.post("/login", response_model=MeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    user_obj = await service.authenticate(db, email=payload.email, password=payload.password)
    if user_obj is None:
        reason = await _classify_login_failure(db, payload.email)
        _log.warning("auth.login_failed", email=payload.email, reason=reason)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")

    s = await sess.create_session(
        db,
        user_id=user_obj.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    _apply_cookie(response, request=request, session_id=s.id)
    return await _me_payload(db, user_obj)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        sid = verify_session_cookie(token, secret=request.app.state.settings.session_secret)
        if sid is not None:
            s = await sess.lookup(db, sid)
            if s is not None:
                await sess.revoke(db, s)
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> MeResponse:
    return await _me_payload(db, user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await service.change_password(
            db,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except service.InvalidCredentials as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_current_password") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
