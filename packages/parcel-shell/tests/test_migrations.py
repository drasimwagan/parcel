from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_shell" / "alembic.ini"


def _make_config(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def test_upgrade_head_creates_shell_schema(database_url: str, engine: AsyncEngine) -> None:
    cfg = _make_config(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'shell'")
        )
        assert result.scalar_one_or_none() == "shell"


async def test_downgrade_base_removes_shell_schema(database_url: str, engine: AsyncEngine) -> None:
    cfg = _make_config(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "base")

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'shell'")
        )
        assert result.scalar_one_or_none() is None

    # Restore state so later tests (which share the session-scoped testcontainer) still see `head`.
    await asyncio.to_thread(command.upgrade, cfg, "head")
