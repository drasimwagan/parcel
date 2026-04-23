# Phase 1 — Shell Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable `parcel-shell` FastAPI service backed by Postgres + Redis, with typed config, async SQLAlchemy, Alembic baseline migration for the `shell` schema, structured logging with per-request IDs, liveness/readiness health endpoints, and an end-to-end `docker compose up` path — all covered by a pytest suite running against a `testcontainers` Postgres.

**Architecture:** A composition-root `create_app()` in `packages/parcel-shell/src/parcel_shell/app.py` wires small, focused modules — `config.py` (pydantic-settings), `logging.py` (structlog + request_id contextvar), `middleware.py` (RequestIdMiddleware), `db.py` (async engine, sessionmaker, `shell_metadata`), `health.py` (routers). Alembic lives inside the `parcel_shell` package, runs only against the `shell` schema, and is invoked explicitly (not on boot) via `entrypoint.sh migrate`.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async · asyncpg · Alembic · redis-py async · pydantic-settings · structlog · pytest + pytest-asyncio · testcontainers · uv workspace · Docker Compose.

**Reference spec:** `docs/superpowers/specs/2026-04-23-phase-1-shell-foundation-design.md`

---

## File plan

**Create:**
- `packages/parcel-shell/src/parcel_shell/config.py`
- `packages/parcel-shell/src/parcel_shell/logging.py`
- `packages/parcel-shell/src/parcel_shell/middleware.py`
- `packages/parcel-shell/src/parcel_shell/db.py`
- `packages/parcel-shell/src/parcel_shell/health.py`
- `packages/parcel-shell/src/parcel_shell/app.py`
- `packages/parcel-shell/src/parcel_shell/alembic.ini`
- `packages/parcel-shell/src/parcel_shell/alembic/env.py`
- `packages/parcel-shell/src/parcel_shell/alembic/script.py.mako`
- `packages/parcel-shell/src/parcel_shell/alembic/versions/0001_create_shell_schema.py`
- `packages/parcel-shell/tests/__init__.py`
- `packages/parcel-shell/tests/conftest.py`
- `packages/parcel-shell/tests/test_config.py`
- `packages/parcel-shell/tests/test_logging.py`
- `packages/parcel-shell/tests/test_middleware.py`
- `packages/parcel-shell/tests/test_db.py`
- `packages/parcel-shell/tests/test_migrations.py`
- `packages/parcel-shell/tests/test_health.py`
- `packages/parcel-shell/tests/test_app_factory.py`

**Modify:**
- `pyproject.toml` (workspace root) — add `testcontainers[postgres]` to dev deps
- `packages/parcel-shell/pyproject.toml` — add runtime deps
- `packages/parcel-shell/src/parcel_shell/__init__.py` — re-export `create_app`, `__version__`
- `docker/entrypoint.sh` — wire `serve` / `migrate` subcommands
- `README.md` — add "Running locally" section with three-command ritual
- `CLAUDE.md` — mark Phase 1 done, Phase 2 next, note dependency additions

---

## Task 1: Add dependencies and sync workspace

**Files:**
- Modify: `pyproject.toml` (workspace root)
- Modify: `packages/parcel-shell/pyproject.toml`

- [ ] **Step 1: Add runtime deps to `packages/parcel-shell/pyproject.toml`**

Replace the `dependencies = []` block with:

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
]
```

- [ ] **Step 2: Add `testcontainers[postgres]` to workspace dev deps**

In root `pyproject.toml`, append to the `[tool.uv] dev-dependencies` list:

```toml
    "testcontainers[postgres]>=4.8",
    "asgi-lifespan>=2.1",
```

(`asgi-lifespan` is needed to run FastAPI lifespan events under the httpx ASGI transport in tests.)

- [ ] **Step 3: Sync the workspace**

Run: `uv sync`
Expected: completes without errors; lockfile updated.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml packages/parcel-shell/pyproject.toml uv.lock
git commit -m "chore: add Phase 1 runtime and test dependencies"
```

---

## Task 2: Config (pydantic-settings)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/config.py`
- Create: `packages/parcel-shell/tests/__init__.py` (empty file)
- Create: `packages/parcel-shell/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/__init__.py` as an empty file.

Create `packages/parcel-shell/tests/test_config.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from parcel_shell.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "PARCEL_SESSION_SECRET": "a" * 32,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "REDIS_URL": "redis://localhost:6379/0",
    }


def test_settings_loads_with_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.env == "dev"
    assert s.port == 8000
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_settings_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("PARCEL_SESSION_SECRET", "DATABASE_URL", "REDIS_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_rejects_non_asyncpg_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"DATABASE_URL": "postgresql://u:p@localhost/db"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_short_secret_ok_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"PARCEL_SESSION_SECRET": "short", "PARCEL_ENV": "dev"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.session_secret == "short"


def test_settings_short_secret_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _base_env() | {"PARCEL_SESSION_SECRET": "short", "PARCEL_ENV": "prod"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcel_shell.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `packages/parcel-shell/src/parcel_shell/config.py`:

```python
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "staging", "prod"] = Field(default="dev", alias="PARCEL_ENV")
    host: str = Field(default="0.0.0.0", alias="PARCEL_HOST")
    port: int = Field(default=8000, alias="PARCEL_PORT")
    session_secret: str = Field(alias="PARCEL_SESSION_SECRET")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="PARCEL_LOG_LEVEL")

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must start with 'postgresql+asyncpg://'")
        return v

    @model_validator(mode="after")
    def _enforce_secret_length(self) -> Settings:
        if self.env != "dev" and len(self.session_secret) < 32:
            raise ValueError(
                "PARCEL_SESSION_SECRET must be at least 32 chars when env is not 'dev'"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_config.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/config.py packages/parcel-shell/tests/__init__.py packages/parcel-shell/tests/test_config.py
git commit -m "feat(shell): typed settings with pydantic-settings"
```

---

## Task 3: Structured logging with request-ID contextvar

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/logging.py`
- Create: `packages/parcel-shell/tests/test_logging.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_logging.py`:

```python
from __future__ import annotations

import json
import logging

import structlog

from parcel_shell.logging import configure_logging, request_id_var


def test_configure_logging_dev_uses_console_renderer(capsys) -> None:
    configure_logging(env="dev", level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", key="value")
    out = capsys.readouterr().out
    assert "hello" in out
    assert "key" in out and "value" in out


def test_configure_logging_prod_emits_json(capsys) -> None:
    configure_logging(env="prod", level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", key="value")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["key"] == "value"
    assert payload["level"] == "info"


def test_request_id_contextvar_bound_in_logs(capsys) -> None:
    configure_logging(env="prod", level="INFO")
    token = request_id_var.set("req-abc")
    try:
        structlog.get_logger("test").info("with-id")
    finally:
        request_id_var.reset(token)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["request_id"] == "req-abc"


def test_configure_logging_is_idempotent() -> None:
    configure_logging(env="dev", level="INFO")
    configure_logging(env="dev", level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_logging.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `logging.py`**

Create `packages/parcel-shell/src/parcel_shell/logging.py`:

```python
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def _merge_request_id(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    event_dict.setdefault("request_id", request_id_var.get())
    return event_dict


def configure_logging(env: str, level: str = "INFO") -> None:
    """Configure structlog + stdlib logging. Safe to call multiple times."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _merge_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env == "dev":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_logging.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/logging.py packages/parcel-shell/tests/test_logging.py
git commit -m "feat(shell): structlog configuration with request-id contextvar"
```

---

## Task 4: Request-ID middleware

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/middleware.py`
- Create: `packages/parcel-shell/tests/test_middleware.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_middleware.py`:

```python
from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from parcel_shell.logging import configure_logging, request_id_var
from parcel_shell.middleware import RequestIdMiddleware


@pytest.fixture
def app() -> FastAPI:
    configure_logging(env="prod", level="INFO")
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/peek")
    async def peek() -> dict[str, str]:
        return {"request_id": request_id_var.get()}

    return app


async def test_middleware_echoes_provided_header(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/peek", headers={"X-Request-ID": "test-123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "test-123"
    assert r.json() == {"request_id": "test-123"}


async def test_middleware_generates_uuid_when_absent(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/peek")
    generated = r.headers["x-request-id"]
    # UUID4 shape
    assert re.fullmatch(r"[0-9a-f-]{36}", generated)
    uuid.UUID(generated)  # raises if malformed
    assert r.json() == {"request_id": generated}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_middleware.py -v`
Expected: FAIL — `parcel_shell.middleware` not found.

- [ ] **Step 3: Implement `middleware.py`**

Create `packages/parcel-shell/src/parcel_shell/middleware.py`:

```python
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from parcel_shell.logging import request_id_var

HEADER_NAME = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(HEADER_NAME)
        request_id = incoming if incoming else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER_NAME] = request_id
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_middleware.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/middleware.py packages/parcel-shell/tests/test_middleware.py
git commit -m "feat(shell): request-id middleware with header propagation"
```

---

## Task 5: Database module (engine, session dep, shell metadata) + conftest

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/db.py`
- Create: `packages/parcel-shell/tests/conftest.py`
- Create: `packages/parcel-shell/tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/conftest.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    # testcontainers yields `postgresql+psycopg2://...`; we need asyncpg.
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
```

Create `packages/parcel-shell/tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_db.py -v`
Expected: FAIL — `parcel_shell.db` not found (the testcontainer will still start; that's fine).

- [ ] **Step 3: Implement `db.py`**

Create `packages/parcel-shell/src/parcel_shell/db.py`:

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
from starlette.requests import Request

SHELL_SCHEMA = "shell"

shell_metadata: MetaData = MetaData(schema=SHELL_SCHEMA)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with session_factory() as session:
        yield session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_db.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/db.py packages/parcel-shell/tests/conftest.py packages/parcel-shell/tests/test_db.py
git commit -m "feat(shell): async engine, sessionmaker, shell metadata, test fixtures"
```

---

## Task 6: Alembic scaffold and baseline migration

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/alembic.ini`
- Create: `packages/parcel-shell/src/parcel_shell/alembic/env.py`
- Create: `packages/parcel-shell/src/parcel_shell/alembic/script.py.mako`
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0001_create_shell_schema.py`
- Create: `packages/parcel-shell/tests/test_migrations.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_migrations.py`:

```python
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "parcel_shell"
    / "alembic.ini"
)


def _make_config(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # Alembic's env.py reads this to override the async URL.
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def test_upgrade_head_creates_shell_schema(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _make_config(database_url)
    command.upgrade(cfg, "head")

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = 'shell'"
            )
        )
        assert result.scalar_one_or_none() == "shell"


async def test_downgrade_base_removes_shell_schema(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _make_config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = 'shell'"
            )
        )
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations.py -v`
Expected: FAIL — alembic.ini missing.

- [ ] **Step 3: Create `alembic.ini`**

Create `packages/parcel-shell/src/parcel_shell/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os
# Overridden at runtime from DATABASE_URL / tests.
sqlalchemy.url = postgresql+asyncpg://parcel:parcel@postgres:5432/parcel

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Create `env.py`**

Create `packages/parcel-shell/src/parcel_shell/alembic/env.py`:

```python
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
if env_url and not config.get_main_option("sqlalchemy.url", "").startswith("postgresql+asyncpg://"):
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = shell_metadata


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema=SHELL_SCHEMA,
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
        version_table_schema=SHELL_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())
```

- [ ] **Step 5: Create `script.py.mako`**

Create `packages/parcel-shell/src/parcel_shell/alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Create baseline migration**

Create `packages/parcel-shell/src/parcel_shell/alembic/versions/0001_create_shell_schema.py`:

```python
"""create shell schema

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "shell"')


def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "shell" CASCADE')
```

- [ ] **Step 7: Run migration tests to verify they pass**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations.py -v`
Expected: both tests PASS.

- [ ] **Step 8: Sanity-check alembic CLI works**

Run:

```bash
uv run alembic -c packages/parcel-shell/src/parcel_shell/alembic.ini history
```

Expected: prints a single history entry for revision `0001 -> (base)`.

- [ ] **Step 9: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/alembic.ini packages/parcel-shell/src/parcel_shell/alembic packages/parcel-shell/tests/test_migrations.py
git commit -m "feat(shell): alembic scaffold + baseline migration for shell schema"
```

---

## Task 7: Health endpoints

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/health.py`
- Create: `packages/parcel-shell/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_health.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from parcel_shell.health import router as health_router


class _FakeRedisOk:
    async def ping(self) -> bool:
        return True


class _FakeRedisFail:
    async def ping(self) -> bool:
        raise RuntimeError("boom")


def _make_app(engine: AsyncEngine | None, redis: Any) -> FastAPI:
    app = FastAPI()
    app.state.engine = engine
    app.state.redis = redis
    app.include_router(health_router)
    return app


async def test_live_always_ok() -> None:
    app = _make_app(engine=None, redis=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_ok_when_deps_up(engine: AsyncEngine) -> None:
    app = _make_app(engine=engine, redis=_FakeRedisOk())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"db": "ok", "redis": "ok"}


async def test_ready_503_when_redis_down(engine: AsyncEngine) -> None:
    app = _make_app(engine=engine, redis=_FakeRedisFail())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"].startswith("error:")


async def test_ready_503_when_db_down() -> None:
    # A namespace object whose .connect() blows up.
    class _BadEngine:
        def connect(self) -> Any:
            raise RuntimeError("db down")

    app = _make_app(engine=_BadEngine(), redis=_FakeRedisOk())  # type: ignore[arg-type]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["checks"]["db"].startswith("error:")
    assert body["checks"]["redis"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_health.py -v`
Expected: FAIL — `parcel_shell.health` not found.

- [ ] **Step 3: Implement `health.py`**

Create `packages/parcel-shell/src/parcel_shell/health.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.requests import Request

router = APIRouter(prefix="/health", tags=["health"])

_TIMEOUT_SECONDS = 5.0


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


async def _check_db(engine: Any) -> str:
    try:
        async def _run() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_run(), timeout=_TIMEOUT_SECONDS)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


async def _check_redis(redis: Any) -> str:
    try:
        await asyncio.wait_for(redis.ping(), timeout=_TIMEOUT_SECONDS)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    engine = request.app.state.engine
    redis = request.app.state.redis
    db_status, redis_status = await asyncio.gather(
        _check_db(engine), _check_redis(redis)
    )
    checks = {"db": db_status, "redis": redis_status}
    if all(v == "ok" for v in checks.values()):
        return JSONResponse({"status": "ok", "checks": checks})
    return JSONResponse({"status": "degraded", "checks": checks}, status_code=503)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_health.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/health.py packages/parcel-shell/tests/test_health.py
git commit -m "feat(shell): liveness and readiness health endpoints"
```

---

## Task 8: App factory and lifespan

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/app.py`
- Modify: `packages/parcel-shell/src/parcel_shell/__init__.py`
- Create: `packages/parcel-shell/tests/test_app_factory.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_app_factory.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from parcel_shell.app import create_app
from parcel_shell.config import Settings


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": database_url,
            "REDIS_URL": "redis://localhost:1",  # not actually connected in these tests
            "PARCEL_LOG_LEVEL": "INFO",
        }
    )


async def test_create_app_returns_fastapi(settings: Settings) -> None:
    app = create_app(settings=settings)
    assert app.title  # FastAPI default has a title


async def test_lifespan_attaches_and_disposes_state(settings: Settings) -> None:
    app = create_app(settings=settings)
    async with LifespanManager(app):
        assert isinstance(app.state.engine, AsyncEngine)
        assert app.state.sessionmaker is not None
        assert app.state.redis is not None


async def test_live_endpoint_via_factory(settings: Settings) -> None:
    app = create_app(settings=settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/health/live")
    assert r.status_code == 200


async def test_unhandled_exception_returns_500_with_request_id(settings: Settings) -> None:
    app = create_app(settings=settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/boom", headers={"X-Request-ID": "rid-9"})
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_server_error"
    assert body["request_id"] == "rid-9"
    assert r.headers["x-request-id"] == "rid-9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_app_factory.py -v`
Expected: FAIL — `parcel_shell.app` not found.

- [ ] **Step 3: Implement `app.py`**

Create `packages/parcel-shell/src/parcel_shell/app.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from parcel_shell.config import Settings, get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.health import router as health_router
from parcel_shell.logging import configure_logging, request_id_var
from parcel_shell.middleware import RequestIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(env=settings.env, level=settings.log_level)
    log = structlog.get_logger("parcel_shell")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        app.state.settings = settings
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

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        rid = request_id_var.get()
        log.exception("shell.unhandled_exception", error=str(exc), request_id=rid)
        return JSONResponse(
            {"error": "internal_server_error", "request_id": rid},
            status_code=500,
            headers={"X-Request-ID": rid},
        )

    return app
```

The file ends at `create_app`'s `return app`. No module-level `app = ...` — uvicorn will be invoked with `--factory parcel_shell.app:create_app` (see Task 9) so settings are only resolved at process start, not on every import.

- [ ] **Step 4: Update package `__init__.py`**

Replace `packages/parcel-shell/src/parcel_shell/__init__.py` with:

```python
"""Parcel shell — FastAPI app hosting auth, RBAC, admin UI, module lifecycle, AI authoring."""

from __future__ import annotations

from parcel_shell.app import create_app

__all__ = ["__version__", "create_app"]
__version__ = "0.1.0"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_app_factory.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest`
Expected: all tests green (config, logging, middleware, db, migrations, health, app_factory).

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/src/parcel_shell/__init__.py packages/parcel-shell/tests/test_app_factory.py
git commit -m "feat(shell): app factory with lifespan and global exception handler"
```

---

## Task 9: Wire entrypoint.sh and verify docker-compose end-to-end

**Files:**
- Modify: `docker/entrypoint.sh`
- Modify: `docker/Dockerfile` (ensure alembic.ini is reachable)

- [ ] **Step 1: Rewrite `docker/entrypoint.sh`**

Replace entire contents of `docker/entrypoint.sh`:

```bash
#!/usr/bin/env bash
# Parcel container entrypoint.

set -euo pipefail

cmd="${1:-serve}"

case "$cmd" in
  serve)
    exec uv run uvicorn --factory parcel_shell.app:create_app \
      --host "${PARCEL_HOST:-0.0.0.0}" \
      --port "${PARCEL_PORT:-8000}" \
      --reload
    ;;
  migrate)
    exec uv run alembic \
      -c packages/parcel-shell/src/parcel_shell/alembic.ini \
      upgrade head
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "[parcel] Unknown command: $cmd"
    echo "Usage: $0 {serve|migrate|shell}"
    exit 1
    ;;
esac
```

- [ ] **Step 2: Verify Dockerfile still works**

Read `docker/Dockerfile`. Confirm it copies `packages/` after the workspace root. No changes should be needed, but if `uv sync --frozen` fails due to the lockfile update from Task 1, that's expected — the existing fallback `|| uv sync` handles it.

- [ ] **Step 3: Create local `.env` for compose**

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Then edit `.env` to set `PARCEL_SESSION_SECRET` to any 32+ character string for non-dev use (optional for dev).

- [ ] **Step 4: Build and bring up the stack**

```bash
docker compose build shell
docker compose up -d postgres redis
docker compose run --rm shell migrate
docker compose up -d shell
```

Expected: all services become healthy. `docker compose logs shell` shows `shell.startup` log line.

- [ ] **Step 5: Smoke-test endpoints**

```bash
curl -sS http://localhost:8000/health/live
curl -sS http://localhost:8000/health/ready
curl -sS -i -H "X-Request-ID: smoke-1" http://localhost:8000/health/live
```

Expected:
- `/health/live` → `{"status":"ok"}`
- `/health/ready` → `{"status":"ok","checks":{"db":"ok","redis":"ok"}}`
- Third call: response includes `X-Request-ID: smoke-1`; `docker compose logs shell` shows a log line containing `request_id=smoke-1` (or `"request_id": "smoke-1"` in JSON).

- [ ] **Step 6: Negative check — readiness degrades without redis**

```bash
docker compose stop redis
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/health/ready
docker compose start redis
```

Expected: status `503` while redis is down; `200` after restart.

- [ ] **Step 7: Commit**

```bash
git add docker/entrypoint.sh
git commit -m "feat(docker): wire entrypoint serve/migrate to parcel-shell"
```

---

## Task 10: Quality gates, docs, and CLAUDE.md update

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check
uv run ruff format --check
```

Expected: clean. If ruff complains, fix in-place (imports, line length) before continuing.

- [ ] **Step 2: Run pyright**

```bash
uv run pyright packages/parcel-shell
```

Expected: no errors. Fix any type issues before continuing.

- [ ] **Step 3: Run the full test suite once more**

```bash
uv run pytest
```

Expected: green.

- [ ] **Step 4: Update `README.md`**

Under the existing content (read the current file first), add a "Running locally" section:

````markdown
## Running locally (Phase 1)

Requires Docker.

```bash
cp .env.example .env                       # then edit PARCEL_SESSION_SECRET
docker compose up -d postgres redis
docker compose run --rm shell migrate      # creates the `shell` schema
docker compose up -d shell                 # starts the FastAPI service
```

Smoke-check:

```bash
curl http://localhost:8000/health/live    # → {"status":"ok"}
curl http://localhost:8000/health/ready   # → {"status":"ok","checks":{"db":"ok","redis":"ok"}}
```

### Running tests

```bash
uv sync
uv run pytest    # requires Docker (uses testcontainers to spin up Postgres)
```
````

- [ ] **Step 5: Update `CLAUDE.md`**

Change the "Current phase" section from:

```markdown
**Phase 0 — Repository scaffolded. No application code yet.**

Next: **Phase 1 — Shell foundation.** ...
```

to:

```markdown
**Phase 1 — Shell foundation done.** FastAPI app (`create_app`), pydantic-settings config, async SQLAlchemy engine, Alembic baseline migration for the `shell` schema, structlog with per-request IDs, `/health/live` + `/health/ready`, end-to-end `docker compose up`, and pytest suite over testcontainers Postgres.

Next: **Phase 2 — Auth + RBAC.** Start a new session; prompt: "Begin Phase 2: auth + RBAC per `CLAUDE.md` roadmap."
```

In the "Phased roadmap" table, change the Phase 1 row's Status from `⏭ next` to `✅ done`, and change the Phase 2 row's Status to `⏭ next`.

At the bottom of the "Locked-in decisions" table, append:

```markdown
| Phase 1 shell deps | fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, redis, pydantic, pydantic-settings, structlog |
| Phase 1 test deps | testcontainers[postgres], asgi-lifespan |
| Logging | structlog; console in dev, JSON in staging/prod |
| Health endpoints | `/health/live` (always 200) and `/health/ready` (pg + redis checks; 503 on degraded) |
| Migrations | Run explicitly via `docker compose run --rm shell migrate`, never on boot |
```

- [ ] **Step 6: Final commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: close Phase 1, document shell foundation usage"
```

---

## Verification summary (Phase 1 definition of done)

Run through each item from the spec's "Definition of done":

- [ ] `docker compose up -d` — postgres + redis + shell all healthy.
- [ ] `docker compose run --rm shell migrate` creates the `shell` schema.
- [ ] `GET /health/live` → 200.
- [ ] `GET /health/ready` → 200 while deps are up; 503 with `docker compose stop redis`.
- [ ] Request with `X-Request-ID: test-123` echoes the header and shows up in shell logs.
- [ ] `uv run pytest` green.
- [ ] `uv run ruff check` and `uv run pyright packages/parcel-shell` clean.
- [ ] README documents the three-command ritual.
- [ ] CLAUDE.md: Phase 1 ✅, Phase 2 ⏭ next, dependency additions noted.
