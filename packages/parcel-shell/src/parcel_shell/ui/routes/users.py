from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.auth.sessions import revoke_all_for_user
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": sidebar_for(request, perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    user=Depends(html_require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    users, _ = await service.list_users(db, offset=0, limit=200)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "users/list.html",
        {**(await _ctx(request, user, db, "/users")), "users": users},
    )


@router.get("/users/new", response_class=HTMLResponse)
async def users_new_form(
    request: Request,
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(request, "users/new.html", await _ctx(request, user, db, "/users"))


@router.post("/users")
async def users_create(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        new_user = await service.create_user(db, email=email, password=password)
    except ValueError as e:
        tpl = get_templates()
        return tpl.TemplateResponse(
            request,
            "users/new.html",
            {**(await _ctx(request, user, db, "/users")), "error": str(e), "email": email},
            status_code=400,
        )
    response = RedirectResponse(url=f"/users/{new_user.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created {new_user.email}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def users_detail(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "users/detail.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.post("/users/{user_id}/edit")
async def users_edit(
    user_id: uuid.UUID,
    request: Request,
    email: str = Form(...),
    is_active: str | None = Form(None),
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    try:
        await service.update_user(db, user=target, email=email, is_active=(is_active is not None))
    except service.SystemIdentityError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system_identity_immutable") from None
    response = Response(status_code=204)
    set_flash(
        response,
        Flash(kind="success", msg="User updated."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/users/{user_id}/delete")
async def users_delete(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    try:
        await service.deactivate_user(db, user=target)
    except service.SystemIdentityError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system_identity_immutable") from None
    response = Response(status_code=204)
    set_flash(
        response,
        Flash(kind="info", msg="User deactivated."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/users/{user_id}/roles", response_class=HTMLResponse)
async def users_add_role(
    user_id: uuid.UUID,
    request: Request,
    role_id: uuid.UUID = Form(...),
    user=Depends(html_require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.assign_role_to_user(db, user=target, role=role)
    except service.SystemIdentityError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system_identity_immutable") from None
    await db.refresh(target, ["roles"])
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "users/_roles_block.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.post("/users/{user_id}/roles/{role_id}/remove", response_class=HTMLResponse)
async def users_remove_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    role = await service.get_role(db, role_id)
    if target is None or role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    try:
        await service.unassign_role_from_user(db, user=target, role=role)
    except service.SystemIdentityError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system_identity_immutable") from None
    await db.refresh(target, ["roles"])
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "users/_roles_block.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.get("/users/{user_id}/sessions", response_class=HTMLResponse)
async def users_sessions(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("sessions.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(DbSession)
                .where(
                    DbSession.user_id == user_id,
                    DbSession.revoked_at.is_(None),
                    DbSession.expires_at > now,
                )
                .order_by(DbSession.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "users/sessions.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "sessions": rows,
        },
    )


@router.post("/users/{user_id}/sessions/revoke")
async def users_sessions_revoke(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("sessions.revoke")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_all_for_user(db, user_id)
    response = RedirectResponse(url=f"/users/{user_id}/sessions", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="All sessions revoked."),
        secret=request.app.state.settings.session_secret,
    )
    return response
