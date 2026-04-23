from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from starlette.requests import Request

SHELL_SCHEMA = "shell"

shell_metadata: MetaData = MetaData(schema=SHELL_SCHEMA)


class ShellBase(DeclarativeBase):
    """Declarative base for all shell-owned tables.

    Tables defined against this base live in the `shell` schema via
    ``shell_metadata``, so Alembic autogenerate picks them up automatically.
    """

    metadata = shell_metadata


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an AsyncSession per request.

    Commits on successful completion, rolls back on any exception. This keeps
    write-bearing endpoints (login, admin mutations, etc.) durable without
    requiring each handler to call ``session.commit()`` itself.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
