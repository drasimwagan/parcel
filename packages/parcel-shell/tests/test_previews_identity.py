from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.auth.cookies import verify_session_cookie
from parcel_shell.rbac.models import Permission, Role, role_permissions
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.sandbox.previews import identity

PREVIEW_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")


def _make_factory(url: str):
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_sync_preview_role_assigns_all_permissions(migrations_applied: str) -> None:
    engine, factory = _make_factory(migrations_applied)
    try:
        # Insert a fresh permission to verify it gets synced.
        async with factory() as s:
            s.add(Permission(name="test.preview.sync", description="x", module="shell"))
            await s.commit()

        await identity.sync_preview_role(factory)

        async with factory() as s:
            role = (
                await s.execute(select(Role).where(Role.name == "sandbox-preview"))
            ).scalar_one()
            synced = (
                (
                    await s.execute(
                        select(role_permissions.c.permission_name).where(
                            role_permissions.c.role_id == role.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert "test.preview.sync" in synced
    finally:
        async with factory() as s:
            from sqlalchemy import delete

            await s.execute(delete(Permission).where(Permission.name == "test.preview.sync"))
            await s.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_preview_role_idempotent(migrations_applied: str) -> None:
    engine, factory = _make_factory(migrations_applied)
    try:
        await identity.sync_preview_role(factory)
        await identity.sync_preview_role(factory)  # second call must not raise

        async with factory() as s:
            role = (
                await s.execute(select(Role).where(Role.name == "sandbox-preview"))
            ).scalar_one()
            count_first = len(
                (
                    await s.execute(
                        select(role_permissions.c.permission_name).where(
                            role_permissions.c.role_id == role.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        await identity.sync_preview_role(factory)
        async with factory() as s:
            count_second = len(
                (
                    await s.execute(
                        select(role_permissions.c.permission_name).where(
                            role_permissions.c.role_id == role.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert count_first == count_second
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mint_and_revoke_session_cookie(migrations_applied: str, settings) -> None:
    engine, factory = _make_factory(migrations_applied)
    try:
        session_id, cookie_value = await identity.mint_session_cookie(factory, settings)

        # Cookie deserializes back to the session_id.
        parsed = verify_session_cookie(cookie_value, secret=settings.session_secret)
        assert parsed == session_id

        # Session row exists, points at preview user.
        async with factory() as s:
            row = await s.get(DbSession, session_id)
            assert row is not None
            assert row.user_id == PREVIEW_USER_ID
            assert row.revoked_at is None

        await identity.revoke_session(factory, session_id)
        async with factory() as s:
            row = await s.get(DbSession, session_id)
            assert row is not None
            assert row.revoked_at is not None
    finally:
        await engine.dispose()
