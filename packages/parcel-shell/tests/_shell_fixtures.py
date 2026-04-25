from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
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


@pytest.fixture
async def sessionmaker_factory(migrations_applied: str):
    """Real committing sessionmaker for runner tests that need an isolated session.

    Truncates `shell.workflow_audit` on both setup and teardown so the test
    sees a clean slate even when sibling tests (which don't use this fixture)
    have written audit rows earlier in the run.
    """
    from sqlalchemy import text as _text

    eng = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        await s.execute(_text("TRUNCATE TABLE shell.workflow_audit"))
        await s.commit()
    try:
        yield factory
    finally:
        async with factory() as s:
            await s.execute(_text("TRUNCATE TABLE shell.workflow_audit"))
            await s.commit()
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
            async_session = async_sessionmaker(
                bind=conn, expire_on_commit=False, class_=AsyncSession
            )
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


# ── Phase 3 fixtures ────────────────────────────────────────────────────

_FIXTURE_MODULE_SRC = (Path(__file__).parent / "_fixtures" / "test_module" / "src").resolve()


@pytest.fixture(scope="session")
def test_module_on_path() -> Iterator[None]:
    """Put the fixture module's src/ on sys.path for the session."""
    import sys

    added = str(_FIXTURE_MODULE_SRC)
    if added not in sys.path:
        sys.path.insert(0, added)
    yield


@pytest.fixture
def discovered_test_module(test_module_on_path: None):
    """Load the fixture module fresh and return a DiscoveredModule."""
    import importlib
    import sys

    for mod_name in list(sys.modules):
        if mod_name.startswith("parcel_mod_test"):
            del sys.modules[mod_name]
    mod_pkg = importlib.import_module("parcel_mod_test")

    from parcel_shell.modules.discovery import DiscoveredModule

    return DiscoveredModule(
        module=mod_pkg.module,
        distribution_name="parcel-mod-test",
        distribution_version="0.1.0",
    )


@pytest.fixture
def patch_entry_points(monkeypatch, discovered_test_module):
    """Make discovery return the fixture module."""
    from importlib.metadata import EntryPoint

    import parcel_shell.modules.discovery as disco

    synthetic = EntryPoint(
        name="test",
        value="parcel_mod_test:module",
        group="parcel.modules",
    )

    def fake_entry_points(*, group: str):
        return [synthetic] if group == "parcel.modules" else []

    monkeypatch.setattr(disco, "entry_points", fake_entry_points)
    return discovered_test_module


@pytest.fixture
def empty_entry_points(monkeypatch):
    """Make discovery return nothing."""
    import parcel_shell.modules.discovery as disco

    def fake_entry_points(*, group: str):
        return []

    monkeypatch.setattr(disco, "entry_points", fake_entry_points)


# For module router tests that need real commits (the service commits mid-request
# so alembic sees the schema). Uses the production get_session (which commits on
# success) instead of the savepoint-wrapped db_session.


@pytest.fixture
async def committing_app(settings: Settings) -> AsyncIterator[Any]:
    from parcel_shell.app import create_app

    fastapi_app = create_app(settings=settings)
    async with LifespanManager(fastapi_app):
        yield fastapi_app


@pytest.fixture
async def committing_client(committing_app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=committing_app, raise_app_exceptions=False),
        base_url="http://t",
    ) as c:
        yield c


@pytest.fixture
async def committing_admin(committing_client: AsyncClient, settings: Settings):
    """Create a fresh admin user, log in, clean up after."""
    import uuid

    from sqlalchemy import select

    from parcel_shell.bootstrap import create_admin_user
    from parcel_shell.rbac.models import User

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    email = f"admin-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234-long"

    try:
        async with factory() as s:
            await create_admin_user(s, email=email, password=password, force=False)
            await s.commit()

        r = await committing_client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        yield committing_client
    finally:
        async with factory() as s:
            user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is not None:
                await s.delete(user)
                await s.commit()
        await engine.dispose()


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
async def admin_user(user_factory, db_session: AsyncSession) -> User:
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
