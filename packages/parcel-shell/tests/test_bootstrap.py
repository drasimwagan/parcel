from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.bootstrap import create_admin_user


async def test_create_admin_creates_user_and_assigns_admin_role(
    db_session: AsyncSession,
) -> None:
    u = await create_admin_user(
        db_session, email="root@x.com", password="password-1234"
    )
    assert u.email == "root@x.com"
    role_names = {r.name for r in u.roles}
    assert "admin" in role_names


async def test_create_admin_rejects_short_password(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="at least 12"):
        await create_admin_user(db_session, email="x@x.com", password="short")


async def test_create_admin_duplicate_email_without_force_raises(
    db_session: AsyncSession,
) -> None:
    await create_admin_user(db_session, email="dup@x.com", password="password-1234")
    with pytest.raises(RuntimeError, match="already exists"):
        await create_admin_user(
            db_session, email="dup@x.com", password="password-1234"
        )


async def test_create_admin_with_force_rehashes_preserves_role(
    db_session: AsyncSession,
) -> None:
    u1 = await create_admin_user(db_session, email="f@x.com", password="password-1234")
    original_hash = u1.password_hash
    u2 = await create_admin_user(
        db_session, email="f@x.com", password="new-password-1234", force=True
    )
    assert u2.id == u1.id
    assert u2.password_hash != original_hash
    assert any(r.name == "admin" for r in u2.roles)
