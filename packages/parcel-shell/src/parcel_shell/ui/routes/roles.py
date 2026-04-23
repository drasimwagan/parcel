from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.db import get_session
from parcel_shell.rbac import service
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


@router.get("/roles", response_class=HTMLResponse)
async def roles_list(
    request: Request,
    user=Depends(html_require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "roles/list.html",
        {**(await _ctx(request, user, db, "/roles")), "roles": roles},
    )


@router.get("/roles/new", response_class=HTMLResponse)
async def roles_new_form(
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(request, "roles/new.html", await _ctx(request, user, db, "/roles"))


@router.post("/roles")
async def roles_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    new_role = await service.create_role(db, name=name, description=description or None)
    response = RedirectResponse(url=f"/roles/{new_role.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created role {new_role.name}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/roles/{role_id}", response_class=HTMLResponse)
async def roles_detail(
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "roles/detail.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )


@router.post("/roles/{role_id}/edit")
async def roles_edit(
    role_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.update_role(db, role, name=name, description=description or None)
    except service.BuiltinRoleError:
        response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg="Built-in roles cannot be modified."),
            secret=request.app.state.settings.session_secret,
        )
        return response
    response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Role updated."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/roles/{role_id}/delete")
async def roles_delete(
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.delete_role(db, role)
    except service.BuiltinRoleError:
        response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg="Built-in roles cannot be deleted."),
            secret=request.app.state.settings.session_secret,
        )
        return response
    response = RedirectResponse(url="/roles", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Deleted role {role.name}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/roles/{role_id}/permissions", response_class=HTMLResponse)
async def roles_add_permission(
    role_id: uuid.UUID,
    request: Request,
    permission_name: str = Form(...),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.assign_permission_to_role(db, role=role, permission_name=permission_name)
    except service.PermissionNotRegistered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permission_not_found") from None
    await db.refresh(role, ["permissions"])
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "roles/_perms_block.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )


@router.post("/roles/{role_id}/permissions/{name}/remove", response_class=HTMLResponse)
async def roles_remove_permission(
    role_id: uuid.UUID,
    name: str,
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    await service.unassign_permission_from_role(db, role=role, permission_name=name)
    await db.refresh(role, ["permissions"])
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "roles/_perms_block.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )
