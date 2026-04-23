# Phase 5 — Contacts Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver two things in parallel — (1) extend `parcel-sdk` so modules can contribute a UI (`Module.router`, `Module.templates_dir`, `Module.sidebar_items`, plus a new `SidebarItem` SDK dataclass) and teach the shell to mount them on install and at boot; (2) ship the Contacts demo module (Contact + Company entities, roomy two-line list pages, form-first detail pages, `contacts.read` / `contacts.write` permissions) under `/mod/contacts/*`.

**Architecture:** SDK adds three optional fields to `Module` and a re-usable `SidebarItem` dataclass. Shell gains `parcel_shell/modules/integration.py` (mount/unmount, boot-time sync for active modules) and composes its static `SIDEBAR` with per-module contributions at render time. The contacts module is a normal workspace package at `modules/contacts/`, declares its own Alembic migrations, models, service, router, templates. Module template folder is prepended to the Jinja `FileSystemLoader` chain so `{% extends "_base.html" %}` resolves to the shell's base. No module-owned static assets yet (no `static_dir` field) — the module relies on shell CSS.

**Tech Stack:** Python 3.12 · parcel-sdk (extended) · SQLAlchemy 2.0 async · asyncpg · Alembic · FastAPI · Jinja2 · HTMX 2.x · pytest + testcontainers · asgi-lifespan · httpx.

**Reference spec:** `docs/superpowers/specs/2026-04-23-phase-5-contacts-module-design.md`

---

## File plan

**Create:**
- `packages/parcel-sdk/src/parcel_sdk/sidebar.py` — `SidebarItem` dataclass
- `packages/parcel-shell/src/parcel_shell/modules/integration.py` — mount/unmount/sync helpers
- `packages/parcel-shell/tests/test_sdk_sidebar.py`
- `packages/parcel-shell/tests/test_module_integration.py`
- `modules/contacts/src/parcel_mod_contacts/__init__.py`
- `modules/contacts/src/parcel_mod_contacts/models.py`
- `modules/contacts/src/parcel_mod_contacts/service.py`
- `modules/contacts/src/parcel_mod_contacts/sidebar.py`
- `modules/contacts/src/parcel_mod_contacts/router.py`
- `modules/contacts/src/parcel_mod_contacts/templates/contacts/list.html`
- `modules/contacts/src/parcel_mod_contacts/templates/contacts/list_rows.html`
- `modules/contacts/src/parcel_mod_contacts/templates/contacts/new.html`
- `modules/contacts/src/parcel_mod_contacts/templates/contacts/detail.html`
- `modules/contacts/src/parcel_mod_contacts/templates/companies/list.html`
- `modules/contacts/src/parcel_mod_contacts/templates/companies/list_rows.html`
- `modules/contacts/src/parcel_mod_contacts/templates/companies/new.html`
- `modules/contacts/src/parcel_mod_contacts/templates/companies/detail.html`
- `modules/contacts/src/parcel_mod_contacts/alembic.ini`
- `modules/contacts/src/parcel_mod_contacts/alembic/env.py`
- `modules/contacts/src/parcel_mod_contacts/alembic/script.py.mako`
- `modules/contacts/src/parcel_mod_contacts/alembic/versions/0001_create_contact_company.py`
- `modules/contacts/tests/conftest.py`
- `modules/contacts/tests/test_contacts_migrations.py`
- `modules/contacts/tests/test_contacts_service.py`
- `modules/contacts/tests/test_contacts_router.py`

**Modify:**
- `packages/parcel-sdk/src/parcel_sdk/module.py` — add `router`, `templates_dir`, `sidebar_items`
- `packages/parcel-sdk/src/parcel_sdk/__init__.py` — re-export `SidebarItem`
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` — import `SidebarItem` from SDK; expose `composed_sections(perms, module_sections)`
- `packages/parcel-shell/src/parcel_shell/ui/templates.py` — make the Jinja loader extensible (accept extra search dirs from `app.state`)
- `packages/parcel-shell/src/parcel_shell/modules/service.py` — call `integration.mount_module(app, discovered)` after a successful install; no unmount on uninstall (process restart required)
- `packages/parcel-shell/src/parcel_shell/app.py` — after `sync_on_boot`, load active modules via `integration.sync_active_modules(app, sessionmaker)`
- `packages/parcel-shell/src/parcel_shell/ui/routes/*.py` + `ui/routes/auth.py` + dashboard route — pass `module_sections` from `app.state.active_modules_sidebar` into the base template context (one helper, reused across routes)
- `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html` — render `module_sections` below `sidebar`
- `modules/contacts/pyproject.toml` — real package declaration + entry point + workspace dep on parcel-sdk + parcel-shell
- `CLAUDE.md` — Phase 5 ✅ / Phase 6 ⏭; note the SDK additions and module integration pattern
- `README.md` — add one line about the demo contacts module

---

## Task 1: Extend the SDK — `SidebarItem` + new `Module` fields

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/sidebar.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/module.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/__init__.py`
- Create: `packages/parcel-shell/tests/test_sdk_sidebar.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_sdk_sidebar.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter

from parcel_sdk import Module, Permission, SidebarItem


def test_sidebar_item_shape() -> None:
    s = SidebarItem(label="Contacts", href="/mod/contacts/", permission="contacts.read")
    assert s.label == "Contacts"
    assert s.href == "/mod/contacts/"
    assert s.permission == "contacts.read"


def test_sidebar_item_optional_permission() -> None:
    s = SidebarItem(label="Dashboard", href="/", permission=None)
    assert s.permission is None


def test_module_new_fields_default_to_none_and_empty() -> None:
    m = Module(name="foo", version="0.1.0")
    assert m.router is None
    assert m.templates_dir is None
    assert m.sidebar_items == ()


def test_module_accepts_router_templates_sidebar() -> None:
    r = APIRouter()
    m = Module(
        name="foo",
        version="0.1.0",
        permissions=(Permission("foo.read", "Read foo"),),
        router=r,
        templates_dir=Path("/tmp/foo/templates"),
        sidebar_items=(SidebarItem(label="Foo", href="/mod/foo/", permission="foo.read"),),
    )
    assert m.router is r
    assert m.templates_dir == Path("/tmp/foo/templates")
    assert m.sidebar_items[0].label == "Foo"


def test_module_is_still_frozen_after_adding_fields() -> None:
    m = Module(name="foo", version="0.1.0")
    with pytest.raises(Exception):  # noqa: B017
        m.name = "bar"  # type: ignore[misc]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_sdk_sidebar.py -v`
Expected: FAIL — `SidebarItem` not importable.

- [ ] **Step 3: Create `sidebar.py`**

Create `packages/parcel-sdk/src/parcel_sdk/sidebar.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarItem:
    label: str
    href: str
    permission: str | None = None
```

- [ ] **Step 4: Extend `Module`**

Open `packages/parcel-sdk/src/parcel_sdk/module.py` and replace the file with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter  # noqa: F401
    from sqlalchemy import MetaData  # noqa: F401

from parcel_sdk.sidebar import SidebarItem


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
    # Phase 5 additions — optional UI contribution:
    router: "Any | None" = None
    templates_dir: Path | None = None
    sidebar_items: tuple[SidebarItem, ...] = ()
```

(`router` is typed as `Any | None` rather than `APIRouter | None` to avoid forcing FastAPI as a runtime SDK dep; modules that use it import `APIRouter` themselves. `TYPE_CHECKING` import keeps the hint available for IDE/type checkers.)

- [ ] **Step 5: Re-export from `__init__.py`**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py`:

```python
"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 5 surface: Module, Permission, SidebarItem, run_async_migrations.
"""

from __future__ import annotations

from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.module import Module, Permission
from parcel_sdk.sidebar import SidebarItem

__all__ = ["Module", "Permission", "SidebarItem", "run_async_migrations", "__version__"]
__version__ = "0.2.0"
```

- [ ] **Step 6: Run the test**

Run: `uv run pytest packages/parcel-shell/tests/test_sdk_sidebar.py -v`
Expected: all 5 PASS.

- [ ] **Step 7: Ensure Phase 3 SDK tests still pass**

Run: `uv run pytest packages/parcel-sdk/tests/ -v`
Expected: all 5 Phase 3 SDK tests still PASS (Module defaults unchanged).

- [ ] **Step 8: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/ packages/parcel-shell/tests/test_sdk_sidebar.py
git commit -m "feat(sdk): add SidebarItem + Module.router/templates_dir/sidebar_items"
```

---

## Task 2: Shell — make Jinja template loader extensible

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ui/templates.py`

- [ ] **Step 1: Replace `templates.py`**

Replace `packages/parcel-shell/src/parcel_shell/ui/templates.py`:

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import jinja2
from fastapi.templating import Jinja2Templates

_SHELL_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Shell-only Jinja2Templates. Module templates are mounted dynamically via
    :func:`add_template_dir`, which mutates the underlying loader search path.
    """
    tpl = Jinja2Templates(directory=str(_SHELL_TEMPLATES_DIR))
    # Swap in a ChoiceLoader so we can prepend module template dirs at runtime.
    tpl.env.loader = jinja2.ChoiceLoader([jinja2.FileSystemLoader(str(_SHELL_TEMPLATES_DIR))])
    return tpl


def add_template_dir(directory: Path) -> None:
    """Prepend ``directory`` to the Jinja loader chain, if not already present.

    Idempotent — calling twice with the same path is a no-op.
    """
    tpl = get_templates()
    loader = tpl.env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    as_str = str(directory)
    # Skip if this FileSystemLoader is already in the chain.
    for existing in loader.loaders:
        if isinstance(existing, jinja2.FileSystemLoader) and as_str in existing.searchpath:
            return
    loader.loaders = [jinja2.FileSystemLoader(as_str), *loader.loaders]
```

- [ ] **Step 2: Verify import still works**

Run: `uv run python -c "from parcel_shell.ui.templates import get_templates, add_template_dir; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Run existing Phase 4 UI tests**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_auth.py packages/parcel-shell/tests/test_ui_layout.py -q`
Expected: all PASS (no regression).

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/templates.py
git commit -m "feat(shell/ui): make Jinja template loader extensible via add_template_dir()"
```

---

## Task 3: Shell — move `SidebarItem` to SDK, compose shell + module sections

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`

- [ ] **Step 1: Replace `sidebar.py`**

Replace `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import SidebarItem

# Re-export for internal callers that used ``from parcel_shell.ui.sidebar import SidebarItem``.
__all__ = ["SIDEBAR", "SidebarItem", "SidebarSection", "visible_sections", "composed_sections"]


@dataclass(frozen=True)
class SidebarSection:
    label: str
    items: tuple[SidebarItem, ...]


SIDEBAR: tuple[SidebarSection, ...] = (
    SidebarSection(
        label="Overview",
        items=(SidebarItem(label="Dashboard", href="/", permission=None),),
    ),
    SidebarSection(
        label="Access",
        items=(
            SidebarItem(label="Users", href="/users", permission="users.read"),
            SidebarItem(label="Roles", href="/roles", permission="roles.read"),
        ),
    ),
    SidebarSection(
        label="System",
        items=(SidebarItem(label="Modules", href="/modules", permission="modules.read"),),
    ),
)


def visible_sections(perms: set[str]) -> list[SidebarSection]:
    """Shell-only sections visible to the user. Phase 2/3/4 API preserved."""
    out: list[SidebarSection] = []
    for section in SIDEBAR:
        items = tuple(
            i for i in section.items if i.permission is None or i.permission in perms
        )
        if items:
            out.append(SidebarSection(label=section.label, items=items))
    return out


def composed_sections(
    perms: set[str],
    module_sections: dict[str, tuple[SidebarItem, ...]] | None = None,
) -> list[SidebarSection]:
    """Shell sections followed by one section per active module with visible items."""
    out = visible_sections(perms)
    if not module_sections:
        return out
    for name, items in sorted(module_sections.items()):
        visible = tuple(i for i in items if i.permission is None or i.permission in perms)
        if visible:
            out.append(SidebarSection(label=name.capitalize(), items=visible))
    return out
```

- [ ] **Step 2: Sanity check imports**

Run: `uv run python -c "from parcel_shell.ui.sidebar import SIDEBAR, visible_sections, composed_sections, SidebarItem; print(len(SIDEBAR), composed_sections(set()))"`
Expected: prints `3 [SidebarSection(label='Overview', items=(SidebarItem(label='Dashboard', href='/', permission=None),))]` (shell's static sidebar length 3, unauthed sees only Overview).

- [ ] **Step 3: Run Phase 4 tests that depend on sidebar**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_layout.py -v`
Expected: all PASS (existing API unchanged).

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/sidebar.py
git commit -m "feat(shell/ui): import SidebarItem from SDK; add composed_sections for modules"
```

---

## Task 4: Shell — module integration (mount / sync on boot)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/modules/integration.py`
- Modify: `packages/parcel-shell/src/parcel_shell/modules/service.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`
- Create: `packages/parcel-shell/tests/test_module_integration.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-shell/tests/test_module_integration.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

from parcel_sdk import Module, SidebarItem
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


def _app_with_state() -> FastAPI:
    app = FastAPI()
    app.state.active_modules = set()
    app.state.active_modules_sidebar = {}
    return app


def test_mount_module_adds_router_with_prefix(tmp_path: Path) -> None:
    router = APIRouter()

    @router.get("/")
    async def _root() -> dict:
        return {"hi": "from-module"}

    templates_dir = tmp_path / "tpl"
    templates_dir.mkdir()

    module = Module(
        name="demo",
        version="0.1.0",
        router=router,
        templates_dir=templates_dir,
        sidebar_items=(SidebarItem(label="Demo", href="/mod/demo/"),),
    )
    discovered = DiscoveredModule(
        module=module, distribution_name="demo", distribution_version="0.1.0"
    )

    app = _app_with_state()
    mount_module(app, discovered)

    # Router mounted at /mod/demo
    paths = [r.path for r in app.routes]
    assert any(p.startswith("/mod/demo") for p in paths)

    # Template dir registered
    from parcel_shell.ui.templates import get_templates
    import jinja2

    loader = get_templates().env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    search = []
    for sub in loader.loaders:
        if isinstance(sub, jinja2.FileSystemLoader):
            search.extend(sub.searchpath)
    assert str(templates_dir) in search

    # State updated
    assert "demo" in app.state.active_modules
    assert app.state.active_modules_sidebar["demo"] == (
        SidebarItem(label="Demo", href="/mod/demo/"),
    )


def test_mount_module_idempotent(tmp_path: Path) -> None:
    router = APIRouter()
    module = Module(name="demo2", version="0.1.0", router=router, templates_dir=tmp_path)
    discovered = DiscoveredModule(
        module=module, distribution_name="demo2", distribution_version="0.1.0"
    )
    app = _app_with_state()
    mount_module(app, discovered)
    before = len(app.routes)
    mount_module(app, discovered)  # second call: no duplicate routes
    assert len(app.routes) == before


def test_mount_module_no_router_is_noop(tmp_path: Path) -> None:
    module = Module(name="nohttp", version="0.1.0")
    discovered = DiscoveredModule(
        module=module, distribution_name="nohttp", distribution_version="0.1.0"
    )
    app = _app_with_state()
    mount_module(app, discovered)
    # Should still register in state (permissions etc. are Phase 3), but no routes.
    assert "nohttp" in app.state.active_modules
    assert app.state.active_modules_sidebar.get("nohttp", ()) == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_module_integration.py -v`
Expected: FAIL — `parcel_shell.modules.integration` not found.

- [ ] **Step 3: Create `integration.py`**

Create `packages/parcel-shell/src/parcel_shell/modules/integration.py`:

```python
from __future__ import annotations

import structlog
from fastapi import FastAPI

from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.ui.templates import add_template_dir

_log = structlog.get_logger("parcel_shell.modules.integration")


def _ensure_state(app: FastAPI) -> None:
    if not hasattr(app.state, "active_modules"):
        app.state.active_modules = set()
    if not hasattr(app.state, "active_modules_sidebar"):
        app.state.active_modules_sidebar = {}


def mount_module(app: FastAPI, discovered: DiscoveredModule) -> None:
    """Mount a module's router, templates, and sidebar onto the live app.

    Idempotent: calling twice with the same module is a no-op.
    """
    _ensure_state(app)
    name = discovered.module.name
    if name in app.state.active_modules:
        return

    if discovered.module.router is not None:
        app.include_router(discovered.module.router, prefix=f"/mod/{name}")
    if discovered.module.templates_dir is not None:
        add_template_dir(discovered.module.templates_dir)

    app.state.active_modules.add(name)
    app.state.active_modules_sidebar[name] = tuple(discovered.module.sidebar_items)
    _log.info("module.mounted", name=name)


async def sync_active_modules(app: FastAPI) -> None:
    """At lifespan startup, mount every active installed module.

    Assumes :func:`parcel_shell.modules.service.sync_on_boot` has already run,
    so orphans have been flipped to ``is_active=false``.
    """
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule
    from sqlalchemy import select

    _ensure_state(app)
    sessionmaker = app.state.sessionmaker
    discovered = {d.module.name: d for d in discover_modules()}
    async with sessionmaker() as s:
        rows = (
            await s.execute(select(InstalledModule).where(InstalledModule.is_active.is_(True)))
        ).scalars().all()
    for row in rows:
        d = discovered.get(row.name)
        if d is None:
            continue
        mount_module(app, d)
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest packages/parcel-shell/tests/test_module_integration.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Hook into service.install_module**

Edit `packages/parcel-shell/src/parcel_shell/modules/service.py`. At the very bottom of `install_module`, right before `return row`, add a call that mounts the module onto the running app. Since service functions currently don't receive an `app` reference, add an optional parameter:

Locate the `install_module` signature and replace the function. The final version:

```python
async def install_module(
    db: AsyncSession,
    *,
    name: str,
    approve_capabilities: list[str],
    discovered: dict[str, DiscoveredModule],
    database_url: str,
    app: "FastAPI | None" = None,
) -> InstalledModule:
    d = discovered.get(name)
    if d is None:
        raise ModuleNotDiscovered(name)
    if await db.get(InstalledModule, name) is not None:
        raise ModuleAlreadyInstalled(name)
    if set(approve_capabilities) != set(d.module.capabilities):
        raise CapabilityMismatch(
            f"declared={sorted(d.module.capabilities)!r} "
            f"approved={sorted(approve_capabilities)!r}"
        )

    from sqlalchemy import text as sa_text

    schema = f"mod_{name}"
    await db.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    if d.module.permissions:
        stmt = pg_insert(Permission).values(
            [
                {"name": p.name, "description": p.description, "module": name}
                for p in d.module.permissions
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Permission.name],
            set_={
                "description": stmt.excluded.description,
                "module": stmt.excluded.module,
            },
        )
        await db.execute(stmt)

    await db.flush()
    await db.commit()

    cfg = _alembic_config(database_url, d)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        _log.exception("module.install_migration_failed", name=name, error=str(exc))
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

    # Phase 5: mount the module onto the running app, if provided.
    if app is not None:
        from parcel_shell.modules.integration import mount_module

        mount_module(app, d)

    return row
```

Also add the `FastAPI` type annotation import at the top of the file, inside `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
```

Update the UI module router to pass `app`. Edit `packages/parcel-shell/src/parcel_shell/ui/routes/modules.py` in the install endpoint's service call (the existing `ui/routes/modules.py` — not to be confused with `modules/router_admin.py` which is the JSON API). Find the `await module_service.install_module(` call and add `app=request.app`:

```python
await module_service.install_module(
    db,
    name=payload.name,
    approve_capabilities=payload.approve_capabilities,
    discovered=index,
    database_url=database_url,
    app=request.app,
)
```

Do the same edit in `packages/parcel-shell/src/parcel_shell/modules/router_admin.py` (the JSON API):

```python
row = await service.install_module(
    db,
    name=payload.name,
    approve_capabilities=payload.approve_capabilities,
    discovered=index,
    database_url=database_url,
    app=request.app,
)
```

- [ ] **Step 6: Hook `sync_active_modules` into app.py lifespan**

Edit `packages/parcel-shell/src/parcel_shell/app.py`. Find the block after the existing `module_service.sync_on_boot` call and add:

```python
        from parcel_shell.modules.integration import sync_active_modules

        await sync_active_modules(app)
```

(So the lifespan order is: engine + sessionmaker set up → permission registry sync → module `sync_on_boot` (flip orphans inactive) → `sync_active_modules` (mount routers/templates/sidebar for the remaining active modules) → log startup.)

- [ ] **Step 7: Expose `active_modules_sidebar` to templates**

Every HTML route that renders a full page currently builds its context with `{"sidebar": visible_sections(perms), ...}`. We want `sidebar: composed_sections(perms, app.state.active_modules_sidebar)`.

Centralize this in a small helper. Edit `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` and append:

```python
def sidebar_for(request, perms: set[str]) -> list[SidebarSection]:
    """Convenience: compose the sidebar using the live app state."""
    module_sections = getattr(request.app.state, "active_modules_sidebar", None)
    return composed_sections(perms, module_sections)
```

Then update each HTML route that uses `visible_sections(perms)` to use `sidebar_for(request, perms)` instead. Files to change:

- `packages/parcel-shell/src/parcel_shell/ui/routes/auth.py` — in `profile_page` and `profile_change_password` error paths
- `packages/parcel-shell/src/parcel_shell/ui/routes/dashboard.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/users.py` — in `_ctx`
- `packages/parcel-shell/src/parcel_shell/ui/routes/roles.py` — in `_ctx`
- `packages/parcel-shell/src/parcel_shell/ui/routes/modules.py` — in `_ctx`

Exact changes: replace `visible_sections(perms)` with `sidebar_for(request, perms)` and update the `from` import accordingly (`from parcel_shell.ui.sidebar import sidebar_for`).

- [ ] **Step 8: Run regression suite**

Run: `uv run pytest packages/parcel-shell/tests/`
Expected: all PASS (including the new `test_module_integration.py`).

- [ ] **Step 9: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ packages/parcel-shell/tests/test_module_integration.py
git commit -m "feat(shell): mount module routers/templates/sidebar at install + lifespan"
```

---

## Task 5: Contacts module — `pyproject.toml`

**Files:**
- Modify: `modules/contacts/pyproject.toml`

- [ ] **Step 1: Replace `pyproject.toml`**

Replace `modules/contacts/pyproject.toml`:

```toml
[project]
name = "parcel-mod-contacts"
version = "0.1.0"
description = "Parcel demo module — Contacts / CRM lite"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
    "parcel-sdk",
    # Phase 5 pragmatic concession: Contacts module imports shell hooks
    # (get_session, html_require_permission, sidebar_for, etc.) directly from
    # parcel-shell. Phase 6 ("SDK polish") extracts a stable SDK facade so
    # modules no longer depend on parcel-shell internals.
    "parcel-shell",
    "fastapi>=0.115",
]

[project.entry-points."parcel.modules"]
contacts = "parcel_mod_contacts:module"

[tool.uv.sources]
parcel-sdk = { workspace = true }
parcel-shell = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parcel_mod_contacts"]
```

- [ ] **Step 2: Sync workspace**

Run: `uv sync --all-packages`
Expected: `parcel-mod-contacts` appears in the installed set; entry-point becomes discoverable next time shell starts.

- [ ] **Step 3: Commit**

```bash
git add modules/contacts/pyproject.toml uv.lock
git commit -m "chore(mod-contacts): turn scaffold into a real workspace package"
```

---

## Task 6: Contacts module — models + alembic scaffolding

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/__init__.py` (empty at first — updated in Task 10)
- Create: `modules/contacts/src/parcel_mod_contacts/models.py`
- Create: `modules/contacts/src/parcel_mod_contacts/alembic.ini`
- Create: `modules/contacts/src/parcel_mod_contacts/alembic/env.py`
- Create: `modules/contacts/src/parcel_mod_contacts/alembic/script.py.mako`
- Create: `modules/contacts/src/parcel_mod_contacts/alembic/versions/0001_create_contact_company.py`

- [ ] **Step 1: Create empty `__init__.py`**

Create `modules/contacts/src/parcel_mod_contacts/__init__.py` with no content.

- [ ] **Step 2: Create `models.py`**

Create `modules/contacts/src/parcel_mod_contacts/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, MetaData, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

metadata = MetaData(schema="mod_contacts")


class ContactsBase(DeclarativeBase):
    metadata = metadata  # type: ignore[assignment]


def _uuid4() -> uuid.UUID:
    return uuid.uuid4()


class Company(ContactsBase):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Contact(ContactsBase):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mod_contacts.companies.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped[Company | None] = relationship(lazy="selectin")
```

- [ ] **Step 3: Create `alembic.ini`**

Create `modules/contacts/src/parcel_mod_contacts/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os
path_separator = os
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

- [ ] **Step 4: Create `alembic/env.py`**

Create `modules/contacts/src/parcel_mod_contacts/alembic/env.py`:

```python
from parcel_mod_contacts import module
from parcel_sdk.alembic_env import run_async_migrations

run_async_migrations(module)
```

- [ ] **Step 5: Create `script.py.mako`**

Create `modules/contacts/src/parcel_mod_contacts/alembic/script.py.mako`:

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

- [ ] **Step 6: Create the first migration**

Create `modules/contacts/src/parcel_mod_contacts/alembic/versions/0001_create_contact_company.py`:

```python
"""create contact and company tables

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("website", sa.Text()),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="mod_contacts",
    )

    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("first_name", sa.Text()),
        sa.Column("last_name", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mod_contacts.companies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="mod_contacts",
    )
    op.create_index("ix_contacts_email", "contacts", ["email"], schema="mod_contacts")
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"], schema="mod_contacts")


def downgrade() -> None:
    op.drop_index("ix_contacts_company_id", table_name="contacts", schema="mod_contacts")
    op.drop_index("ix_contacts_email", table_name="contacts", schema="mod_contacts")
    op.drop_table("contacts", schema="mod_contacts")
    op.drop_table("companies", schema="mod_contacts")
```

- [ ] **Step 7: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/
git commit -m "feat(mod-contacts): models + alembic scaffolding + initial migration"
```

---

## Task 7: Contacts module — service layer

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/service.py`

- [ ] **Step 1: Implement `service.py`**

Create `modules/contacts/src/parcel_mod_contacts/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.models import Company, Contact


# ── Contacts ────────────────────────────────────────────────────────────


async def list_contacts(
    db: AsyncSession, *, q: str | None = None, offset: int = 0, limit: int = 50
) -> tuple[list[Contact], int]:
    stmt = select(Contact)
    if q:
        pat = f"%{q}%"
        stmt = stmt.where(
            or_(
                Contact.email.ilike(pat),
                Contact.first_name.ilike(pat),
                Contact.last_name.ilike(pat),
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(stmt.order_by(Contact.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def get_contact(db: AsyncSession, contact_id: uuid.UUID) -> Contact | None:
    return await db.get(Contact, contact_id)


async def create_contact(
    db: AsyncSession,
    *,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_id: uuid.UUID | None = None,
) -> Contact:
    c = Contact(
        email=email.lower().strip(),
        first_name=first_name or None,
        last_name=last_name or None,
        phone=phone or None,
        company_id=company_id,
    )
    db.add(c)
    await db.flush()
    return c


async def update_contact(
    db: AsyncSession,
    *,
    contact: Contact,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_id: uuid.UUID | None = None,
    clear_company: bool = False,
) -> Contact:
    if email is not None:
        contact.email = email.lower().strip()
    if first_name is not None:
        contact.first_name = first_name or None
    if last_name is not None:
        contact.last_name = last_name or None
    if phone is not None:
        contact.phone = phone or None
    if clear_company:
        contact.company_id = None
    elif company_id is not None:
        contact.company_id = company_id
    contact.updated_at = datetime.now(UTC)
    await db.flush()
    return contact


async def delete_contact(db: AsyncSession, *, contact: Contact) -> None:
    await db.delete(contact)
    await db.flush()


# ── Companies ──────────────────────────────────────────────────────────


async def list_companies(
    db: AsyncSession, *, q: str | None = None, offset: int = 0, limit: int = 50
) -> tuple[list[Company], int]:
    stmt = select(Company)
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(stmt.order_by(Company.name).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def get_company(db: AsyncSession, company_id: uuid.UUID) -> Company | None:
    return await db.get(Company, company_id)


async def create_company(
    db: AsyncSession, *, name: str, website: str | None = None
) -> Company:
    c = Company(name=name.strip(), website=(website or None))
    db.add(c)
    await db.flush()
    return c


async def update_company(
    db: AsyncSession,
    *,
    company: Company,
    name: str | None = None,
    website: str | None = None,
) -> Company:
    if name is not None:
        company.name = name.strip()
    if website is not None:
        company.website = website or None
    company.updated_at = datetime.now(UTC)
    await db.flush()
    return company


async def delete_company(db: AsyncSession, *, company: Company) -> None:
    await db.delete(company)
    await db.flush()
```

- [ ] **Step 2: Sanity check import**

Run: `uv run python -c "from parcel_mod_contacts import service, models; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/service.py
git commit -m "feat(mod-contacts): service layer — CRUD + search for contacts and companies"
```

---

## Task 8: Contacts module — templates

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/templates/contacts/list.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/contacts/list_rows.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/contacts/new.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/contacts/detail.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/companies/list.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/companies/list_rows.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/companies/new.html`
- Create: `modules/contacts/src/parcel_mod_contacts/templates/companies/detail.html`

- [ ] **Step 1: Create `contacts/list.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/contacts/list.html`:

```html
{% extends "_base.html" %}
{% block title %}Contacts{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">Contacts</h2>
  <a class="btn primary" href="/mod/contacts/new">+ New contact</a>
</div>

<input class="input" type="search" name="q" placeholder="Search by name or email…"
       value="{{ q or '' }}"
       hx-get="/mod/contacts/"
       hx-trigger="keyup changed delay:300ms, search"
       hx-target="#contacts-rows"
       hx-select="#contacts-rows > *"
       hx-swap="innerHTML"
       style="max-width: 360px; margin-bottom: 12px;">

<div class="surface" id="contacts-rows" style="border-radius: 6px;">
  {% include "contacts/list_rows.html" %}
</div>
{% endblock %}
```

- [ ] **Step 2: Create `contacts/list_rows.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/contacts/list_rows.html`:

```html
{% for c in contacts %}
<a href="/mod/contacts/{{ c.id }}" style="display:grid; grid-template-columns: 1fr auto; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); text-decoration: none; color: var(--text);">
  <div>
    <div style="font-weight: 600;">{% if c.first_name or c.last_name %}{{ c.first_name or '' }} {{ c.last_name or '' }}{% else %}{{ c.email }}{% endif %}</div>
    <div class="muted" style="font-size: 12px;">{{ c.email }}</div>
  </div>
  <div class="muted" style="font-size: 12px; text-align: right; align-self: center;">
    {% if c.company %}{{ c.company.name }}{% else %}—{% endif %}
  </div>
</a>
{% else %}
<div class="muted" style="padding: 24px; text-align: center;">No contacts match.</div>
{% endfor %}
```

- [ ] **Step 3: Create `contacts/new.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/contacts/new.html`:

```html
{% extends "_base.html" %}
{% block title %}New contact{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">New contact</h2>
<div class="surface" style="padding: 20px; max-width: 560px; border-radius: 6px;">
  {% if error %}<div class="alert error" style="margin: 0 0 12px;">{{ error }}</div>{% endif %}
  <form method="post" action="/mod/contacts/">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px;">
      <div>
        <label style="display:block; font-size: 13px; margin: 0 0 4px;">First name</label>
        <input class="input" type="text" name="first_name" value="{{ first_name or '' }}">
      </div>
      <div>
        <label style="display:block; font-size: 13px; margin: 0 0 4px;">Last name</label>
        <input class="input" type="text" name="last_name" value="{{ last_name or '' }}">
      </div>
      <div style="grid-column: 1 / span 2;">
        <label style="display:block; font-size: 13px; margin: 0 0 4px;">Email</label>
        <input class="input" type="email" name="email" required value="{{ email or '' }}">
      </div>
      <div>
        <label style="display:block; font-size: 13px; margin: 0 0 4px;">Phone</label>
        <input class="input" type="text" name="phone" value="{{ phone or '' }}">
      </div>
      <div>
        <label style="display:block; font-size: 13px; margin: 0 0 4px;">Company</label>
        <select class="input" name="company_id">
          <option value="">—</option>
          {% for co in companies %}
          <option value="{{ co.id }}">{{ co.name }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <div style="margin-top: 16px;">
      <button class="btn primary" type="submit">Create</button>
      <a class="btn" href="/mod/contacts/" style="margin-left: 8px;">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 4: Create `contacts/detail.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/contacts/detail.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ contact.email }}{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">{% if contact.first_name or contact.last_name %}{{ contact.first_name or '' }} {{ contact.last_name or '' }}{% else %}{{ contact.email }}{% endif %}</h2>
  <a href="/mod/contacts/" class="btn">← All contacts</a>
</div>

<form class="surface" method="post" action="/mod/contacts/{{ contact.id }}/edit" style="padding: 20px; max-width: 640px; border-radius: 6px;">
  <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px;">
    <div>
      <label style="display:block; font-size: 13px; margin: 0 0 4px;">First name</label>
      <input class="input" type="text" name="first_name" value="{{ contact.first_name or '' }}">
    </div>
    <div>
      <label style="display:block; font-size: 13px; margin: 0 0 4px;">Last name</label>
      <input class="input" type="text" name="last_name" value="{{ contact.last_name or '' }}">
    </div>
    <div style="grid-column: 1 / span 2;">
      <label style="display:block; font-size: 13px; margin: 0 0 4px;">Email</label>
      <input class="input" type="email" name="email" required value="{{ contact.email }}">
    </div>
    <div>
      <label style="display:block; font-size: 13px; margin: 0 0 4px;">Phone</label>
      <input class="input" type="text" name="phone" value="{{ contact.phone or '' }}">
    </div>
    <div>
      <label style="display:block; font-size: 13px; margin: 0 0 4px;">Company</label>
      <select class="input" name="company_id">
        <option value="">—</option>
        {% for co in companies %}
        <option value="{{ co.id }}" {% if contact.company_id == co.id %}selected{% endif %}>{{ co.name }}</option>
        {% endfor %}
      </select>
    </div>
  </div>
  <div style="margin-top: 16px;">
    <button class="btn primary" type="submit">Save</button>
    <button class="btn danger" type="submit" formaction="/mod/contacts/{{ contact.id }}/delete" style="margin-left: 8px;" onclick="return confirm('Delete this contact?')">Delete</button>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 5: Create `companies/list.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/companies/list.html`:

```html
{% extends "_base.html" %}
{% block title %}Companies{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">Companies</h2>
  <a class="btn primary" href="/mod/contacts/companies/new">+ New company</a>
</div>

<input class="input" type="search" name="q" placeholder="Search companies…"
       value="{{ q or '' }}"
       hx-get="/mod/contacts/companies"
       hx-trigger="keyup changed delay:300ms, search"
       hx-target="#companies-rows"
       hx-select="#companies-rows > *"
       hx-swap="innerHTML"
       style="max-width: 360px; margin-bottom: 12px;">

<div class="surface" id="companies-rows" style="border-radius: 6px;">
  {% include "companies/list_rows.html" %}
</div>
{% endblock %}
```

- [ ] **Step 6: Create `companies/list_rows.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/companies/list_rows.html`:

```html
{% for co in companies %}
<a href="/mod/contacts/companies/{{ co.id }}" style="display:grid; grid-template-columns: 1fr auto; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); text-decoration: none; color: var(--text);">
  <div>
    <div style="font-weight: 600;">{{ co.name }}</div>
    <div class="muted" style="font-size: 12px;">{{ co.website or '' }}</div>
  </div>
</a>
{% else %}
<div class="muted" style="padding: 24px; text-align: center;">No companies.</div>
{% endfor %}
```

- [ ] **Step 7: Create `companies/new.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/companies/new.html`:

```html
{% extends "_base.html" %}
{% block title %}New company{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">New company</h2>
<div class="surface" style="padding: 20px; max-width: 520px; border-radius: 6px;">
  {% if error %}<div class="alert error" style="margin: 0 0 12px;">{{ error }}</div>{% endif %}
  <form method="post" action="/mod/contacts/companies">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Name</label>
    <input class="input" type="text" name="name" required value="{{ name or '' }}" style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Website</label>
    <input class="input" type="url" name="website" value="{{ website or '' }}" style="margin-bottom: 16px;">
    <button class="btn primary" type="submit">Create company</button>
    <a class="btn" href="/mod/contacts/companies" style="margin-left: 8px;">Cancel</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 8: Create `companies/detail.html`**

Create `modules/contacts/src/parcel_mod_contacts/templates/companies/detail.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ company.name }}{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">{{ company.name }}</h2>
  <a href="/mod/contacts/companies" class="btn">← All companies</a>
</div>
<form class="surface" method="post" action="/mod/contacts/companies/{{ company.id }}/edit" style="padding: 20px; max-width: 520px; border-radius: 6px;">
  <label style="display:block; font-size: 13px; margin: 0 0 4px;">Name</label>
  <input class="input" type="text" name="name" required value="{{ company.name }}" style="margin-bottom: 12px;">
  <label style="display:block; font-size: 13px; margin: 0 0 4px;">Website</label>
  <input class="input" type="url" name="website" value="{{ company.website or '' }}" style="margin-bottom: 16px;">
  <button class="btn primary" type="submit">Save</button>
  <button class="btn danger" type="submit" formaction="/mod/contacts/companies/{{ company.id }}/delete" style="margin-left: 8px;" onclick="return confirm('Delete this company? Contacts linked to it will be kept but unlinked.')">Delete</button>
</form>
{% endblock %}
```

- [ ] **Step 9: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/templates/
git commit -m "feat(mod-contacts): Jinja templates for contact+company list/new/detail"
```

---

## Task 9: Contacts module — sidebar + router

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/sidebar.py`
- Create: `modules/contacts/src/parcel_mod_contacts/router.py`

- [ ] **Step 1: Create `sidebar.py`**

Create `modules/contacts/src/parcel_mod_contacts/sidebar.py`:

```python
from __future__ import annotations

from parcel_sdk import SidebarItem

SIDEBAR_ITEMS = (
    SidebarItem(label="Contacts", href="/mod/contacts/", permission="contacts.read"),
    SidebarItem(label="Companies", href="/mod/contacts/companies", permission="contacts.read"),
)
```

- [ ] **Step 2: Create `router.py`**

Create `modules/contacts/src/parcel_mod_contacts/router.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_mod_contacts import service
from parcel_shell.db import get_session
from parcel_shell.rbac import service as rbac_service
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["mod-contacts"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await rbac_service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": sidebar_for(request, perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


# ── Contacts ────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def contacts_list(
    request: Request,
    q: str | None = None,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contacts, _ = await service.list_contacts(db, q=q)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "contacts/list.html",
        {**(await _ctx(request, user, db, "/mod/contacts")), "contacts": contacts, "q": q},
    )


@router.get("/new", response_class=HTMLResponse)
async def contacts_new_form(
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    companies, _ = await service.list_companies(db, limit=500)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "contacts/new.html",
        {**(await _ctx(request, user, db, "/mod/contacts")), "companies": companies},
    )


@router.post("/")
async def contacts_create(
    request: Request,
    email: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    phone: str = Form(""),
    company_id: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    cid = uuid.UUID(company_id) if company_id else None
    try:
        new = await service.create_contact(
            db,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            company_id=cid,
        )
    except Exception as e:  # noqa: BLE001
        companies, _ = await service.list_companies(db, limit=500)
        tpl = get_templates()
        return tpl.TemplateResponse(
            request, "contacts/new.html",
            {
                **(await _ctx(request, user, db, "/mod/contacts")),
                "companies": companies,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url=f"/mod/contacts/{new.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created {new.email}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/{contact_id}", response_class=HTMLResponse)
async def contacts_detail(
    contact_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    companies, _ = await service.list_companies(db, limit=500)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "contacts/detail.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts")),
            "contact": contact,
            "companies": companies,
        },
    )


@router.post("/{contact_id}/edit")
async def contacts_edit(
    contact_id: uuid.UUID,
    request: Request,
    email: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    phone: str = Form(""),
    company_id: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    if company_id:
        await service.update_contact(
            db,
            contact=contact,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            company_id=uuid.UUID(company_id),
        )
    else:
        await service.update_contact(
            db,
            contact=contact,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            clear_company=True,
        )
    response = RedirectResponse(url=f"/mod/contacts/{contact_id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Contact saved."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/{contact_id}/delete")
async def contacts_delete(
    contact_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    await service.delete_contact(db, contact=contact)
    response = RedirectResponse(url="/mod/contacts/", status_code=303)
    set_flash(
        response,
        Flash(kind="info", msg="Contact deleted."),
        secret=request.app.state.settings.session_secret,
    )
    return response


# ── Companies ──────────────────────────────────────────────────────────


@router.get("/companies", response_class=HTMLResponse)
async def companies_list(
    request: Request,
    q: str | None = None,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    companies, _ = await service.list_companies(db, q=q)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "companies/list.html",
        {**(await _ctx(request, user, db, "/mod/contacts/companies")), "companies": companies, "q": q},
    )


@router.get("/companies/new", response_class=HTMLResponse)
async def companies_new_form(
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "companies/new.html",
        await _ctx(request, user, db, "/mod/contacts/companies"),
    )


@router.post("/companies")
async def companies_create(
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        new = await service.create_company(db, name=name, website=website)
    except Exception as e:  # noqa: BLE001
        tpl = get_templates()
        return tpl.TemplateResponse(
            request, "companies/new.html",
            {
                **(await _ctx(request, user, db, "/mod/contacts/companies")),
                "name": name,
                "website": website,
                "error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url=f"/mod/contacts/companies/{new.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created {new.name}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def companies_detail(
    company_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "companies/detail.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts/companies")),
            "company": company,
        },
    )


@router.post("/companies/{company_id}/edit")
async def companies_edit(
    company_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    await service.update_company(db, company=company, name=name, website=website)
    response = RedirectResponse(url=f"/mod/contacts/companies/{company_id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Company saved."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/companies/{company_id}/delete")
async def companies_delete(
    company_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    await service.delete_company(db, company=company)
    response = RedirectResponse(url="/mod/contacts/companies", status_code=303)
    set_flash(
        response,
        Flash(kind="info", msg="Company deleted."),
        secret=request.app.state.settings.session_secret,
    )
    return response
```

- [ ] **Step 3: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/sidebar.py modules/contacts/src/parcel_mod_contacts/router.py
git commit -m "feat(mod-contacts): router with HTML + HTMX search; sidebar declaration"
```

---

## Task 10: Contacts module — the `Module` object

**Files:**
- Modify: `modules/contacts/src/parcel_mod_contacts/__init__.py`

- [ ] **Step 1: Populate `__init__.py`**

Replace `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
from __future__ import annotations

from pathlib import Path

from parcel_sdk import Module, Permission

from parcel_mod_contacts.models import metadata
from parcel_mod_contacts.router import router
from parcel_mod_contacts.sidebar import SIDEBAR_ITEMS

module = Module(
    name="contacts",
    version="0.1.0",
    permissions=(
        Permission("contacts.read", "View contacts and companies"),
        Permission("contacts.write", "Create, update, and delete contacts and companies"),
    ),
    capabilities=(),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=SIDEBAR_ITEMS,
)

__all__ = ["module"]
```

- [ ] **Step 2: Sanity check**

Run: `uv run python -c "from parcel_mod_contacts import module; print(module.name, module.version, [p.name for p in module.permissions], [i.href for i in module.sidebar_items])"`
Expected: `contacts 0.1.0 ['contacts.read', 'contacts.write'] ['/mod/contacts/', '/mod/contacts/companies']`

- [ ] **Step 3: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/__init__.py
git commit -m "feat(mod-contacts): Module definition wiring up everything"
```

---

## Task 11: Contacts module — tests (migrations + service)

**Files:**
- Create: `modules/contacts/tests/conftest.py`
- Create: `modules/contacts/tests/test_contacts_migrations.py`
- Create: `modules/contacts/tests/test_contacts_service.py`

- [ ] **Step 1: Create `conftest.py`**

Create `modules/contacts/tests/conftest.py`:

```python
"""Tests for parcel-mod-contacts reuse the shell's testcontainers fixtures."""
from __future__ import annotations

# The shell's conftest.py at packages/parcel-shell/tests/conftest.py defines
# postgres_container, database_url, migrations_applied, committing_client,
# committing_admin, patch_entry_points, etc. pytest auto-discovers it when
# running from the workspace root.
```

(This file exists mostly as a signpost; pytest uses the root conftest already. No fixtures needed here.)

- [ ] **Step 2: Create `test_contacts_migrations.py`**

Create `modules/contacts/tests/test_contacts_migrations.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = (
    Path(__file__).resolve().parents[1] / "src" / "parcel_mod_contacts" / "alembic.ini"
)


def _cfg(url: str) -> Config:
    c = Config(str(ALEMBIC_INI))
    c.set_main_option("sqlalchemy.url", url)
    return c


async def test_upgrade_creates_mod_contacts_schema(
    database_url: str, engine: AsyncEngine
) -> None:
    # Clean up any prior run of this schema.
    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()

    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'mod_contacts' ORDER BY table_name"
                )
            )
        ).all()
    names = {r[0] for r in tables}
    assert names == {"alembic_version", "companies", "contacts"}

    # Cleanup so later tests don't inherit the schema.
    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()


async def test_downgrade_removes_tables(
    database_url: str, engine: AsyncEngine
) -> None:
    cfg = _cfg(database_url)
    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()

    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.downgrade, cfg, "base")

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'mod_contacts'"
                )
            )
        ).all()
    # After downgrade to base the tables are gone; only alembic_version may remain
    # (it's managed by alembic itself, and drops empty on full downgrade).
    assert "contacts" not in {r[0] for r in tables}
    assert "companies" not in {r[0] for r in tables}

    async with engine.connect() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await conn.commit()
```

- [ ] **Step 3: Create `test_contacts_service.py`**

Create `modules/contacts/tests/test_contacts_service.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from parcel_mod_contacts import service
from parcel_mod_contacts.models import Company, Contact


@pytest.fixture
async def contacts_session(migrations_applied: str) -> AsyncIterator[AsyncSession]:
    """Real committing session with mod_contacts schema migrated."""
    from alembic import command
    from alembic.config import Config
    import asyncio
    from pathlib import Path

    ini = (
        Path(__file__).resolve().parents[1] / "src" / "parcel_mod_contacts" / "alembic.ini"
    )
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", migrations_applied)

    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await conn.commit()
        await asyncio.to_thread(command.upgrade, cfg, "head")

        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            yield s
    finally:
        async with engine.connect() as conn:
            await conn.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await conn.commit()
        await engine.dispose()


async def test_create_and_get_contact(contacts_session: AsyncSession) -> None:
    c = await service.create_contact(contacts_session, email="Ada@Example.com", first_name="Ada")
    await contacts_session.commit()
    assert c.email == "ada@example.com"
    got = await service.get_contact(contacts_session, c.id)
    assert got is not None and got.email == "ada@example.com"


async def test_list_contacts_search(contacts_session: AsyncSession) -> None:
    await service.create_contact(contacts_session, email="a@x.com", first_name="Ada")
    await service.create_contact(contacts_session, email="b@x.com", first_name="Bob")
    await contacts_session.commit()
    rows, total = await service.list_contacts(contacts_session, q="ada")
    assert len(rows) == 1 and rows[0].first_name == "Ada"
    assert total == 1


async def test_create_and_link_company(contacts_session: AsyncSession) -> None:
    co = await service.create_company(contacts_session, name="Analytical Co.")
    await contacts_session.commit()
    c = await service.create_contact(
        contacts_session, email="ada@x.com", first_name="Ada", company_id=co.id
    )
    await contacts_session.commit()
    got = await service.get_contact(contacts_session, c.id)
    assert got.company_id == co.id


async def test_company_delete_sets_contact_company_null(
    contacts_session: AsyncSession,
) -> None:
    co = await service.create_company(contacts_session, name="Doomed Inc.")
    c = await service.create_contact(
        contacts_session, email="x@x.com", company_id=co.id
    )
    await contacts_session.commit()

    await service.delete_company(contacts_session, company=co)
    await contacts_session.commit()

    refreshed = await service.get_contact(contacts_session, c.id)
    assert refreshed is not None
    assert refreshed.company_id is None


async def test_update_contact_clears_company_on_request(contacts_session: AsyncSession) -> None:
    co = await service.create_company(contacts_session, name="Temporary")
    c = await service.create_contact(contacts_session, email="y@x.com", company_id=co.id)
    await contacts_session.commit()

    await service.update_contact(contacts_session, contact=c, clear_company=True)
    await contacts_session.commit()
    got = await service.get_contact(contacts_session, c.id)
    assert got is not None and got.company_id is None
```

- [ ] **Step 4: Run**

Run: `uv run pytest modules/contacts/tests/test_contacts_migrations.py modules/contacts/tests/test_contacts_service.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/contacts/tests/conftest.py modules/contacts/tests/test_contacts_migrations.py modules/contacts/tests/test_contacts_service.py
git commit -m "test(mod-contacts): migrations + service CRUD + search + FK-set-null on company delete"
```

---

## Task 12: Contacts module — router tests

**Files:**
- Create: `modules/contacts/tests/test_contacts_router.py`

- [ ] **Step 1: Create the test**

Create `modules/contacts/tests/test_contacts_router.py`:

```python
"""End-to-end tests for the contacts module through the shell.

Each test installs the contacts module at the start of the session, runs
against the real app via ``committing_admin``, and hard-uninstalls at the
end. Because the shell's ``committing_app`` fixture creates a fresh FastAPI
instance per test function, we re-mount the module for each test.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
async def _contacts_installed(settings) -> AsyncIterator[None]:
    """Install the contacts module via the module service, then clean up after."""
    from parcel_mod_contacts import module as contacts_module
    from parcel_shell.modules import service as module_service
    from parcel_shell.modules.discovery import DiscoveredModule

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    index = {
        "contacts": DiscoveredModule(
            module=contacts_module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        )
    }

    # Wipe any previous state.
    async with factory() as s:
        await s.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await s.execute(text("DELETE FROM shell.installed_modules WHERE name = 'contacts'"))
        await s.execute(text("DELETE FROM shell.permissions WHERE module = 'contacts'"))
        await s.commit()

    # Install fresh.
    async with factory() as s:
        await module_service.install_module(
            s,
            name="contacts",
            approve_capabilities=[],
            discovered=index,
            database_url=settings.database_url,
        )
        await s.commit()

    try:
        yield
    finally:
        async with factory() as s:
            try:
                await module_service.uninstall_module(
                    s,
                    name="contacts",
                    drop_data=True,
                    discovered=index,
                    database_url=settings.database_url,
                )
                await s.commit()
            except Exception:
                await s.rollback()
            # Defensive cleanup.
            await s.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await s.execute(text("DELETE FROM shell.installed_modules WHERE name = 'contacts'"))
            await s.execute(text("DELETE FROM shell.permissions WHERE module = 'contacts'"))
            await s.commit()
        await engine.dispose()


@pytest.fixture
async def authed_contacts(committing_client: AsyncClient, settings) -> AsyncClient:
    """Override of committing_admin that mounts the contacts module onto the live app.

    ``_contacts_installed`` puts rows in the DB but the per-test FastAPI app
    hasn't mounted the module yet; do that here.
    """
    import uuid
    from sqlalchemy import select

    from parcel_mod_contacts import module as contacts_module
    from parcel_shell.bootstrap import create_admin_user
    from parcel_shell.modules.discovery import DiscoveredModule
    from parcel_shell.modules.integration import mount_module
    from parcel_shell.rbac.models import User

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    email = f"admin-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234-long"
    async with factory() as s:
        await create_admin_user(s, email=email, password=password, force=False)
        await s.commit()

    # Mount the module onto the underlying app (committing_client wraps a transport
    # whose ASGI app is our FastAPI instance).
    app = committing_client._transport.app  # type: ignore[attr-defined]
    discovered = DiscoveredModule(
        module=contacts_module,
        distribution_name="parcel-mod-contacts",
        distribution_version="0.1.0",
    )
    mount_module(app, discovered)

    r = await committing_client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    try:
        yield committing_client
    finally:
        async with factory() as s:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_contacts_list_renders(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.get("/mod/contacts/")
    assert r.status_code == 200, r.text
    assert "Contacts" in r.text
    assert "Search by name or email" in r.text


async def test_create_contact_redirects_to_detail(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "ada@example.com", "first_name": "Ada", "last_name": "Lovelace"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"].startswith("/mod/contacts/")
    detail = await authed_contacts.get(r.headers["location"])
    assert "Ada" in detail.text
    assert "ada@example.com" in detail.text


async def test_edit_contact(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "grace@example.com", "first_name": "Grace"},
        follow_redirects=False,
    )
    contact_url = r.headers["location"]
    contact_id = contact_url.rsplit("/", 1)[1]
    r2 = await authed_contacts.post(
        f"/mod/contacts/{contact_id}/edit",
        data={
            "email": "grace.hopper@example.com",
            "first_name": "Grace",
            "last_name": "Hopper",
            "phone": "+1 555 0100",
            "company_id": "",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    detail = await authed_contacts.get(contact_url)
    assert "grace.hopper@example.com" in detail.text
    assert "Hopper" in detail.text


async def test_delete_contact_redirects_to_list(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "doomed@example.com"},
        follow_redirects=False,
    )
    contact_id = r.headers["location"].rsplit("/", 1)[1]
    r2 = await authed_contacts.post(
        f"/mod/contacts/{contact_id}/delete", follow_redirects=False
    )
    assert r2.status_code == 303
    assert r2.headers["location"] == "/mod/contacts/"


async def test_search_filters_list(authed_contacts: AsyncClient) -> None:
    await authed_contacts.post("/mod/contacts/", data={"email": "alan@example.com", "first_name": "Alan"})
    await authed_contacts.post("/mod/contacts/", data={"email": "ada@example.com", "first_name": "Ada"})
    r = await authed_contacts.get("/mod/contacts/?q=ada")
    assert r.status_code == 200
    assert "ada@example.com" in r.text
    assert "alan@example.com" not in r.text


async def test_company_create_link_and_delete_nulls_company(
    authed_contacts: AsyncClient,
) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/companies",
        data={"name": "Analytical Co."},
        follow_redirects=False,
    )
    company_id = r.headers["location"].rsplit("/", 1)[1]

    r2 = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "ada@x.com", "company_id": company_id},
        follow_redirects=False,
    )
    contact_id = r2.headers["location"].rsplit("/", 1)[1]

    # Delete company.
    r3 = await authed_contacts.post(
        f"/mod/contacts/companies/{company_id}/delete", follow_redirects=False
    )
    assert r3.status_code == 303

    detail = await authed_contacts.get(f"/mod/contacts/{contact_id}")
    # Company dropdown shows "—" selected by default now.
    assert "Analytical Co." not in detail.text.split('<h2')[0]  # gone from sidebar/header
```

- [ ] **Step 2: Run**

Run: `uv run pytest modules/contacts/tests/test_contacts_router.py -v`
Expected: all 6 PASS.

- [ ] **Step 3: Run the full suite to check for regressions**

Run: `uv run pytest`
Expected: all tests across phases green (Phase 1 + 2 + 3 + 4 + 5).

- [ ] **Step 4: Commit**

```bash
git add modules/contacts/tests/test_contacts_router.py
git commit -m "test(mod-contacts): end-to-end HTML route coverage incl. search, FK nullify on delete"
```

---

## Task 13: Docker Compose verification

**Files:** None (verification only).

- [ ] **Step 1: Rebuild shell image**

Run: `docker compose build shell`
Expected: succeeds; the contacts workspace member is included since the Dockerfile uses `uv sync --all-packages`.

- [ ] **Step 2: Bring up the stack**

```bash
docker compose up -d postgres redis
docker compose run --rm shell migrate
docker compose up -d shell
```

Wait for healthy. Sign in at http://localhost:8000 with the admin from Phase 2.

- [ ] **Step 3: Verify discovery**

Visit `/modules` in the browser. The `contacts` module should appear as "available" (not yet installed).

- [ ] **Step 4: Install via UI**

Click into `/modules/contacts`, submit the install form (no capabilities to approve). Watch the page redirect to the detail view with "Installed and active".

- [ ] **Step 5: Restart shell and confirm the sidebar**

Run: `docker compose restart shell`
Wait for healthy. Reload the browser. The sidebar should now show a new **Contacts** section with two items (Contacts, Companies).

- [ ] **Step 6: Use the UI**

Create a company, then a contact linked to it, edit the contact, search for it, delete it. Confirm everything works.

- [ ] **Step 7: Hard uninstall**

`/modules/contacts` → **Uninstall + drop data**. Confirm the schema is dropped and the sidebar section disappears after a restart (soft-uninstall doesn't unmount routes mid-process; that's called out in the spec's "restart to remove routes" note).

No commit for this task.

---

## Task 14: Quality gates + docs

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Ruff + pyright**

```bash
uv run ruff check packages/parcel-shell packages/parcel-sdk modules/contacts
uv run ruff format --check packages/parcel-shell packages/parcel-sdk modules/contacts
uv run pyright packages/parcel-shell packages/parcel-sdk modules/contacts
```

If anything fails, auto-fix:

```bash
uv run ruff check --fix packages/parcel-shell packages/parcel-sdk modules/contacts
uv run ruff format packages/parcel-shell packages/parcel-sdk modules/contacts
```

- [ ] **Step 2: Update `README.md`**

Replace the `### What Phase 4+ will add` block with:

```markdown
### Demo module: contacts

The repo ships a demo Contacts/CRM-lite module at `modules/contacts`. Install it from `/modules` (no capabilities to approve). After a restart, the sidebar grows a "Contacts" section; each entity has list, detail, and create pages, with HTMX live search.

### What Phase 6+ will add

A `parcel` CLI (Phase 6) — one entry point for `new-module`, `install`, `migrate`, `dev`, `serve`. The AI module generator lands in Phase 7.
```

- [ ] **Step 3: Update `CLAUDE.md`**

Replace the "Current phase" block with:

```markdown
**Phase 5 — Contacts demo module done.** `parcel-sdk` gained `Module.router`, `Module.templates_dir`, `Module.sidebar_items` plus a `SidebarItem` dataclass. Shell mounts active modules at install-time and at lifespan startup: their router goes under `/mod/<name>/*`, their template dir is prepended to the Jinja loader, and their sidebar items show up as a dedicated section. The Contacts module (`modules/contacts`) ships Contact + Company entities, two permissions (`contacts.read`, `contacts.write`), roomy two-line list with live search, form-first detail pages.

Next: **Phase 6 — SDK polish + `parcel` CLI.** Start a new session; prompt: "Begin Phase 6 per `CLAUDE.md` roadmap." Do not begin Phase 6 inside the Phase 5 commit cluster.
```

In the roadmap table, change Phase 5 to `✅ done` and Phase 6 to `⏭ next`.

Append to the "Locked-in decisions" table:

```markdown
| Module UI seam | `Module.router`, `Module.templates_dir`, `Module.sidebar_items` (Phase 5 SDK additions) |
| Module URL prefix | `/mod/<name>/*`. Template dir prepended to Jinja loader; sidebar items rendered as a per-module section. |
| Module removal on uninstall | Routes stay mounted until next process restart (FastAPI doesn't support clean router removal). Soft uninstall flips `is_active=false`; next boot skips mounting. |
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: close Phase 5, document module UI integration pattern"
```

---

## Verification summary (Phase 5 definition of done)

- [ ] `docker compose build shell` bundles the contacts workspace member; discovery reports the module.
- [ ] Installing the module via `/modules` writes `shell.installed_modules` + `mod_contacts` schema; permissions appear in `/admin/permissions`.
- [ ] After restart, sidebar has a "Contacts" section with Contacts / Companies links visible to users with `contacts.read`.
- [ ] Creating/editing/deleting a contact and company via the browser works; live search filters the list via HTMX.
- [ ] Hard-uninstalling drops the schema + permissions; schema gone after restart.
- [ ] `uv run pytest` green across all five phases.
- [ ] `uv run ruff check` + `uv run pyright` clean on shell, sdk, and modules/contacts.
- [ ] README + CLAUDE.md updated; Phase 5 ✅, Phase 6 ⏭.
