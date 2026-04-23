from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac import service
from parcel_shell.rbac.models import Permission


async def test_create_user_lowercases_email(db_session: AsyncSession) -> None:
    u = await service.create_user(db_session, email="FOO@Bar.com", password="password-1234")
    assert u.email == "foo@bar.com"
    assert u.password_hash.startswith("$argon2")


async def test_create_user_rejects_short_password(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="at least 12"):
        await service.create_user(db_session, email="x@x.com", password="short")


async def test_authenticate_success(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(email="ok@x.com", password="password-1234")
    got = await service.authenticate(db_session, email="ok@x.com", password="password-1234")
    assert got is not None and got.id == u.id


async def test_authenticate_wrong_password(db_session: AsyncSession, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    assert await service.authenticate(db_session, email="ok@x.com", password="nope") is None


async def test_authenticate_inactive_user(db_session: AsyncSession, user_factory) -> None:
    await user_factory(email="off@x.com", password="password-1234", is_active=False)
    assert await service.authenticate(db_session, email="off@x.com", password="password-1234") is None


async def test_authenticate_unknown_user(db_session: AsyncSession) -> None:
    assert await service.authenticate(db_session, email="missing@x.com", password="x") is None


async def test_change_password_success(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(password="password-1234")
    await service.change_password(
        db_session, user=u, current_password="password-1234", new_password="new-password-1234"
    )
    assert await service.authenticate(db_session, email=u.email, password="new-password-1234")


async def test_change_password_wrong_current(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(password="password-1234")
    with pytest.raises(service.InvalidCredentials):
        await service.change_password(
            db_session, user=u, current_password="wrong", new_password="new-password-1234"
        )


async def test_role_crud_and_builtin_protection(db_session: AsyncSession, role_factory) -> None:
    r = await service.create_role(db_session, name="editor", description="Edits things")
    assert r.name == "editor"

    builtin = await role_factory(name="guard", is_builtin=True)
    with pytest.raises(service.BuiltinRoleError):
        await service.delete_role(db_session, builtin)
    with pytest.raises(service.BuiltinRoleError):
        await service.update_role(db_session, builtin, name="renamed")


async def test_effective_permissions_unions_roles(
    db_session: AsyncSession, user_factory, role_factory
) -> None:
    r1 = await role_factory(permissions=("users.read",))
    r2 = await role_factory(permissions=("users.write", "users.read"))
    u = await user_factory(roles=(r1, r2))
    perms = await service.effective_permissions(db_session, u.id)
    assert perms == {"users.read", "users.write"}


async def test_assign_permission_requires_registered(
    db_session: AsyncSession, role_factory
) -> None:
    r = await role_factory()
    with pytest.raises(service.PermissionNotRegistered):
        await service.assign_permission_to_role(db_session, role=r, permission_name="bogus.perm")


async def test_assign_permission_idempotent(db_session: AsyncSession, role_factory) -> None:
    # seed a registered permission via the table
    db_session.add(Permission(name="foo.read", description="x", module="shell"))
    await db_session.flush()
    r = await role_factory()
    await service.assign_permission_to_role(db_session, role=r, permission_name="foo.read")
    await service.assign_permission_to_role(db_session, role=r, permission_name="foo.read")
    assert {p.name for p in r.permissions} == {"foo.read"}
