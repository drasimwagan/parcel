from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_shell" / "alembic.ini"


def _cfg(url: str) -> Config:
    c = Config(str(ALEMBIC_INI))
    c.set_main_option("sqlalchemy.url", url)
    return c


async def test_0003_creates_installed_modules(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'installed_modules'"
                )
            )
        ).all()
    assert len(rows) == 1


async def test_0003_seeds_module_permissions_on_admin(
    database_url: str, engine: AsyncEngine
) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT id FROM shell.roles WHERE name = 'admin'"))).one()
        perms = (
            await conn.execute(
                text(
                    "SELECT permission_name FROM shell.role_permissions "
                    "WHERE role_id = :rid AND permission_name LIKE 'modules.%' "
                    "ORDER BY permission_name"
                ),
                {"rid": row.id},
            )
        ).all()
    assert [r[0] for r in perms] == [
        "modules.install",
        "modules.read",
        "modules.uninstall",
        "modules.upgrade",
    ]


async def test_0003_downgrade_removes_table_and_permissions(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _cfg(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "0002")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'installed_modules'"
                )
            )
        ).all()
        perms = (
            await conn.execute(
                text("SELECT name FROM shell.permissions WHERE name LIKE 'modules.%'")
            )
        ).all()
    assert tables == []
    assert perms == []

    # Restore state for subsequent tests.
    await asyncio.to_thread(command.upgrade, cfg, "head")
