# Phase 3 — Module System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working Parcel module system — `parcel-sdk` exposes `Module`/`Permission`/`run_async_migrations`; shell discovers modules via `parcel.modules` entry points; admins explicitly install/upgrade/uninstall via `/admin/modules/*`; each installed module owns a `mod_<name>` Postgres schema and its own Alembic migrations run in-process on install/upgrade; a fixture test module under `tests/_fixtures/` exercises the full flow.

**Architecture:** Three focused modules under `parcel-sdk` (one dataclass file, one alembic env helper, re-exports) and five under `parcel_shell/modules/` (discovery, models, service, schemas, router_admin). The `shell.installed_modules` table tracks active installs; migration 0003 seeds four new shell permissions. Service functions are pure async over `AsyncSession`; routers are thin parse/call/serialize layers; FastAPI dependency `require_permission` gates every admin endpoint. Boot-time sync flips orphaned rows to inactive without aborting shell startup.

**Tech Stack:** Python 3.12 · `parcel-sdk` (dataclasses + alembic helper) · SQLAlchemy 2.0 async · Alembic · `importlib.metadata` · FastAPI · pydantic · pytest + testcontainers · asgi-lifespan · httpx.

**Reference spec:** `docs/superpowers/specs/2026-04-23-phase-3-module-system-design.md`

---

## File plan

**Create:**
- `packages/parcel-sdk/src/parcel_sdk/__init__.py` (replace skeleton)
- `packages/parcel-sdk/src/parcel_sdk/module.py`
- `packages/parcel-sdk/src/parcel_sdk/alembic_env.py`
- `packages/parcel-sdk/tests/__init__.py`
- `packages/parcel-sdk/tests/test_module.py`
- `packages/parcel-shell/src/parcel_shell/modules/__init__.py`
- `packages/parcel-shell/src/parcel_shell/modules/discovery.py`
- `packages/parcel-shell/src/parcel_shell/modules/models.py`
- `packages/parcel-shell/src/parcel_shell/modules/service.py`
- `packages/parcel-shell/src/parcel_shell/modules/schemas.py`
- `packages/parcel-shell/src/parcel_shell/modules/router_admin.py`
- `packages/parcel-shell/src/parcel_shell/alembic/versions/0003_install_modules.py`
- `packages/parcel-shell/tests/_fixtures/__init__.py`
- `packages/parcel-shell/tests/_fixtures/test_module/pyproject.toml`
- `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/__init__.py`
- `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic.ini`
- `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/env.py`
- `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/script.py.mako`
- `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/versions/0001_initial.py`
- `packages/parcel-shell/tests/test_discovery.py`
- `packages/parcel-shell/tests/test_module_service.py`
- `packages/parcel-shell/tests/test_modules_router.py`
- `packages/parcel-shell/tests/test_module_boot.py`

**Modify:**
- `packages/parcel-sdk/pyproject.toml` — add `sqlalchemy[asyncio]`, `alembic` deps
- `packages/parcel-shell/src/parcel_shell/rbac/registry.py` — add the four `modules.*` permissions to `SHELL_PERMISSIONS`
- `packages/parcel-shell/src/parcel_shell/app.py` — include `modules.router_admin`; in lifespan, call `service.sync_on_boot` after the existing permission sync
- `packages/parcel-shell/tests/conftest.py` — add `test_module_on_path`, `discovered_test_module`, `patch_entry_points` fixtures
- `CLAUDE.md` — Phase 3 ✅, Phase 4 ⏭, note SDK now has real content

---

## Task 1: SDK dependencies

**Files:**
- Modify: `packages/parcel-sdk/pyproject.toml`

- [ ] **Step 1: Replace the `dependencies` block**

Open `packages/parcel-sdk/pyproject.toml`. Replace:

```toml
dependencies = [
    # Phase 6 will populate. Keeping empty to avoid premature coupling.
]
```

with:

```toml
dependencies = [
    "sqlalchemy[asyncio]>=2.0.36",
    "alembic>=1.14",
]
```

- [ ] **Step 2: Sync workspace**

Run: `uv sync --all-packages`
Expected: completes without errors; lockfile updated (may be a no-op if shell already pulls these transitively).

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-sdk/pyproject.toml uv.lock
git commit -m "chore(sdk): add sqlalchemy and alembic runtime deps for Phase 3"
```

---

## Task 2: SDK `Module` + `Permission` dataclasses

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/module.py`
- Create: `packages/parcel-sdk/tests/__init__.py` (empty)
- Create: `packages/parcel-sdk/tests/test_module.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/__init__.py`

- [ ] **Step 1: Create empty `tests/__init__.py`**

Create `packages/parcel-sdk/tests/__init__.py` with no content.

- [ ] **Step 2: Write the failing test**

Create `packages/parcel-sdk/tests/test_module.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import MetaData

from parcel_sdk import Module, Permission


def test_permission_is_frozen_dataclass() -> None:
    p = Permission("foo.read", "Read foo")
    assert p.name == "foo.read"
    assert p.description == "Read foo"
    with pytest.raises(Exception):
        p.name = "bar.read"  # type: ignore[misc]


def test_module_defaults() -> None:
    m = Module(name="foo", version="0.1.0")
    assert m.permissions == ()
    assert m.capabilities == ()
    assert m.alembic_ini is None
    assert m.metadata is None


def test_module_full() -> None:
    md = MetaData(schema="mod_foo")
    m = Module(
        name="foo",
        version="1.2.3",
        permissions=(Permission("foo.read", "Read"),),
        capabilities=("http_egress",),
        alembic_ini=Path("/tmp/foo/alembic.ini"),
        metadata=md,
    )
    assert m.permissions[0].name == "foo.read"
    assert m.capabilities == ("http_egress",)
    assert m.metadata is md


def test_module_is_frozen() -> None:
    m = Module(name="foo", version="0.1.0")
    with pytest.raises(Exception):
        m.version = "0.2.0"  # type: ignore[misc]


def test_module_equality_by_value() -> None:
    a = Module(name="foo", version="0.1.0", capabilities=("x",))
    b = Module(name="foo", version="0.1.0", capabilities=("x",))
    assert a == b
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest packages/parcel-sdk/tests/test_module.py -v`
Expected: ImportError (`parcel_sdk.Module` not found).

- [ ] **Step 4: Implement `parcel_sdk/module.py`**

Create `packages/parcel-sdk/src/parcel_sdk/module.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import MetaData


@dataclass(frozen=True)
class Permission:
    name: str
    description: str


@dataclass(frozen=True)
class Module:
    name: str
    version: str
    permissions: tuple[Permission, ...] = ()
    capabilities: tuple[str, ...] = ()
    alembic_ini: Path | None = None
    metadata: "MetaData | None" = None
```

- [ ] **Step 5: Re-export from the package `__init__.py`**

Replace the contents of `packages/parcel-sdk/src/parcel_sdk/__init__.py` with:

```python
"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 3 surface: Module, Permission, run_async_migrations.
"""

from __future__ import annotations

from parcel_sdk.module import Module, Permission

__all__ = ["Module", "Permission", "__version__"]
__version__ = "0.1.0"
```

(The `run_async_migrations` re-export is added in Task 3 once it exists.)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest packages/parcel-sdk/tests/test_module.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/__init__.py packages/parcel-sdk/src/parcel_sdk/module.py packages/parcel-sdk/tests/__init__.py packages/parcel-sdk/tests/test_module.py
git commit -m "feat(sdk): Module and Permission dataclasses"
```

---

## Task 3: SDK `run_async_migrations` helper

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/alembic_env.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/__init__.py`

- [ ] **Step 1: Implement `alembic_env.py`**

Create `packages/parcel-sdk/src/parcel_sdk/alembic_env.py`:

```python
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
```

- [ ] **Step 2: Re-export from `__init__.py`**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py` to:

```python
"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 3 surface: Module, Permission, run_async_migrations.
"""

from __future__ import annotations

from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.module import Module, Permission

__all__ = ["Module", "Permission", "run_async_migrations", "__version__"]
__version__ = "0.1.0"
```

- [ ] **Step 3: Sanity check — SDK imports cleanly**

Run: `uv run python -c "from parcel_sdk import Module, Permission, run_async_migrations; print('ok')"`
Expected output: `ok`.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/alembic_env.py packages/parcel-sdk/src/parcel_sdk/__init__.py
git commit -m "feat(sdk): run_async_migrations helper for module alembic env.py"
```

---

## Task 4: Test fixture module

**Files:**
- Create: `packages/parcel-shell/tests/_fixtures/__init__.py` (empty)
- Create: `packages/parcel-shell/tests/_fixtures/test_module/pyproject.toml`
- Create: `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/__init__.py`
- Create: `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic.ini`
- Create: `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/env.py`
- Create: `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/script.py.mako`
- Create: `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/versions/0001_initial.py`

- [ ] **Step 1: Create `_fixtures/__init__.py`**

Create `packages/parcel-shell/tests/_fixtures/__init__.py` with no content.

- [ ] **Step 2: Create the fixture module's `pyproject.toml`**

Create `packages/parcel-shell/tests/_fixtures/test_module/pyproject.toml`:

```toml
# Fixture-only package used by Phase 3 tests. NOT part of the workspace.
# The tests put this package's `src/` on sys.path and synthesize an entry point
# in-process; this file exists only so the directory is a self-describing package.

[project]
name = "parcel-mod-test"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["parcel-sdk"]

[project.entry-points."parcel.modules"]
test = "parcel_mod_test:module"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parcel_mod_test"]
```

- [ ] **Step 3: Create the module entry (`__init__.py`)**

Create `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/__init__.py`:

```python
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, Text

from parcel_sdk import Module, Permission

metadata = MetaData(schema="mod_test")

items = Table(
    "items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
)

module = Module(
    name="test",
    version="0.1.0",
    permissions=(Permission("test.read", "Read test items"),),
    capabilities=("http_egress",),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
)
```

- [ ] **Step 4: Create the fixture module's `alembic.ini`**

Create `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os
path_separator = os
# Overridden at runtime.
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

- [ ] **Step 5: Create the fixture module's `env.py`**

Create `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/env.py`:

```python
from parcel_mod_test import module
from parcel_sdk.alembic_env import run_async_migrations

run_async_migrations(module)
```

- [ ] **Step 6: Create `script.py.mako`**

Create `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/script.py.mako`:

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

- [ ] **Step 7: Create the first migration**

Create `packages/parcel-shell/tests/_fixtures/test_module/src/parcel_mod_test/alembic/versions/0001_initial.py`:

```python
"""create items

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        schema="mod_test",
    )


def downgrade() -> None:
    op.drop_table("items", schema="mod_test")
```

- [ ] **Step 8: Commit**

```bash
git add packages/parcel-shell/tests/_fixtures/
git commit -m "test(shell): add fixture module parcel-mod-test for Phase 3"
```

---

## Task 5: `InstalledModule` ORM model

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/modules/models.py`

- [ ] **Step 1: Create empty `modules/__init__.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/__init__.py` with no content.

- [ ] **Step 2: Create `models.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from parcel_shell.db import ShellBase


class InstalledModule(ShellBase):
    __tablename__ = "installed_modules"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    capabilities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    schema_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    installed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_migrated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_migrated_rev: Mapped[str | None] = mapped_column(Text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "is_active": self.is_active,
            "capabilities": list(self.capabilities or []),
            "schema_name": self.schema_name,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "last_migrated_at": self.last_migrated_at,
            "last_migrated_rev": self.last_migrated_rev,
        }
```

- [ ] **Step 3: Sanity check — model imports**

Run: `uv run python -c "from parcel_shell.modules.models import InstalledModule; print(InstalledModule.__tablename__)"`
Expected output: `installed_modules`.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/__init__.py packages/parcel-shell/src/parcel_shell/modules/models.py
git commit -m "feat(shell): InstalledModule ORM model"
```

---

## Task 6: Alembic migration 0003

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0003_install_modules.py`
- Create: `packages/parcel-shell/tests/test_migrations_0003.py`
- Modify: `packages/parcel-shell/src/parcel_shell/rbac/registry.py`

- [ ] **Step 1: Append the 4 new permissions to the SHELL_PERMISSIONS tuple**

Open `packages/parcel-shell/src/parcel_shell/rbac/registry.py`. Replace the `SHELL_PERMISSIONS` tuple with:

```python
SHELL_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("users.read", "List and view user accounts"),
    ("users.write", "Create, update, and deactivate user accounts"),
    ("roles.read", "List and view roles"),
    ("roles.write", "Create, update, and delete roles; assign permissions to roles"),
    ("users.roles.assign", "Assign and unassign roles on users"),
    ("sessions.read", "List another user's sessions"),
    ("sessions.revoke", "Revoke another user's sessions"),
    ("permissions.read", "List registered permissions"),
    ("modules.read", "View registered and discovered modules"),
    ("modules.install", "Install a discovered module"),
    ("modules.upgrade", "Run migrations for an already-installed module"),
    ("modules.uninstall", "Deactivate or remove a module"),
)
```

- [ ] **Step 2: Write the failing migration test**

Create `packages/parcel-shell/tests/test_migrations_0003.py`:

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


async def test_0003_creates_installed_modules(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'installed_modules'"
                )
            )
        ).all()
    assert len(rows) == 1


async def test_0003_seeds_module_permissions_on_admin(
    database_url: str, engine: AsyncEngine
) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT id FROM shell.roles WHERE name = 'admin'"))
        ).one()
        perms = (
            await conn.execute(
                text(
                    "SELECT permission_name FROM shell.role_permissions "
                    "WHERE role_id = :rid AND permission_name LIKE 'modules.%' "
                    "ORDER BY permission_name"
                ),
                {"rid": row.id},
            )
        ).all()
    assert [r[0] for r in perms] == [
        "modules.install",
        "modules.read",
        "modules.uninstall",
        "modules.upgrade",
    ]


async def test_0003_downgrade_removes_table_and_permissions(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _cfg(database_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "0002")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'shell' AND table_name = 'installed_modules'"
                )
            )
        ).all()
        perms = (
            await conn.execute(
                text(
                    "SELECT name FROM shell.permissions WHERE name LIKE 'modules.%'"
                )
            )
        ).all()
    assert tables == []
    assert perms == []

    # Restore state for subsequent tests.
    await asyncio.to_thread(command.upgrade, cfg, "head")
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations_0003.py -v`
Expected: FAIL — migration 0003 not found.

- [ ] **Step 4: Create migration 0003**

Create `packages/parcel-shell/src/parcel_shell/alembic/versions/0003_install_modules.py`:

```python
"""install_modules + modules.* permissions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


MODULE_PERMISSIONS = (
    ("modules.read", "View registered and discovered modules"),
    ("modules.install", "Install a discovered module"),
    ("modules.upgrade", "Run migrations for an already-installed module"),
    ("modules.uninstall", "Deactivate or remove a module"),
)


def upgrade() -> None:
    op.create_table(
        "installed_modules",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "capabilities",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("schema_name", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "installed_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_migrated_at", TIMESTAMP(timezone=True)),
        sa.Column("last_migrated_rev", sa.Text()),
        schema="shell",
    )

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
            for name, description in MODULE_PERMISSIONS
        ],
    )

    conn = op.get_bind()
    admin_id = conn.execute(
        sa.text("SELECT id FROM shell.roles WHERE name = 'admin'")
    ).scalar_one()
    conn.execute(
        sa.text(
            "INSERT INTO shell.role_permissions (role_id, permission_name) "
            "VALUES (:rid, :name)"
        ),
        [{"rid": admin_id, "name": n} for n, _ in MODULE_PERMISSIONS],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM shell.permissions WHERE name LIKE 'modules.%'")
    )
    op.drop_table("installed_modules", schema="shell")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations_0003.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Verify all migration tests still pass**

Run: `uv run pytest packages/parcel-shell/tests/test_migrations.py packages/parcel-shell/tests/test_migrations_0002.py packages/parcel-shell/tests/test_migrations_0003.py -v`
Expected: 8 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/rbac/registry.py packages/parcel-shell/src/parcel_shell/alembic/versions/0003_install_modules.py packages/parcel-shell/tests/test_migrations_0003.py
git commit -m "feat(shell): Alembic 0003 — installed_modules + modules.* permissions"
```

---

## Task 7: Conftest additions (sys.path + entry-point patching + fixture helpers)

**Files:**
- Modify: `packages/parcel-shell/tests/conftest.py`

- [ ] **Step 1: Add fixture-module sys.path + discovery-patching helpers**

Open `packages/parcel-shell/tests/conftest.py`. At the top of the file (after the existing imports), add these session- and function-scoped fixtures. Append this block immediately before `# ── Factories`:

```python
# ── Phase 3 fixtures ────────────────────────────────────────────────────

_FIXTURE_MODULE_SRC = (
    Path(__file__).parent / "_fixtures" / "test_module" / "src"
).resolve()


@pytest.fixture(scope="session")
def test_module_on_path() -> Iterator[None]:
    """Put the fixture module's src/ on sys.path for the session."""
    import sys

    added = str(_FIXTURE_MODULE_SRC)
    if added not in sys.path:
        sys.path.insert(0, added)
    yield
    # Leave sys.path alone between tests; removing it would just force re-insertion.


@pytest.fixture
def discovered_test_module(test_module_on_path: None):
    """Load the fixture module fresh and return a DiscoveredModule-shaped object."""
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
    """Make `parcel_shell.modules.discovery.entry_points` return the fixture module.

    Usage in a test:  use `patch_entry_points` to have the fixture module
    discovered; call `patch_entry_points(include_test=False)` via pytest by
    requesting the `empty_entry_points` fixture instead.
    """
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
    """Make `parcel_shell.modules.discovery.entry_points` return nothing."""
    import parcel_shell.modules.discovery as disco

    def fake_entry_points(*, group: str):
        return []

    monkeypatch.setattr(disco, "entry_points", fake_entry_points)
```

Also add `from pathlib import Path` to the imports at the top of the file if it isn't already there (Phase 2 introduced it — verify).

- [ ] **Step 2: Run registry tests to confirm nothing regressed**

Run: `uv run pytest packages/parcel-shell/tests/test_registry.py -v`
Expected: all 5 tests still PASS.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/conftest.py
git commit -m "test(shell): Phase 3 fixtures — sys.path + entry_points patching helpers"
```

---

## Task 8: Discovery

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/discovery.py`
- Create: `packages/parcel-shell/tests/test_discovery.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_discovery.py`:

```python
from __future__ import annotations

from importlib.metadata import EntryPoint


def test_discover_returns_fixture_module(patch_entry_points) -> None:
    from parcel_shell.modules.discovery import discover_modules

    out = discover_modules()
    assert len(out) == 1
    d = out[0]
    assert d.module.name == "test"
    assert d.module.version == "0.1.0"
    assert d.distribution_name == "parcel-mod-test"


def test_discover_returns_empty_when_no_entry_points(empty_entry_points) -> None:
    from parcel_shell.modules.discovery import discover_modules

    assert discover_modules() == []


def test_discover_skips_failing_entry_points(monkeypatch) -> None:
    from parcel_shell.modules import discovery

    bad = EntryPoint(name="bad", value="nonexistent_pkg:module", group="parcel.modules")

    def fake_entry_points(*, group: str):
        return [bad] if group == "parcel.modules" else []

    monkeypatch.setattr(discovery, "entry_points", fake_entry_points)
    assert discovery.discover_modules() == []


def test_discover_skips_entry_points_returning_non_module(monkeypatch) -> None:
    """An entry point that resolves to something that isn't a Module is skipped."""
    from parcel_shell.modules import discovery

    # Build an EntryPoint that resolves to `typing.Any` (not a Module).
    ep = EntryPoint(name="wrongtype", value="typing:Any", group="parcel.modules")

    def fake_entry_points(*, group: str):
        return [ep] if group == "parcel.modules" else []

    monkeypatch.setattr(discovery, "entry_points", fake_entry_points)
    assert discovery.discover_modules() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_discovery.py -v`
Expected: FAIL — `parcel_shell.modules.discovery` not found.

- [ ] **Step 3: Implement `discovery.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/discovery.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points

import structlog

from parcel_sdk import Module

_log = structlog.get_logger("parcel_shell.modules.discovery")


@dataclass(frozen=True)
class DiscoveredModule:
    module: Module
    distribution_name: str
    distribution_version: str


def discover_modules() -> list[DiscoveredModule]:
    """Enumerate modules exposed via the ``parcel.modules`` entry-point group.

    Bad entry points (import errors, non-Module objects) are logged and skipped
    rather than raised — shell must not fail to boot because of a third-party
    module's problem.
    """
    out: list[DiscoveredModule] = []
    for ep in entry_points(group="parcel.modules"):
        try:
            resolved = ep.load()
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "module.discovery_failed",
                entry_point=ep.name,
                error=str(exc),
            )
            continue
        if not isinstance(resolved, Module):
            _log.warning(
                "module.discovery_bad_type",
                entry_point=ep.name,
                got=type(resolved).__name__,
            )
            continue
        dist = getattr(ep, "dist", None)
        out.append(
            DiscoveredModule(
                module=resolved,
                distribution_name=dist.name if dist else ep.name,
                distribution_version=dist.version if dist else "0.0.0",
            )
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_discovery.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/discovery.py packages/parcel-shell/tests/test_discovery.py
git commit -m "feat(shell): entry-point-based module discovery"
```

---

## Task 9: Module service (install / upgrade / uninstall / sync_on_boot)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/service.py`
- Create: `packages/parcel-shell/tests/test_module_service.py`

**Convention:** `install_module`, `upgrade_module`, and `uninstall_module` all take an explicit `database_url: str` keyword argument. The service layer does not reach into `db.bind` to infer the URL (an `AsyncSession` whose `bind` is an `AsyncConnection` — as used by our `db_session` fixture — doesn't expose a URL cleanly). In tests, pass `database_url=migrations_applied`. In the router layer (Task 11), pass `database_url=request.app.state.settings.database_url`.

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_module_service.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.modules import service
from parcel_shell.modules.models import InstalledModule


@pytest.fixture
def index(discovered_test_module) -> dict:
    return {discovered_test_module.module.name: discovered_test_module}


async def test_install_happy_path(
    db_session: AsyncSession, index, migrations_applied: str
) -> None:
    row = await service.install_module(
        db_session,
        name="test",
        approve_capabilities=["http_egress"],
        discovered=index,
        database_url=migrations_applied,
    )
    await db_session.commit()

    assert row.name == "test"
    assert row.is_active is True
    assert row.capabilities == ["http_egress"]
    assert row.schema_name == "mod_test"
    assert row.last_migrated_rev == "0001"

    # Schema and table created
    async with db_session.bind.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'mod_test' ORDER BY table_name"
                )
            )
        ).all()
    assert {r[0] for r in tables} == {"items", "alembic_version"}

    # Cleanup so other tests start clean.
    await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
    await db_session.commit()


async def test_install_rejects_capability_mismatch(db_session: AsyncSession, index) -> None:
    with pytest.raises(service.CapabilityMismatch):
        await service.install_module(
            db_session, name="test", approve_capabilities=[], discovered=index
        )


async def test_install_rejects_unknown_module(db_session: AsyncSession, index) -> None:
    with pytest.raises(service.ModuleNotDiscovered):
        await service.install_module(
            db_session, name="nope", approve_capabilities=[], discovered=index
        )


async def test_install_rejects_double_install(db_session: AsyncSession, index) -> None:
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()
    try:
        with pytest.raises(service.ModuleAlreadyInstalled):
            await service.install_module(
                db_session, name="test", approve_capabilities=["http_egress"], discovered=index
            )
    finally:
        await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
        await db_session.commit()


async def test_uninstall_soft_keeps_schema(db_session: AsyncSession, index) -> None:
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()

    await service.uninstall_module(db_session, name="test", drop_data=False, discovered=index)
    await db_session.commit()

    row = await db_session.get(InstalledModule, "test")
    assert row is not None
    assert row.is_active is False

    async with db_session.bind.connect() as conn:
        result = (
            await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'mod_test'"
                )
            )
        ).scalar_one_or_none()
    assert result == "mod_test"

    # Cleanup
    await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
    await db_session.commit()


async def test_uninstall_hard_drops_everything(db_session: AsyncSession, index) -> None:
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()

    await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
    await db_session.commit()

    assert await db_session.get(InstalledModule, "test") is None

    async with db_session.bind.connect() as conn:
        schema = (
            await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = 'mod_test'"
                )
            )
        ).scalar_one_or_none()
        perm = (
            await conn.execute(
                text("SELECT name FROM shell.permissions WHERE name = 'test.read'")
            )
        ).scalar_one_or_none()
    assert schema is None
    assert perm is None


async def test_upgrade_is_noop_when_at_head(db_session: AsyncSession, index) -> None:
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()

    try:
        row = await service.upgrade_module(db_session, name="test", discovered=index)
        await db_session.commit()
        assert row.last_migrated_rev == "0001"
    finally:
        await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
        await db_session.commit()


async def test_sync_on_boot_flips_orphans(db_session: AsyncSession, index) -> None:
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()

    # Discovery no longer sees the module.
    await service.sync_on_boot(db_session, discovered={})
    await db_session.commit()

    row = await db_session.get(InstalledModule, "test")
    assert row is not None and row.is_active is False

    # Cleanup (re-add to index so hard uninstall has the alembic config)
    await service.uninstall_module(db_session, name="test", drop_data=True, discovered=index)
    await db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_module_service.py -v`
Expected: FAIL — `parcel_shell.modules.service` not found.

- [ ] **Step 3: Implement `service.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/service.py`:

```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.models import InstalledModule
from parcel_shell.rbac.models import Permission

_log = structlog.get_logger("parcel_shell.modules.service")


class ModuleNotDiscovered(Exception):
    pass


class ModuleAlreadyInstalled(Exception):
    pass


class CapabilityMismatch(Exception):
    pass


class ModuleMigrationFailed(Exception):
    pass


def _alembic_config(database_url: str, discovered: DiscoveredModule) -> Config:
    ini = discovered.module.alembic_ini
    if ini is None:
        raise ValueError(f"module {discovered.module.name!r} has no alembic_ini")
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def install_module(
    db: AsyncSession,
    *,
    name: str,
    approve_capabilities: list[str],
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> InstalledModule:
    d = discovered.get(name)
    if d is None:
        raise ModuleNotDiscovered(name)
    if await db.get(InstalledModule, name) is not None:
        raise ModuleAlreadyInstalled(name)
    if set(approve_capabilities) != set(d.module.capabilities):
        raise CapabilityMismatch(
            f"declared={sorted(d.module.capabilities)!r} approved={sorted(approve_capabilities)!r}"
        )

    from sqlalchemy import text as sa_text

    schema = f"mod_{name}"
    await db.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # Upsert declared permissions for this module.
    if d.module.permissions:
        stmt = pg_insert(Permission).values(
            [
                {"name": p.name, "description": p.description, "module": name}
                for p in d.module.permissions
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Permission.name],
            set_={"description": stmt.excluded.description, "module": stmt.excluded.module},
        )
        await db.execute(stmt)

    # The migrations open their own connection; they must see our in-flight
    # changes (esp. the CREATE SCHEMA), so flush + commit before running them.
    await db.flush()
    await db.commit()

    cfg = _alembic_config(database_url, d)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        _log.exception("module.install_migration_failed", name=name, error=str(exc))
        # Best-effort cleanup of what we committed.
        await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.execute(
            sa_text("DELETE FROM shell.permissions WHERE module = :name"),
            {"name": name},
        )
        await db.commit()
        raise ModuleMigrationFailed(str(exc)) from exc

    head = ScriptDirectory.from_config(cfg).get_current_head()
    now = datetime.now(UTC)
    row = InstalledModule(
        name=name,
        version=d.module.version,
        is_active=True,
        capabilities=sorted(set(approve_capabilities)),
        schema_name=schema,
        installed_at=now,
        updated_at=now,
        last_migrated_at=now,
        last_migrated_rev=head,
    )
    db.add(row)
    await db.flush()
    return row


async def upgrade_module(
    db: AsyncSession,
    *,
    name: str,
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> InstalledModule:
    row = await db.get(InstalledModule, name)
    if row is None:
        raise ModuleNotDiscovered(name)
    d = discovered.get(name)
    if d is None:
        raise ModuleNotDiscovered(name)

    cfg = _alembic_config(database_url, d)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        _log.exception("module.upgrade_failed", name=name, error=str(exc))
        raise ModuleMigrationFailed(str(exc)) from exc

    head = ScriptDirectory.from_config(cfg).get_current_head()
    now = datetime.now(UTC)
    row.version = d.module.version
    row.updated_at = now
    row.last_migrated_at = now
    row.last_migrated_rev = head
    await db.flush()
    return row


async def uninstall_module(
    db: AsyncSession,
    *,
    name: str,
    drop_data: bool = False,
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> None:
    row = await db.get(InstalledModule, name)
    if row is None:
        raise ModuleNotDiscovered(name)

    from sqlalchemy import text as sa_text

    now = datetime.now(UTC)

    if not drop_data:
        row.is_active = False
        row.updated_at = now
        await db.flush()
        return

    # Hard uninstall: attempt downgrade, then DROP SCHEMA CASCADE, then delete
    # the permissions and installed_modules row.
    d = discovered.get(name)
    if d is not None:
        cfg = _alembic_config(database_url, d)
        try:
            await asyncio.to_thread(command.downgrade, cfg, "base")
        except Exception as exc:
            # Continue — we're going to CASCADE-drop anyway, but log it.
            _log.warning("module.downgrade_skipped", name=name, error=str(exc))

    await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "mod_{name}" CASCADE'))
    # Permission rows with `module=name` are removed; role_permissions cascades.
    await db.execute(
        sa_text("DELETE FROM shell.permissions WHERE module = :name"),
        {"name": name},
    )
    await db.delete(row)
    await db.flush()


async def sync_on_boot(
    db: AsyncSession,
    *,
    discovered: dict[str, DiscoveredModule] | None = None,
) -> None:
    """Flip rows whose module is no longer entry-point-discoverable to inactive."""
    if discovered is None:
        from parcel_shell.modules.discovery import discover_modules

        discovered = {d.module.name: d for d in discover_modules()}

    rows = (
        await db.execute(select(InstalledModule).where(InstalledModule.is_active.is_(True)))
    ).scalars().all()
    now = datetime.now(UTC)
    for row in rows:
        if row.name not in discovered:
            _log.warning("module.missing", name=row.name)
            row.is_active = False
            row.updated_at = now
    await db.flush()
```

A small helper note: `sync_on_boot` accepts `discovered` as a keyword for tests but the test above calls `sync_on_boot(db_session, discovered={})` positionally. Since the test signature must match the function, update `sync_on_boot` to accept `discovered` as a positional-or-keyword arg — the signature above does this via the default.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_module_service.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/service.py packages/parcel-shell/tests/test_module_service.py
git commit -m "feat(shell): module install/upgrade/uninstall service + boot sync"
```

---

## Task 10: Pydantic schemas for the admin router

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/schemas.py`

- [ ] **Step 1: Create schemas**

Create `packages/parcel-shell/src/parcel_shell/modules/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ModuleSummary(BaseModel):
    name: str
    version: str
    is_active: bool | None
    is_discoverable: bool
    declared_capabilities: list[str]
    approved_capabilities: list[str]
    schema_name: str | None
    installed_at: datetime | None
    last_migrated_at: datetime | None
    last_migrated_rev: str | None


class InstallModuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    approve_capabilities: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Sanity check — schemas import**

Run: `uv run python -c "from parcel_shell.modules.schemas import ModuleSummary, InstallModuleRequest; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/schemas.py
git commit -m "feat(shell): pydantic schemas for module admin API"
```

---

## Task 11: `/admin/modules` router

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/router_admin.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`
- Create: `packages/parcel-shell/tests/test_modules_router.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_modules_router.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_list_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/admin/modules")
    assert r.status_code == 401


async def test_list_shows_discovered_only(authed_client: AsyncClient, patch_entry_points) -> None:
    r = await authed_client.get("/admin/modules")
    assert r.status_code == 200
    items = {m["name"]: m for m in r.json()}
    assert "test" in items
    assert items["test"]["is_discoverable"] is True
    assert items["test"]["is_active"] is None  # not installed yet


async def test_install_requires_exact_capability_approval(
    authed_client: AsyncClient, patch_entry_points
) -> None:
    r = await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": []},
    )
    assert r.status_code == 403


async def test_install_happy_path(authed_client: AsyncClient, patch_entry_points) -> None:
    r = await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["is_active"] is True
    assert body["schema_name"] == "mod_test"

    # Shows up as installed + discoverable in the list
    lr = await authed_client.get("/admin/modules")
    items = {m["name"]: m for m in lr.json()}
    assert items["test"]["is_active"] is True
    assert items["test"]["is_discoverable"] is True

    # And permissions.read can see the new permission
    pr = await authed_client.get("/admin/permissions")
    assert any(p["name"] == "test.read" for p in pr.json())

    # Cleanup
    await authed_client.post("/admin/modules/test/uninstall?drop_data=true")


async def test_install_duplicate_is_409(
    authed_client: AsyncClient, patch_entry_points
) -> None:
    await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    assert r.status_code == 409
    await authed_client.post("/admin/modules/test/uninstall?drop_data=true")


async def test_upgrade_happy_path(authed_client: AsyncClient, patch_entry_points) -> None:
    await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await authed_client.post("/admin/modules/test/upgrade")
    assert r.status_code == 200
    assert r.json()["last_migrated_rev"] == "0001"
    await authed_client.post("/admin/modules/test/uninstall?drop_data=true")


async def test_uninstall_soft(authed_client: AsyncClient, patch_entry_points) -> None:
    await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await authed_client.post("/admin/modules/test/uninstall")
    assert r.status_code == 204
    got = await authed_client.get("/admin/modules/test")
    assert got.json()["is_active"] is False
    # Cleanup hard
    await authed_client.post("/admin/modules/test/uninstall?drop_data=true")


async def test_uninstall_hard(authed_client: AsyncClient, patch_entry_points) -> None:
    await authed_client.post(
        "/admin/modules/install",
        json={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await authed_client.post("/admin/modules/test/uninstall?drop_data=true")
    assert r.status_code == 204
    got = await authed_client.get("/admin/modules/test")
    # After hard uninstall: not installed; still discoverable (entry point present).
    assert got.status_code == 200
    assert got.json()["is_active"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_modules_router.py -v`
Expected: FAIL — `/admin/modules` not mounted.

- [ ] **Step 3: Implement `router_admin.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/router_admin.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.dependencies import require_permission
from parcel_shell.db import get_session
from parcel_shell.modules import service
from parcel_shell.modules.discovery import DiscoveredModule, discover_modules
from parcel_shell.modules.models import InstalledModule
from parcel_shell.modules.schemas import InstallModuleRequest, ModuleSummary

router = APIRouter(prefix="/admin/modules", tags=["admin", "modules"])


def _discovered_index() -> dict[str, DiscoveredModule]:
    return {d.module.name: d for d in discover_modules()}


def _summary(
    name: str,
    row: InstalledModule | None,
    d: DiscoveredModule | None,
) -> ModuleSummary:
    declared = list(d.module.capabilities) if d is not None else []
    installed_ver = row.version if row else (d.module.version if d else "")
    return ModuleSummary(
        name=name,
        version=installed_ver,
        is_active=(row.is_active if row is not None else None),
        is_discoverable=(d is not None),
        declared_capabilities=sorted(declared),
        approved_capabilities=(list(row.capabilities) if row else []),
        schema_name=(row.schema_name if row else None),
        installed_at=(row.installed_at if row else None),
        last_migrated_at=(row.last_migrated_at if row else None),
        last_migrated_rev=(row.last_migrated_rev if row else None),
    )


@router.get("", response_model=list[ModuleSummary])
async def list_modules(
    _: object = Depends(require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> list[ModuleSummary]:
    index = _discovered_index()
    rows = (await db.execute(select(InstalledModule))).scalars().all()
    by_name = {r.name: r for r in rows}
    names = sorted(set(index) | set(by_name))
    return [_summary(n, by_name.get(n), index.get(n)) for n in names]


@router.get("/{name}", response_model=ModuleSummary)
async def get_module(
    name: str,
    _: object = Depends(require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    row = await db.get(InstalledModule, name)
    if row is None and name not in index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found")
    return _summary(name, row, index.get(name))


@router.post("/install", response_model=ModuleSummary, status_code=201)
async def install(
    payload: InstallModuleRequest,
    _: object = Depends(require_permission("modules.install")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    try:
        row = await service.install_module(
            db,
            name=payload.name,
            approve_capabilities=payload.approve_capabilities,
            discovered=index,
        )
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_discovered") from e
    except service.ModuleAlreadyInstalled as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "module_already_installed") from e
    except service.CapabilityMismatch as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "capability_mismatch") from e
    except service.ModuleMigrationFailed as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "module_install_failed"
        ) from e
    return _summary(row.name, row, index.get(row.name))


@router.post("/{name}/upgrade", response_model=ModuleSummary)
async def upgrade(
    name: str,
    _: object = Depends(require_permission("modules.upgrade")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    try:
        row = await service.upgrade_module(db, name=name, discovered=index)
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from e
    except service.ModuleMigrationFailed as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "module_upgrade_failed"
        ) from e
    return _summary(row.name, row, index.get(row.name))


@router.post("/{name}/uninstall", status_code=204)
async def uninstall(
    name: str,
    drop_data: bool = Query(default=False),
    _: object = Depends(require_permission("modules.uninstall")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    try:
        await service.uninstall_module(
            db, name=name, drop_data=drop_data, discovered=index
        )
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from e
    return Response(status_code=204)
```

- [ ] **Step 4: Wire the router into the app**

Edit `packages/parcel-shell/src/parcel_shell/app.py`. Add the import with the other router imports:

```python
from parcel_shell.modules.router_admin import router as modules_router
```

And include it after the existing `admin_router` include:

```python
    app.include_router(modules_router)
```

- [ ] **Step 5: Wire `sync_on_boot` into the lifespan**

In the same file, inside the `lifespan` async generator, after the existing `permission_registry.sync_to_db(s)` block, add:

```python
        # Flip previously-installed modules whose package is no longer discoverable
        # to is_active=false, so we don't pretend they're there.
        async with sessionmaker() as s:
            from parcel_shell.modules import service as module_service

            await module_service.sync_on_boot(s)
            await s.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_modules_router.py -v`
Expected: all 8 tests PASS.

Note: these tests install and uninstall the fixture module in each test. The `patch_entry_points` fixture covers discovery inside the endpoint handlers — without it, `discover_modules()` inside the handler would return the empty list.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/router_admin.py packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/tests/test_modules_router.py
git commit -m "feat(shell): /admin/modules endpoints + boot-time orphan sync"
```

---

## Task 12: End-to-end boot-orphan test

**Files:**
- Create: `packages/parcel-shell/tests/test_module_boot.py`

- [ ] **Step 1: Write the test**

Create `packages/parcel-shell/tests/test_module_boot.py`:

```python
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.modules import service
from parcel_shell.modules.models import InstalledModule


async def test_sync_on_boot_flips_orphan_with_warning(
    db_session: AsyncSession, discovered_test_module, caplog
) -> None:
    index = {discovered_test_module.module.name: discovered_test_module}
    await service.install_module(
        db_session, name="test", approve_capabilities=["http_egress"], discovered=index
    )
    await db_session.commit()

    caplog.set_level(logging.WARNING)

    # Now pretend discovery no longer sees the module.
    await service.sync_on_boot(db_session, discovered={})
    await db_session.commit()

    row = await db_session.get(InstalledModule, "test")
    assert row is not None and row.is_active is False

    # Cleanup
    await service.uninstall_module(
        db_session, name="test", drop_data=True, discovered=index
    )
    await db_session.commit()
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest packages/parcel-shell/tests/test_module_boot.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest`
Expected: all tests across Phase 1 + 2 + 3 green.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/tests/test_module_boot.py
git commit -m "test(shell): orphan-module boot sync end-to-end"
```

---

## Task 13: Docker Compose verification

**Files:** None (live verification only).

- [ ] **Step 1: Rebuild the shell image**

Run: `docker compose build shell`
Expected: succeeds.

- [ ] **Step 2: Apply migration 0003**

Run: `docker compose run --rm shell migrate`
Expected log line: `INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, install_modules + modules.* permissions`.

- [ ] **Step 3: Start the shell**

```bash
docker compose up -d shell
```

Wait for the container to become healthy.

- [ ] **Step 4: Log in as admin (using the account from Phase 2)**

```bash
curl -sS -c /tmp/padmin -H 'content-type: application/json' \
  -d '{"email":"admin@parcel.example.com","password":"pw-at-least-12-chars"}' \
  http://localhost:8000/auth/login > /dev/null
```

(If the admin wasn't created yet, run `docker compose run --rm shell bootstrap create-admin --email admin@parcel.example.com --password 'pw-at-least-12-chars'`.)

- [ ] **Step 5: Confirm admin has the 4 new module permissions**

```bash
curl -sS -b /tmp/padmin http://localhost:8000/auth/me | python -c "import sys, json; perms = json.load(sys.stdin)['permissions']; print(sorted(p for p in perms if p.startswith('modules.')))"
```

Expected output: `['modules.install', 'modules.read', 'modules.uninstall', 'modules.upgrade']`.

- [ ] **Step 6: Confirm `/admin/modules` returns an empty list**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -b /tmp/padmin http://localhost:8000/admin/modules
```

Expected: `200` (response body is `[]` since the container has no pip-installed modules).

No commit for this task.

---

## Task 14: Quality gates + docs

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check packages/parcel-shell packages/parcel-sdk
uv run ruff format --check packages/parcel-shell packages/parcel-sdk
```

If anything fails, auto-fix:

```bash
uv run ruff check packages/parcel-shell packages/parcel-sdk --fix
uv run ruff format packages/parcel-shell packages/parcel-sdk
```

- [ ] **Step 2: Run pyright**

```bash
uv run pyright packages/parcel-shell packages/parcel-sdk
```

Expected: 0 errors. If pyright complains about pydantic `BaseModel(...)` calls in any Phase 3 test, add `# pyright: reportCallIssue=false` at the top of that file (same pattern as Phase 2).

- [ ] **Step 3: Run the full test suite once more**

```bash
uv run pytest
```

Expected: green.

- [ ] **Step 4: Update `README.md`**

Update the `Status:` line:

```markdown
**Status:** Pre-alpha. Phase 3 complete — shell discovers modules via entry points, admins can install/upgrade/uninstall them through `/admin/modules/*`, each module owns its own Postgres schema and Alembic migrations. The Contacts demo module lands in Phase 5.
```

Append a new section after "Create an admin user":

```markdown
### Inspect module state (Phase 3+)

```bash
curl -b cookies.txt http://localhost:8000/admin/modules
```

Out of the box this is empty. Once Phase 5 ships a real Contacts module, it
will appear here and can be installed with:

```bash
curl -b cookies.txt -H 'content-type: application/json' \
  -d '{"name":"contacts","approve_capabilities":[]}' \
  http://localhost:8000/admin/modules/install
```
```

- [ ] **Step 5: Update `CLAUDE.md`**

Change the `## Current phase` block to:

```markdown
**Phase 3 — Module system done.** `parcel-sdk` exposes `Module`, `Permission`, and a `run_async_migrations` helper for module `env.py` files. Shell discovers modules via the `parcel.modules` entry-point group; admins explicitly install/upgrade/uninstall via `/admin/modules/*` (4 new permissions, all on the built-in `admin` role). Each installed module owns a `mod_<name>` schema; migrations run in-process via `alembic.command.upgrade`. Orphaned rows (package pip-uninstalled while row exists) flip to `is_active=false` at boot with a warning; shell never refuses to boot because of a module issue.

Next: **Phase 4 — Admin UI shell.** Start a new session; prompt: "Begin Phase 4: admin UI shell per `CLAUDE.md` roadmap." Do not begin Phase 4 inside the Phase 3 commit cluster.
```

In the "Phased roadmap" table, change Phase 3 to `✅ done` and Phase 4 to `⏭ next`.

Append to the "Locked-in decisions" table:

```markdown
| Phase 3 SDK deps | sqlalchemy[asyncio], alembic (runtime, so module env.py works) |
| Module install model | Explicit — discovery lists candidates; admin calls `POST /admin/modules/install` to activate |
| Module uninstall | Soft by default (`is_active=false`); `?drop_data=true` runs `alembic downgrade base`, drops `mod_<name>` schema, removes permissions + row |
| Module migrations | In-process `alembic.command.upgrade` against the module's `alembic.ini`; per-module `alembic_version` lives inside the module's own schema |
| Module orphans at boot | Warn + flip to `is_active=false`; shell never refuses to boot |
| Shell permissions (12) | Phase 2's 8 + `modules.{read,install,upgrade,uninstall}` |
```

- [ ] **Step 6: Final commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: close Phase 3, document module install/upgrade/uninstall flow"
```

---

## Verification summary (Phase 3 definition of done)

- [ ] `docker compose run --rm shell migrate` applies 0003; `shell.installed_modules` exists; admin role has 12 permissions.
- [ ] Installing the test fixture module (via pytest) creates `mod_test` with `items` and `alembic_version`; `test.read` is a registered permission.
- [ ] Hard-uninstalling drops `mod_test` and removes `test.read`.
- [ ] Orphaning the fixture (empty entry points) on next `sync_on_boot` flips `is_active=false` with a `module.missing` warning.
- [ ] `uv run pytest` green across Phase 1 + 2 + 3.
- [ ] `uv run ruff check` + `uv run pyright packages/parcel-shell packages/parcel-sdk` clean.
- [ ] README + CLAUDE.md updated; Phase 3 ✅, Phase 4 ⏭.
