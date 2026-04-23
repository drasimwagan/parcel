from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from parcel_shell.db import create_engine, shell_metadata


async def test_create_engine_connects(database_url: str) -> None:
    eng = create_engine(database_url)
    try:
        async with eng.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await eng.dispose()


def test_shell_metadata_uses_shell_schema() -> None:
    assert shell_metadata.schema == "shell"


async def test_provided_engine_fixture_works(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT 42"))).scalar_one() == 42
