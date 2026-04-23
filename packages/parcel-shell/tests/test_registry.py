from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import Permission
from parcel_shell.rbac.registry import (
    PermissionRegistry,
    RegisteredPermission,
    register_shell_permissions,
)


def test_register_adds_permission() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo", module="shell")
    items = reg.all()
    assert items == [RegisteredPermission(name="foo.read", description="Read foo", module="shell")]


def test_register_duplicate_same_description_is_noop() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    reg.register("foo.read", "Read foo")
    assert len(reg.all()) == 1


def test_register_duplicate_different_description_raises() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    with pytest.raises(ValueError, match="foo.read"):
        reg.register("foo.read", "Something else")


def test_register_shell_permissions_adds_eight() -> None:
    reg = PermissionRegistry()
    register_shell_permissions(reg)
    names = {p.name for p in reg.all()}
    assert names == {
        "users.read",
        "users.write",
        "roles.read",
        "roles.write",
        "users.roles.assign",
        "sessions.read",
        "sessions.revoke",
        "permissions.read",
    }


async def test_sync_to_db_upserts(db_session: AsyncSession) -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    reg.register("foo.write", "Write foo")
    await reg.sync_to_db(db_session)
    await db_session.flush()

    rows = (await db_session.execute(select(Permission).order_by(Permission.name))).scalars().all()
    names = [r.name for r in rows]
    assert "foo.read" in names and "foo.write" in names

    # re-sync does not duplicate; description update propagates
    reg2 = PermissionRegistry()
    reg2.register("foo.read", "Read foo v2")
    await reg2.sync_to_db(db_session)
    await db_session.flush()
    db_session.expire_all()

    got = (await db_session.execute(select(Permission).where(Permission.name == "foo.read"))).scalar_one()
    assert got.description == "Read foo v2"
