"""Tests for parcel-mod-contacts.

Shared fixtures (committing_admin, migrations_applied, etc.) are registered
as a pytest plugin by the workspace-root conftest.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_mod_contacts" / "alembic.ini"


@pytest.fixture
async def contacts_session(migrations_applied: str) -> AsyncIterator[AsyncSession]:
    """Real committing session with mod_contacts schema migrated."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", migrations_applied)

    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await conn.commit()
        await asyncio.to_thread(command.upgrade, cfg, "head")

        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            yield s
    finally:
        async with engine.connect() as conn:
            await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await conn.commit()
        await engine.dispose()
