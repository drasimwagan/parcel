# Phase 5 — Contacts Module Design

**Date:** 2026-04-23
**Phase:** 5 (next after Phase 4 — admin UI shell)
**Goal (from `CLAUDE.md`):** Contacts / CRM-lite demo module end-to-end.

## Scope

Phase 5 does two things in parallel, because they need each other:

1. **Extends `parcel-sdk`** so modules can contribute a UI — adds `router`, `templates_dir`, and `sidebar_items` to `Module`. Wires the shell to mount these on install and at boot.
2. **Ships the Contacts module** — two entities (`Contact`, `Company`), roomy two-line list pages, form-first detail pages, basic name/email search, two permissions (`contacts.read`, `contacts.write`).

The module is installable from `/modules` like any other, declares zero capabilities, and once installed appears in the sidebar as a new section. It becomes the fixture the AI generator (Phase 7) is benchmarked against.

Phase 5 does **not** ship: Note entity (deferred per brainstorming), tags, filters beyond simple search, bulk actions, CSV import/export, per-entity permissions (`companies.read` etc. — two permissions cover both entities), attachments, activity feed, the Phase 7 AI generator, or a `parcel-mod-contacts` static directory (no module-owned CSS/JS yet).

## Locked decisions from brainstorming

| Question | Decision |
|---|---|
| SDK integration surface | `Module.router` (FastAPI APIRouter), `Module.templates_dir` (Path), `Module.sidebar_items` (tuple of `SidebarItem`). No `static_dir` yet. |
| Entity scope | Contact + Company (related via nullable FK). Note deferred. |
| Permissions | `contacts.read`, `contacts.write`. No per-entity split. |
| URL prefix | `/mod/contacts/*` |
| List layout | Roomy two-line rows (name bold, email below, company right-aligned). |
| Detail layout | Form-first — no separate view mode. Save/Delete buttons in the header. |
| Search | Single text input, `ILIKE '%q%'` on relevant text columns. |

## Package layout additions

### `parcel-sdk` additions

```
packages/parcel-sdk/src/parcel_sdk/
  module.py                # extend Module dataclass
  sidebar.py               # new: SidebarItem dataclass (module-side)
```

`Module` gains three optional fields:

```python
@dataclass(frozen=True)
class Module:
    name: str
    version: str
    permissions: tuple[Permission, ...] = ()
    capabilities: tuple[str, ...] = ()
    alembic_ini: Path | None = None
    metadata: MetaData | None = None
    # New in Phase 5:
    router: APIRouter | None = None          # mounted at /mod/<name>
    templates_dir: Path | None = None        # added to Jinja loader search path
    sidebar_items: tuple[SidebarItem, ...] = ()
```

`SidebarItem` moves from the shell into the SDK so modules can declare their own:

```python
@dataclass(frozen=True)
class SidebarItem:
    label: str
    href: str                # absolute path, e.g. "/mod/contacts/"
    permission: str | None   # shown only if user has this permission
```

(The shell's internal `SidebarItem` in `parcel_shell/ui/sidebar.py` gets replaced by re-exporting the SDK version. Shell's `SIDEBAR` tuple is built with the SDK type.)

### Shell additions

```
packages/parcel-shell/src/parcel_shell/
  modules/
    integration.py         # mount_module_router(), register_module_templates(), sync_active_modules_on_boot()
    sidebar.py             # collect_module_sidebar() — walks active modules and returns their sidebar sections
  ui/
    sidebar.py             # (modified) re-exports SDK SidebarItem; composes shell SIDEBAR + module contributions at render time
```

Shell lifespan gains a step after `sync_on_boot`: for each active installed module, re-load its `Module` object from discovery, mount its router, register its templates, and cache its sidebar items on `app.state.active_modules`.

Boot-time wiring is idempotent (adding the same router twice is a FastAPI error — the shell checks `app.state.active_modules` before mounting).

### Contacts module

```
modules/contacts/
  pyproject.toml                     # entry point contacts = "parcel_mod_contacts:module"; dep on parcel-sdk
  src/parcel_mod_contacts/
    __init__.py                      # exports `module = Module(...)`
    models.py                        # Contact, Company SQLAlchemy models on a local MetaData(schema="mod_contacts")
    service.py                       # pure async service functions
    schemas.py                       # Pydantic models (not used in MVP; kept for JSON endpoints later)
    router.py                        # APIRouter with /mod/contacts/* routes
    sidebar.py                       # the SidebarItem tuple for the module
    templates/
      contacts/
        list.html
        new.html
        detail.html
        row.html                     # partial for HTMX swap
      companies/
        list.html
        new.html
        detail.html
        row.html
    alembic.ini
    alembic/
      env.py                         # one-liner using parcel_sdk.alembic_env
      script.py.mako
      versions/
        0001_create_contact_company.py
```

### Test file additions

```
packages/parcel-shell/tests/
  test_sdk_module_extensions.py      # new Module fields, SidebarItem shape
  test_module_integration.py         # mount/unmount router at install/uninstall, sidebar collection, template loader registration

modules/contacts/tests/
  conftest.py                        # reuse shell's committing_admin via sys.path — tests run against the real running app with contacts installed
  test_contacts_migrations.py
  test_contacts_service.py
  test_contacts_router.py            # HTMX round-trips on /mod/contacts/*
```

### Module boundaries

- **`parcel_sdk.module`** — pure dataclasses. No FastAPI import — `router: APIRouter | None` uses `TYPE_CHECKING` plus string annotation. The field is populated by modules, so they import `APIRouter` normally.
- **`parcel_shell.modules.integration`** — one file, three functions: `mount_module(app, discovered)`, `unmount_module(app, name)`, `sync_active_modules(app, sessionmaker)`. Pure in the sense that it takes an app and a discovered-module; no global state beyond what's stashed on `app.state`.
- **`parcel_shell.ui.sidebar`** — the base `SIDEBAR` stays static. A new helper `visible_sections(perms, module_sections)` merges shell and module-contributed sections before rendering. Callers supply `app.state.active_modules_sidebar` when available.
- **`parcel_mod_contacts.models`** — declarative models against `MetaData(schema="mod_contacts")`. No mention of shell internals.
- **`parcel_mod_contacts.service`** — pure async functions over `AsyncSession`: `list_contacts(db, *, q=None, offset=0, limit=50)`, `create_contact(...)`, etc. Also takes an opaque `permissions_ok: bool` for any checks — more likely the router layer does permission checks before calling services.
- **`parcel_mod_contacts.router`** — thin FastAPI layer that reuses the shell's `html_require_permission`. Module templates extend the shell's `_base.html` via Jinja `{% extends %}`.

## SDK + shell integration flow

### On install (`POST /admin/modules/install`)

Phase 3's `install_module` is extended: after the alembic upgrade succeeds, if the module has a router / templates_dir / sidebar_items, call `integration.mount_module(app, discovered)` to:

1. Add `module.templates_dir` to the Jinja `FileSystemLoader` chain (prepended so modules can override shell templates if they need to).
2. `app.include_router(module.router, prefix=f"/mod/{module.name}")`.
3. Stash the module's sidebar items in `app.state.active_modules_sidebar[name] = module.sidebar_items`.
4. Permissions are already synced by the in-memory registry + migration upsert.

### On uninstall (`POST /admin/modules/{name}/uninstall`)

Soft uninstall (default) leaves the router mounted for the current process but clears the sidebar entry and marks the row inactive. FastAPI doesn't cleanly support removing a router at runtime — we document that a restart is required for soft-uninstall to fully take routes offline. Next boot will skip mounting (since `sync_on_boot` flipped the row to inactive).

Hard uninstall (`?drop_data=true`) runs the downgrade, drops the schema, removes the installed_modules row. Same "restart to remove routes" caveat applies.

### On boot (`lifespan`)

After existing `sync_on_boot`:

```python
async with sessionmaker() as s:
    active = await service.list_active_modules(s)
index = {d.module.name: d for d in discover_modules()}
for row in active:
    d = index.get(row.name)
    if d is not None:
        mount_module(app, d)
```

## Contacts module specifics

### Schema (`mod_contacts`)

```sql
CREATE TABLE mod_contacts.companies (
  id            uuid PRIMARY KEY,
  name          text NOT NULL UNIQUE,
  website       text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mod_contacts.contacts (
  id            uuid PRIMARY KEY,
  email         text NOT NULL UNIQUE,
  first_name    text,
  last_name     text,
  phone         text,
  company_id    uuid REFERENCES mod_contacts.companies(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_contacts_email ON mod_contacts.contacts (email);
CREATE INDEX ix_contacts_company_id ON mod_contacts.contacts (company_id);
```

Migration `0001_create_contact_company.py` creates both tables and indexes; downgrade drops them.

### Service functions

```python
# modules/contacts/src/parcel_mod_contacts/service.py

async def list_contacts(db, *, q: str | None = None, offset=0, limit=50) -> tuple[list[Contact], int]: ...
async def get_contact(db, contact_id: uuid.UUID) -> Contact | None: ...
async def create_contact(db, *, email, first_name, last_name, phone=None, company_id=None) -> Contact: ...
async def update_contact(db, *, contact: Contact, ...) -> Contact: ...
async def delete_contact(db, *, contact: Contact) -> None: ...

async def list_companies(db, *, q=None, offset=0, limit=50) -> tuple[list[Company], int]: ...
async def get_company(db, company_id: uuid.UUID) -> Company | None: ...
async def create_company(db, *, name, website=None) -> Company: ...
async def update_company(db, *, company: Company, ...) -> Company: ...
async def delete_company(db, *, company: Company) -> None: ...
```

### Permissions (declared on the module, seeded into `shell.permissions` on install)

| name | description |
|---|---|
| `contacts.read` | View contacts and companies |
| `contacts.write` | Create, update, and delete contacts and companies |

### Routes

All under `/mod/contacts` prefix, all require a permission via `html_require_permission`:

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/` | `contacts.read` | Contacts list (roomy two-line rows) with search input |
| GET | `/new` | `contacts.write` | New-contact form |
| POST | `/` | `contacts.write` | Create contact; redirect to detail |
| GET | `/{id}` | `contacts.read` | Form-first detail page (editable fields visible immediately) |
| POST | `/{id}/edit` | `contacts.write` | Save; HTMX returns updated row partial |
| POST | `/{id}/delete` | `contacts.write` | Delete; HTMX returns 204; page redirects to `/mod/contacts/` |
| GET | `/companies` | `contacts.read` | Company list |
| GET | `/companies/new` | `contacts.write` | New-company form |
| POST | `/companies` | `contacts.write` | Create |
| GET | `/companies/{id}` | `contacts.read` | Detail (form-first) |
| POST | `/companies/{id}/edit` | `contacts.write` | Save via HTMX |
| POST | `/companies/{id}/delete` | `contacts.write` | Delete |

### Search

List pages accept `?q=<string>`. If present:

- **Contacts:** `WHERE email ILIKE '%q%' OR first_name ILIKE '%q%' OR last_name ILIKE '%q%'`
- **Companies:** `WHERE name ILIKE '%q%'`

Search form uses `hx-get` with `hx-trigger="keyup changed delay:300ms, search"` and `hx-target="#list-body"` so the list updates as the user types, without a full page reload.

### Sidebar contribution

```python
# modules/contacts/src/parcel_mod_contacts/sidebar.py
from parcel_sdk import SidebarItem

SIDEBAR_ITEMS = (
    SidebarItem(label="Contacts", href="/mod/contacts/", permission="contacts.read"),
    SidebarItem(label="Companies", href="/mod/contacts/companies", permission="contacts.read"),
)
```

The shell's sidebar render composes shell sections + one section per active module. Module sections are named after the module label (from `Module.name` title-cased) and appear after shell sections.

## Data flow per mutation (representative)

Editing a contact:

1. User lands on `GET /mod/contacts/{id}`. Template renders a form — each field is a real `<input>` with the current value. Action is `hx-post="/mod/contacts/{id}/edit"`, target is `#contact-{id}-row` (not visible on this page but the ID is set on the form's outer container for later).
2. User changes `first_name`, clicks Save. HTMX posts; server calls `service.update_contact(...)`; returns `row.html` partial with `HX-Trigger: {"flash": {"kind": "success", "msg": "Contact saved."}}` so the toast region shows.
3. The form stays on the detail page — after successful POST, server responds with `HX-Location: /mod/contacts/{id}` so HTMX triggers a page replacement to the (now up-to-date) detail. (Alternative: re-render the detail page; using `HX-Location` is simpler.)
4. Validation errors return the same form with error messages inline.

Deleting a contact:

1. Delete button is a plain `<button>` with `hx-post="/mod/contacts/{id}/delete" hx-confirm="Delete this contact?"`.
2. On 204, HTMX fires `htmx:afterRequest`; a small inline `hx-on::after-request` redirects to `/mod/contacts/`.

## Testing strategy

### SDK integration tests

`test_sdk_module_extensions.py` — Module accepts router/templates_dir/sidebar_items as optional fields; defaults are None/empty; hashable/equal etc.

`test_module_integration.py` — given a minimal fixture module with an APIRouter that has one route, call `mount_module(app, ...)`, assert the route is reachable, the templates_dir is in the Jinja loader, and the sidebar items are on app state.

### Contacts end-to-end

Contacts tests live in `modules/contacts/tests/`. They spin up the shell (like Phase 4), install the Contacts module via `service.install_module` during a session-scoped fixture, and exercise the HTML routes through `committing_admin`. After the session, the fixture runs hard uninstall.

Inventory (~20 tests):

1. `test_contacts_migrations.py` — `alembic upgrade head` creates the two tables; downgrade drops them.
2. `test_contacts_service.py` — CRUD happy paths for contacts + companies; company deletion nulls out `company_id` on related contacts; search filters.
3. `test_contacts_router.py` — 
   - `/mod/contacts/` renders; only visible to users with `contacts.read`.
   - Create via POST, redirects to detail.
   - Edit via HTMX returns updated row; flash toast triggered.
   - Delete via HTMX returns 204; record gone from list.
   - Search query filters the visible rows.
   - Without `contacts.read` the sidebar doesn't contain Contacts/Companies items.
4. `test_contacts_sidebar.py` — after install, a logged-in admin's dashboard shows a "Contacts" section with two items.

Module tests run as part of `uv run pytest` (the module is a workspace member and its tests collect normally).

## Dependency changes

`modules/contacts/pyproject.toml`:

- Becomes a real package with `parcel-sdk` (workspace) dep, entry-point declaration, `packages = ["src/parcel_mod_contacts"]`.
- No other runtime deps needed; sqlalchemy + alembic come via parcel-sdk.

No new shell-side runtime deps. No workspace-root additions.

## Definition of done

1. `docker compose build shell && docker compose up -d shell` — container includes the contacts module package (via `uv sync --all-packages` in the Dockerfile). Logs show `module.discovered name=contacts` at boot.
2. Browser: visit `/modules` as admin → Contacts appears as "available". Install it (zero capabilities → checkbox unnecessary). Detail page shows "Installed and active".
3. Restart container; sidebar now contains a "Contacts" section with Contacts / Companies items.
4. Create a company, create a contact linked to that company, edit the contact's phone, delete the contact — all via browser.
5. Search "ada" in the contacts list filters the rows live.
6. Hard-uninstall the Contacts module → schema dropped, sidebar section gone, permissions removed.
7. `uv run pytest` green across all phases (Phase 1 + 2 + 3 + 4 + 5).
8. `uv run ruff check packages/parcel-shell packages/parcel-sdk modules/contacts` clean.
9. `uv run pyright packages/parcel-shell packages/parcel-sdk modules/contacts` — 0 errors.
10. CLAUDE.md: Phase 5 ✅ / Phase 6 ⏭; sidebar-contribution pattern noted.

## Out of scope (deferred)

- Note entity — would add a third CRUD set without teaching anything new.
- Tags, activity feeds, attachments.
- Bulk actions (multi-select delete, bulk import).
- CSV import/export.
- Per-entity permissions (separate companies.* set).
- Module static assets (CSS/JS) — `static_dir` SDK field waits for a module that needs it.
- Template override mechanism (modules overriding shell templates) — the loader order allows it but Phase 5 doesn't ship any overrides.
- Search by company in the contacts list — string-match only.
- Pagination UI beyond next/prev (same as Phase 4).
- Phase 7's AI generator consuming this module as a fixture.
