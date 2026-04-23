from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from parcel_shell.db import SHELL_SCHEMA, shell_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer env var in production; tests set sqlalchemy.url directly.
env_url = os.getenv("DATABASE_URL")
if env_url and not config.get_main_option("sqlalchemy.url", "").startswith(
    "postgresql+asyncpg://"
):
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = shell_metadata


def _do_run_migrations(connection: Connection) -> None:
    # alembic_version intentionally lives in `public` (not `shell`):
    # the baseline migration drops the shell schema on downgrade, which would
    # also drop a version table sited there and break alembic's bookkeeping.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        # Ensure the shell schema exists before Alembic tries to write its version table there.
        await connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{SHELL_SCHEMA}"')
        await connection.commit()
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())
