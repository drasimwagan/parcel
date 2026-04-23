"""Standard alembic env.py entry point for Parcel modules.

A module's alembic/env.py is expected to be a single call:

    from parcel_mod_foo import module
    from parcel_sdk.alembic_env import run_async_migrations
    run_async_migrations(module)
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

if TYPE_CHECKING:
    from parcel_sdk.module import Module


def run_async_migrations(module: "Module") -> None:
    """Run the calling module's migrations scoped to its own `mod_<name>` schema.

    Reads `sqlalchemy.url` from the alembic config first, falling back to the
    ``DATABASE_URL`` environment variable. Creates the module schema if needed,
    keeps the version table inside the module schema, and runs migrations.
    """
    cfg = context.config
    database_url = cfg.get_main_option("sqlalchemy.url") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL not set and no sqlalchemy.url in alembic config"
        )
    cfg.set_main_option("sqlalchemy.url", database_url)
    schema = f"mod_{module.name}"

    asyncio.run(_run(module, schema))


async def _run(module: "Module", schema: str) -> None:
    cfg = context.config
    connectable = async_engine_from_config(
        cfg.get_section(cfg.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.commit()
        await conn.run_sync(lambda c: _do(c, module, schema))
    await connectable.dispose()


def _do(connection: Connection, module: "Module", schema: str) -> None:
    context.configure(
        connection=connection,
        target_metadata=module.metadata,
        version_table="alembic_version",
        version_table_schema=schema,
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
