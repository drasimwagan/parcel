from __future__ import annotations

import asyncio
import uuid
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


async def test_0008_adds_attempt_column(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'shell' "
                    "AND table_name = 'workflow_audit' "
                    "AND column_name = 'attempt'"
                )
            )
        ).all()
    assert len(rows) == 1
    assert rows[0][1] == "NO"  # NOT NULL


async def test_0008_existing_rows_get_attempt_default(
    database_url: str, engine: AsyncEngine
) -> None:
    """Insert a row before applying 0008, upgrade, confirm attempt=1."""
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "0007")
    rid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO shell.workflow_audit "
                "(id, module, workflow_slug, event, status, payload) "
                "VALUES (:id, 'm', 's', 'e', 'ok', '{}'::json)"
            ),
            {"id": rid},
        )
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        attempt = (
            await conn.execute(
                text("SELECT attempt FROM shell.workflow_audit WHERE id = :id"),
                {"id": rid},
            )
        ).scalar_one()
    assert attempt == 1
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM shell.workflow_audit WHERE id = :id"), {"id": rid}
        )


async def test_0008_downgrade_drops_column(
    database_url: str, engine: AsyncEngine
) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    await asyncio.to_thread(command.downgrade, _cfg(database_url), "0007")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'shell' "
                    "AND table_name = 'workflow_audit' "
                    "AND column_name = 'attempt'"
                )
            )
        ).all()
    assert rows == []
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
