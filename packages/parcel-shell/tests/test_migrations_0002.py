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


async def test_0002_creates_expected_tables(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' ORDER BY table_name"
                )
            )
        ).all()
    names = {r[0] for r in rows}
    assert names == {"users", "sessions", "permissions", "roles", "user_roles", "role_permissions"}


async def test_0002_seeds_admin_role_with_all_shell_permissions(
    database_url: str, engine: AsyncEngine
) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        role = (
            await conn.execute(
                text("SELECT id, name, is_builtin FROM shell.roles WHERE name = 'admin'")
            )
        ).one()
        assert role.is_builtin is True

        rows = (
            await conn.execute(
                text(
                    "SELECT permission_name FROM shell.role_permissions "
                    "WHERE role_id = :rid ORDER BY permission_name"
                ),
                {"rid": role.id},
            )
        ).all()
    assert {r[0] for r in rows} == {
        "users.read",
        "users.write",
        "roles.read",
        "roles.write",
        "users.roles.assign",
        "sessions.read",
        "sessions.revoke",
        "permissions.read",
    }


async def test_0002_downgrade_removes_tables(database_url: str, engine: AsyncEngine) -> None:
    cfg = _cfg(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "0001")

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'shell'"
                )
            )
        ).all()
    assert rows == []

    # Restore state so later tests see `head`.
    await asyncio.to_thread(command.upgrade, cfg, "head")
