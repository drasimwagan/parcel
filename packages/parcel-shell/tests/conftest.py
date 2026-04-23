from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from parcel_shell.auth.hashing import hash_password
from parcel_shell.config import Settings
from parcel_shell.db import get_session
from parcel_shell.rbac.models import Role, User

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_shell" / "alembic.ini"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    raw = postgres_container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


def _upgrade_head(url: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def migrations_applied(database_url: str) -> str:
    """Runs `alembic upgrade head` once per test session; returns the DB URL.

    Returning the URL (not an engine) avoids cross-event-loop reuse of
    asyncpg connections, which is unreliable on Windows.
    """
    _upgrade_head(database_url)
    return database_url


@pytest.fixture
async def db_session(migrations_applied: str) -> AsyncIterator[AsyncSession]:
    """Per-test AsyncSession wrapped in a savepoint that is always rolled back."""
    eng = create_async_engine(migrations_applied, pool_pre_ping=True)
    try:
        async with eng.connect() as conn:
            trans = await conn.begin()
            async_session = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
            try:
                async with async_session() as s:
                    yield s
            finally:
                await trans.rollback()
    finally:
        await eng.dispose()


@pytest.fixture
def settings(migrations_applied: str) -> Settings:
    return Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": migrations_applied,
            "REDIS_URL": "redis://localhost:1",
            "PARCEL_LOG_LEVEL": "WARNING",
        }
    )


@pytest.fixture
async def app(settings: Settings, db_session: AsyncSession) -> AsyncIterator[Any]:
    """FastAPI app whose `get_session` dep is wired to `db_session`."""
    from parcel_shell.app import create_app

    fastapi_app = create_app(settings=settings)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    fastapi_app.dependency_overrides[get_session] = _override_session

    async with LifespanManager(fastapi_app):
        yield fastapi_app


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://t",
    ) as c:
        yield c


# ── Factories ────────────────────────────────────────────────────────────

@pytest.fixture
def user_factory(db_session: AsyncSession):
    async def _make(
        email: str | None = None,
        password: str = "password-1234",
        roles: tuple[Role, ...] = (),
        is_active: bool = True,
    ) -> User:
        u = User(
            id=uuid.uuid4(),
            email=(email or f"u-{uuid.uuid4().hex[:8]}@x.com").lower(),
            password_hash=hash_password(password),
            is_active=is_active,
        )
        if roles:
            u.roles = list(roles)
        db_session.add(u)
        await db_session.flush()
        return u

    return _make


@pytest.fixture
def role_factory(db_session: AsyncSession):
    async def _make(
        name: str | None = None,
        permissions: tuple[str, ...] = (),
        is_builtin: bool = False,
    ) -> Role:
        from parcel_shell.rbac.models import Permission

        role = Role(
            id=uuid.uuid4(),
            name=name or f"role-{uuid.uuid4().hex[:6]}",
            is_builtin=is_builtin,
        )
        if permissions:
            perms = []
            for p in permissions:
                existing = await db_session.get(Permission, p)
                perms.append(existing or Permission(name=p, description=p, module="shell"))
            role.permissions = perms
        db_session.add(role)
        await db_session.flush()
        return role

    return _make


@pytest.fixture
async def admin_user(
    user_factory, db_session: AsyncSession
) -> User:
    from sqlalchemy import select

    admin_role = (await db_session.execute(select(Role).where(Role.name == "admin"))).scalar_one()
    return await user_factory(email="admin@test.example.com", roles=(admin_role,))


@pytest.fixture
async def authed_client(client: AsyncClient, admin_user: User) -> AsyncClient:
    r = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "password-1234"},
    )
    assert r.status_code == 200, r.text
    return client
