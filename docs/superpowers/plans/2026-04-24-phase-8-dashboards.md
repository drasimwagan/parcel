# Phase 8 — Dashboards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a first-class dashboards primitive — modules declare `Dashboard(...)` on their manifest; the shell auto-mounts `/dashboards/<module>/<slug>`, lazy-loads each widget via HTMX, and Contacts ships a reference "Overview" dashboard.

**Architecture:** Pure declarative additions on `parcel_sdk.Module.dashboards`; shell collects them into `app.state.dashboards` during module mount; FastAPI router renders list/detail/per-widget HTML. Chart.js 4 via CDN. Per-dashboard permission check reuses `effective_permissions`. No caching, no new migrations, no new shell permissions.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX, Tailwind, Chart.js 4 (CDN), pytest, async SQLAlchemy.

**Spec:** [docs/superpowers/specs/2026-04-24-phase-8-dashboards-design.md](../specs/2026-04-24-phase-8-dashboards-design.md)

---

## File structure

**New files:**
- `packages/parcel-sdk/src/parcel_sdk/dashboards.py` — dataclasses + query helpers.
- `packages/parcel-sdk/tests/test_dashboards.py` — dataclass + helper tests.
- `packages/parcel-shell/src/parcel_shell/dashboards/__init__.py`
- `packages/parcel-shell/src/parcel_shell/dashboards/registry.py`
- `packages/parcel-shell/src/parcel_shell/dashboards/router.py`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/list.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/detail.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_kpi.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_line.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_bar.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_table.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_headline.html`
- `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_error.html`
- `packages/parcel-shell/tests/test_dashboards_registry.py`
- `packages/parcel-shell/tests/test_dashboards_routes.py`
- `packages/parcel-shell/tests/test_dashboards_sidebar.py`
- `modules/contacts/src/parcel_mod_contacts/dashboards.py`
- `modules/contacts/tests/test_contacts_dashboard.py`

**Modified files:**
- `packages/parcel-sdk/src/parcel_sdk/module.py` — add `dashboards` field.
- `packages/parcel-sdk/src/parcel_sdk/__init__.py` — re-exports, version bump to 0.4.0.
- `packages/parcel-sdk/pyproject.toml` — version 0.4.0.
- `packages/parcel-shell/src/parcel_shell/modules/integration.py` — collect dashboards at mount time.
- `packages/parcel-shell/src/parcel_shell/app.py` — include dashboards router + add template dir.
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` — auto-inject "Dashboards" link.
- `packages/parcel-shell/src/parcel_shell/ui/templates.py` — register dashboards template dir on first call.
- `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html` — Chart.js CDN script.
- `modules/contacts/src/parcel_mod_contacts/__init__.py` — pass `dashboards=` into `Module(...)`.

---

## Task 1: SDK dashboards dataclasses

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/dashboards.py`
- Test: `packages/parcel-sdk/tests/test_dashboards.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/parcel-sdk/tests/test_dashboards.py
from __future__ import annotations

import pytest

from parcel_sdk.dashboards import (
    BarWidget,
    Dashboard,
    Dataset,
    HeadlineWidget,
    Kpi,
    KpiWidget,
    LineWidget,
    Series,
    Table,
    TableWidget,
)


def _kpi_fn(_ctx):  # pragma: no cover - placeholder
    ...


def test_dashboard_basic_construction():
    dash = Dashboard(
        name="contacts.overview",
        slug="overview",
        title="Contacts overview",
        permission="contacts.read",
        widgets=(
            KpiWidget(id="total", title="Total", data=_kpi_fn),
            HeadlineWidget(id="note", title="", text="Hi", col_span=4),
        ),
    )
    assert dash.slug == "overview"
    assert dash.permission == "contacts.read"
    assert len(dash.widgets) == 2
    assert dash.widgets[0].id == "total"


def test_widget_is_frozen():
    w = HeadlineWidget(id="x", title="t", text="hi")
    with pytest.raises(Exception):
        w.text = "mutated"  # type: ignore[misc]


def test_series_and_table_dataclasses():
    s = Series(labels=["a", "b"], datasets=[Dataset(label="count", values=[1, 2])])
    assert s.datasets[0].values == [1, 2]
    t = Table(columns=["a", "b"], rows=[[1, 2], [3, 4]])
    assert t.columns == ["a", "b"]


def test_kpi_optional_delta():
    k = Kpi(value=42)
    assert k.delta is None and k.delta_label is None
    k2 = Kpi(value=42, delta=0.12, delta_label="vs last week")
    assert k2.delta == 0.12


def test_widget_default_col_span_is_two():
    w = HeadlineWidget(id="h", title="t", text="x")
    assert w.col_span == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests/test_dashboards.py -v`
Expected: FAIL with `ModuleNotFoundError: parcel_sdk.dashboards`.

- [ ] **Step 3: Write minimal implementation**

```python
# packages/parcel-sdk/src/parcel_sdk/dashboards.py
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Ctx:
    """Per-request context passed to widget data functions."""

    session: AsyncSession
    user_id: UUID


@dataclass(frozen=True)
class Dataset:
    label: str
    values: list[float | int]


@dataclass(frozen=True)
class Series:
    labels: list[str]
    datasets: list[Dataset]


@dataclass(frozen=True)
class Kpi:
    value: str | int | float
    delta: float | None = None
    delta_label: str | None = None


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[Any]]


@dataclass(frozen=True)
class Widget:
    """Base widget. Subclasses add a type-specific `data` field."""

    id: str
    title: str
    col_span: int = 2


@dataclass(frozen=True)
class KpiWidget(Widget):
    data: Callable[[Ctx], Awaitable[Kpi]] = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class LineWidget(Widget):
    data: Callable[[Ctx], Awaitable[Series]] = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class BarWidget(Widget):
    data: Callable[[Ctx], Awaitable[Series]] = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class TableWidget(Widget):
    data: Callable[[Ctx], Awaitable[Table]] = field(default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class HeadlineWidget(Widget):
    text: str = ""
    href: str | None = None


@dataclass(frozen=True)
class Dashboard:
    name: str
    slug: str
    title: str
    permission: str
    widgets: tuple[Widget, ...]
    description: str = ""


__all__ = [
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Series",
    "Table",
    "TableWidget",
    "Widget",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests/test_dashboards.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/dashboards.py packages/parcel-sdk/tests/test_dashboards.py
git commit -m "feat(sdk): dashboards dataclasses (Widget, Dashboard, Ctx, series/kpi/table)"
```

---

## Task 2: SDK query helpers

Params-only wrappers around `sqlalchemy.text()` so modules can emit one-liners without needing the `raw_sql` capability themselves.

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/dashboards.py`
- Test: `packages/parcel-sdk/tests/test_dashboards.py`

- [ ] **Step 1: Append failing tests**

```python
# append to packages/parcel-sdk/tests/test_dashboards.py
import asyncio
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk.dashboards import scalar_query, series_query, table_query


@pytest.mark.asyncio
async def test_scalar_query_executes_with_params(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash"))
    await pg_session.execute(text("CREATE TABLE t_dash.x (id int primary key, v int)"))
    await pg_session.execute(text("INSERT INTO t_dash.x VALUES (1, 10), (2, 20)"))
    await pg_session.commit()
    n = await scalar_query(pg_session, "SELECT COUNT(*) FROM t_dash.x WHERE v > :min", min=5)
    assert n == 2


@pytest.mark.asyncio
async def test_series_query_shapes_result(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash2"))
    await pg_session.execute(text("CREATE TABLE t_dash2.x (label text, v int)"))
    await pg_session.execute(
        text("INSERT INTO t_dash2.x VALUES ('a', 1), ('b', 2), ('c', 3)")
    )
    await pg_session.commit()
    s = await series_query(
        pg_session,
        "SELECT label, v FROM t_dash2.x ORDER BY label",
        label_col="label",
        value_col="v",
    )
    assert s.labels == ["a", "b", "c"]
    assert s.datasets[0].values == [1, 2, 3]


@pytest.mark.asyncio
async def test_table_query_shapes_rows(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash3"))
    await pg_session.execute(text("CREATE TABLE t_dash3.x (a text, b int)"))
    await pg_session.execute(text("INSERT INTO t_dash3.x VALUES ('x', 1), ('y', 2)"))
    await pg_session.commit()
    t = await table_query(
        pg_session, "SELECT a, b FROM t_dash3.x ORDER BY a", 
    )
    assert t.columns == ["a", "b"]
    assert t.rows == [["x", 1], ["y", 2]]
```

If the SDK test suite does not already have a `pg_session` fixture, add one to `packages/parcel-sdk/tests/conftest.py`:

```python
# packages/parcel-sdk/tests/conftest.py
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest_asyncio.fixture(scope="session")
async def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg").replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        yield url


@pytest_asyncio.fixture()
async def pg_session(pg_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(pg_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests/test_dashboards.py -v`
Expected: FAIL with `ImportError: cannot import name 'scalar_query'`.

- [ ] **Step 3: Append implementation to `dashboards.py`**

```python
# append to packages/parcel-sdk/src/parcel_sdk/dashboards.py
from sqlalchemy import text


async def scalar_query(session, sql: str, **params) -> Any:
    """Return the first column of the first row, or None if empty.

    Params are bound via SQLAlchemy parameterisation — never string-interpolate.
    """
    result = await session.execute(text(sql), params)
    row = result.first()
    if row is None:
        return None
    return row[0]


async def series_query(
    session,
    sql: str,
    label_col: str,
    value_col: str,
    **params,
) -> Series:
    """Shape a query result into a single-dataset ``Series``."""
    result = await session.execute(text(sql), params)
    rows = result.mappings().all()
    labels = [str(r[label_col]) for r in rows]
    values = [r[value_col] for r in rows]
    return Series(labels=labels, datasets=[Dataset(label=value_col, values=values)])


async def table_query(session, sql: str, **params) -> Table:
    """Shape a query result into a ``Table`` using column order."""
    result = await session.execute(text(sql), params)
    rows = result.all()
    columns = list(result.keys()) if rows else []
    return Table(columns=columns, rows=[list(r) for r in rows])


# update __all__ to include the three helpers
__all__ += ["scalar_query", "series_query", "table_query"]
```

(Merge into the existing `__all__` tuple instead of appending if that reads cleaner.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests/test_dashboards.py -v`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/dashboards.py packages/parcel-sdk/tests/test_dashboards.py packages/parcel-sdk/tests/conftest.py
git commit -m "feat(sdk): scalar_query / series_query / table_query helpers"
```

---

## Task 3: Module.dashboards field + SDK re-exports + version bump

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/module.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/__init__.py`
- Modify: `packages/parcel-sdk/pyproject.toml`
- Test: `packages/parcel-sdk/tests/test_module.py`

- [ ] **Step 1: Write failing test**

```python
# append to packages/parcel-sdk/tests/test_module.py
from parcel_sdk import Dashboard, KpiWidget, Module


def _fn(_ctx): ...


def test_module_accepts_dashboards_tuple():
    d = Dashboard(
        name="m.overview",
        slug="overview",
        title="t",
        permission="m.read",
        widgets=(KpiWidget(id="k", title="t", data=_fn),),
    )
    m = Module(name="m", version="0.1.0", dashboards=(d,))
    assert m.dashboards == (d,)


def test_module_dashboards_defaults_empty():
    m = Module(name="m", version="0.1.0")
    assert m.dashboards == ()
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests/test_module.py -v`
Expected: FAIL — `Module.__init__` does not accept `dashboards`.

- [ ] **Step 3: Add field + re-exports + bump**

```python
# packages/parcel-sdk/src/parcel_sdk/module.py — add import + field
from parcel_sdk.dashboards import Dashboard  # add near other imports
# … inside Module:
    dashboards: tuple[Dashboard, ...] = ()
```

```python
# packages/parcel-sdk/src/parcel_sdk/__init__.py — full file
from __future__ import annotations

from parcel_sdk import shell_api
from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.dashboards import (
    BarWidget,
    Ctx,
    Dashboard,
    Dataset,
    HeadlineWidget,
    Kpi,
    KpiWidget,
    LineWidget,
    Series,
    Table,
    TableWidget,
    Widget,
    scalar_query,
    series_query,
    table_query,
)
from parcel_sdk.module import Module, Permission
from parcel_sdk.sidebar import SidebarItem

__all__ = [
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Module",
    "Permission",
    "Series",
    "SidebarItem",
    "Table",
    "TableWidget",
    "Widget",
    "__version__",
    "run_async_migrations",
    "scalar_query",
    "series_query",
    "shell_api",
    "table_query",
]
__version__ = "0.4.0"
```

Update `packages/parcel-sdk/pyproject.toml` version line:
```toml
version = "0.4.0"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --package parcel-sdk pytest packages/parcel-sdk/tests -v`
Expected: PASS (all SDK tests green).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/module.py packages/parcel-sdk/src/parcel_sdk/__init__.py packages/parcel-sdk/pyproject.toml packages/parcel-sdk/tests/test_module.py
git commit -m "feat(sdk): Module.dashboards field + dashboards re-exports + v0.4.0"
```

---

## Task 4: Shell registry

Collects dashboards from active modules into `app.state.dashboards`.

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/registry.py`
- Test: `packages/parcel-shell/tests/test_dashboards_registry.py`

- [ ] **Step 1: Write failing test**

```python
# packages/parcel-shell/tests/test_dashboards_registry.py
from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import Dashboard, HeadlineWidget, Module
from parcel_shell.dashboards.registry import (
    RegisteredDashboard,
    collect_dashboards,
    find_dashboard,
)


def _mkmod(name: str, dashboards: tuple[Dashboard, ...] = ()) -> Module:
    return Module(name=name, version="0.1.0", dashboards=dashboards)


def _app_with_modules(*modules: Module):
    return SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={m.name: m for m in modules},
            active_modules={m.name for m in modules},
        )
    )


def test_collect_dashboards_from_active_modules():
    d1 = Dashboard(
        name="a.overview", slug="overview", title="A", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    d2 = Dashboard(
        name="b.stats", slug="stats", title="B", permission="b.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    app = _app_with_modules(_mkmod("a", (d1,)), _mkmod("b", (d2,)), _mkmod("c"))
    result = collect_dashboards(app)
    assert result == [
        RegisteredDashboard(module_name="a", dashboard=d1),
        RegisteredDashboard(module_name="b", dashboard=d2),
    ]


def test_find_dashboard_by_module_and_slug():
    d = Dashboard(
        name="a.overview", slug="overview", title="A", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    app = _app_with_modules(_mkmod("a", (d,)))
    reg = collect_dashboards(app)
    assert find_dashboard(reg, "a", "overview") is not None
    assert find_dashboard(reg, "a", "missing") is None
    assert find_dashboard(reg, "missing", "overview") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_registry.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

```python
# packages/parcel-shell/src/parcel_shell/dashboards/__init__.py
"""Shell-side dashboards plumbing (registry, router, templates)."""
```

```python
# packages/parcel-shell/src/parcel_shell/dashboards/registry.py
from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Dashboard, Module


@dataclass(frozen=True)
class RegisteredDashboard:
    module_name: str
    dashboard: Dashboard


def collect_dashboards(app) -> list[RegisteredDashboard]:
    """Walk active modules' manifests and return their dashboards in order.

    Reads ``app.state.active_modules_manifest`` (populated by mount_module).
    Returns ``[]`` if the state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredDashboard] = []
    for name in sorted(manifests):
        module = manifests[name]
        for dash in module.dashboards:
            out.append(RegisteredDashboard(module_name=name, dashboard=dash))
    return out


def find_dashboard(
    registered: list[RegisteredDashboard], module_name: str, slug: str
) -> RegisteredDashboard | None:
    for r in registered:
        if r.module_name == module_name and r.dashboard.slug == slug:
            return r
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_registry.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/dashboards/__init__.py packages/parcel-shell/src/parcel_shell/dashboards/registry.py packages/parcel-shell/tests/test_dashboards_registry.py
git commit -m "feat(shell): dashboards registry (collect_dashboards, find_dashboard)"
```

---

## Task 5: Wire manifest capture into mount_module

Today `mount_module` stores only sidebar items per module. Dashboards need the full manifest object, so we also stash it in `app.state.active_modules_manifest`.

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/modules/integration.py`
- Test: `packages/parcel-shell/tests/test_module_integration.py`

- [ ] **Step 1: Append failing test**

```python
# append to packages/parcel-shell/tests/test_module_integration.py
from parcel_sdk import Dashboard, HeadlineWidget, Module as SdkModule
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


def test_mount_module_records_manifest(fresh_app):  # fresh_app: existing fixture that yields a FastAPI app
    m = SdkModule(
        name="demo",
        version="0.1.0",
        dashboards=(
            Dashboard(
                name="demo.ov", slug="ov", title="T", permission="demo.read",
                widgets=(HeadlineWidget(id="h", title="t", text="x"),),
            ),
        ),
    )
    mount_module(fresh_app, DiscoveredModule(module=m, distribution=None))
    assert "demo" in fresh_app.state.active_modules_manifest
    assert fresh_app.state.active_modules_manifest["demo"] is m
```

If `fresh_app` doesn't exist, use:
```python
from fastapi import FastAPI
fresh_app = FastAPI()
```
directly inline — mount_module doesn't need lifespan state.

- [ ] **Step 2: Run — expect FAIL (AttributeError on active_modules_manifest).**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_module_integration.py -v`

- [ ] **Step 3: Implement**

Update `_ensure_state` and `mount_module` in `integration.py`:

```python
def _ensure_state(app: FastAPI) -> None:
    if not hasattr(app.state, "active_modules"):
        app.state.active_modules = set()
    if not hasattr(app.state, "active_modules_sidebar"):
        app.state.active_modules_sidebar = {}
    if not hasattr(app.state, "active_modules_manifest"):
        app.state.active_modules_manifest = {}


def mount_module(app: FastAPI, discovered: DiscoveredModule) -> None:
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
    app.state.active_modules_manifest[name] = discovered.module
    _log.info("module.mounted", name=name)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_module_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/integration.py packages/parcel-shell/tests/test_module_integration.py
git commit -m "feat(shell): stash module manifests in app.state for dashboards"
```

---

## Task 6: Dashboards router — list page

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/router.py`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/list.html`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/templates.py` — register dashboards template dir.
- Modify: `packages/parcel-shell/src/parcel_shell/app.py` — include router.
- Test: `packages/parcel-shell/tests/test_dashboards_routes.py`

- [ ] **Step 1: Write failing test**

```python
# packages/parcel-shell/tests/test_dashboards_routes.py
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_empty_when_no_dashboards(authed_client: AsyncClient):
    resp = await authed_client.get("/dashboards")
    assert resp.status_code == 200
    assert "No dashboards" in resp.text


async def test_list_redirects_when_unauthenticated(client: AsyncClient):
    resp = await client.get("/dashboards", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]
```

(The `authed_client` / `client` fixtures come from `_shell_fixtures`. Confirm by reading `packages/parcel-shell/tests/_shell_fixtures.py` — it already provides these for Phase 7c tests.)

- [ ] **Step 2: Run — expect FAIL (404 or missing route).**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_routes.py -v`

- [ ] **Step 3: Template**

```html
<!-- packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/list.html -->
{% extends "_base.html" %}
{% block title %}Dashboards · Parcel{% endblock %}
{% block content %}
<h1 class="text-2xl font-semibold mb-4">Dashboards</h1>
{% if not groups %}
<p class="text-gray-500">No dashboards available.</p>
{% else %}
{% for module_name, items in groups %}
<section class="mb-6">
  <h2 class="text-lg font-medium mb-2 capitalize">{{ module_name }}</h2>
  <ul class="space-y-1">
    {% for dash in items %}
    <li>
      <a href="/dashboards/{{ module_name }}/{{ dash.slug }}" class="text-blue-600 hover:underline">
        {{ dash.title }}
      </a>
      {% if dash.description %}<span class="text-gray-500 ml-2">{{ dash.description }}</span>{% endif %}
    </li>
    {% endfor %}
  </ul>
</section>
{% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Router**

```python
# packages/parcel-shell/src/parcel_shell/dashboards/router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from parcel_shell.dashboards.registry import collect_dashboards, find_dashboard
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _group_by_module(registered, perms: set[str]):
    groups: dict[str, list] = {}
    for r in registered:
        if r.dashboard.permission in perms:
            groups.setdefault(r.module_name, []).append(r.dashboard)
    return sorted(groups.items())


@router.get("", response_class=HTMLResponse)
async def dashboards_list(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    groups = _group_by_module(registered, perms)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboards/list.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/dashboards",
            "settings": request.app.state.settings,
            "permissions": perms,
            "groups": groups,
        },
    )
```

- [ ] **Step 5: Register template dir + include router**

In `packages/parcel-shell/src/parcel_shell/ui/templates.py`, after the `ChoiceLoader` line inside `get_templates`, add the dashboards dir:

```python
    _DASHBOARDS_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "templates"
    tpl.env.loader = jinja2.ChoiceLoader([
        jinja2.FileSystemLoader(str(_SHELL_TEMPLATES_DIR)),
        jinja2.FileSystemLoader(str(_DASHBOARDS_DIR)),
    ])
```

(Define `_DASHBOARDS_DIR` at module top next to `_SHELL_TEMPLATES_DIR` for cleanliness.)

In `packages/parcel-shell/src/parcel_shell/app.py`, after the existing HTML UI includes and the AI chat include, add:

```python
    from parcel_shell.dashboards.router import router as dashboards_router
    app.include_router(dashboards_router)
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_routes.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/dashboards/router.py packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/list.html packages/parcel-shell/src/parcel_shell/ui/templates.py packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/tests/test_dashboards_routes.py
git commit -m "feat(shell): dashboards list page + router mount"
```

---

## Task 7: Dashboard detail page (grid skeleton)

Renders the dashboard page with placeholder `<div>`s whose HTMX `hx-get` loads each widget.

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/detail.html`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_headline.html`
- Modify: `packages/parcel-shell/src/parcel_shell/dashboards/router.py`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html` — add Chart.js CDN.
- Test: `packages/parcel-shell/tests/test_dashboards_routes.py`

- [ ] **Step 1: Append failing tests**

```python
# append to packages/parcel-shell/tests/test_dashboards_routes.py
async def test_detail_404_on_unknown(authed_client: AsyncClient):
    resp = await authed_client.get("/dashboards/missing/overview")
    assert resp.status_code == 404


async def test_detail_renders_with_mounted_dashboard(authed_client_with_demo_dashboard: AsyncClient):
    resp = await authed_client_with_demo_dashboard.get("/dashboards/demo/overview")
    assert resp.status_code == 200
    assert 'hx-get="/dashboards/demo/overview/widgets/greet"' in resp.text


async def test_detail_404_when_user_lacks_permission(authed_client_with_gated_dashboard: AsyncClient):
    resp = await authed_client_with_gated_dashboard.get("/dashboards/demo/overview")
    assert resp.status_code == 404
```

Two new fixtures are needed (add at bottom of `packages/parcel-shell/tests/_shell_fixtures.py`, or in a nearby `_dashboard_fixtures.py` imported from conftest). Full fixture code:

```python
# packages/parcel-shell/tests/_dashboard_fixtures.py
from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient

from parcel_sdk import Dashboard, HeadlineWidget, KpiWidget, Kpi, Module
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


async def _kpi_greet(ctx) -> Kpi:
    return Kpi(value="hello")


DEMO_DASHBOARD = Dashboard(
    name="demo.overview",
    slug="overview",
    title="Demo overview",
    permission="users.read",  # every admin already has this
    widgets=(
        KpiWidget(id="greet", title="Greeting", data=_kpi_greet),
        HeadlineWidget(id="note", title="", text="Hi", col_span=4),
    ),
)

GATED_DASHBOARD = Dashboard(
    name="demo.overview",
    slug="overview",
    title="Demo overview",
    permission="nobody.has.this",
    widgets=(HeadlineWidget(id="h", title="", text="x"),),
)


@pytest_asyncio.fixture()
async def authed_client_with_demo_dashboard(app, authed_client: AsyncClient) -> AsyncClient:
    mount_module(
        app,
        DiscoveredModule(
            module=Module(name="demo", version="0.1.0", dashboards=(DEMO_DASHBOARD,)),
            distribution=None,
        ),
    )
    return authed_client


@pytest_asyncio.fixture()
async def authed_client_with_gated_dashboard(app, authed_client: AsyncClient) -> AsyncClient:
    mount_module(
        app,
        DiscoveredModule(
            module=Module(name="demo", version="0.1.0", dashboards=(GATED_DASHBOARD,)),
            distribution=None,
        ),
    )
    return authed_client
```

Register the fixture module as a pytest plugin in the workspace conftest the same way `_shell_fixtures` already is. If that pattern isn't obvious, simply put the fixtures inline in `_shell_fixtures.py`.

- [ ] **Step 2: Run — expect FAIL on all three.**

- [ ] **Step 3: Add Chart.js CDN to `_base.html`**

In `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html`, after the existing `<script defer src="https://unpkg.com/alpinejs@3.13.7/...` line, add:

```html
<script defer src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
```

- [ ] **Step 4: Templates**

```html
<!-- packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/detail.html -->
{% extends "_base.html" %}
{% block title %}{{ dashboard.title }} · Parcel{% endblock %}
{% block content %}
<h1 class="text-2xl font-semibold mb-4">{{ dashboard.title }}</h1>
{% if dashboard.description %}
<p class="text-gray-500 mb-4">{{ dashboard.description }}</p>
{% endif %}
<div class="grid grid-cols-4 gap-4">
  {% for widget in dashboard.widgets %}
    {% if widget.__class__.__name__ == "HeadlineWidget" %}
    <div class="col-span-{{ widget.col_span }}">
      {% include "dashboards/_widget_headline.html" %}
    </div>
    {% else %}
    <div
      class="col-span-{{ widget.col_span }} border rounded p-4 min-h-[120px]"
      hx-get="/dashboards/{{ module_name }}/{{ dashboard.slug }}/widgets/{{ widget.id }}"
      hx-trigger="load"
      hx-swap="outerHTML"
    >
      <div class="text-sm text-gray-400">Loading {{ widget.title }}…</div>
    </div>
    {% endif %}
  {% endfor %}
</div>
{% endblock %}
```

```html
<!-- packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_headline.html -->
<div class="border rounded p-4">
  {% if widget.href %}
  <a href="{{ widget.href }}" class="text-blue-600 hover:underline text-lg font-medium">{{ widget.text }}</a>
  {% else %}
  <p class="text-lg font-medium">{{ widget.text }}</p>
  {% endif %}
</div>
```

- [ ] **Step 5: Router detail endpoint**

Append to `packages/parcel-shell/src/parcel_shell/dashboards/router.py`:

```python
@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def dashboard_detail(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    hit = find_dashboard(registered, module_name, slug)
    if hit is None or hit.dashboard.permission not in perms:
        raise _http_404()
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboards/detail.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/dashboards",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "dashboard": hit.dashboard,
        },
    )


def _http_404():
    from fastapi import HTTPException
    return HTTPException(status_code=404, detail="Not found")
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_routes.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/dashboards/router.py packages/parcel-shell/src/parcel_shell/dashboards/templates/ packages/parcel-shell/src/parcel_shell/ui/templates/_base.html packages/parcel-shell/tests/
git commit -m "feat(shell): dashboard detail page with lazy widget containers"
```

---

## Task 8: Per-widget endpoint + remaining widget partials

Renders one widget's data. KPI / line / bar / table / error partials ship here.

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_kpi.html`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_line.html`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_bar.html`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_table.html`
- Create: `packages/parcel-shell/src/parcel_shell/dashboards/templates/dashboards/_widget_error.html`
- Modify: `packages/parcel-shell/src/parcel_shell/dashboards/router.py`
- Test: `packages/parcel-shell/tests/test_dashboards_routes.py`

- [ ] **Step 1: Append failing tests**

```python
# append to packages/parcel-shell/tests/test_dashboards_routes.py
async def test_widget_kpi_renders_value(authed_client_with_demo_dashboard: AsyncClient):
    resp = await authed_client_with_demo_dashboard.get("/dashboards/demo/overview/widgets/greet")
    assert resp.status_code == 200
    assert "hello" in resp.text


async def test_widget_404_on_missing_widget(authed_client_with_demo_dashboard: AsyncClient):
    resp = await authed_client_with_demo_dashboard.get("/dashboards/demo/overview/widgets/nope")
    assert resp.status_code == 404


async def test_widget_error_partial_on_raise(authed_client_with_failing_widget: AsyncClient):
    resp = await authed_client_with_failing_widget.get("/dashboards/demo/overview/widgets/bad")
    assert resp.status_code == 200
    assert "Couldn't load this widget" in resp.text
```

Add an `authed_client_with_failing_widget` fixture with a `KpiWidget` whose data fn raises:

```python
# append to _dashboard_fixtures.py
async def _kpi_fail(_ctx):
    raise RuntimeError("boom")


FAILING_DASHBOARD = Dashboard(
    name="demo.overview", slug="overview", title="T", permission="users.read",
    widgets=(KpiWidget(id="bad", title="Bad", data=_kpi_fail),),
)


@pytest_asyncio.fixture()
async def authed_client_with_failing_widget(app, authed_client: AsyncClient) -> AsyncClient:
    mount_module(
        app,
        DiscoveredModule(
            module=Module(name="demo", version="0.1.0", dashboards=(FAILING_DASHBOARD,)),
            distribution=None,
        ),
    )
    return authed_client
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Widget partials**

```html
<!-- _widget_kpi.html -->
<div class="border rounded p-4">
  <div class="text-sm text-gray-500">{{ widget.title }}</div>
  <div class="text-3xl font-semibold mt-1">{{ data.value }}</div>
  {% if data.delta is not none %}
  <div class="text-xs mt-1 {% if data.delta >= 0 %}text-green-600{% else %}text-red-600{% endif %}">
    {{ '%+.1f%%'|format(data.delta * 100) }}
    {% if data.delta_label %}<span class="text-gray-400 ml-1">{{ data.delta_label }}</span>{% endif %}
  </div>
  {% endif %}
</div>
```

```html
<!-- _widget_line.html -->
<div class="border rounded p-4">
  <div class="text-sm text-gray-500 mb-2">{{ widget.title }}</div>
  <canvas id="chart-{{ widget.id }}" height="180"></canvas>
  <script>
  (function(){
    var el = document.getElementById("chart-{{ widget.id }}");
    if (!el || typeof Chart === "undefined") return;
    new Chart(el, {
      type: "line",
      data: {
        labels: {{ data.labels | tojson }},
        datasets: [{% for ds in data.datasets %}{
          label: {{ ds.label | tojson }},
          data: {{ ds.values | tojson }},
          borderColor: "rgb(59, 130, 246)",
          backgroundColor: "rgba(59, 130, 246, 0.1)",
          tension: 0.25,
        }{% if not loop.last %},{% endif %}{% endfor %}],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  })();
  </script>
</div>
```

```html
<!-- _widget_bar.html -->
<div class="border rounded p-4">
  <div class="text-sm text-gray-500 mb-2">{{ widget.title }}</div>
  <canvas id="chart-{{ widget.id }}" height="180"></canvas>
  <script>
  (function(){
    var el = document.getElementById("chart-{{ widget.id }}");
    if (!el || typeof Chart === "undefined") return;
    new Chart(el, {
      type: "bar",
      data: {
        labels: {{ data.labels | tojson }},
        datasets: [{% for ds in data.datasets %}{
          label: {{ ds.label | tojson }},
          data: {{ ds.values | tojson }},
          backgroundColor: "rgba(59, 130, 246, 0.6)",
        }{% if not loop.last %},{% endif %}{% endfor %}],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  })();
  </script>
</div>
```

```html
<!-- _widget_table.html -->
<div class="border rounded p-4 overflow-x-auto">
  <div class="text-sm text-gray-500 mb-2">{{ widget.title }}</div>
  <table class="min-w-full text-sm">
    <thead>
      <tr>{% for c in data.columns %}<th class="text-left pr-4 pb-1 font-medium">{{ c }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
      {% for row in data.rows %}
      <tr class="border-t">
        {% for cell in row %}<td class="pr-4 py-1">{{ cell }}</td>{% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

```html
<!-- _widget_error.html -->
<div class="border border-red-200 bg-red-50 rounded p-4">
  <div class="text-sm text-red-700">Couldn't load this widget.</div>
  <small class="text-red-400">{{ widget.id }}</small>
</div>
```

- [ ] **Step 4: Router — widget endpoint**

Append to `router.py`:

```python
import structlog
from parcel_sdk.dashboards import (
    BarWidget,
    Ctx,
    HeadlineWidget,
    KpiWidget,
    LineWidget,
    TableWidget,
)

_log = structlog.get_logger("parcel_shell.dashboards")

_PARTIALS = {
    KpiWidget: "dashboards/_widget_kpi.html",
    LineWidget: "dashboards/_widget_line.html",
    BarWidget: "dashboards/_widget_bar.html",
    TableWidget: "dashboards/_widget_table.html",
    HeadlineWidget: "dashboards/_widget_headline.html",
}


@router.get("/{module_name}/{slug}/widgets/{widget_id}", response_class=HTMLResponse)
async def dashboard_widget(
    module_name: str,
    slug: str,
    widget_id: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    hit = find_dashboard(registered, module_name, slug)
    if hit is None or hit.dashboard.permission not in perms:
        raise _http_404()
    widget = next((w for w in hit.dashboard.widgets if w.id == widget_id), None)
    if widget is None:
        raise _http_404()

    templates = get_templates()
    template_name = _PARTIALS[type(widget)]

    if isinstance(widget, HeadlineWidget):
        return templates.TemplateResponse(
            request, template_name, {"widget": widget}
        )

    try:
        data = await widget.data(Ctx(session=db, user_id=user.id))
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "dashboards.widget.failed",
            module=module_name,
            slug=slug,
            widget=widget_id,
            error=str(exc),
        )
        return templates.TemplateResponse(
            request, "dashboards/_widget_error.html", {"widget": widget}
        )

    return templates.TemplateResponse(
        request, template_name, {"widget": widget, "data": data}
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_routes.py -v`
Expected: all PASS (kpi render, 404 missing, error partial).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/dashboards/ packages/parcel-shell/tests/
git commit -m "feat(shell): widget endpoint with kpi/line/bar/table/error partials"
```

---

## Task 9: Sidebar auto-adds "Dashboards" link

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`
- Test: `packages/parcel-shell/tests/test_dashboards_sidebar.py`

- [ ] **Step 1: Write failing test**

```python
# packages/parcel-shell/tests/test_dashboards_sidebar.py
from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import Dashboard, HeadlineWidget, Module
from parcel_shell.ui.sidebar import sidebar_for


def _req_with_dashboards(modules):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        active_modules_manifest={m.name: m for m in modules},
        active_modules={m.name for m in modules},
        active_modules_sidebar={m.name: () for m in modules},
    )))


def test_no_dashboards_link_when_none_visible():
    req = _req_with_dashboards([Module(name="a", version="0.1.0")])
    result = sidebar_for(req, perms=set())
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" not in hrefs


def test_dashboards_link_appears_when_user_has_permission():
    d = Dashboard(
        name="a.o", slug="o", title="T", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="", text="x"),),
    )
    m = Module(name="a", version="0.1.0", dashboards=(d,))
    req = _req_with_dashboards([m])
    result = sidebar_for(req, perms={"a.read"})
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" in hrefs


def test_dashboards_link_hidden_when_no_matching_permission():
    d = Dashboard(
        name="a.o", slug="o", title="T", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="", text="x"),),
    )
    m = Module(name="a", version="0.1.0", dashboards=(d,))
    req = _req_with_dashboards([m])
    result = sidebar_for(req, perms={"other.perm"})
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" not in hrefs
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Modify `sidebar_for`**

At top of `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`:

```python
def _dashboards_section(request, perms: set[str]) -> SidebarSection | None:
    """Return a sidebar section for dashboards if the user can see ≥ 1.

    Reads ``app.state.active_modules_manifest`` and checks each dashboard's
    permission against the user's effective permissions.
    """
    manifest = getattr(request.app.state, "active_modules_manifest", {}) or {}
    visible = False
    for module in manifest.values():
        for dash in getattr(module, "dashboards", ()):
            if dash.permission in perms:
                visible = True
                break
        if visible:
            break
    if not visible:
        return None
    return SidebarSection(
        label="Dashboards",
        items=(SidebarItem(label="Dashboards", href="/dashboards", permission=None),),
    )
```

Then update `sidebar_for`:

```python
def sidebar_for(request, perms: set[str]) -> list[SidebarSection]:
    module_sections = getattr(request.app.state, "active_modules_sidebar", None)
    out = composed_sections(perms, module_sections)
    dash = _dashboards_section(request, perms)
    if dash is not None:
        # Insert after the "Overview" section if present, else at front.
        insert_at = 1 if out and out[0].label == "Overview" else 0
        out.insert(insert_at, dash)
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --package parcel-shell pytest packages/parcel-shell/tests/test_dashboards_sidebar.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/sidebar.py packages/parcel-shell/tests/test_dashboards_sidebar.py
git commit -m "feat(shell): auto-add Dashboards sidebar link when user has any dashboard"
```

---

## Task 10: Contacts reference dashboard

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/dashboards.py`
- Modify: `modules/contacts/src/parcel_mod_contacts/__init__.py`
- Test: `modules/contacts/tests/test_contacts_dashboard.py`

- [ ] **Step 1: Write failing test**

```python
# modules/contacts/tests/test_contacts_dashboard.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_sdk.dashboards import Ctx


pytestmark = pytest.mark.asyncio


@pytest.fixture()
def ctx(contacts_session: AsyncSession):
    return Ctx(session=contacts_session, user_id=uuid4())


async def _seed(session: AsyncSession, n_now: int = 3, n_old: int = 2):
    now = datetime.now(tz=timezone.utc)
    for i in range(n_now):
        await session.execute(
            text(
                "INSERT INTO mod_contacts.contact (id, first_name, last_name, email, created_at, updated_at) "
                "VALUES (:id, :f, :l, :e, :c, :c)"
            ),
            {"id": uuid4(), "f": f"F{i}", "l": f"L{i}", "e": f"x{i}@e.com", "c": now},
        )
    for i in range(n_old):
        await session.execute(
            text(
                "INSERT INTO mod_contacts.contact (id, first_name, last_name, email, created_at, updated_at) "
                "VALUES (:id, :f, :l, :e, :c, :c)"
            ),
            {
                "id": uuid4(), "f": f"O{i}", "l": f"O{i}", "e": f"o{i}@e.com",
                "c": now - timedelta(days=40),
            },
        )
    await session.commit()


async def test_overview_dashboard_declaration():
    assert overview_dashboard.slug == "overview"
    assert overview_dashboard.permission == "contacts.read"
    ids = [w.id for w in overview_dashboard.widgets]
    assert ids == ["total", "new_week", "new_30d", "recent"]


async def test_total_kpi(ctx, contacts_session):
    await _seed(contacts_session, n_now=3, n_old=2)
    w = next(w for w in overview_dashboard.widgets if w.id == "total")
    kpi = await w.data(ctx)
    assert kpi.value == 5


async def test_new_week_kpi_returns_count(ctx, contacts_session):
    await _seed(contacts_session, n_now=3, n_old=2)
    w = next(w for w in overview_dashboard.widgets if w.id == "new_week")
    kpi = await w.data(ctx)
    assert kpi.value == 3


async def test_new_30d_series(ctx, contacts_session):
    await _seed(contacts_session, n_now=3, n_old=0)
    w = next(w for w in overview_dashboard.widgets if w.id == "new_30d")
    series = await w.data(ctx)
    assert sum(series.datasets[0].values) == 3


async def test_recent_table(ctx, contacts_session):
    await _seed(contacts_session, n_now=3, n_old=0)
    w = next(w for w in overview_dashboard.widgets if w.id == "recent")
    table = await w.data(ctx)
    assert table.columns == ["Name", "Email", "Added"]
    assert len(table.rows) == 3
```

(The `contacts_session` fixture already exists in `modules/contacts/tests/conftest.py` per Phase 5. If not, point to the fixture name used by the other contacts tests.)

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

```python
# modules/contacts/src/parcel_mod_contacts/dashboards.py
from __future__ import annotations

from parcel_sdk.dashboards import (
    Ctx,
    Dashboard,
    KpiWidget,
    Kpi,
    LineWidget,
    TableWidget,
    scalar_query,
    series_query,
    table_query,
)


async def _total(ctx: Ctx) -> Kpi:
    n = await scalar_query(ctx.session, "SELECT COUNT(*) FROM mod_contacts.contact")
    return Kpi(value=int(n or 0))


async def _new_this_week(ctx: Ctx) -> Kpi:
    now_n = await scalar_query(
        ctx.session,
        "SELECT COUNT(*) FROM mod_contacts.contact "
        "WHERE created_at >= NOW() - INTERVAL '7 days'",
    )
    prev_n = await scalar_query(
        ctx.session,
        "SELECT COUNT(*) FROM mod_contacts.contact "
        "WHERE created_at >= NOW() - INTERVAL '14 days' "
        "  AND created_at <  NOW() - INTERVAL '7 days'",
    )
    now_n = int(now_n or 0)
    prev_n = int(prev_n or 0)
    delta = None
    if prev_n > 0:
        delta = (now_n - prev_n) / prev_n
    return Kpi(value=now_n, delta=delta, delta_label="vs prior week")


async def _new_30d(ctx: Ctx):
    return await series_query(
        ctx.session,
        """
        SELECT
          to_char(d, 'YYYY-MM-DD') AS day,
          COALESCE(c.n, 0) AS n
        FROM generate_series(
          (CURRENT_DATE - INTERVAL '29 days')::date,
          CURRENT_DATE,
          INTERVAL '1 day'
        ) AS d
        LEFT JOIN (
          SELECT date_trunc('day', created_at)::date AS day, COUNT(*) AS n
          FROM mod_contacts.contact
          WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
          GROUP BY 1
        ) c ON c.day = d::date
        ORDER BY d
        """,
        label_col="day",
        value_col="n",
    )


async def _recent(ctx: Ctx):
    return await table_query(
        ctx.session,
        """
        SELECT
          (first_name || ' ' || last_name) AS "Name",
          email AS "Email",
          to_char(created_at, 'YYYY-MM-DD HH24:MI') AS "Added"
        FROM mod_contacts.contact
        ORDER BY created_at DESC
        LIMIT 10
        """,
    )


overview_dashboard = Dashboard(
    name="contacts.overview",
    slug="overview",
    title="Contacts overview",
    permission="contacts.read",
    description="At-a-glance state of your contact list.",
    widgets=(
        KpiWidget(id="total", title="Total contacts", data=_total, col_span=1),
        KpiWidget(id="new_week", title="New this week", data=_new_this_week, col_span=1),
        LineWidget(id="new_30d", title="New contacts (last 30 days)", data=_new_30d, col_span=4),
        TableWidget(id="recent", title="Recently added", data=_recent, col_span=4),
    ),
)
```

Update `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
from parcel_mod_contacts.dashboards import overview_dashboard
# … inside module = Module(...):
    dashboards=(overview_dashboard,),
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --package parcel-mod-contacts pytest modules/contacts/tests/test_contacts_dashboard.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/dashboards.py modules/contacts/src/parcel_mod_contacts/__init__.py modules/contacts/tests/test_contacts_dashboard.py
git commit -m "feat(contacts): overview dashboard (total, new-this-week, 30-day series, recent)"
```

---

## Task 11: Full-suite regression + verification

- [ ] **Step 1: Run everything**

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run pyright
```

Expected: previous 259 tests + all new tests green; ruff + pyright clean.

- [ ] **Step 2: Manual smoke test (optional but recommended)**

```bash
docker compose up -d
docker compose run --rm shell migrate
uv run parcel dev
```

Then:
- Log in as admin → sidebar shows new "Dashboards" entry.
- Visit `/dashboards` → Contacts grouping appears with "Contacts overview".
- Visit `/dashboards/contacts/overview` → grid shows 4 widgets; each lazy-loads; charts render in Chart.js.
- Seed a few contacts, reload, confirm KPI + series + table update.

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`:
- Flip the roadmap table row for Phase 8 to ✅ done.
- Update "Current phase" section to describe Phase 8 as shipped (what landed, what's next).
- Append 3-5 new rows under "Locked-in decisions" capturing the concrete decisions from this spec (Chart.js 4 via CDN; per-dashboard permission; `Module.dashboards` field; SDK `scalar_query`/`series_query`/`table_query` helpers are params-only; widget endpoints are per-widget HTMX lazy-loads with `_widget_error.html` on failure).
- Set Phase 9 (Reports + PDF) as "next".

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): mark phase 8 done, promote phase 9 to next"
```

---

## Self-review against spec

- ✅ Chart library = Chart.js CDN → Task 7 adds `<script>` to `_base.html`.
- ✅ Widget data contract = async function with query helpers → Tasks 1 + 2.
- ✅ Per-dashboard permission → Tasks 7, 8 check `dashboard.permission in perms`.
- ✅ No caching → every widget endpoint hits DB per request; no cache code added.
- ✅ `Module.dashboards` field + auto-mount → Tasks 3 + 4 + 5.
- ✅ Five widget types → Tasks 1 (dataclasses), 8 (partials + endpoint).
- ✅ Per-widget isolation + error partial → Task 8's `try/except` + `_widget_error.html`.
- ✅ Contacts reference dashboard → Task 10.
- ✅ Sidebar "Dashboards" auto-link when visible → Task 9.
- ✅ Tests: SDK (Task 1, 2, 3), shell registry (Task 4), routes (Task 6, 7, 8), sidebar (Task 9), contacts (Task 10).
- ✅ Permission denial returns 404 (not 403) matching Phase 7c policy → Task 7.

No placeholders, no "similar to" refs, complete code blocks everywhere.
