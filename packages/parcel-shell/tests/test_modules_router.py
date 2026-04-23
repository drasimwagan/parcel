"""Module admin router tests.

Uses `committing_admin` — a real-commit client (not savepoint-wrapped) because
the install flow commits mid-request so alembic sees the schema. Each test
cleans up the fixture module state via hard-uninstall so later tests see a
clean slate.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from parcel_shell.config import Settings


@pytest.fixture(autouse=True)
async def _cleanup_test_module(settings: Settings):
    """Before and after each test: make sure mod_test and its row are gone."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _wipe() -> None:
        async with factory() as s:
            await s.execute(text("DELETE FROM shell.installed_modules WHERE name = 'test'"))
            await s.execute(text("DELETE FROM shell.permissions WHERE module = 'test'"))
            await s.execute(text('DROP SCHEMA IF EXISTS "mod_test" CASCADE'))
            await s.commit()

    await _wipe()
    try:
        yield
    finally:
        await _wipe()
        await engine.dispose()


async def test_list_requires_auth(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/admin/modules")
    assert r.status_code == 401


async def test_list_shows_discovered_only(committing_admin, patch_entry_points) -> None:
    r = await committing_admin.get("/admin/modules")
    assert r.status_code == 200
    items = {m["name"]: m for m in r.json()}
    assert "test" in items
    assert items["test"]["is_discoverable"] is True
    assert items["test"]["is_active"] is None


async def test_install_requires_exact_capability_approval(
    committing_admin, patch_entry_points
) -> None:
    r = await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": []},
    )
    assert r.status_code == 403


async def test_install_happy_path(committing_admin, patch_entry_points) -> None:
    r = await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_active"] is True
    assert body["schema_name"] == "mod_test"

    lr = await committing_admin.get("/admin/modules")
    items = {m["name"]: m for m in lr.json()}
    assert items["test"]["is_active"] is True

    pr = await committing_admin.get("/admin/permissions")
    assert any(p["name"] == "test.read" for p in pr.json())


async def test_install_duplicate_is_409(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    assert r.status_code == 409


async def test_upgrade_happy_path(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await committing_admin.post("/admin/modules/test/upgrade")
    assert r.status_code == 200
    assert r.json()["last_migrated_rev"] == "0001"


async def test_uninstall_soft(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await committing_admin.post("/admin/modules/test/uninstall")
    assert r.status_code == 204
    got = await committing_admin.get("/admin/modules/test")
    assert got.json()["is_active"] is False


async def test_uninstall_hard(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await committing_admin.post("/admin/modules/test/uninstall?drop_data=true")
    assert r.status_code == 204
    got = await committing_admin.get("/admin/modules/test")
    assert got.status_code == 200
    assert got.json()["is_active"] is None
