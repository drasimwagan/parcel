from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.hashing import hash_password, needs_rehash, verify_password
from parcel_shell.rbac.models import Permission, Role, User, role_permissions, user_roles

MIN_PASSWORD_LENGTH = 12


class InvalidCredentials(Exception):
    """Wrong current password on change-password."""


class BuiltinRoleError(Exception):
    """Tried to mutate or delete an is_builtin=True role."""


class PermissionNotRegistered(Exception):
    """Tried to assign a permission that is not in `shell.permissions`."""


# ── Users ───────────────────────────────────────────────────────────────

async def create_user(
    db: AsyncSession, *, email: str, password: str, is_active: bool = True
) -> User:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    u = User(
        email=email.lower(),
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(u)
    await db.flush()
    return u


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User | None:
    u = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if u is None:
        return None
    if not verify_password(u.password_hash, password):
        return None
    if not u.is_active:
        return None
    if needs_rehash(u.password_hash):
        u.password_hash = hash_password(password)
        u.updated_at = datetime.now(timezone.utc)
    return u


async def change_password(
    db: AsyncSession, *, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise InvalidCredentials()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def list_users(db: AsyncSession, *, offset: int = 0, limit: int = 50) -> tuple[list[User], int]:
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    rows = (
        await db.execute(select(User).order_by(User.created_at).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), total


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def update_user(
    db: AsyncSession, *, user: User, email: str | None = None, is_active: bool | None = None
) -> User:
    if email is not None:
        user.email = email.lower()
    if is_active is not None:
        user.is_active = is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def deactivate_user(db: AsyncSession, *, user: User) -> User:
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    from parcel_shell.auth.sessions import revoke_all_for_user

    await revoke_all_for_user(db, user.id)
    await db.flush()
    return user


# ── Roles ───────────────────────────────────────────────────────────────

async def create_role(db: AsyncSession, *, name: str, description: str | None = None) -> Role:
    r = Role(name=name, description=description)
    db.add(r)
    await db.flush()
    return r


async def list_roles(db: AsyncSession) -> list[Role]:
    return list((await db.execute(select(Role).order_by(Role.name))).scalars().all())


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> Role | None:
    return await db.get(Role, role_id)


async def update_role(
    db: AsyncSession, role: Role, *, name: str | None = None, description: str | None = None
) -> Role:
    if role.is_builtin:
        raise BuiltinRoleError(role.name)
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    await db.flush()
    return role


async def delete_role(db: AsyncSession, role: Role) -> None:
    if role.is_builtin:
        raise BuiltinRoleError(role.name)
    await db.delete(role)
    await db.flush()


async def assign_permission_to_role(
    db: AsyncSession, *, role: Role, permission_name: str
) -> None:
    perm = await db.get(Permission, permission_name)
    if perm is None:
        raise PermissionNotRegistered(permission_name)
    # Ensure the `permissions` relationship is loaded before we read it.
    await db.refresh(role, ["permissions"])
    if any(p.name == permission_name for p in role.permissions):
        return
    role.permissions.append(perm)
    await db.flush()


async def unassign_permission_from_role(
    db: AsyncSession, *, role: Role, permission_name: str
) -> None:
    await db.refresh(role, ["permissions"])
    role.permissions = [p for p in role.permissions if p.name != permission_name]
    await db.flush()


# ── User ↔ Role ─────────────────────────────────────────────────────────

async def assign_role_to_user(db: AsyncSession, *, user: User, role: Role) -> None:
    await db.refresh(user, ["roles"])
    if any(r.id == role.id for r in user.roles):
        return
    user.roles.append(role)
    await db.flush()


async def unassign_role_from_user(db: AsyncSession, *, user: User, role: Role) -> None:
    await db.refresh(user, ["roles"])
    user.roles = [r for r in user.roles if r.id != role.id]
    await db.flush()


# ── Permissions ─────────────────────────────────────────────────────────

async def list_permissions(db: AsyncSession) -> list[Permission]:
    return list(
        (await db.execute(select(Permission).order_by(Permission.name))).scalars().all()
    )


async def effective_permissions(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = (
        await db.execute(
            select(role_permissions.c.permission_name)
            .select_from(role_permissions)
            .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
            .where(user_roles.c.user_id == user_id)
            .distinct()
        )
    ).all()
    return {r[0] for r in rows}
