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


async def test_0007_creates_workflow_audit(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'workflow_audit'"
                )
            )
        ).all()
    assert len(rows) == 1


async def test_0007_columns(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'shell' AND table_name = 'workflow_audit' "
                    "ORDER BY column_name"
                )
            )
        ).all()
    cols = {r[0] for r in rows}
    assert {
        "id",
        "created_at",
        "module",
        "workflow_slug",
        "event",
        "subject_id",
        "status",
        "error_message",
        "failed_action_index",
        "payload",
    }.issubset(cols)


async def test_0007_downgrade_drops_table(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    await asyncio.to_thread(command.downgrade, _cfg(database_url), "0006")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'workflow_audit'"
                )
            )
        ).all()
    assert len(rows) == 0
    # Restore for subsequent tests in the session.
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
