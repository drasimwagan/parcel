# Phase 3 — Module System Design

**Date:** 2026-04-23
**Phase:** 3 (next after Phase 2 — auth + RBAC)
**Goal (from `CLAUDE.md`):** Module system — manifest spec, entry-point discovery, migration orchestrator, admin module API.

## Scope

Phase 3 delivers the infrastructure Phase 5 (Contacts demo module) will plug into:

- A minimal `parcel-sdk` surface: `Module`, `Permission`, and an `alembic_env.run_async_migrations` helper.
- Shell-side entry-point discovery over the `parcel.modules` group.
- Explicit install / upgrade / uninstall flow with an `installed_modules` table.
- Per-module schema creation (`mod_<name>`) and in-process alembic migration orchestration.
- `/admin/modules/*` JSON endpoints gated by four new permissions.
- Soft-by-default uninstall; hard uninstall with `?drop_data=true`.
- Orphaned-module handling at boot (row present, entry-point gone) — log + flip inactive, keep booting.
- A real fixture module living under `packages/parcel-shell/tests/_fixtures/test_module/` used by the test suite.

Phase 3 does **not** deliver: any module's own HTTP routes, the Contacts module itself, admin HTML pages, AI-generated modules, module dependency resolution, or runtime capability enforcement.

## Locked decisions from brainstorming

| Question | Decision |
|---|---|
| Install model | Explicit. Discovery lists candidates; admin must `POST /admin/modules/install` to activate. |
| Capabilities | Data model only in Phase 3 — stored on install, admin approves. Runtime enforcement (AST/import-hook) is Phase 7. |
| Migration orchestration | In-process `alembic.command.upgrade` / `downgrade`. No subprocess. |
| Uninstall | Soft by default (`is_active=false`). Hard via `?drop_data=true` runs `downgrade base`, drops schema, deletes row. |
| SDK surface | Minimal: `Module`, `Permission`, `run_async_migrations`. No dependency graph. |
| Orphaned module at boot | Warn, flip `is_active=false`, keep booting. |

## Package layout additions

```
packages/parcel-sdk/src/parcel_sdk/
  __init__.py              # re-exports Module, Permission, run_async_migrations
  module.py                # Module + Permission dataclasses
  alembic_env.py           # run_async_migrations helper

packages/parcel-shell/src/parcel_shell/modules/
  __init__.py
  discovery.py             # discover_modules() -> list[DiscoveredModule]
  models.py                # InstalledModule ORM model
  service.py               # install / upgrade / uninstall / sync_on_boot
  schemas.py               # pydantic request/response models
  router_admin.py          # /admin/modules/* endpoints

packages/parcel-shell/src/parcel_shell/alembic/versions/
  0003_install_modules.py  # shell.installed_modules + 4 new permissions

packages/parcel-shell/tests/
  _fixtures/test_module/                 # a real installable module used as a test fixture
    pyproject.toml
    src/parcel_mod_test/__init__.py      # declares `module = Module(...)` with 1 permission + 1 capability
    src/parcel_mod_test/alembic.ini
    src/parcel_mod_test/alembic/env.py
    src/parcel_mod_test/alembic/script.py.mako
    src/parcel_mod_test/alembic/versions/0001_initial.py
  test_sdk_module.py
  test_discovery.py
  test_module_service.py
  test_modules_router.py
  test_module_boot.py
```

### Module boundaries

- **`parcel_sdk.module`** — pure dataclasses. No I/O, no alembic, no SQLAlchemy. Safe to import anywhere.
- **`parcel_sdk.alembic_env`** — the one piece of SDK code that depends on SQLAlchemy + Alembic. Called from module `env.py` files only. Reads `DATABASE_URL` from env; creates the `mod_<name>` schema; runs migrations scoped to that schema and a version table also in that schema.
- **`parcel_shell.modules.discovery`** — wraps `importlib.metadata.entry_points(group="parcel.modules")`. Returns a list; never raises; bad entry points are logged and skipped.
- **`parcel_shell.modules.service`** — pure async functions over `AsyncSession`. Orchestrates install/upgrade/uninstall and the lifespan sync. The only place that calls `alembic.command.upgrade/downgrade`.
- **`parcel_shell.modules.router_admin`** — thin FastAPI layer.
- **`parcel_shell.modules.models.InstalledModule`** — ORM model on `ShellBase`, lives in `shell` schema.

## SDK surface (parcel-sdk)

```python
# parcel_sdk/module.py
from __future__ import annotations

from dataclasses import dataclass, field
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
    alembic_ini: Path | None = None       # filled in by module_root / "alembic.ini" by convention
    metadata: "MetaData | None" = None    # SQLAlchemy MetaData; required if the module has tables
```

```python
# parcel_sdk/alembic_env.py  (abbreviated)
import asyncio, os
from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

def run_async_migrations(module) -> None:
    cfg = context.config
    database_url = os.getenv("DATABASE_URL") or cfg.get_main_option("sqlalchemy.url")
    schema = f"mod_{module.name}"
    cfg.set_main_option("sqlalchemy.url", database_url)

    async def _run():
        connectable = async_engine_from_config(
            cfg.get_section(cfg.config_ini_section, {}), prefix="sqlalchemy."
        )
        async with connectable.connect() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            await conn.commit()
            await conn.run_sync(lambda c: _do(c, module, schema))
        await connectable.dispose()

    asyncio.run(_run())


def _do(connection, module, schema):
    context.configure(
        connection=connection,
        target_metadata=module.metadata,
        version_table="alembic_version",
        version_table_schema=schema,   # each module's version table lives in its own schema
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
```

A module's full `alembic/env.py` becomes:

```python
from parcel_mod_foo import module
from parcel_sdk.alembic_env import run_async_migrations
run_async_migrations(module)
```

Module-schema alembic_version lives inside the module's own schema (unlike shell, which keeps `alembic_version` in `public` because the shell baseline drops its own schema on downgrade). Module downgrades drop the schema CASCADE, which also drops the version table cleanly — no conflict.

## Data model

### `shell.installed_modules`

| column | type | notes |
|---|---|---|
| `name` | `text` PK | matches the entry-point key |
| `version` | `text` NOT NULL | `Module.version` at install (or latest upgrade) |
| `is_active` | `boolean` NOT NULL DEFAULT `true` | set `false` on soft uninstall or orphan detection |
| `capabilities` | `jsonb` NOT NULL DEFAULT `'[]'::jsonb` | the capabilities the admin approved |
| `schema_name` | `text` NOT NULL UNIQUE | always `mod_<name>` |
| `installed_at` | `timestamptz` NOT NULL DEFAULT `now()` | |
| `updated_at` | `timestamptz` NOT NULL DEFAULT `now()` | |
| `last_migrated_at` | `timestamptz` | set by `install` and `upgrade` |
| `last_migrated_rev` | `text` | alembic head revision after the run |

### Migration `0003_install_modules`

- Creates `shell.installed_modules`.
- Seeds four new shell permissions:
  - `modules.read` — View registered and discovered modules
  - `modules.install` — Install a discovered module
  - `modules.upgrade` — Run migrations for an already-installed module
  - `modules.uninstall` — Deactivate or remove a module
- Attaches all four to the `admin` role.

Downgrade: delete those four permission names (cascades via `role_permissions`), drop `installed_modules`.

## Shell-owned permissions after Phase 3

12 total: the 8 from Phase 2 plus `modules.{read,install,upgrade,uninstall}`. Seeded by migration 0003. All attached to the built-in `admin` role.

## Discovery

```python
# parcel_shell/modules/discovery.py
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
    out: list[DiscoveredModule] = []
    for ep in entry_points(group="parcel.modules"):
        try:
            mod = ep.load()
        except Exception as exc:  # noqa: BLE001
            _log.warning("module.discovery_failed", entry_point=ep.name, error=str(exc))
            continue
        if not isinstance(mod, Module):
            _log.warning("module.discovery_bad_type", entry_point=ep.name, got=type(mod).__name__)
            continue
        dist = ep.dist
        out.append(
            DiscoveredModule(
                module=mod,
                distribution_name=dist.name if dist else ep.name,
                distribution_version=dist.version if dist else "0.0.0",
            )
        )
    return out
```

Tests monkeypatch `parcel_shell.modules.discovery.entry_points` to inject fixtures.

## Install / upgrade / uninstall (service)

```python
# parcel_shell/modules/service.py  (shapes only; implementation filled in the plan)

class ModuleNotDiscovered(Exception): ...
class ModuleAlreadyInstalled(Exception): ...
class CapabilityMismatch(Exception): ...
class ModuleMigrationFailed(Exception): ...


async def install_module(
    db: AsyncSession,
    *,
    name: str,
    approve_capabilities: list[str],
) -> InstalledModule: ...

async def upgrade_module(db: AsyncSession, *, name: str) -> InstalledModule: ...

async def uninstall_module(
    db: AsyncSession,
    *,
    name: str,
    drop_data: bool = False,
) -> None: ...

async def sync_on_boot(
    db: AsyncSession,
    discovered_index: dict[str, DiscoveredModule],
) -> None:
    """Flip orphaned rows to is_active=false and log a warning."""
```

### Install semantics

1. `discovered_index[name]` must exist → else `ModuleNotDiscovered` → 404.
2. Row in `installed_modules.name` must NOT exist → else `ModuleAlreadyInstalled` → 409.
3. `set(approve_capabilities) == set(module.capabilities)` → else `CapabilityMismatch` → 403. (MVP: whole-or-nothing approval.)
4. In a single txn:
   - `CREATE SCHEMA mod_<name>`.
   - Upsert declared permissions via the `PermissionRegistry` pattern from Phase 2, tagged with `module=<name>`.
   - Call `alembic.command.upgrade(cfg, "head")` in-process. Failure → `ModuleMigrationFailed` → roll back txn → `DROP SCHEMA mod_<name> CASCADE` best-effort → 500. (Alembic migrations on Postgres are transactional; our explicit schema drop cleans up anything before alembic took over.)
   - Insert `installed_modules` row with the current head revision (queried via `ScriptDirectory.from_config(cfg).get_current_head()`).

Capabilities are recorded as a sorted list of strings (canonical form). The approval requirement applies to `approve_capabilities` being **exactly** the declared set — callers cannot subset. This avoids a "half-approved" state.

### Upgrade semantics

Runs `alembic.command.upgrade(cfg, "head")` for an already-active module. Updates `version`, `last_migrated_at`, `last_migrated_rev`. Errors return 500; the row is left unchanged (no partial-version bookkeeping). Schema remains intact since alembic's own migrations run in-txn.

### Uninstall semantics

Soft (default): `is_active=false`, `updated_at=now()`. Schema and data stay.

Hard (`drop_data=true`):
1. `alembic.command.downgrade(cfg, "base")`.
2. `DROP SCHEMA mod_<name> CASCADE`.
3. `DELETE FROM shell.permissions WHERE module = '<name>'` (cascades to `role_permissions`).
4. `DELETE FROM installed_modules WHERE name = '<name>'`.

All four steps in one txn. Migration-drop failures abort the whole thing.

### Boot sync

In lifespan, after Phase 2's registry sync:

```python
discovered = discover_modules()
index = {d.module.name: d for d in discovered}
await service.sync_on_boot(session, index)
```

`sync_on_boot`:
- Loads all rows in `installed_modules` where `is_active=true`.
- For each row, if `row.name not in index`: log `module.missing`, set `is_active=false`.
- Does **not** register permissions or run migrations (that happens on explicit install/upgrade).

Phase 4+ will add a second pass that mounts active modules' routers and registers permissions into the in-memory registry for the request layer.

## API endpoints

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/admin/modules` | `modules.read` | Lists installed + discovered-but-not-installed. |
| GET | `/admin/modules/{name}` | `modules.read` | 404 if neither installed nor discovered. |
| POST | `/admin/modules/install` | `modules.install` | Body: `{name, approve_capabilities}`. Returns the new InstalledModule. |
| POST | `/admin/modules/{name}/upgrade` | `modules.upgrade` | Body empty. Returns updated InstalledModule. |
| POST | `/admin/modules/{name}/uninstall` | `modules.uninstall` | Query: `drop_data=bool` (default `false`). Returns 204. |

### Response shapes

```python
class ModuleSummary(BaseModel):
    name: str
    version: str
    is_active: bool | None              # None when discovered-but-not-installed
    is_discoverable: bool
    declared_capabilities: list[str]
    approved_capabilities: list[str]    # [] when not installed
    schema_name: str | None
    installed_at: datetime | None
    last_migrated_at: datetime | None
    last_migrated_rev: str | None

class InstallModuleRequest(BaseModel):
    name: str
    approve_capabilities: list[str] = Field(default_factory=list)
```

### Error codes

- 404 `module_not_found` — neither installed nor discovered.
- 404 `module_not_discovered` — install target isn't in discovery.
- 409 `module_already_installed`.
- 403 `capability_mismatch` — approve_capabilities doesn't equal declared.
- 500 `module_install_failed` / `module_upgrade_failed` / `module_uninstall_failed` — detail in response body when debug, opaque in prod.

## Testing strategy

### Test fixture module

Under `packages/parcel-shell/tests/_fixtures/test_module/`:

- `pyproject.toml` — package `parcel-mod-test`, entry point `[project.entry-points."parcel.modules"] test = "parcel_mod_test:module"`.
- `src/parcel_mod_test/__init__.py`:
  ```python
  from pathlib import Path
  from sqlalchemy import Column, Integer, MetaData, Table, Text
  from parcel_sdk import Module, Permission

  metadata = MetaData(schema="mod_test")
  items = Table("items", metadata, Column("id", Integer, primary_key=True), Column("name", Text))

  module = Module(
      name="test",
      version="0.1.0",
      permissions=(Permission("test.read", "Read test items"),),
      capabilities=("http_egress",),
      alembic_ini=Path(__file__).parent / "alembic.ini",
      metadata=metadata,
  )
  ```
- A one-step alembic migration that creates `mod_test.items`.

The fixture is **not** added to the root workspace — it's a self-contained package under `tests/`. Loading strategy:

1. A session-scoped conftest fixture prepends `packages/parcel-shell/tests/_fixtures/test_module/src` to `sys.path`, making `parcel_mod_test` importable.
2. A function-scoped fixture monkeypatches `parcel_shell.modules.discovery.entry_points` (re-bound at the call site) to return a synthetic `EntryPoint` that resolves to `parcel_mod_test.module`.

Avoiding `pip install -e` means tests don't touch the venv's installed-packages set, which keeps CI deterministic and allows parallel test runs without state leakage.

### Fixtures added to conftest

- `test_module_installed` (session-scoped): runs `uv pip install -e <fixture path>` once per session; yields the resolved `Module` object.
- `discovered_test_module` (function-scoped): returns the `DiscoveredModule` for the fixture.
- `empty_discovery(monkeypatch)`: monkeypatches `discovery.entry_points` to return nothing (for orphan-handling tests).

### Test inventory (~25 tests)

1. **`test_sdk_module.py`**
   - `Module` / `Permission` are frozen dataclasses; equality, hashing, defaults work.
   - `Module.capabilities` default is empty tuple; `permissions` default is empty tuple.

2. **`test_discovery.py`**
   - `discover_modules()` finds the test module after install.
   - An entry point that raises on `.load()` is logged and skipped (not raised).
   - An entry point resolving to a non-`Module` object is logged and skipped.

3. **`test_module_service.py`**
   - `install_module` creates `mod_test` schema, inserts row, upserts permission, runs migration (asserting `mod_test.items` exists).
   - `install_module` raises `ModuleNotDiscovered` for unknown name.
   - `install_module` raises `ModuleAlreadyInstalled` on re-install.
   - `install_module` raises `CapabilityMismatch` when `approve_capabilities` doesn't equal declared.
   - `upgrade_module` on a module at head is a no-op but bumps `last_migrated_at`.
   - `uninstall_module(drop_data=False)` sets `is_active=false`, leaves schema.
   - `uninstall_module(drop_data=True)` drops schema, deletes permission row, deletes installed_modules row.

4. **`test_modules_router.py`**
   - GET /admin/modules requires `modules.read`.
   - GET lists both installed (the fixture after install) and discovered-only (before install).
   - POST /admin/modules/install with mismatched capabilities → 403.
   - POST /admin/modules/install happy path → 201.
   - POST /admin/modules/install on already-installed → 409.
   - POST /admin/modules/{name}/upgrade → 200.
   - POST /admin/modules/{name}/uninstall (soft) → 204, module listed `is_active=false`.
   - POST /admin/modules/{name}/uninstall?drop_data=true → 204, schema gone, permission gone.

5. **`test_module_boot.py`**
   - Install the fixture; then monkeypatch discovery to return nothing; boot; assert row is `is_active=false` and `module.missing` was logged.

### Running tests

`uv run pytest` continues to work with the same testcontainers Postgres. First run pays a one-time cost to install the fixture module editable; subsequent runs re-use the install.

## Dependency changes

`packages/parcel-sdk/pyproject.toml`:
- `sqlalchemy[asyncio]>=2.0.36` (for `MetaData` in type hints, used at runtime by `alembic_env`)
- `alembic>=1.14`

No new shell-side deps. Root workspace unchanged.

## Definition of done

1. `docker compose run --rm shell migrate` applies 0003 cleanly; `shell.installed_modules` exists; `admin` role has 12 permissions.
2. Installing the test fixture module via the API creates `mod_test` schema with `items` and `alembic_version` tables; `test.read` appears in `/admin/permissions`.
3. Hard-uninstalling drops `mod_test` schema and `test.read` permission.
4. Removing the fixture's entry point and rebooting produces `module.missing` warning + row flip to `is_active=false`; shell boots healthy.
5. `uv run pytest` green across all three phases.
6. `uv run ruff check` clean; `uv run pyright packages/parcel-shell packages/parcel-sdk` → 0 errors.
7. CLAUDE.md: Phase 3 ✅, Phase 4 ⏭ next; SDK now has real content noted in Locked-in decisions.

## Out of scope (deferred)

- Module dependencies (`Module.requires`) — add when a second module needs it.
- Runtime capability enforcement — Phase 7's AI safety story.
- Contacts / CRM lite module code — Phase 5.
- Admin HTML module page — Phase 4.
- `parcel` CLI commands for install/upgrade/uninstall — Phase 6.
- Concurrent install safety (two admins installing simultaneously) — relies on DB-level unique constraints for now; advisory locks are overkill.
- Auto-upgrade on boot — migrations run only on explicit admin action.
