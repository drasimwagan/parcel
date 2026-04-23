# Phase 2 — Auth + RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a JSON-only authentication + RBAC layer: users, Argon2id-hashed passwords, server-side sessions keyed by a signed cookie, roles, permissions with a registry seam modules will hook into in Phase 3, `/auth/*` and `/admin/*` endpoints, and a `python -m parcel_shell.bootstrap create-admin` CLI — all covered by pytest against the existing testcontainers Postgres.

**Architecture:** Five focused modules under `parcel_shell/auth/` (hashing, cookies, sessions, dependencies, router) and four under `parcel_shell/rbac/` (registry, models, service, router_admin). Services are pure async functions over an `AsyncSession`; routers are thin parse/call/serialize layers; FastAPI dependencies (`current_user`, `require_permission`) are the single enforcement point. One Alembic migration (`0002_auth_rbac`) creates six tables in the `shell` schema and seeds the built-in `admin` role with all shell permissions.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async (declarative) · asyncpg · Alembic · argon2-cffi · itsdangerous · pydantic · pytest + pytest-asyncio · testcontainers · asgi-lifespan · httpx.

**Reference spec:** `docs/superpowers/specs/2026-04-23-phase-2-auth-rbac-design.md`

---

## File plan

**Create:**
- `packages/parcel-shell/src/parcel_shell/auth/__init__.py`
- `packages/parcel-shell/src/parcel_shell/auth/hashing.py`
- `packages/parcel-shell/src/parcel_shell/auth/cookies.py`
- `packages/parcel-shell/src/parcel_shell/auth/sessions.py`
- `packages/parcel-shell/src/parcel_shell/auth/dependencies.py`
- `packages/parcel-shell/src/parcel_shell/auth/router.py`
- `packages/parcel-shell/src/parcel_shell/auth/schemas.py`
- `packages/parcel-shell/src/parcel_shell/rbac/__init__.py`
- `packages/parcel-shell/src/parcel_shell/rbac/models.py`
- `packages/parcel-shell/src/parcel_shell/rbac/registry.py`
- `packages/parcel-shell/src/parcel_shell/rbac/service.py`
- `packages/parcel-shell/src/parcel_shell/rbac/schemas.py`
- `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py`
- `packages/parcel-shell/src/parcel_shell/bootstrap.py`
- `packages/parcel-shell/src/parcel_shell/alembic/versions/0002_auth_rbac.py`
- `packages/parcel-shell/tests/test_hashing.py`
- `packages/parcel-shell/tests/test_cookies.py`
- `packages/parcel-shell/tests/test_sessions.py`
- `packages/parcel-shell/tests/test_registry.py`
- `packages/parcel-shell/tests/test_rbac_service.py`
- `packages/parcel-shell/tests/test_auth_router.py`
- `packages/parcel-shell/tests/test_admin_users_router.py`
- `packages/parcel-shell/tests/test_admin_roles_router.py`
- `packages/parcel-shell/tests/test_admin_sessions_router.py`
- `packages/parcel-shell/tests/test_bootstrap.py`
- `packages/parcel-shell/tests/test_auth_integration.py`

**Modify:**
- `packages/parcel-shell/pyproject.toml` — add `argon2-cffi`, `itsdangerous`
- `packages/parcel-shell/src/parcel_shell/app.py` — wire registry + new routers into lifespan
- `packages/parcel-shell/src/parcel_shell/db.py` — add `ShellBase` declarative base
- `packages/parcel-shell/tests/conftest.py` — add `migrated_engine`, `db_session`, `app`, `client`, factory fixtures
- `CLAUDE.md` — mark Phase 2 done, Phase 3 next, note new deps

---

## Task 1: Add dependencies

**Files:**
- Modify: `packages/parcel-shell/pyproject.toml`

- [ ] **Step 1: Edit `packages/parcel-shell/pyproject.toml`**

Add `argon2-cffi>=23.1` and `itsdangerous>=2.2` to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "redis>=5.2",
    "pydantic>=2.10",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "argon2-cffi>=23.1",
    "itsdangerous>=2.2",
]
```

- [ ] **Step 2: Sync the workspace**

Run: `uv sync --all-packages`
Expected: adds `argon2-cffi` and `itsdangerous` (plus any transitive deps) without errors.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/pyproject.toml uv.lock
git commit -m "chore(shell): add argon2-cffi and itsdangerous for Phase 2"
```

---

## Task 2: Password hashing

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/auth/hashing.py`
- Create: `packages/parcel-shell/tests/test_hashing.py`

- [ ] **Step 1: Create empty `auth/__init__.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/__init__.py` with no content.

- [ ] **Step 2: Write the failing test**

Create `packages/parcel-shell/tests/test_hashing.py`:

```python
from __future__ import annotations

from parcel_shell.auth.hashing import hash_password, needs_rehash, verify_password


def test_hash_password_returns_argon2_string() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2")
    assert len(h) > 50


def test_verify_roundtrip() -> None:
    h = hash_password("swordfish-123!")
    assert verify_password(h, "swordfish-123!") is True


def test_verify_rejects_wrong_password() -> None:
    h = hash_password("swordfish-123!")
    assert verify_password(h, "something-else") is False


def test_verify_handles_malformed_hash() -> None:
    assert verify_password("not-a-real-hash", "whatever") is False


def test_needs_rehash_false_for_fresh_hash() -> None:
    h = hash_password("pw-twelve-chars")
    assert needs_rehash(h) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_hashing.py -v`
Expected: FAIL — `parcel_shell.auth.hashing` not found.

- [ ] **Step 4: Implement `hashing.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/hashing.py`:

```python
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        return _hasher.verify(hashed, plaintext)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:  # noqa: BLE001
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_hashing.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/auth packages/parcel-shell/tests/test_hashing.py
git commit -m "feat(shell): Argon2id password hashing helpers"
```

---

## Task 3: Signed session-id cookies

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/cookies.py`
- Create: `packages/parcel-shell/tests/test_cookies.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_cookies.py`:

```python
from __future__ import annotations

import uuid

from parcel_shell.auth.cookies import sign_session_id, verify_session_cookie


def test_sign_then_verify_roundtrip() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    assert verify_session_cookie(token, secret="a" * 32) == sid


def test_verify_rejects_tampered_token() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    tampered = token[:-2] + ("zz" if not token.endswith("zz") else "aa")
    assert verify_session_cookie(tampered, secret="a" * 32) is None


def test_verify_rejects_wrong_secret() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    assert verify_session_cookie(token, secret="b" * 32) is None


def test_verify_rejects_malformed_token() -> None:
    assert verify_session_cookie("", secret="a" * 32) is None
    assert verify_session_cookie("garbage", secret="a" * 32) is None
    assert verify_session_cookie("only-one-half", secret="a" * 32) is None


def test_verify_rejects_non_uuid_payload() -> None:
    from itsdangerous import URLSafeSerializer

    forged = URLSafeSerializer("a" * 32).dumps("not-a-uuid")
    assert verify_session_cookie(forged, secret="a" * 32) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_cookies.py -v`
Expected: FAIL — `parcel_shell.auth.cookies` not found.

- [ ] **Step 3: Implement `cookies.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/cookies.py`:

```python
from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeSerializer

_SALT = "parcel.session.v1"


def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt=_SALT)


def sign_session_id(session_id: uuid.UUID, *, secret: str) -> str:
    return _serializer(secret).dumps(str(session_id))


def verify_session_cookie(token: str, *, secret: str) -> uuid.UUID | None:
    if not token:
        return None
    try:
        raw = _serializer(secret).loads(token)
    except BadSignature:
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_cookies.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/auth/cookies.py packages/parcel-shell/tests/test_cookies.py
git commit -m "feat(shell): signed session-id cookie helpers via itsdangerous"
```

---

## Task 4: ShellBase declarative base + SQLAlchemy models

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/db.py`
- Create: `packages/parcel-shell/src/parcel_shell/rbac/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/rbac/models.py`

- [ ] **Step 1: Add `ShellBase` to `db.py`**

Modify `packages/parcel-shell/src/parcel_shell/db.py`. Add `ShellBase` below the `shell_metadata` line:

```python
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
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with session_factory() as session:
        yield session
```

- [ ] **Step 2: Create empty `rbac/__init__.py`**

Create `packages/parcel-shell/src/parcel_shell/rbac/__init__.py` with no content.

- [ ] **Step 3: Create `rbac/models.py`**

Create `packages/parcel-shell/src/parcel_shell/rbac/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, ForeignKey, Index, Table, Text, func
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from parcel_shell.db import ShellBase

ABSOLUTE_TTL = timedelta(days=7)
IDLE_TTL = timedelta(hours=24)


def _uuid4() -> uuid.UUID:
    return uuid.uuid4()


def _expires_at() -> datetime:
    return datetime.now(timezone.utc) + ABSOLUTE_TTL


user_roles = Table(
    "user_roles",
    ShellBase.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("shell.users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("shell.roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    ShellBase.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("shell.roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_name", Text, ForeignKey("shell.permissions.name", ondelete="CASCADE"), primary_key=True),
)


class User(ShellBase):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")


class Session(ShellBase):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shell.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_expires_at
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class Role(ShellBase):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )


class Permission(ShellBase):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False, server_default="shell", default="shell")
```

- [ ] **Step 4: Sanity check — models import without error**

Run: `uv run python -c "from parcel_shell.rbac import models; print(sorted(m.__tablename__ for m in [models.User, models.Session, models.Role, models.Permission]))"`

Expected output: `['permissions', 'roles', 'sessions', 'users']`

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/db.py packages/parcel-shell/src/parcel_shell/rbac/__init__.py packages/parcel-shell/src/parcel_shell/rbac/models.py
git commit -m "feat(shell): ShellBase declarative base + user/session/role/permission models"
```

---

## Task 5: Permission registry

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/rbac/registry.py`
- Create: `packages/parcel-shell/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_registry.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import Permission
from parcel_shell.rbac.registry import (
    PermissionRegistry,
    RegisteredPermission,
    register_shell_permissions,
)


def test_register_adds_permission() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo", module="shell")
    items = reg.all()
    assert items == [RegisteredPermission(name="foo.read", description="Read foo", module="shell")]


def test_register_duplicate_same_description_is_noop() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    reg.register("foo.read", "Read foo")
    assert len(reg.all()) == 1


def test_register_duplicate_different_description_raises() -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    with pytest.raises(ValueError, match="foo.read"):
        reg.register("foo.read", "Something else")


def test_register_shell_permissions_adds_eight() -> None:
    reg = PermissionRegistry()
    register_shell_permissions(reg)
    names = {p.name for p in reg.all()}
    assert names == {
        "users.read",
        "users.write",
        "roles.read",
        "roles.write",
        "users.roles.assign",
        "sessions.read",
        "sessions.revoke",
        "permissions.read",
    }


async def test_sync_to_db_upserts(db_session: AsyncSession) -> None:
    reg = PermissionRegistry()
    reg.register("foo.read", "Read foo")
    reg.register("foo.write", "Write foo")
    await reg.sync_to_db(db_session)
    await db_session.commit()

    rows = (await db_session.execute(select(Permission).order_by(Permission.name))).scalars().all()
    assert [r.name for r in rows] == ["foo.read", "foo.write"]

    # re-sync does not duplicate; description update propagates
    reg2 = PermissionRegistry()
    reg2.register("foo.read", "Read foo v2")
    await reg2.sync_to_db(db_session)
    await db_session.commit()

    got = (await db_session.execute(select(Permission).where(Permission.name == "foo.read"))).scalar_one()
    assert got.description == "Read foo v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_registry.py -v`
Expected: FAIL — `parcel_shell.rbac.registry` not found (and `db_session` fixture not yet present; that's fine — fixture comes in Task 7).

- [ ] **Step 3: Implement `registry.py`**

Create `packages/parcel-shell/src/parcel_shell/rbac/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import Permission


@dataclass(frozen=True)
class RegisteredPermission:
    name: str
    description: str
    module: str = "shell"


class PermissionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, RegisteredPermission] = {}

    def register(self, name: str, description: str, module: str = "shell") -> None:
        existing = self._items.get(name)
        if existing is None:
            self._items[name] = RegisteredPermission(name=name, description=description, module=module)
            return
        if existing.description != description or existing.module != module:
            raise ValueError(f"permission {name!r} re-registered with different attributes")

    def all(self) -> list[RegisteredPermission]:
        return list(self._items.values())

    async def sync_to_db(self, session: AsyncSession) -> None:
        if not self._items:
            return
        payload = [
            {"name": p.name, "description": p.description, "module": p.module}
            for p in self._items.values()
        ]
        stmt = insert(Permission).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Permission.name],
            set_={
                "description": stmt.excluded.description,
                "module": stmt.excluded.module,
            },
        )
        await session.execute(stmt)


SHELL_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("users.read", "List and view user accounts"),
    ("users.write", "Create, update, and deactivate user accounts"),
    ("roles.read", "List and view roles"),
    ("roles.write", "Create, update, and delete roles; assign permissions to roles"),
    ("users.roles.assign", "Assign and unassign roles on users"),
    ("sessions.read", "List another user's sessions"),
    ("sessions.revoke", "Revoke another user's sessions"),
    ("permissions.read", "List registered permissions"),
)


def register_shell_permissions(registry: PermissionRegistry) -> None:
    for name, description in SHELL_PERMISSIONS:
        registry.register(name, description, module="shell")


# Global singleton. Shell registers into this at import time (below); modules
# register into the same instance in Phase 3 before lifespan startup.
registry = PermissionRegistry()
register_shell_permissions(registry)
```

- [ ] **Step 4: Run test to verify the unit tests pass (skip the DB one)**

Run: `uv run pytest packages/parcel-shell/tests/test_registry.py -v -k 'not sync_to_db'`
Expected: 4 tests PASS; the `test_sync_to_db_upserts` test either errors on the missing `db_session` fixture (fine) or is skipped.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/registry.py packages/parcel-shell/tests/test_registry.py
git commit -m "feat(shell): permission registry with shell-owned permissions"
```

---

## Task 6: Alembic migration 0002_auth_rbac

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0002_auth_rbac.py`
- Create: `packages/parcel-shell/tests/test_migrations_0002.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_migrations_0002.py`:

```python
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


async def test_0002_downgrade_removes_tables(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _cfg(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "0001")

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell'"
                )
            )
        ).all()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations_0002.py -v`
Expected: FAIL — migration `0002` not found (Alembic says nothing to upgrade, or auth tables don't exist).

- [ ] **Step 3: Create the migration**

Create `packages/parcel-shell/src/parcel_shell/alembic/versions/0002_auth_rbac.py`:

```python
"""auth + RBAC

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


SHELL_PERMISSIONS = (
    ("users.read", "List and view user accounts"),
    ("users.write", "Create, update, and deactivate user accounts"),
    ("roles.read", "List and view roles"),
    ("roles.write", "Create, update, and delete roles; assign permissions to roles"),
    ("users.roles.assign", "Assign and unassign roles on users"),
    ("sessions.read", "List another user's sessions"),
    ("sessions.revoke", "Revoke another user's sessions"),
    ("permissions.read", "List registered permissions"),
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="shell",
    )

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", TIMESTAMP(timezone=True)),
        sa.Column("ip_address", INET()),
        sa.Column("user_agent", sa.Text()),
        schema="shell",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema="shell")
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], schema="shell")

    op.create_table(
        "permissions",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("module", sa.Text(), nullable=False, server_default="shell"),
        schema="shell",
    )

    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="shell",
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="shell",
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_name",
            sa.Text(),
            sa.ForeignKey("shell.permissions.name", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="shell",
    )

    # Seed shell permissions.
    op.bulk_insert(
        sa.table(
            "permissions",
            sa.column("name", sa.Text()),
            sa.column("description", sa.Text()),
            sa.column("module", sa.Text()),
            schema="shell",
        ),
        [
            {"name": name, "description": description, "module": "shell"}
            for name, description in SHELL_PERMISSIONS
        ],
    )

    # Seed the built-in admin role and attach every shell permission.
    conn = op.get_bind()
    admin_id = conn.execute(
        sa.text(
            "INSERT INTO shell.roles (id, name, description, is_builtin) "
            "VALUES (gen_random_uuid(), 'admin', 'Built-in administrator role', true) "
            "RETURNING id"
        )
    ).scalar_one()

    conn.execute(
        sa.text(
            "INSERT INTO shell.role_permissions (role_id, permission_name) "
            "SELECT :rid, name FROM shell.permissions"
        ),
        {"rid": admin_id},
    )


def downgrade() -> None:
    op.drop_table("role_permissions", schema="shell")
    op.drop_table("user_roles", schema="shell")
    op.drop_table("roles", schema="shell")
    op.drop_table("permissions", schema="shell")
    op.drop_index("ix_sessions_expires_at", table_name="sessions", schema="shell")
    op.drop_index("ix_sessions_user_id", table_name="sessions", schema="shell")
    op.drop_table("sessions", schema="shell")
    op.drop_table("users", schema="shell")
```

Note: `gen_random_uuid()` requires the `pgcrypto` extension. Postgres 13+ ships it as a system extension, but it needs to be enabled. Add this line at the very top of `upgrade()`, immediately before the first `create_table` call:

```python
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations_0002.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Verify existing migration tests still pass**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations.py packages/parcel-shell/tests/test_migrations_0002.py -v`
Expected: 5 tests PASS (2 from phase 1 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/alembic/versions/0002_auth_rbac.py packages/parcel-shell/tests/test_migrations_0002.py
git commit -m "feat(shell): Alembic 0002 — auth/RBAC tables with seeded admin role"
```

---

## Task 7: Conftest additions (migrated_engine, db_session, app, client, factories)

**Files:**
- Modify: `packages/parcel-shell/tests/conftest.py`

- [ ] **Step 1: Rewrite `conftest.py`**

Replace the contents of `packages/parcel-shell/tests/conftest.py`:

```python
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
async def migrated_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Engine with `alembic upgrade head` applied once per session."""
    await asyncio.to_thread(_upgrade_head, database_url)
    eng = create_async_engine(database_url, pool_pre_ping=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def db_session(migrated_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test AsyncSession wrapped in a savepoint that is always rolled back."""
    async with migrated_engine.connect() as conn:
        trans = await conn.begin()
        async_session = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        try:
            async with async_session() as s:
                yield s
        finally:
            await trans.rollback()


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": database_url,
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
    return await user_factory(email="admin@test.local", roles=(admin_role,))


@pytest.fixture
async def authed_client(client: AsyncClient, admin_user: User) -> AsyncClient:
    r = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "password-1234"},
    )
    assert r.status_code == 200, r.text
    return client
```

- [ ] **Step 2: Verify the registry DB test now runs green**

Run: `uv run pytest packages/parcel-shell/tests/test_registry.py -v`
Expected: all 5 tests PASS (including `test_sync_to_db_upserts`).

- [ ] **Step 3: Verify the Phase 1 suite still passes**

Run: `uv run pytest packages/parcel-shell/tests/test_app_factory.py packages/parcel-shell/tests/test_health.py packages/parcel-shell/tests/test_migrations.py -v`
Expected: all previous tests PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/tests/conftest.py
git commit -m "test(shell): migrated_engine, db_session, app, client, factory fixtures"
```

---

## Task 8: Session helpers (create/lookup/bump/revoke)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/sessions.py`
- Create: `packages/parcel-shell/tests/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_sessions.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth import sessions as sess
from parcel_shell.rbac.models import IDLE_TTL, Session


async def test_create_session_persists_row(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id, ip="127.0.0.1", user_agent="pytest")
    got = (await db_session.execute(select(Session).where(Session.id == s.id))).scalar_one()
    assert got.user_id == u.id
    assert got.ip_address == "127.0.0.1"
    assert got.user_agent == "pytest"
    assert got.revoked_at is None
    assert got.expires_at > datetime.now(timezone.utc)


async def test_lookup_returns_session_when_valid(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    await db_session.flush()
    got = await sess.lookup(db_session, s.id)
    assert got is not None and got.id == s.id


async def test_lookup_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    assert await sess.lookup(db_session, uuid.uuid4()) is None


async def test_lookup_returns_none_for_revoked(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    await sess.revoke(db_session, s)
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_lookup_returns_none_when_absolute_expired(
    db_session: AsyncSession, user_factory
) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_lookup_returns_none_when_idle_expired(
    db_session: AsyncSession, user_factory
) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    s.last_seen_at = datetime.now(timezone.utc) - (IDLE_TTL + timedelta(minutes=1))
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_bump_advances_last_seen(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    original = s.last_seen_at
    s.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.flush()
    await sess.bump(db_session, s)
    await db_session.flush()
    assert s.last_seen_at > original


async def test_revoke_all_for_user(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    a = await sess.create_session(db_session, user_id=u.id)
    b = await sess.create_session(db_session, user_id=u.id)
    other_user = await user_factory()
    c = await sess.create_session(db_session, user_id=other_user.id)
    await db_session.flush()

    await sess.revoke_all_for_user(db_session, u.id)
    await db_session.flush()

    assert await sess.lookup(db_session, a.id) is None
    assert await sess.lookup(db_session, b.id) is None
    assert await sess.lookup(db_session, c.id) is not None  # unaffected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_sessions.py -v`
Expected: FAIL — `parcel_shell.auth.sessions` not found.

- [ ] **Step 3: Implement `sessions.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/sessions.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import IDLE_TTL, Session


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Session:
    s = Session(
        user_id=user_id,
        ip_address=ip,
        user_agent=(user_agent[:500] if user_agent else None),
    )
    db.add(s)
    await db.flush()
    return s


async def lookup(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    s = await db.get(Session, session_id)
    if s is None:
        return None
    if s.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    if s.expires_at <= now:
        return None
    if now - s.last_seen_at > IDLE_TTL:
        return None
    return s


async def bump(db: AsyncSession, session: Session) -> None:
    session.last_seen_at = datetime.now(timezone.utc)
    await db.flush()


async def revoke(db: AsyncSession, session: Session) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Session)
        .where(and_(Session.user_id == user_id, Session.revoked_at.is_(None)))
        .values(revoked_at=now)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_sessions.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/auth/sessions.py packages/parcel-shell/tests/test_sessions.py
git commit -m "feat(shell): session helpers — create/lookup/bump/revoke with TTL enforcement"
```

---

## Task 9: RBAC service layer

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/rbac/service.py`
- Create: `packages/parcel-shell/tests/test_rbac_service.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_rbac_service.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac import service
from parcel_shell.rbac.models import Permission


async def test_create_user_lowercases_email(db_session: AsyncSession) -> None:
    u = await service.create_user(db_session, email="FOO@Bar.com", password="password-1234")
    assert u.email == "foo@bar.com"
    assert u.password_hash.startswith("$argon2")


async def test_create_user_rejects_short_password(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="at least 12"):
        await service.create_user(db_session, email="x@x.com", password="short")


async def test_authenticate_success(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(email="ok@x.com", password="password-1234")
    got = await service.authenticate(db_session, email="ok@x.com", password="password-1234")
    assert got is not None and got.id == u.id


async def test_authenticate_wrong_password(db_session: AsyncSession, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    assert await service.authenticate(db_session, email="ok@x.com", password="nope") is None


async def test_authenticate_inactive_user(db_session: AsyncSession, user_factory) -> None:
    await user_factory(email="off@x.com", password="password-1234", is_active=False)
    assert await service.authenticate(db_session, email="off@x.com", password="password-1234") is None


async def test_authenticate_unknown_user(db_session: AsyncSession) -> None:
    assert await service.authenticate(db_session, email="missing@x.com", password="x") is None


async def test_change_password_success(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(password="password-1234")
    await service.change_password(
        db_session, user=u, current_password="password-1234", new_password="new-password-1234"
    )
    assert await service.authenticate(db_session, email=u.email, password="new-password-1234")


async def test_change_password_wrong_current(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory(password="password-1234")
    with pytest.raises(service.InvalidCredentials):
        await service.change_password(
            db_session, user=u, current_password="wrong", new_password="new-password-1234"
        )


async def test_role_crud_and_builtin_protection(db_session: AsyncSession, role_factory) -> None:
    r = await service.create_role(db_session, name="editor", description="Edits things")
    assert r.name == "editor"

    builtin = await role_factory(name="guard", is_builtin=True)
    with pytest.raises(service.BuiltinRoleError):
        await service.delete_role(db_session, builtin)
    with pytest.raises(service.BuiltinRoleError):
        await service.update_role(db_session, builtin, name="renamed")


async def test_effective_permissions_unions_roles(
    db_session: AsyncSession, user_factory, role_factory
) -> None:
    r1 = await role_factory(permissions=("users.read",))
    r2 = await role_factory(permissions=("users.write", "users.read"))
    u = await user_factory(roles=(r1, r2))
    perms = await service.effective_permissions(db_session, u.id)
    assert perms == {"users.read", "users.write"}


async def test_assign_permission_requires_registered(
    db_session: AsyncSession, role_factory
) -> None:
    r = await role_factory()
    with pytest.raises(service.PermissionNotRegistered):
        await service.assign_permission_to_role(db_session, role=r, permission_name="bogus.perm")


async def test_assign_permission_idempotent(db_session: AsyncSession, role_factory) -> None:
    # seed a registered permission via the table
    db_session.add(Permission(name="foo.read", description="x", module="shell"))
    await db_session.flush()
    r = await role_factory()
    await service.assign_permission_to_role(db_session, role=r, permission_name="foo.read")
    await service.assign_permission_to_role(db_session, role=r, permission_name="foo.read")
    assert {p.name for p in r.permissions} == {"foo.read"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_rbac_service.py -v`
Expected: FAIL — `parcel_shell.rbac.service` not found.

- [ ] **Step 3: Implement `service.py`**

Create `packages/parcel-shell/src/parcel_shell/rbac/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.hashing import hash_password, needs_rehash, verify_password
from parcel_shell.rbac.models import Permission, Role, User, role_permissions, user_roles

MIN_PASSWORD_LENGTH = 12


class InvalidCredentials(Exception):
    """Wrong current password on change-password."""


class BuiltinRoleError(Exception):
    """Tried to mutate or delete an is_builtin=True role."""


class PermissionNotRegistered(Exception):
    """Tried to assign a permission that is not in `shell.permissions`."""


# ── Users ───────────────────────────────────────────────────────────────

async def create_user(
    db: AsyncSession, *, email: str, password: str, is_active: bool = True
) -> User:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    u = User(
        email=email.lower(),
        password_hash=hash_password(password),
        is_active=is_active,
    )
    db.add(u)
    await db.flush()
    return u


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User | None:
    u = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if u is None:
        return None
    if not verify_password(u.password_hash, password):
        return None
    if not u.is_active:
        return None
    if needs_rehash(u.password_hash):
        u.password_hash = hash_password(password)
        u.updated_at = datetime.now(timezone.utc)
    return u


async def change_password(
    db: AsyncSession, *, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise InvalidCredentials()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()


async def list_users(db: AsyncSession, *, offset: int = 0, limit: int = 50) -> tuple[list[User], int]:
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    rows = (
        await db.execute(select(User).order_by(User.created_at).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), total


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def update_user(
    db: AsyncSession, *, user: User, email: str | None = None, is_active: bool | None = None
) -> User:
    if email is not None:
        user.email = email.lower()
    if is_active is not None:
        user.is_active = is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return user


async def deactivate_user(db: AsyncSession, *, user: User) -> User:
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    # Revoke sessions (imported here to avoid a circular import at module load).
    from parcel_shell.auth.sessions import revoke_all_for_user

    await revoke_all_for_user(db, user.id)
    await db.flush()
    return user


# ── Roles ───────────────────────────────────────────────────────────────

async def create_role(db: AsyncSession, *, name: str, description: str | None = None) -> Role:
    r = Role(name=name, description=description)
    db.add(r)
    await db.flush()
    return r


async def list_roles(db: AsyncSession) -> list[Role]:
    return list((await db.execute(select(Role).order_by(Role.name))).scalars().all())


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> Role | None:
    return await db.get(Role, role_id)


async def update_role(
    db: AsyncSession, role: Role, *, name: str | None = None, description: str | None = None
) -> Role:
    if role.is_builtin:
        raise BuiltinRoleError(role.name)
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    await db.flush()
    return role


async def delete_role(db: AsyncSession, role: Role) -> None:
    if role.is_builtin:
        raise BuiltinRoleError(role.name)
    await db.delete(role)
    await db.flush()


async def assign_permission_to_role(
    db: AsyncSession, *, role: Role, permission_name: str
) -> None:
    perm = await db.get(Permission, permission_name)
    if perm is None:
        raise PermissionNotRegistered(permission_name)
    if any(p.name == permission_name for p in role.permissions):
        return
    role.permissions.append(perm)
    await db.flush()


async def unassign_permission_from_role(
    db: AsyncSession, *, role: Role, permission_name: str
) -> None:
    role.permissions = [p for p in role.permissions if p.name != permission_name]
    await db.flush()


# ── User ↔ Role ─────────────────────────────────────────────────────────

async def assign_role_to_user(db: AsyncSession, *, user: User, role: Role) -> None:
    if any(r.id == role.id for r in user.roles):
        return
    user.roles.append(role)
    await db.flush()


async def unassign_role_from_user(db: AsyncSession, *, user: User, role: Role) -> None:
    user.roles = [r for r in user.roles if r.id != role.id]
    await db.flush()


# ── Permissions ─────────────────────────────────────────────────────────

async def list_permissions(db: AsyncSession) -> list[Permission]:
    return list(
        (await db.execute(select(Permission).order_by(Permission.name))).scalars().all()
    )


async def effective_permissions(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = (
        await db.execute(
            select(role_permissions.c.permission_name)
            .select_from(role_permissions)
            .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
            .where(user_roles.c.user_id == user_id)
            .distinct()
        )
    ).all()
    return {r[0] for r in rows}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_rbac_service.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/service.py packages/parcel-shell/tests/test_rbac_service.py
git commit -m "feat(shell): RBAC service layer for users, roles, permissions"
```

---

## Task 10: Auth + RBAC schemas (pydantic response/request models)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/schemas.py`
- Create: `packages/parcel-shell/src/parcel_shell/rbac/schemas.py`

- [ ] **Step 1: Create `auth/schemas.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/schemas.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class RoleSummary(BaseModel):
    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    user: UserSummary
    roles: list[RoleSummary]
    permissions: list[str]
```

- [ ] **Step 2: Create `rbac/schemas.py`**

Create `packages/parcel-shell/src/parcel_shell/rbac/schemas.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from parcel_shell.auth.schemas import RoleSummary, UserSummary


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    is_active: bool | None = None


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    roles: list[RoleSummary]


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int
    offset: int
    limit: int


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class UpdateRoleRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class RoleDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_builtin: bool
    permissions: list[str]


class PermissionResponse(BaseModel):
    name: str
    description: str
    module: str


class AssignRoleRequest(BaseModel):
    role_id: uuid.UUID


class AssignPermissionRequest(BaseModel):
    permission_name: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
```

- [ ] **Step 3: Install `email-validator` dependency**

`EmailStr` pulls in `email-validator`. Add it to `packages/parcel-shell/pyproject.toml` dependencies:

```toml
    "email-validator>=2.2",
```

Then sync:

```bash
uv sync --all-packages
```

- [ ] **Step 4: Sanity check — schemas import**

Run: `uv run python -c "from parcel_shell.auth.schemas import MeResponse; from parcel_shell.rbac.schemas import UserDetailResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/pyproject.toml uv.lock packages/parcel-shell/src/parcel_shell/auth/schemas.py packages/parcel-shell/src/parcel_shell/rbac/schemas.py
git commit -m "feat(shell): pydantic schemas for auth and RBAC APIs"
```

---

## Task 11: Auth dependencies (current_user, require_permission)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/dependencies.py`

- [ ] **Step 1: Create `dependencies.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/dependencies.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from parcel_shell.auth.cookies import verify_session_cookie
from parcel_shell.auth.sessions import bump, lookup
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.rbac.models import User

COOKIE_NAME = "parcel_session"


async def current_session(
    request: Request, db: AsyncSession = Depends(get_session)
) -> DbSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    secret = request.app.state.settings.session_secret
    session_id = verify_session_cookie(token, secret=secret)
    if session_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_session")
    s = await lookup(db, session_id)
    if s is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session_expired")
    await bump(db, s)
    return s


async def current_user(
    s: DbSession = Depends(current_session), db: AsyncSession = Depends(get_session)
) -> User:
    u = await db.get(User, s.user_id)
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_unavailable")
    return u


def require_permission(name: str) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
    ) -> User:
        perms = await service.effective_permissions(db, user.id)
        if name not in perms:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")
        return user

    return _dep
```

- [ ] **Step 2: Sanity check — dependency module imports**

Run: `uv run python -c "from parcel_shell.auth.dependencies import current_user, require_permission; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/auth/dependencies.py
git commit -m "feat(shell): current_user and require_permission FastAPI dependencies"
```

---

## Task 12: `/auth/*` router

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/auth/router.py`
- Create: `packages/parcel-shell/tests/test_auth_router.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_auth_router.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_login_success_sets_cookie(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    r = await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    assert r.status_code == 200
    assert "parcel_session" in r.cookies
    body = r.json()
    assert body["user"]["email"] == "ok@x.com"
    assert body["permissions"] == []


async def test_login_bad_password_is_401(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    r = await client.post("/auth/login", json={"email": "ok@x.com", "password": "nope-nope"})
    assert r.status_code == 401


async def test_login_inactive_user_is_401(client: AsyncClient, user_factory) -> None:
    await user_factory(email="off@x.com", password="password-1234", is_active=False)
    r = await client.post(
        "/auth/login", json={"email": "off@x.com", "password": "password-1234"}
    )
    assert r.status_code == 401


async def test_login_unknown_email_is_401(client: AsyncClient) -> None:
    r = await client.post(
        "/auth/login", json={"email": "missing@x.com", "password": "password-1234"}
    )
    assert r.status_code == 401


async def test_me_without_cookie_is_401(client: AsyncClient) -> None:
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_with_cookie_returns_user(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "ok@x.com"


async def test_logout_clears_cookie_and_invalidates_session(
    client: AsyncClient, user_factory
) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post("/auth/logout")
    assert r.status_code == 204
    r2 = await client.get("/auth/me")
    assert r2.status_code == 401


async def test_change_password_wrong_current_is_400(
    client: AsyncClient, user_factory
) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-password-1234"},
    )
    assert r.status_code == 400


async def test_change_password_success(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post(
        "/auth/change-password",
        json={"current_password": "password-1234", "new_password": "new-password-1234"},
    )
    assert r.status_code == 204
    # cookie still valid; re-login with new password
    await client.post("/auth/logout")
    r2 = await client.post(
        "/auth/login", json={"email": "ok@x.com", "password": "new-password-1234"}
    )
    assert r2.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_auth_router.py -v`
Expected: FAIL — `/auth/*` endpoints not wired up.

- [ ] **Step 3: Implement `router.py`**

Create `packages/parcel-shell/src/parcel_shell/auth/router.py`:

```python
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth import sessions as sess
from parcel_shell.auth.cookies import sign_session_id
from parcel_shell.auth.dependencies import COOKIE_NAME, current_session, current_user
from parcel_shell.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RoleSummary,
    UserSummary,
)
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.rbac.models import User

_log = structlog.get_logger("parcel_shell.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


async def _me_payload(db: AsyncSession, user: User) -> MeResponse:
    perms = await service.effective_permissions(db, user.id)
    return MeResponse(
        user=UserSummary(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
        roles=[RoleSummary(id=r.id, name=r.name) for r in user.roles],
        permissions=sorted(perms),
    )


def _apply_cookie(response: Response, *, request: Request, session_id) -> None:
    secret = request.app.state.settings.session_secret
    env = request.app.state.settings.env
    token = sign_session_id(session_id, secret=secret)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(env != "dev"),
        samesite="lax",
        path="/",
    )


async def _classify_login_failure(db: AsyncSession, email: str) -> str:
    from sqlalchemy import select

    row = (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if row is None:
        return "no_user"
    if not row.is_active:
        return "inactive"
    return "bad_password"


@router.post("/login", response_model=MeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    user_obj = await service.authenticate(db, email=payload.email, password=payload.password)
    if user_obj is None:
        reason = await _classify_login_failure(db, payload.email)
        _log.warning("auth.login_failed", email=payload.email, reason=reason)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")

    s = await sess.create_session(
        db,
        user_id=user_obj.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    _apply_cookie(response, request=request, session_id=s.id)
    return await _me_payload(db, user_obj)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        from parcel_shell.auth.cookies import verify_session_cookie

        sid = verify_session_cookie(
            token, secret=request.app.state.settings.session_secret
        )
        if sid is not None:
            s = await sess.lookup(db, sid)
            if s is not None:
                await sess.revoke(db, s)
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_session)
) -> MeResponse:
    return await _me_payload(db, user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await service.change_password(
            db,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except service.InvalidCredentials:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_current_password")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Wire the router and registry sync into the app**

Modify `packages/parcel-shell/src/parcel_shell/app.py`. The full new file contents:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI

from parcel_shell.auth.router import router as auth_router
from parcel_shell.config import Settings, get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.health import router as health_router
from parcel_shell.logging import configure_logging
from parcel_shell.middleware import RequestIdMiddleware
from parcel_shell.rbac.registry import registry as permission_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(env=settings.env, level=settings.log_level)
    log = structlog.get_logger("parcel_shell")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        sessionmaker = create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        app.state.settings = settings

        # Upsert in-memory permission registry into the DB. Phase 2 is a no-op
        # (the 0002 migration already seeded these rows); the hook exists so
        # Phase 3 modules can register permissions that land here at boot.
        async with sessionmaker() as s:
            await permission_registry.sync_to_db(s)
            await s.commit()

        log.info("shell.startup", env=settings.env)
        try:
            yield
        finally:
            await app.state.redis.aclose()
            await engine.dispose()
            log.info("shell.shutdown")

    app = FastAPI(title="Parcel Shell", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_auth_router.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 6: Verify Phase 1 health/app-factory tests still pass**

Run: `uv run pytest packages/parcel-shell/tests/test_app_factory.py packages/parcel-shell/tests/test_health.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/auth/router.py packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/tests/test_auth_router.py
git commit -m "feat(shell): /auth/* endpoints; lifespan syncs permission registry to DB"
```

---

## Task 13: `/admin/users` router

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py` (first cut — users only)
- Create: `packages/parcel-shell/tests/test_admin_users_router.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_admin_users_router.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_list_users_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/admin/users")
    assert r.status_code == 401


async def test_list_users_forbidden_without_permission(
    client: AsyncClient, user_factory
) -> None:
    await user_factory(email="peon@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "peon@x.com", "password": "password-1234"})
    r = await client.get("/admin/users")
    assert r.status_code == 403


async def test_list_users_as_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(u["email"] == "admin@test.local" for u in body["items"])


async def test_create_user_as_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "new@x.com", "password": "password-1234", "role_ids": []},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new@x.com"
    assert body["is_active"] is True


async def test_get_user_detail(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "det@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.get(f"/admin/users/{uid}")
    assert r2.status_code == 200
    assert r2.json()["email"] == "det@x.com"


async def test_patch_user(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "patch@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.patch(
        f"/admin/users/{uid}", json={"email": "patched@x.com", "is_active": False}
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["email"] == "patched@x.com"
    assert body["is_active"] is False


async def test_delete_user_deactivates_and_revokes_sessions(
    client: AsyncClient, authed_client: AsyncClient, user_factory
) -> None:
    victim = await user_factory(email="vic@x.com", password="password-1234")
    # sign the victim in to create a session
    victim_client = AsyncClient(
        transport=client._transport,
        base_url="http://t",
    )
    await victim_client.post("/auth/login", json={"email": "vic@x.com", "password": "password-1234"})

    r = await authed_client.delete(f"/admin/users/{victim.id}")
    assert r.status_code == 204

    # victim's existing session should now be invalid
    r2 = await victim_client.get("/auth/me")
    assert r2.status_code == 401


async def test_assign_and_unassign_role(authed_client: AsyncClient, role_factory) -> None:
    role = await role_factory(name="editor")
    r = await authed_client.post(
        "/admin/users",
        json={"email": "rr@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.post(
        f"/admin/users/{uid}/roles", json={"role_id": str(role.id)}
    )
    assert r2.status_code == 204

    detail = await authed_client.get(f"/admin/users/{uid}")
    assert any(rr["name"] == "editor" for rr in detail.json()["roles"])

    r3 = await authed_client.delete(f"/admin/users/{uid}/roles/{role.id}")
    assert r3.status_code == 204
    detail2 = await authed_client.get(f"/admin/users/{uid}")
    assert all(rr["name"] != "editor" for rr in detail2.json()["roles"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_users_router.py -v`
Expected: FAIL — `/admin/users` not wired up.

- [ ] **Step 3: Implement the admin router (users portion)**

Create `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.dependencies import require_permission
from parcel_shell.auth.schemas import RoleSummary, UserSummary
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.schemas import (
    AssignRoleRequest,
    CreateUserRequest,
    UpdateUserRequest,
    UserDetailResponse,
    UserListResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_detail(u) -> UserDetailResponse:
    return UserDetailResponse(
        id=u.id,
        email=u.email,
        is_active=u.is_active,
        created_at=u.created_at,
        updated_at=u.updated_at,
        roles=[RoleSummary(id=r.id, name=r.name) for r in u.roles],
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: object = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> UserListResponse:
    items, total = await service.list_users(db, offset=offset, limit=limit)
    return UserListResponse(
        items=[
            UserSummary(
                id=u.id, email=u.email, is_active=u.is_active, created_at=u.created_at
            )
            for u in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/users", response_model=UserDetailResponse, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.create_user(db, email=payload.email, password=payload.password)
    for rid in payload.role_ids:
        role = await service.get_role(db, rid)
        if role is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"role {rid} not found")
        await service.assign_role_to_user(db, user=u, role=role)
    await db.flush()
    await db.refresh(u, attribute_names=["roles"])
    return _user_detail(u)


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    return _user_detail(u)


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def patch_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.update_user(db, user=u, email=payload.email, is_active=payload.is_active)
    return _user_detail(u)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.deactivate_user(db, user=u)
    return Response(status_code=204)


@router.post("/users/{user_id}/roles", status_code=204)
async def assign_role(
    user_id: uuid.UUID,
    payload: AssignRoleRequest,
    _: object = Depends(require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, payload.role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    await service.assign_role_to_user(db, user=u, role=role)
    return Response(status_code=204)


@router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
async def unassign_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    _: object = Depends(require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    u = await service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, role_id)
    if role is None:
        return Response(status_code=204)
    await service.unassign_role_from_user(db, user=u, role=role)
    return Response(status_code=204)
```

- [ ] **Step 4: Include the admin router in `app.py`**

Modify `packages/parcel-shell/src/parcel_shell/app.py`. Add the import:

```python
from parcel_shell.rbac.router_admin import router as admin_router
```

And include it after `auth_router`:

```python
    app.include_router(admin_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_users_router.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/router_admin.py packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/tests/test_admin_users_router.py
git commit -m "feat(shell): /admin/users CRUD + role assignment endpoints"
```

---

## Task 14: `/admin/roles` + `/admin/permissions` router endpoints

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py`
- Create: `packages/parcel-shell/tests/test_admin_roles_router.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_admin_roles_router.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_list_roles_includes_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/roles")
    assert r.status_code == 200
    names = {rr["name"] for rr in r.json()}
    assert "admin" in names


async def test_create_role(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/roles", json={"name": "editor", "description": "Edits stuff"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "editor"
    assert body["is_builtin"] is False


async def test_patch_builtin_role_is_403(authed_client: AsyncClient) -> None:
    roles = (await authed_client.get("/admin/roles")).json()
    admin = next(r for r in roles if r["name"] == "admin")
    r = await authed_client.patch(f"/admin/roles/{admin['id']}", json={"name": "renamed"})
    assert r.status_code == 403


async def test_delete_builtin_role_is_403(authed_client: AsyncClient) -> None:
    roles = (await authed_client.get("/admin/roles")).json()
    admin = next(r for r in roles if r["name"] == "admin")
    r = await authed_client.delete(f"/admin/roles/{admin['id']}")
    assert r.status_code == 403


async def test_assign_permission_to_role(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/roles", json={"name": "viewer", "description": None}
    )
    rid = r.json()["id"]
    r2 = await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "users.read"}
    )
    assert r2.status_code == 204
    detail = await authed_client.get(f"/admin/roles/{rid}")
    assert "users.read" in detail.json()["permissions"]


async def test_assign_unregistered_permission_is_404(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/roles", json={"name": "mis", "description": None}
    )
    rid = r.json()["id"]
    r2 = await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "bogus.perm"}
    )
    assert r2.status_code == 404


async def test_unassign_permission(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/roles", json={"name": "cleaner", "description": None}
    )
    rid = r.json()["id"]
    await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "users.read"}
    )
    r2 = await authed_client.delete(f"/admin/roles/{rid}/permissions/users.read")
    assert r2.status_code == 204
    detail = await authed_client.get(f"/admin/roles/{rid}")
    assert "users.read" not in detail.json()["permissions"]


async def test_list_permissions(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/permissions")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert "users.read" in names and "permissions.read" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_roles_router.py -v`
Expected: FAIL — role/permission endpoints not registered.

- [ ] **Step 3: Append role + permission endpoints to `router_admin.py`**

Append to `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py` (after the user endpoints). Also add the extra imports at the top:

```python
from parcel_shell.rbac.schemas import (
    AssignPermissionRequest,
    AssignRoleRequest,
    CreateRoleRequest,
    CreateUserRequest,
    PermissionResponse,
    RoleDetailResponse,
    UpdateRoleRequest,
    UpdateUserRequest,
    UserDetailResponse,
    UserListResponse,
)
```

Then add the endpoints:

```python
def _role_detail(role) -> RoleDetailResponse:
    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_builtin=role.is_builtin,
        permissions=sorted(p.name for p in role.permissions),
    )


@router.get("/roles", response_model=list[RoleDetailResponse])
async def list_roles(
    _: object = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> list[RoleDetailResponse]:
    return [_role_detail(r) for r in await service.list_roles(db)]


@router.post("/roles", response_model=RoleDetailResponse, status_code=201)
async def create_role(
    payload: CreateRoleRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.create_role(db, name=payload.name, description=payload.description)
    return _role_detail(r)


@router.get("/roles/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: uuid.UUID,
    _: object = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    return _role_detail(r)


@router.patch("/roles/{role_id}", response_model=RoleDetailResponse)
async def patch_role(
    role_id: uuid.UUID,
    payload: UpdateRoleRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> RoleDetailResponse:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.update_role(db, r, name=payload.name, description=payload.description)
    except service.BuiltinRoleError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "builtin_role_protected")
    return _role_detail(r)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        return Response(status_code=204)
    try:
        await service.delete_role(db, r)
    except service.BuiltinRoleError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "builtin_role_protected")
    return Response(status_code=204)


@router.post("/roles/{role_id}/permissions", status_code=204)
async def assign_permission(
    role_id: uuid.UUID,
    payload: AssignPermissionRequest,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.assign_permission_to_role(
            db, role=r, permission_name=payload.permission_name
        )
    except service.PermissionNotRegistered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permission_not_found")
    return Response(status_code=204)


@router.delete("/roles/{role_id}/permissions/{permission_name}", status_code=204)
async def unassign_permission(
    role_id: uuid.UUID,
    permission_name: str,
    _: object = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    r = await service.get_role(db, role_id)
    if r is None:
        return Response(status_code=204)
    await service.unassign_permission_from_role(db, role=r, permission_name=permission_name)
    return Response(status_code=204)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _: object = Depends(require_permission("permissions.read")),
    db: AsyncSession = Depends(get_session),
) -> list[PermissionResponse]:
    rows = await service.list_permissions(db)
    return [
        PermissionResponse(name=p.name, description=p.description, module=p.module)
        for p in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_roles_router.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/router_admin.py packages/parcel-shell/tests/test_admin_roles_router.py
git commit -m "feat(shell): /admin/roles CRUD, permission assignment, /admin/permissions"
```

---

## Task 15: `/admin/users/{id}/sessions` router endpoints

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py`
- Create: `packages/parcel-shell/tests/test_admin_sessions_router.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_admin_sessions_router.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_list_sessions(
    client: AsyncClient, authed_client: AsyncClient, user_factory
) -> None:
    vic = await user_factory(email="vic@x.com", password="password-1234")
    vic_client = AsyncClient(transport=client._transport, base_url="http://t")
    await vic_client.post(
        "/auth/login", json={"email": "vic@x.com", "password": "password-1234"}
    )

    r = await authed_client.get(f"/admin/users/{vic.id}/sessions")
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_revoke_all_sessions(
    client: AsyncClient, authed_client: AsyncClient, user_factory
) -> None:
    vic = await user_factory(email="v2@x.com", password="password-1234")
    vic_client = AsyncClient(transport=client._transport, base_url="http://t")
    await vic_client.post(
        "/auth/login", json={"email": "v2@x.com", "password": "password-1234"}
    )
    ok = await vic_client.get("/auth/me")
    assert ok.status_code == 200

    r = await authed_client.post(f"/admin/users/{vic.id}/sessions/revoke")
    assert r.status_code == 204

    denied = await vic_client.get("/auth/me")
    assert denied.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_sessions_router.py -v`
Expected: FAIL — session endpoints not registered.

- [ ] **Step 3: Append session endpoints to `router_admin.py`**

Append to `packages/parcel-shell/src/parcel_shell/rbac/router_admin.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import and_, select

from parcel_shell.auth.sessions import revoke_all_for_user
from parcel_shell.rbac.models import Session as DbSession
from parcel_shell.rbac.schemas import SessionResponse


@router.get("/users/{user_id}/sessions", response_model=list[SessionResponse])
async def list_user_sessions(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("sessions.read")),
    db: AsyncSession = Depends(get_session),
) -> list[SessionResponse]:
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(DbSession)
            .where(
                and_(
                    DbSession.user_id == user_id,
                    DbSession.revoked_at.is_(None),
                    DbSession.expires_at > now,
                )
            )
            .order_by(DbSession.last_seen_at.desc())
        )
    ).scalars().all()
    return [
        SessionResponse(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            ip_address=str(s.ip_address) if s.ip_address else None,
            user_agent=s.user_agent,
        )
        for s in rows
    ]


@router.post("/users/{user_id}/sessions/revoke", status_code=204)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    _: object = Depends(require_permission("sessions.revoke")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_all_for_user(db, user_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_admin_sessions_router.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/router_admin.py packages/parcel-shell/tests/test_admin_sessions_router.py
git commit -m "feat(shell): /admin/users/{id}/sessions list and revoke endpoints"
```

---

## Task 16: Bootstrap CLI

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/bootstrap.py`
- Create: `packages/parcel-shell/tests/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_bootstrap.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.bootstrap import create_admin_user
from parcel_shell.rbac.models import Role, User


async def test_create_admin_creates_user_and_assigns_admin_role(
    db_session: AsyncSession,
) -> None:
    u = await create_admin_user(
        db_session, email="root@x.com", password="password-1234"
    )
    assert u.email == "root@x.com"
    role_names = {r.name for r in u.roles}
    assert "admin" in role_names


async def test_create_admin_rejects_short_password(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="at least 12"):
        await create_admin_user(db_session, email="x@x.com", password="short")


async def test_create_admin_duplicate_email_without_force_raises(
    db_session: AsyncSession,
) -> None:
    await create_admin_user(db_session, email="dup@x.com", password="password-1234")
    with pytest.raises(RuntimeError, match="already exists"):
        await create_admin_user(
            db_session, email="dup@x.com", password="password-1234"
        )


async def test_create_admin_with_force_rehashes_preserves_role(
    db_session: AsyncSession,
) -> None:
    u1 = await create_admin_user(db_session, email="f@x.com", password="password-1234")
    original_hash = u1.password_hash
    u2 = await create_admin_user(
        db_session, email="f@x.com", password="new-password-1234", force=True
    )
    assert u2.id == u1.id
    assert u2.password_hash != original_hash
    assert any(r.name == "admin" for r in u2.roles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_bootstrap.py -v`
Expected: FAIL — `parcel_shell.bootstrap` not found.

- [ ] **Step 3: Implement `bootstrap.py`**

Create `packages/parcel-shell/src/parcel_shell/bootstrap.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.hashing import hash_password
from parcel_shell.config import get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Role, User


async def _get_admin_role(db: AsyncSession) -> Role:
    role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
    if role is None:
        raise RuntimeError(
            "built-in admin role missing — run 'alembic upgrade head' first"
        )
    return role


async def create_admin_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    force: bool = False,
) -> User:
    if len(password) < service.MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be at least {service.MIN_PASSWORD_LENGTH} characters"
        )
    lowered = email.lower()
    existing = (
        await db.execute(select(User).where(User.email == lowered))
    ).scalar_one_or_none()
    admin_role = await _get_admin_role(db)

    if existing is not None:
        if not force:
            raise RuntimeError(f"user {lowered!r} already exists; use --force to rehash")
        existing.password_hash = hash_password(password)
        existing.updated_at = datetime.now(timezone.utc)
        if not any(r.id == admin_role.id for r in existing.roles):
            existing.roles.append(admin_role)
        await db.flush()
        return existing

    user = User(
        email=lowered,
        password_hash=hash_password(password),
        is_active=True,
    )
    user.roles = [admin_role]
    db.add(user)
    await db.flush()
    return user


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m parcel_shell.bootstrap")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create-admin", help="Create the first admin user")
    create.add_argument("--email", required=True)
    create.add_argument("--password", default=None, help="prompts if omitted")
    create.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    password = args.password
    if password is None:
        password = getpass.getpass("Password: ")

    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        async with sessionmaker() as db:
            try:
                user = await create_admin_user(
                    db, email=args.email, password=password, force=args.force
                )
            except (ValueError, RuntimeError) as e:
                await db.rollback()
                sys.stderr.write(f"error: {e}\n")
                return 1
            await db.commit()
            sys.stdout.write(f"created admin user: {user.id} <{user.email}>\n")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_bootstrap.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/bootstrap.py packages/parcel-shell/tests/test_bootstrap.py
git commit -m "feat(shell): python -m parcel_shell.bootstrap create-admin command"
```

---

## Task 17: Auth integration smoke test

**Files:**
- Create: `packages/parcel-shell/tests/test_auth_integration.py`

- [ ] **Step 1: Write the integration test**

Create `packages/parcel-shell/tests/test_auth_integration.py`:

```python
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.bootstrap import create_admin_user


async def test_admin_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    await create_admin_user(
        db_session, email="boot@x.com", password="password-1234"
    )
    await db_session.flush()

    r = await client.post(
        "/auth/login", json={"email": "boot@x.com", "password": "password-1234"}
    )
    assert r.status_code == 200

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert "users.read" in me.json()["permissions"]

    users = await client.get("/admin/users")
    assert users.status_code == 200

    await client.post("/auth/logout")

    locked = await client.get("/admin/users")
    assert locked.status_code == 401
```

- [ ] **Step 2: Run test**

Run: `uv run pytest packages/parcel-shell/tests/test_auth_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest`
Expected: all tests green across Phase 1 + Phase 2.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/tests/test_auth_integration.py
git commit -m "test(shell): end-to-end auth + admin happy-path integration test"
```

---

## Task 18: End-to-end verification under Docker Compose

**Files:** None (live verification only)

- [ ] **Step 1: Rebuild the shell image**

Run: `docker compose build shell`
Expected: succeeds; image includes the new deps.

- [ ] **Step 2: Run migrations**

Run: `docker compose run --rm shell migrate`
Expected: `INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, auth + RBAC`

- [ ] **Step 3: Bootstrap admin user**

```bash
docker compose run --rm shell python -m parcel_shell.bootstrap create-admin --email admin@parcel.local --password 'pw-at-least-12-chars'
```

Expected: `created admin user: <uuid> <admin@parcel.local>`

- [ ] **Step 4: Start the shell**

```bash
docker compose up -d shell
```

Wait for healthy.

- [ ] **Step 5: Login**

```bash
curl -sS -c /tmp/parcel_cookies -H 'content-type: application/json' \
  -d '{"email":"admin@parcel.local","password":"pw-at-least-12-chars"}' \
  http://localhost:8000/auth/login
```

Expected: 200 with JSON body containing `"email":"admin@parcel.local"` and `"permissions": [...8 items...]`.

- [ ] **Step 6: Call `/auth/me`**

```bash
curl -sS -b /tmp/parcel_cookies http://localhost:8000/auth/me
```

Expected: same user body.

- [ ] **Step 7: Call `/admin/users`**

```bash
curl -sS -b /tmp/parcel_cookies http://localhost:8000/admin/users
```

Expected: JSON with `items`, `total: 1`.

- [ ] **Step 8: Confirm permission enforcement**

Create a non-admin user, log in as them, and hit `/admin/users`:

```bash
curl -sS -b /tmp/parcel_cookies -H 'content-type: application/json' \
  -d '{"email":"peon@x.com","password":"password-1234","role_ids":[]}' \
  http://localhost:8000/admin/users

curl -sS -c /tmp/peon_cookies -H 'content-type: application/json' \
  -d '{"email":"peon@x.com","password":"password-1234"}' \
  http://localhost:8000/auth/login

curl -sS -o /dev/null -w "%{http_code}\n" -b /tmp/peon_cookies http://localhost:8000/admin/users
```

Expected: last command prints `403`.

- [ ] **Step 9: Logout and confirm 401**

```bash
curl -sS -b /tmp/parcel_cookies -X POST http://localhost:8000/auth/logout
curl -sS -o /dev/null -w "%{http_code}\n" -b /tmp/parcel_cookies http://localhost:8000/auth/me
```

Expected: last command prints `401`.

No commit for this task.

---

## Task 19: Quality gates, docs, CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check packages/parcel-shell
uv run ruff format --check packages/parcel-shell
```

If anything fails, fix it:

```bash
uv run ruff check packages/parcel-shell --fix
uv run ruff format packages/parcel-shell
```

- [ ] **Step 2: Run pyright**

```bash
uv run pyright packages/parcel-shell
```

Expected: 0 errors. If any `reportCallIssue` arises from pydantic `BaseModel(...)` calls in tests, add `# pyright: reportCallIssue=false` at the top of the offending test file (same pattern as Phase 1's `test_config.py`).

- [ ] **Step 3: Run the full suite once more**

```bash
uv run pytest
```

Expected: green.

- [ ] **Step 4: Update `README.md`**

Add a new subsection under "Running locally (Phase 1)" (rename the header to "Running locally" if not already), after the migrate step:

```markdown
### Create an admin user (Phase 2+)

```bash
docker compose run --rm shell python -m parcel_shell.bootstrap create-admin \
  --email admin@parcel.local --password 'pw-at-least-12-chars'
```

Then log in via the JSON API:

```bash
curl -c cookies.txt -H 'content-type: application/json' \
  -d '{"email":"admin@parcel.local","password":"pw-at-least-12-chars"}' \
  http://localhost:8000/auth/login

curl -b cookies.txt http://localhost:8000/auth/me
```
```

- [ ] **Step 5: Update `CLAUDE.md`**

Change the "Current phase" section from:

```markdown
**Phase 1 — Shell foundation done.** ...

Next: **Phase 2 — Auth + RBAC.** ...
```

to:

```markdown
**Phase 2 — Auth + RBAC done.** Users (email + Argon2id), signed-cookie sessions with server-side storage in `shell.sessions`, roles + permissions with a registry seam for modules, `/auth/*` and `/admin/*` JSON endpoints, and `python -m parcel_shell.bootstrap create-admin`. Built-in `admin` role seeded with all shell permissions.

Next: **Phase 3 — Module system.** Start a new session; prompt: "Begin Phase 3: module system per `CLAUDE.md` roadmap."
```

In the "Phased roadmap" table, change Phase 2 status from `⏭ next` to `✅ done`, and change Phase 3's status to `⏭ next`.

In the "Locked-in decisions" table, append:

```markdown
| Phase 2 deps | argon2-cffi, itsdangerous, email-validator |
| Session TTL | 7-day absolute, 24-hour idle; bumped on every authenticated request |
| Session cookie | `parcel_session`; HttpOnly; SameSite=Lax; Secure when env != dev; signed with `PARCEL_SESSION_SECRET` |
| Admin role | `admin` seeded by migration 0002, `is_builtin=true`, holds all shell permissions, cannot be modified or deleted via API |
| Failed logins | Logged as `auth.login_failed` with reason (`no_user`/`bad_password`/`inactive`). No rate limiting until a later phase. |
```

- [ ] **Step 6: Final commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: close Phase 2, document auth + bootstrap usage"
```

---

## Verification summary (Phase 2 definition of done)

- [ ] `docker compose run --rm shell migrate` runs cleanly through 0002; all six auth/RBAC tables exist in the `shell` schema.
- [ ] `docker compose run --rm shell python -m parcel_shell.bootstrap create-admin --email … --password …` succeeds and prints the new user id.
- [ ] `curl` login → `/auth/me` returns the admin with all 8 shell permissions.
- [ ] `curl` as a non-admin → `/admin/users` returns 403.
- [ ] Logout invalidates the cookie server-side (next `/auth/me` → 401).
- [ ] `uv run pytest` green (Phase 1 suite + Phase 2 suite).
- [ ] `uv run ruff check` and `uv run pyright packages/parcel-shell` clean.
- [ ] README updated; CLAUDE.md Phase 2 ✅ and Phase 3 ⏭ next.
