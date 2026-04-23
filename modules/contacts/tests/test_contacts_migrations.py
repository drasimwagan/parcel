from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_mod_contacts" / "alembic.ini"


def _cfg(url: str) -> Config:
    c = Config(str(ALEMBIC_INI))
    c.set_main_option("sqlalchemy.url", url)
    return c


async def test_upgrade_creates_mod_contacts_schema(database_url: str, engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()

    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'mod_contacts' ORDER BY table_name"
                )
            )
        ).all()
    names = {r[0] for r in tables}
    assert names == {"alembic_version", "companies", "contacts"}

    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()


async def test_downgrade_removes_tables(database_url: str, engine: AsyncEngine) -> None:
    cfg = _cfg(database_url)
    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()

    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "base")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'mod_contacts'"
                )
            )
        ).all()
    names = {r[0] for r in tables}
    assert "contacts" not in names
    assert "companies" not in names

    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()
