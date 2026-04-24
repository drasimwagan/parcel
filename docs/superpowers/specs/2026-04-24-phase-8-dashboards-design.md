# Phase 8 — Dashboards (design)

> **Status.** Approved 2026-04-24. Next: implementation plan.
> **Predecessor.** Phase 7c (AI chat UI). Successor: Phase 9 (Reports + PDF).

## Goal

Give every Parcel module a first-class way to publish **dashboards** — glance-at-a-KPI surfaces composed of widgets that render independently. A dashboard is a declarative datum on the module manifest; the shell auto-mounts the routes, enforces permission, and renders the widgets. Contacts ships a reference "Contacts overview" dashboard in the same PR.

## Locked decisions

| Area | Decision |
|---|---|
| Chart library | **Chart.js 4.x via CDN**. Same pattern as Tailwind/HTMX/Alpine — no npm build step, themes drive chart palettes via CSS variables. |
| Widget data contract | Async Python function is the primary contract. SDK ships `scalar_query` / `series_query` / `table_query` helpers for common SQL shapes. Helpers are params-only; a module author building SQL strings needs the `raw_sql` capability (unchanged from Phase 7a). |
| Permission model | Per-dashboard. `Dashboard.permission` is a permission name the module already owns (e.g., `contacts.read`). No shell-level `dashboards.*` permissions. |
| Caching | None in Phase 8. Each widget hit runs its query. Revisit with real data after Phase 10 brings ARQ/Redis as first-class. |
| Declaration shape | New `Module.dashboards: tuple[Dashboard, ...] = ()`. Shell auto-mounts routes at `/dashboards/<module>/<slug>`. Modules write no dashboard routes. |
| Widget types | Five: `KpiWidget`, `LineWidget`, `BarWidget`, `TableWidget`, `HeadlineWidget`. |
| Rendering isolation | Each widget is fetched by its own HTMX request. One slow/failing widget does not block the page; errors render a small inline `_widget_error.html` while the rest of the grid loads. |

## SDK surface (additions)

New module `parcel_sdk.dashboards`:

```python
@dataclass(frozen=True)
class Ctx:
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
    delta: float | None = None        # percentage, signed
    delta_label: str | None = None    # e.g., "vs prior week"

@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[Any]]

# Widget types (frozen dataclasses)
class Widget: ...                     # base: id, title, col_span (1..4, default 2)
class KpiWidget(Widget):      data: Callable[[Ctx], Awaitable[Kpi]]
class LineWidget(Widget):     data: Callable[[Ctx], Awaitable[Series]]
class BarWidget(Widget):      data: Callable[[Ctx], Awaitable[Series]]
class TableWidget(Widget):    data: Callable[[Ctx], Awaitable[Table]]
class HeadlineWidget(Widget): text: str; href: str | None = None  # no data fn

@dataclass(frozen=True)
class Dashboard:
    name: str                # e.g., "contacts.overview"
    slug: str                # used in URL
    title: str
    permission: str          # permission user must have to see this dashboard
    widgets: tuple[Widget, ...]
    description: str = ""

# SDK helpers (query helpers — params-only)
async def scalar_query(session, sql: str, **params) -> Any: ...
async def series_query(session, sql: str, label_col: str, value_col: str, **params) -> Series: ...
async def table_query(session, sql: str, **params) -> Table: ...
```

`parcel_sdk.Module` gains `dashboards: tuple[Dashboard, ...] = ()`.

All new public names are re-exported from `parcel_sdk.__init__`; SDK `__version__` bumps to `0.4.0`.

## Shell surface

New package `parcel_shell/dashboards/`:

- `registry.py` — exposes `collect_dashboards(app)` that walks active modules (`app.state.modules`) and builds `app.state.dashboards: list[RegisteredDashboard]` where `RegisteredDashboard = (module_name, Dashboard)`. Called from `mount_modules` during boot and from sandbox-promotion paths that already re-run mount.
- `router.py` — FastAPI router mounted at `/dashboards`. Three endpoints (HTML-only, cookie-auth required via `current_user_html`):
  - `GET /dashboards` → `list.html`, filtered to dashboards whose `permission` is in `effective_permissions(user)`.
  - `GET /dashboards/{module}/{slug}` → `detail.html`. 404 if not found **or** user lacks permission (no 403 — consistent with 7c's cross-owner 404 policy).
  - `GET /dashboards/{module}/{slug}/widgets/{widget_id}` → renders the one widget's partial. Re-verifies permission. Awaits `widget.data(Ctx(session, user_id))`. On exception: logs structured error, renders `_widget_error.html`.
- `templates/dashboards/` — base templates list above; each widget type has its own partial.
- Sidebar: the shell's sidebar builder auto-adds a top-level **Dashboards** link when the user has ≥ 1 dashboard visible. No new SDK surface needed — the shell introspects `app.state.dashboards` against `effective_permissions`.

No new permissions, no new migrations, no new settings.

## Templates

- `list.html` groups dashboards by module name; each entry links to detail.
- `detail.html` renders a CSS grid (Tailwind `grid-cols-4`, gap). Each widget is a `<div hx-get=".../widgets/{id}" hx-trigger="load" hx-swap="outerHTML" class="col-span-{n}">…skeleton…</div>`. `HeadlineWidget` is rendered inline without a follow-up fetch (no data work).
- Widget partials own a consistent frame (`_widget_shell.html` macro with title + body slot) and differ only in the body:
  - `_widget_kpi.html` — large number, optional delta badge (green if positive, red if negative, muted label).
  - `_widget_line.html` / `_widget_bar.html` — `<canvas id="…">` plus a `<script>` block with `new Chart(ctx, {...})` consuming the widget's series data passed as a JSON blob.
  - `_widget_table.html` — simple `<table>` with Tailwind styling.
  - `_widget_headline.html` — heading + optional link.
  - `_widget_error.html` — muted "Couldn't load this widget." with widget id in a `<small>`.
- Chart.js palette pulls from CSS custom properties declared on `<html>` by the theme system, so `plain` / `blue` / `dark` all Just Work.

## Contacts reference dashboard

`modules/contacts/src/parcel_mod_contacts/dashboards.py`:

- Dashboard slug `overview`, title "Contacts overview", permission `contacts.read`.
- Widgets:
  1. `KpiWidget("total", "Total contacts")` — `scalar_query("SELECT COUNT(*) FROM mod_contacts.contact")`.
  2. `KpiWidget("new_week", "New this week")` — scalar + delta vs prior week (explicit Python fn; two scalar queries + compute).
  3. `LineWidget("new_30d", "New contacts (last 30 days)")` — series via `series_query` grouping by day.
  4. `TableWidget("recent", "Recently added")` — top 10 by `created_at`, columns `[Name, Company, Added]`.
- `__init__.py` passes `dashboards=(contacts_overview,)` to `Module(...)`.

## Data flow

1. Browser `GET /dashboards/contacts/overview`.
2. `detail.html` renders the grid; each cell lazy-loads its widget partial via HTMX.
3. Per-widget endpoint opens its own DB session (`get_session` dependency), re-checks permission, awaits data fn, renders partial.
4. Chart widgets emit `<canvas>` + initialization `<script>` inline — Chart.js (loaded once in base layout) picks up on DOM injection.
5. `HeadlineWidget` short-circuits: `detail.html` renders it immediately; no secondary fetch.

## Testing plan

- **SDK** (`packages/parcel-sdk/tests/test_dashboards.py`): dataclass construction + frozen-ness; `scalar_query`, `series_query`, `table_query` against a testcontainer Postgres; param-binding rejects SQL injection attempts gracefully (params only).
- **Shell registry** (`packages/parcel-shell/tests/test_dashboards_registry.py`): collects dashboards from mounted modules, re-collects after install/uninstall cycles.
- **Shell routes** (`packages/parcel-shell/tests/test_dashboards_routes.py`):
  - List page hidden when no dashboards visible; grouped by module when multiple.
  - Detail 404 for unknown module, unknown slug, or missing permission.
  - Each widget type renders its partial correctly.
  - One widget's data fn raising does not break the page; partial is `_widget_error.html`.
  - Unauthenticated GET redirects to login.
- **Contacts** (`modules/contacts/tests/test_dashboard.py`): each widget returns expected shape against seeded data; dashboard page renders all four widgets end-to-end.

Target: ~40 new tests, existing 259 remain green.

## Non-goals (Phase 8)

- Per-widget permissions.
- Any caching (Redis / in-process).
- Dashboard parameter forms (date-range pickers). Phase 9 introduces a parameter-form primitive for reports; dashboards can adopt it afterwards.
- Export, share, favorite.
- User-authored dashboards via UI.
- AI generator updates — the generator's system prompt will learn the dashboard contract in a follow-up spike once the shape is proven in Contacts.

## Risks & mitigations

- **Chart.js bundle size on first visit.** CDN + browser cache. Acceptable for admin-facing UI.
- **Widget data fn holding the session too long.** Each widget request has its own short-lived session; the per-request commit-or-rollback middleware still applies.
- **CSP.** Chart.js init scripts are inline. Align with existing inline-script posture (HTMX / Alpine already do this).
- **Dashboard discovery surprises.** The shell adds the "Dashboards" sidebar item only if ≥ 1 is visible — no empty page for users without permissions.
