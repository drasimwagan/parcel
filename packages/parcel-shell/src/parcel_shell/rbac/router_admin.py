from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.dependencies import require_permission
from parcel_shell.auth.schemas import RoleSummary, UserSummary
from parcel_shell.auth.sessions import revoke_all_for_user
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.rbac.schemas import (
    AssignPermissionRequest,
    AssignRoleRequest,
    CreateRoleRequest,
    CreateUserRequest,
    PermissionResponse,
    RoleDetailResponse,
    SessionResponse,
    UpdateRoleRequest,
    UpdateUserRequest,
    UserDetailResponse,
    UserListResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_detail(u) -> UserDetailResponse:
    return UserDetailResponse(
        id=u.id,
        email=u.email,
        is_active=u.is_active,
        created_at=u.created_at,
        updated_at=u.updated_at,
        roles=[RoleSummary(id=r.id, name=r.name) for r in u.roles],
    )


def _role_detail(role) -> RoleDetailResponse:
    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_builtin=role.is_builtin,
        permissions=sorted(p.name for p in role.permissions),
    )


# ── Users ───────────────────────────────────────────────────────────────


@router.get("/users", response_model=UserListResponse)
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: object = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> UserListResponse:
    items, total = await service.list_users(db, offset=offset, limit=limit)
    return UserListResponse(
        items=[
            UserSummary(id=u.id, email=u.email, is_active=u.is_active, created_at=u.created_at)
            for u in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/users", response_model=UserDetailResponse, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.create_user(db, email=payload.email, password=payload.password)
    for rid in payload.role_ids:
        role = await service.get_role(db, rid)
        if role is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"role {rid} not found")
        await service.assign_role_to_user(db, user=u, role=role)
    await db.flush()
    await db.refresh(u, attribute_names=["roles"])
    return _user_detail(u)


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    return _user_detail(u)


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def patch_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.update_user(db, user=u, email=payload.email, is_active=payload.is_active)
    return _user_detail(u)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.deactivate_user(db, user=u)
    return Response(status_code=204)


@router.post("/users/{user_id}/roles", status_code=204)
async def assign_role(
    user_id: uuid.UUID,
    payload: AssignRoleRequest,
    _: object = Depends(require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, payload.role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    await service.assign_role_to_user(db, user=u, role=role)
    return Response(status_code=204)


@router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
async def unassign_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    _: object = Depends(require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, role_id)
    if role is None:
        return Response(status_code=204)
    await service.unassign_role_from_user(db, user=u, role=role)
    return Response(status_code=204)


# ── Roles ───────────────────────────────────────────────────────────────


@router.get("/roles", response_model=list[RoleDetailResponse])
async def list_roles(
    _: object = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> list[RoleDetailResponse]:
    return [_role_detail(r) for r in await service.list_roles(db)]


@router.post("/roles", response_model=RoleDetailResponse, status_code=201)
async def create_role(
    payload: CreateRoleRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.create_role(db, name=payload.name, description=payload.description)
    await db.refresh(r, ["permissions"])
    return _role_detail(r)


@router.get("/roles/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: uuid.UUID,
    _: object = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    return _role_detail(r)


@router.patch("/roles/{role_id}", response_model=RoleDetailResponse)
async def patch_role(
    role_id: uuid.UUID,
    payload: UpdateRoleRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.update_role(db, r, name=payload.name, description=payload.description)
    except service.BuiltinRoleError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "builtin_role_protected") from e
    await db.refresh(r, ["permissions"])
    return _role_detail(r)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        return Response(status_code=204)
    try:
        await service.delete_role(db, r)
    except service.BuiltinRoleError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "builtin_role_protected") from e
    return Response(status_code=204)


@router.post("/roles/{role_id}/permissions", status_code=204)
async def assign_permission(
    role_id: uuid.UUID,
    payload: AssignPermissionRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.assign_permission_to_role(db, role=r, permission_name=payload.permission_name)
    except service.PermissionNotRegistered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permission_not_found") from e
    return Response(status_code=204)


@router.delete("/roles/{role_id}/permissions/{permission_name}", status_code=204)
async def unassign_permission(
    role_id: uuid.UUID,
    permission_name: str,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        return Response(status_code=204)
    await service.unassign_permission_from_role(db, role=r, permission_name=permission_name)
    return Response(status_code=204)


# ── Permissions ─────────────────────────────────────────────────────────


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _: object = Depends(require_permission("permissions.read")),
    db: AsyncSession = Depends(get_session),
) -> list[PermissionResponse]:
    rows = await service.list_permissions(db)
    return [
        PermissionResponse(name=p.name, description=p.description, module=p.module) for p in rows
    ]


# ── Sessions ────────────────────────────────────────────────────────────


@router.get("/users/{user_id}/sessions", response_model=list[SessionResponse])
async def list_user_sessions(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("sessions.read")),
    db: AsyncSession = Depends(get_session),
) -> list[SessionResponse]:
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(DbSession)
                .where(
                    and_(
                        DbSession.user_id == user_id,
                        DbSession.revoked_at.is_(None),
                        DbSession.expires_at > now,
                    )
                )
                .order_by(DbSession.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        SessionResponse(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            ip_address=str(s.ip_address) if s.ip_address else None,
            user_agent=s.user_agent,
        )
        for s in rows
    ]


@router.post("/users/{user_id}/sessions/revoke", status_code=204)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("sessions.revoke")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_all_for_user(db, user_id)
    return Response(status_code=204)
