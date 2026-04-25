# Module Authoring Guide

**Status:** Current through Phase 8. The SDK surface is stable at `parcel-sdk` 0.4.x.

## What a Parcel module is

A pip-installable Python package that:

1. Depends only on `parcel-sdk` (not `parcel-shell`).
2. Exposes a `Module` object via the `parcel.modules` entry point.
3. Owns its own Postgres schema (`mod_<name>`) and Alembic migration directory.
4. Declares its permissions and capabilities in the manifest.

## Quickstart — scaffold with the CLI

```bash
uv run parcel new-module widgets
uv sync --all-packages
uv run parcel install ./modules/widgets
uv run parcel dev
# visit http://localhost:8000/mod/widgets/
```

`parcel new-module` writes:

```
modules/widgets/
  pyproject.toml                          # parcel-sdk dep, entry point to parcel_mod_widgets:module
  README.md
  src/parcel_mod_widgets/
    __init__.py                           # exports `module`
    module.py                             # Module(...) manifest
    models.py                             # DeclarativeBase bound to mod_widgets schema
    router.py                             # APIRouter; one hello-world view
    alembic.ini                           # points at ./alembic
    alembic/
      env.py                              # calls parcel_sdk.alembic_env.run_async_migrations
      script.py.mako
      versions/0001_init.py               # CREATE SCHEMA IF NOT EXISTS "mod_widgets"
    templates/widgets/index.html
  tests/test_smoke.py
```

## The `Module` manifest

```python
# modules/widgets/src/parcel_mod_widgets/__init__.py
from pathlib import Path

from parcel_mod_widgets.models import metadata
from parcel_mod_widgets.router import router
from parcel_sdk import Module, Permission, SidebarItem

module = Module(
    name="widgets",
    version="0.1.0",
    permissions=(
        Permission("widgets.read", "View widgets"),
        Permission("widgets.write", "Create and edit widgets"),
    ),
    capabilities=(),                                      # e.g., ("http_egress",) — admin approves at install
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=(
        SidebarItem(label="Widgets", href="/mod/widgets/", permission="widgets.read"),
    ),
)
```

```toml
# pyproject.toml
[project]
name = "parcel-mod-widgets"
dependencies = ["parcel-sdk", "fastapi>=0.115"]

[project.entry-points."parcel.modules"]
widgets = "parcel_mod_widgets:module"
```

## Writing routes — `parcel_sdk.shell_api`

Modules get DB sessions, auth, permission checks, flashes, templates, and the composed sidebar exclusively through `parcel_sdk.shell_api`. You never import `parcel_shell.*`.

```python
# router.py
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_sdk import shell_api
from parcel_sdk.shell_api import Flash

router = APIRouter(tags=["mod-widgets"])


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Any = Depends(shell_api.require_permission("widgets.read")),
    db: AsyncSession = Depends(shell_api.get_session()),
) -> Response:
    perms = await shell_api.effective_permissions(request, user)
    tpl = shell_api.get_templates()
    return tpl.TemplateResponse(
        request,
        "widgets/index.html",
        {
            "user": user,
            "sidebar": shell_api.sidebar_for(request, perms),
            "active_path": "/mod/widgets",
            "settings": request.app.state.settings,
        },
    )


@router.post("/do-something")
async def do_it(
    request: Request,
    user: Any = Depends(shell_api.require_permission("widgets.write")),
) -> Response:
    response = RedirectResponse(url="/mod/widgets/", status_code=303)
    shell_api.set_flash(response, Flash(kind="success", msg="Done."))
    return response
```

### The six facade functions

| Symbol | Use for |
|---|---|
| `shell_api.get_session()` | `db: AsyncSession = Depends(shell_api.get_session())` — one session per request, auto-commit on success. |
| `shell_api.require_permission(name)` | HTML-auth dep. Redirects to `/login?next=…` if unauthed, to `/` with an error flash if missing the permission. |
| `shell_api.effective_permissions(request, user)` | Compute the user's full permission set (for filtering sidebar items, conditional UI). |
| `shell_api.set_flash(response, flash)` | Attach a one-shot banner message to the next page view. |
| `shell_api.get_templates()` | Shared `Jinja2Templates`. Your `templates_dir` is already on the loader chain — reference templates as `"<name>/whatever.html"`. |
| `shell_api.sidebar_for(request, perms)` | Composed sidebar (shell sections + every active module's section) filtered by the user's perms, for template context. |
| `shell_api.Flash(kind, msg)` | Frozen dataclass. `kind` is `"success" \| "error" \| "info"`. |

## Models

```python
# models.py
from sqlalchemy import MetaData, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="mod_widgets")


class WidgetsBase(DeclarativeBase):
    metadata = metadata  # type: ignore[assignment]


class Widget(WidgetsBase):
    __tablename__ = "widgets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[...] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
```

Bind every table to your `metadata` so Alembic autogenerate picks up your models and nothing else.

## Migrations

Each module owns its own Alembic directory and `alembic_version` row (lives inside `mod_<name>.alembic_version`, not `public`, so downgrading past the shell baseline is safe).

```bash
# create a new revision
cd modules/widgets/src/parcel_mod_widgets
uv run alembic revision --autogenerate -m "add widget fields"

# apply (or use `uv run parcel migrate --module widgets`)
uv run alembic upgrade head
```

The scaffold's initial migration is just `CREATE SCHEMA IF NOT EXISTS "mod_widgets"`. Add your tables in subsequent revisions.

## Templates

Jinja templates live under `src/parcel_mod_<name>/templates/<name>/`. Your templates can `{% extends "_base.html" %}` — the shell's base template is already on the loader. Template context you'll typically pass:

- `user`, `sidebar`, `active_path`, `settings` (the four keys `_base.html` expects)
- Anything else your view needs.

## Testing

```python
# tests/test_smoke.py
from parcel_mod_widgets import module


def test_module_identity() -> None:
    assert module.name == "widgets"
    assert module.version == "0.1.0"
```

Integration tests can import `parcel_shell.*` freely — the SDK-only constraint applies to **runtime/library** code, not tests. The workspace-root `conftest.py` binds `shell_api` at pytest collection time so module imports that reach into `Depends(shell_api.require_permission(...))` at decoration time don't crash.

## Capabilities and the sandbox gate (Phase 7a)

As of Phase 7a, `capabilities` is a real enforcement hook when a module is installed through the sandbox pipeline (admin uploads a zip, or `parcel sandbox install <path>`). The gate runs `ruff` + `bandit` + a custom AST policy and rejects anything that imports or calls a dangerous primitive unless the manifest declares the matching capability.

**The four capability values:**

| Capability | Unlocks |
|---|---|
| `filesystem` | `import os`, `open(...)` |
| `process` | `import subprocess` |
| `network` | `socket`, `urllib`, `http.*`, `httpx`, `requests`, `aiohttp` |
| `raw_sql` | `sqlalchemy.text(...)` |

Declare them in the `Module()` manifest:

```python
module = Module(
    name="widgets",
    version="0.1.0",
    capabilities=("network",),  # module plans to make outbound HTTP calls
    ...
)
```

**Always blocked** regardless of what's declared: `import sys`, `import importlib`, anything from `parcel_shell.*`, calls to the four dynamic-code builtins (`eval`/`exec`/`compile`/`__import__`), and attribute access to sandbox-escape dunders (`__class__`, `__subclasses__`, `__globals__`, `__builtins__`, `__mro__`, `__code__`).

The gate only scans **runtime** code. Tests are allowed to import `parcel_shell.*` or call `subprocess` freely — the SDK-only constraint is a runtime rule, not a test rule.

Human-authored modules installed via `parcel install` or `POST /admin/modules/install` bypass the gate entirely (trusted input). The gate exists so that AI-generated modules — landing in Phase 7b — go through a consistent safety check before the admin sees a preview.

## Dashboards (Phase 8)

A module can ship one or more `Dashboard` objects — glance-at-a-KPI surfaces composed of widgets. The shell auto-mounts them at `/dashboards/<module>/<slug>`; you don't write any routes.

### Declaring a dashboard

```python
# modules/widgets/src/parcel_mod_widgets/dashboards.py
from parcel_sdk.dashboards import (
    Ctx, Dashboard, Kpi, KpiWidget, LineWidget, TableWidget,
    scalar_query, series_query, table_query,
)


async def _total(ctx: Ctx) -> Kpi:
    n = await scalar_query(ctx.session, "SELECT COUNT(*) FROM mod_widgets.widget")
    return Kpi(value=int(n or 0))


async def _new_30d(ctx: Ctx):
    return await series_query(
        ctx.session,
        """
        SELECT to_char(d, 'YYYY-MM-DD') AS day, COALESCE(c.n, 0) AS n
        FROM generate_series(
          (CURRENT_DATE - INTERVAL '29 days')::date, CURRENT_DATE, INTERVAL '1 day'
        ) AS d
        LEFT JOIN (
          SELECT date_trunc('day', created_at)::date AS day, COUNT(*) AS n
          FROM mod_widgets.widget
          WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
          GROUP BY 1
        ) c ON c.day = d::date
        ORDER BY d
        """,
        label_col="day",
        value_col="n",
    )


overview_dashboard = Dashboard(
    name="widgets.overview",
    slug="overview",
    title="Widgets overview",
    permission="widgets.read",
    description="At-a-glance state of your widgets.",
    widgets=(
        KpiWidget(id="total", title="Total widgets", data=_total, col_span=1),
        LineWidget(id="new_30d", title="Created in last 30 days", data=_new_30d, col_span=4),
    ),
)
```

Then plug it into the manifest:

```python
module = Module(
    name="widgets",
    version="0.1.0",
    # ... permissions, metadata, router, etc ...
    dashboards=(overview_dashboard,),
)
```

That's it. The shell collects the dashboard at mount time, adds a "Dashboards" entry to the sidebar (only if the user has `widgets.read`), and serves the list/detail pages. Each widget fetches its data via its own HTMX request — a slow widget doesn't block the page, and a failing widget renders a small error card without killing siblings.

### Widget types

| Type | Data function returns | Renders as |
| --- | --- | --- |
| `KpiWidget` | `Kpi(value, delta=None, delta_label=None)` | Big number with optional signed delta |
| `LineWidget` | `Series(labels, datasets)` | Chart.js line chart |
| `BarWidget` | `Series(labels, datasets)` | Chart.js bar chart |
| `TableWidget` | `Table(columns, rows)` | Plain HTML table |
| `HeadlineWidget` | — (has `text` / `href` directly) | Static heading, no data fetch |

`col_span` (default 2) controls how wide the widget is on a 4-column grid.

### SDK query helpers

The three `parcel_sdk.dashboards.*` query helpers wrap `sqlalchemy.text()` with bound parameters. They are **params-only** — always bind via kwargs, never interpolate into the SQL string:

```python
# Good — value bound, safe
n = await scalar_query(ctx.session, "SELECT COUNT(*) FROM x WHERE v > :min", min=5)

# Bad — interpolation; triggers the Phase 7a `raw_sql` gate and is a SQL-injection footgun
n = await scalar_query(ctx.session, f"SELECT COUNT(*) FROM x WHERE v > {user_input}")
```

- `scalar_query(session, sql, **params) -> Any` — first column of first row, `None` if empty.
- `series_query(session, sql, label_col, value_col, **params) -> Series` — coerces values to `float` for Chart.js.
- `table_query(session, sql, **params) -> Table` — reads columns from the cursor (preserves headers on empty results).

These live inside the SDK (trusted code), so using them does **not** require declaring the `raw_sql` capability in your manifest. If you need to build SQL strings yourself (outside these helpers), you do — see the Capabilities section above.

### Data returned from widgets

- Table cells are rendered via Jinja's default `{{ cell }}` (`str()` with HTML escaping). Format timestamps, currencies, etc. in SQL or in your data function — don't expect the template to do it.
- Chart values should be plain numbers. Postgres `numeric` columns come back as `Decimal` — `series_query` coerces for you; if you write a custom data function for `LineWidget`/`BarWidget`, cast to `float`.
- Widget `data` callables are async and receive a single `Ctx(session, user_id)`. The session is the same short-lived request session; don't hold it across awaits outside its scope.

### Permissions

`Dashboard.permission` is one of your module's own permissions (e.g., `widgets.read`) — not a `dashboards.*` name. Users without it don't see the dashboard in the sidebar list and get a 404 if they visit the URL directly.

### Testing dashboards

Widget data functions are plain async functions; test them directly against a testcontainers-backed session:

```python
@pytest.fixture()
def ctx(widgets_session) -> Ctx:
    return Ctx(session=widgets_session, user_id=uuid4())


async def test_total_kpi(ctx, widgets_session):
    # seed rows...
    w = next(w for w in overview_dashboard.widgets if w.id == "total")
    kpi = await w.data(ctx)
    assert kpi.value == 3
```

The `modules/contacts/tests/test_contacts_dashboard.py` file in the repo is a complete reference.


## Reports (Phase 9)

A module can declare any number of **reports** — printable, parameterised
documents that admins fill out a form for, preview as HTML, and download as
PDF. Reports complement dashboards: dashboards are live snapshots, reports are
point-in-time documents you can attach to a ticket or send by email.

### Declaring a report

```python
# src/parcel_mod_<name>/reports/<slug>.py
from datetime import date
from pydantic import BaseModel
from sqlalchemy import select

from parcel_sdk import Report, ReportContext

from parcel_mod_widgets.models import Widget


class WidgetReportParams(BaseModel):
    color: str | None = None
    created_after: date | None = None


async def widget_report_data(ctx: ReportContext) -> dict[str, object]:
    p: WidgetReportParams = ctx.params
    stmt = select(Widget).order_by(Widget.created_at.desc())
    if p.color:
        stmt = stmt.where(Widget.color.ilike(f"%{p.color}%"))
    if p.created_after:
        stmt = stmt.where(Widget.created_at >= p.created_after)
    rows = (await ctx.session.scalars(stmt)).all()
    return {
        "widgets": rows,
        "total": len(rows),
        "param_summary": (f"color={p.color}" if p.color else "all widgets"),
    }


widget_directory = Report(
    slug="directory",                # url-safe; unique per module
    title="Widget directory",
    permission="widgets.read",       # one of your module's permissions
    template="reports/directory.html",
    data=widget_report_data,
    params=WidgetReportParams,       # or `None` for parameter-less reports
)
```

Wire it into your manifest:

```python
module = Module(
    name="widgets",
    version="0.1.0",
    permissions=(Permission("widgets.read", "View widgets"),),
    templates_dir=Path(__file__).parent / "templates",
    reports=(widget_directory,),
)
```

The shell auto-mounts three URLs as soon as the module is active:

| Method | Path | Purpose |
|---|---|---|
| GET | `/reports/widgets/directory` | Parameter form |
| GET | `/reports/widgets/directory/render?<params>` | HTML preview, wrapped in admin chrome |
| GET | `/reports/widgets/directory/pdf?<params>` | Streamed `application/pdf` download |

If the user lacks `widgets.read`, all three return **404** (consistent with
dashboards / the AI chat — never leaks existence).

### Writing the template

Module report templates extend the shell's `reports/_report_base.html`. The
base template provides A4 portrait, 20mm margins, a page header with the
report title, and a footer page counter. Override `{% block page_css %}` for
landscape, Letter, or custom margins; override `{% block content %}` for the
body.

```html
{% extends "reports/_report_base.html" %}
{% block page_css %}@page { size: A4 landscape; }{% endblock %}
{% block content %}
  <p>Total: <strong>{{ total }}</strong> widget{{ "" if total == 1 else "s" }}</p>
  <table>
    <thead>
      <tr><th>Name</th><th>Color</th><th>Created</th></tr>
    </thead>
    <tbody>
      {% for w in widgets %}
        <tr>
          <td>{{ w.name }}</td>
          <td>{{ w.color }}</td>
          <td>{{ w.created_at.strftime("%Y-%m-%d") }}</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
{% endblock %}
```

Notes:

- The base CSS is intentionally tight (10pt body, 16pt title, 9pt header/footer). The report's HTML is rendered by headless Chromium, but the print pipeline waits only for the `load` event — long-running JS is not your friend in a printable document.
- Module templates live under `<module_pkg>/templates/`. The shell prepends the directory to the Jinja loader at mount time.
- `param_summary` returned from your data function appears in the page header next to "Generated &lt;timestamp&gt;". If you don't return one, the shell auto-builds `key=value; key=value` from the parameter model.

### Parameter forms

The shell auto-renders an HTML form from the Pydantic params model. Supported
types and their controls:

| Pydantic field | HTML control |
|---|---|
| `str`, `str \| None` | `<input type="text">` |
| `int` | `<input type="number" step="1">` |
| `float` | `<input type="number" step="any">` |
| `bool` | `<input type="checkbox">` |
| `date` | `<input type="date">` |
| `datetime` | `<input type="datetime-local">` |
| `Literal["a", "b"]` | `<select>` |
| `Enum` subclass | `<select>` |

Optional fields (`T | None`) drop the `required` attribute. `Field(description=...)`
becomes the helper text under the input. For a multi-line textarea, set
`json_schema_extra={"widget": "textarea"}`. Anything more exotic? Set
`Report.form_template = "reports/your_form.html"` and write your own Jinja
partial; the shell will pass `{values, errors, model}` to it.

Validation errors come from Pydantic's `ValidationError`; the shell re-renders
the form with messages grouped per field, no DB hit on `report.data`.

### Permissions

`Report.permission` is one of your module's own permissions. There are no
`reports.*` shell permissions and no shell migrations — adding a report is
purely a manifest change.

If `Report.permission` doesn't match any permission your module declares,
the shell logs `module.report.unknown_permission` at WARN on mount. The
report still mounts, but no user can ever see it.

### Testing reports

Data functions are plain async coroutines. Hit them with a real session and
the parameter model:

```python
async def test_directory_no_filters_returns_all(contacts_session):
    # seed contacts...
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(),
    )
    out = await directory_data(ctx)
    assert out["total"] == 3
```

For end-to-end coverage of the route, mount the module on the live app
fixture and `GET /reports/<module>/<slug>{,/render,/pdf}`.
`modules/contacts/tests/test_contacts_report_directory.py` and the
`test_directory_report_*` block in `modules/contacts/tests/test_contacts_router.py`
are complete references.

### PDF rendering

The shell uses **Playwright + headless Chromium** to render the report
template (extending `_report_base.html`, no admin chrome) into PDF bytes.
Chromium ships as a self-contained ~250 MB binary — no GTK, no Cairo, no
Pango, no Windows GTK runtime. The Docker image runs
`playwright install --with-deps chromium`; on a fresh dev machine you'll
need to run that once:

```bash
uv run playwright install chromium
```

After that, PDF tests run cross-platform with no skip markers. The page
size and margins come from your report's CSS `@page` rule (Playwright
honours this via `prefer_css_page_size=True`). The page counter at the
bottom of each printed page is forced through Playwright's `footer_template`
rather than CSS — Chromium ignores the CSS Generated Content for Paged
Media spec (`@top-center` / `@bottom-right`), so don't put running headers
or footers in your `@page` rule.

Each request spins up a fresh Chromium process (~500 ms-1 s startup). At
Phase 9 volumes that's acceptable. If a deployment ever serves enough PDF
requests for the cold start to matter, swap to a long-lived browser in
`app.state` and reuse contexts.
