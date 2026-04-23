"""Module install/upgrade/uninstall service tests.

These tests commit real transactions against the testcontainers Postgres,
because the module's alembic migrations open their own connection and must
see our session's writes. Each test cleans up by running hard-uninstall.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from parcel_shell.modules import service
from parcel_shell.modules.models import InstalledModule


@pytest.fixture
async def real_session(migrations_applied: str) -> AsyncIterator[AsyncSession]:
    """A real, committing AsyncSession. Caller is responsible for cleanup."""
    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            yield s
    finally:
        await engine.dispose()


@pytest.fixture
def index(discovered_test_module) -> dict:
    return {discovered_test_module.module.name: discovered_test_module}


async def _cleanup(db: AsyncSession, name: str, index: dict, url: str) -> None:
    row = await db.get(InstalledModule, name)
    if row is not None:
        try:
            await service.uninstall_module(
                db, name=name, drop_data=True, discovered=index, database_url=url
            )
            await db.commit()
        except Exception:
            await db.rollback()
    # Defensive: also drop schema and permissions if left behind from a failed install.
    await db.execute(text(f'DROP SCHEMA IF EXISTS "mod_{name}" CASCADE'))
    await db.execute(text("DELETE FROM shell.permissions WHERE module = :n"), {"n": name})
    await db.commit()


async def test_install_happy_path(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    try:
        row = await service.install_module(
            real_session,
            name="test",
            approve_capabilities=["http_egress"],
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()

        assert row.name == "test"
        assert row.is_active is True
        assert row.capabilities == ["http_egress"]
        assert row.schema_name == "mod_test"
        assert row.last_migrated_rev == "0001"

        async with real_session.bind.connect() as conn:  # type: ignore[union-attr]
            tables = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'mod_test' ORDER BY table_name"
                    )
                )
            ).all()
        assert {r[0] for r in tables} == {"items", "alembic_version"}
    finally:
        await _cleanup(real_session, "test", index, migrations_applied)


async def test_install_rejects_capability_mismatch(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    with pytest.raises(service.CapabilityMismatch):
        await service.install_module(
            real_session,
            name="test",
            approve_capabilities=[],
            discovered=index,
            database_url=migrations_applied,
        )


async def test_install_rejects_unknown_module(
    real_session: AsyncSession, migrations_applied: str
) -> None:
    with pytest.raises(service.ModuleNotDiscovered):
        await service.install_module(
            real_session,
            name="nope",
            approve_capabilities=[],
            discovered={},
            database_url=migrations_applied,
        )


async def test_install_rejects_double_install(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    try:
        await service.install_module(
            real_session,
            name="test",
            approve_capabilities=["http_egress"],
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()
        with pytest.raises(service.ModuleAlreadyInstalled):
            await service.install_module(
                real_session,
                name="test",
                approve_capabilities=["http_egress"],
                discovered=index,
                database_url=migrations_applied,
            )
    finally:
        await _cleanup(real_session, "test", index, migrations_applied)


async def test_uninstall_soft_keeps_schema(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    try:
        await service.install_module(
            real_session,
            name="test",
            approve_capabilities=["http_egress"],
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()

        await service.uninstall_module(
            real_session,
            name="test",
            drop_data=False,
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()

        row = await real_session.get(InstalledModule, "test")
        assert row is not None
        assert row.is_active is False

        async with real_session.bind.connect() as conn:  # type: ignore[union-attr]
            schema = (
                await conn.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name = 'mod_test'"
                    )
                )
            ).scalar_one_or_none()
        assert schema == "mod_test"
    finally:
        await _cleanup(real_session, "test", index, migrations_applied)


async def test_uninstall_hard_drops_everything(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    await service.install_module(
        real_session,
        name="test",
        approve_capabilities=["http_egress"],
        discovered=index,
        database_url=migrations_applied,
    )
    await real_session.commit()

    await service.uninstall_module(
        real_session,
        name="test",
        drop_data=True,
        discovered=index,
        database_url=migrations_applied,
    )
    await real_session.commit()

    assert await real_session.get(InstalledModule, "test") is None

    async with real_session.bind.connect() as conn:  # type: ignore[union-attr]
        schema = (
            await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'mod_test'"
                )
            )
        ).scalar_one_or_none()
        perm = (
            await conn.execute(
                text("SELECT name FROM shell.permissions WHERE name = 'test.read'")
            )
        ).scalar_one_or_none()
    assert schema is None
    assert perm is None


async def test_upgrade_is_noop_when_at_head(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    try:
        await service.install_module(
            real_session,
            name="test",
            approve_capabilities=["http_egress"],
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()

        row = await service.upgrade_module(
            real_session,
            name="test",
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()
        assert row.last_migrated_rev == "0001"
    finally:
        await _cleanup(real_session, "test", index, migrations_applied)


async def test_sync_on_boot_flips_orphans(
    real_session: AsyncSession, index, migrations_applied: str
) -> None:
    try:
        await service.install_module(
            real_session,
            name="test",
            approve_capabilities=["http_egress"],
            discovered=index,
            database_url=migrations_applied,
        )
        await real_session.commit()

        await service.sync_on_boot(real_session, discovered={})
        await real_session.commit()

        row = await real_session.get(InstalledModule, "test")
        assert row is not None and row.is_active is False
    finally:
        await _cleanup(real_session, "test", index, migrations_applied)
