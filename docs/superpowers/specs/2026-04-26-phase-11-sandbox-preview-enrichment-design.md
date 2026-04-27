# Phase 11 — Sandbox preview enrichment

**Status:** design approved 2026-04-26.
**Builds on:** Phase 7a (sandbox install + gate), Phase 9 (Playwright + Chromium), Phase 10b (ARQ worker + Redis).

## Goal

When a candidate module lands in the sandbox — uploaded zip, `parcel sandbox install`, or AI-generated — produce a static visual preview the operator can scan in seconds: full-page screenshots of every declared route at three viewport sizes, optionally driven by sample data the module's author seeded. Surface those screenshots on the existing `/sandbox/<id>` detail page. Replaces the "click through it live" preview with "look at these screenshots" and removes the need to give every reviewer a real session in the sandbox URL prefix.

## Pre-decided context (from `CLAUDE.md`)

- Sample data is sourced from a Claude- or human-authored `seed.py` shipped with the module. No synthetic / polyfactory fallback in this phase — modules without `seed.py` render against empty schemas (still useful: empty-state UI verification).
- Playwright + headless Chromium is already in the shell image since Phase 9. No new infra.
- Storage is local filesystem under `var/sandbox/<uuid>/previews/` — same place as the rest of the sandbox files.
- Three viewport sizes: mobile 375px, tablet 768px, desktop 1280px.
- Hard cap of 30 screenshots per sandbox to bound runtime and disk.
- Rendering rides on ARQ (Phase 10b) — auto-fires on sandbox creation, runs in the worker container, inline-mode short-circuit for tests.

## Architecture

A new `parcel_shell.sandbox.previews` subsystem orchestrates seed-data injection, headless Chromium navigation, screenshot persistence, and admin UI surfacing.

### Components

| Component | Responsibility |
|---|---|
| `previews.runner` | The render coroutine. Mints the cookie, loads the sandbox module, runs seed, walks routes, drives Playwright, writes files + DB. One implementation, two entry points (worker + inline). |
| `previews.routes` | Pure helper turning a loaded `Module` into a list of route paths to capture. Knows auto-walk + `preview_routes` override + path-param resolution. |
| `previews.storage` | Writes/reads PNGs under `var/sandbox/<uuid>/previews/`. Centralises filename hashing and path validation for the served-image route. |
| `previews.seed_runner` | Imports `seed.py` from the loaded sandbox module (file presence is the discovery mechanism), opens an `AsyncSession` against the schema-patched metadata, awaits `seed(session)`, commits. |
| `previews.identity` | Idempotently syncs the `sandbox-preview` builtin role's permissions; signs a `parcel_session` cookie value for the seeded synthetic user via `itsdangerous`. |
| `previews.queue` | Honours `PARCEL_WORKFLOWS_INLINE`; either `asyncio.create_task` or `arq_pool.enqueue_job`. |
| `previews.worker` | ARQ-registered job function `render_sandbox_previews(ctx, sandbox_id)`. Joins the existing two job functions in `WorkerSettings.functions`. |

### Data flow on sandbox creation (auto-fire)

```
POST /sandbox  (zip upload)
   → create_sandbox(...)            # existing — extract, gate, schema, alembic, mount, DB row
   → previews.queue.enqueue(sandbox_id, app, settings)   # new
   → 303 to /sandbox/<id>           # detail page polls

[ARQ worker (or inline task)]
render_sandbox_previews(ctx, sandbox_id):
   row = SandboxInstall  → preview_status='rendering', preview_started_at=now()
   identity.sync_preview_role(sessionmaker)
   session_id, cookie_value = identity.mint_session_cookie(sessionmaker, settings)
   try:
   loaded = sandbox_service.load_sandbox_module(...)    # idempotent re-load
   loaded.module.metadata.schema = row.schema_name
   if seed_runner.has_seed(loaded):
       seed_runner.run(loaded, sessionmaker)
   pairs = routes.resolve(loaded.module, session, schema_name)
   pairs = pairs[:MAX_SCREENSHOTS // len(VIEWPORTS)]    # 30 / 3 = 10 routes max
   playwright.launch_chromium()
     for viewport in VIEWPORTS:
        context = browser.new_context(viewport=..., base_url=settings.public_base_url)
        context.add_cookies([parcel_session=cookie_value])
        page = context.new_page()
        for path in pairs:
           url = f"{row.url_prefix}{path}"
           filename = storage.filename_for(path, viewport)
           try: page.goto(url, wait_until="networkidle", timeout=10s)
                page.screenshot(full_page=True, type="png")
                entry = {route, viewport, filename, status:'ok'}
           except: entry = {..., status:'error', error: str(exc)}
   row.previews = entries
   row.preview_status = 'ready' if any(ok) else 'failed'
   row.preview_finished_at = now()
   finally:
       identity.revoke_session(sessionmaker, session_id)
```

### Inline mode

When `PARCEL_WORKFLOWS_INLINE=1` (set by pytest config and `parcel dev`), `previews.queue.enqueue` short-circuits to `asyncio.create_task(_render(...))`. Tasks are tracked in `app.state.preview_tasks`; the lifespan exit cancels and gathers them. The `_render` coroutine opens its own `async with sessionmaker() as session` blocks — never reuses the request's session, which is closed by the time the redirect returns. Top-level `except BaseException` catches `CancelledError` so previews never stay stuck in `'rendering'` across shutdown.

This mirrors AI chat's `run_turn` (Phase 7c) and the workflow runner's inline path (Phase 10b).

### Orphan sweep

On shell boot (after `mount_sandbox_on_boot`), `sweep_orphan_previews` flips any `preview_status='rendering'` rows to `'failed'` with `preview_error='process_restart'`. Runs once per boot. Same pattern as AI chat's orphan sweep.

## SDK contract

### `parcel_sdk.module.Module` — one new field

```python
preview_routes: tuple[PreviewRoute, ...] = ()
```

Empty by default. When empty, the runner auto-walks `module.router.routes`. When populated, the runner uses these declarations directly and skips auto-walk.

### `parcel_sdk.previews.PreviewRoute` — new module + dataclass

```python
@dataclass(frozen=True, kw_only=True)
class PreviewRoute:
    path: str                       # e.g. "/contacts" or "/contacts/{id}"
    title: str | None = None        # caption surfaced in the UI; falls back to path
    params: Callable[[AsyncSession], Awaitable[dict[str, str]]] | None = None
```

`params` is the path-param resolver. When the module declares a route with `{id}`, the author passes an async callable that returns `{"id": "<value>"}`. Auto-walked routes get an automatic resolver (see below); explicit routes get this hook.

### Auto-walk path-param resolution

When `preview_routes` is empty, `routes.resolve`:

1. Iterates `module.router.routes`, filtered to `APIRoute` with `"GET" in methods`.
2. For each route:
   - No path params → take it.
   - Path params present → fabricate values from seeded data. For each `{name}` placeholder, look for a model in `module.metadata.tables` whose primary-key column name matches (`id` is the common case) and whose table has at least one row in the sandbox schema; substitute the first row's PK as a string.
   - Any param can't be resolved → skip the route, log `sandbox.preview.route_skipped` at DEBUG.
3. Skip routes whose `response_class` is JSON-only (best-effort — checked via the route's declared `response_class`, defaulting to keep).

Contacts (with seed.py shipping in this phase) will auto-discover `/contacts`, `/contacts/new`, and `/contacts/<seed-id>`.

### `seed.py` contract

Discovered by file presence at `<module_root>/src/parcel_mod_<name>/seed.py`. Defines exactly one async function:

```python
async def seed(session: AsyncSession) -> None: ...
```

Runs through the existing static-analysis gate at sandbox-install time — same allow-list, same capability rules. The module's `metadata.schema` is already patched to `mod_sandbox_<uuid>` by the time `seed_runner` calls in, so `session.add(Contact(...))` writes to the sandbox schema automatically.

No SDK type defines this — file presence is the discovery mechanism.

### Versioning

`parcel-sdk` bumps from `0.9.0` to `0.10.0` (new public type + new `Module` field).
`parcel-mod-contacts` bumps from `0.6.0` to `0.7.0` (ships `seed.py`).

## Persistence

### Migration 0009 — sandbox column additions + system identity

Adds five columns to `shell.sandbox_installs`:

| Column | Type | Default | Notes |
|---|---|---|---|
| `preview_status` | `text` | `'pending'` | enum-by-convention: `pending` / `rendering` / `ready` / `failed`. No Postgres `CHECK` — runner is the gatekeeper |
| `preview_error` | `text` | `null` | Truncated to 500 chars by the runner |
| `previews` | `jsonb` | `'[]'::jsonb` | List of entries — `{route, viewport, filename, status, error?}` |
| `preview_started_at` | `timestamptz` | `null` | Set when status flips to `rendering` |
| `preview_finished_at` | `timestamptz` | `null` | Set when status reaches a terminal value |

Backfills existing rows to `preview_status='pending'`. They never auto-render — admins click "Re-render" if they want previews on a pre-Phase-11 sandbox.

The same migration seeds:

- One `User` row at `sandbox-preview@parcel.local`, `id = '00000000-0000-0000-0000-000000000011'`, `is_active=True`, password hash set to a random Argon2 hash that no human knows. `is_active=True` is required because `auth.dependencies.current_user` rejects inactive users; login is prevented by the unknown password (the form has no other escape hatch). The `User` row has no `is_builtin` column — protection is via the special-cased email in admin endpoints.
- One `Role` at `name='sandbox-preview'`, `is_builtin=True`, `description='Used by the sandbox preview renderer to drive headless Chromium'`.
- One `user_roles` row binding the user to the role.
- Role-permission rows are NOT seeded by this migration — they're synced at render time by `identity.sync_preview_role` against the live `permissions` table (which stores permissions by `name` text PK; `role_permissions` joins by `permission_name`).

The fixed UUID `00000000-0000-0000-0000-000000000011` is documented in `CLAUDE.md` and referenced by the runner so cookie minting doesn't need a DB lookup.

### `sandbox-preview` invisibility

The `sandbox-preview` user and role are filtered out of the `/users` and `/roles` admin pages by the listing queries (the role list filters `WHERE name != 'sandbox-preview'`; the user list filters `WHERE email != 'sandbox-preview@parcel.local'`). They aren't mutable through the existing admin endpoints either — the user-update and role-update endpoints reject these targets with 403, mirroring the existing protection for the `admin` builtin role.

### `previews` JSONB shape

```json
[
  {"route": "/contacts", "viewport": 375, "filename": "a3f2e1c4_375.png", "status": "ok"},
  {"route": "/contacts/new", "viewport": 768, "filename": "b1d2c4a5_768.png", "status": "ok"},
  {"route": "/contacts/{id}", "viewport": 1280, "filename": null, "status": "error",
   "error": "Timeout 10000ms exceeded"}
]
```

`route` carries the original path with placeholders (so admins see what was intended), not the substituted URL. `filename` is `null` on errored entries — the served-image route refuses anything not in this list with `status='ok'`.

## Identity (`previews.identity`)

```python
_PREVIEW_USER_ID = UUID("00000000-0000-0000-0000-000000000011")
_PREVIEW_ROLE_NAME = "sandbox-preview"


async def sync_preview_role(sessionmaker) -> None:
    """Idempotent — assigns every Permission name to the sandbox-preview role.

    role_permissions joins by permission_name (text), so we sync names not ids.
    """
    async with sessionmaker() as session:
        async with session.begin():
            role_row = (await session.execute(
                select(Role).where(Role.name == _PREVIEW_ROLE_NAME)
            )).scalar_one()
            existing = set((await session.execute(
                select(role_permissions.c.permission_name).where(
                    role_permissions.c.role_id == role_row.id
                )
            )).scalars().all())
            all_perm_names = set((await session.execute(select(Permission.name))).scalars().all())
            for pname in all_perm_names - existing:
                await session.execute(
                    role_permissions.insert().values(
                        role_id=role_row.id, permission_name=pname
                    )
                )


async def mint_session_cookie(sessionmaker, settings: Settings) -> tuple[uuid.UUID, str]:
    """Create a Session row for the sandbox-preview user and return (session_id, cookie_value).

    The auth dependency `current_session` looks up the session in the DB by the
    UUID encoded in the cookie, so a real row must exist. The render runner
    revokes the session in its `finally` to keep `shell.sessions` from growing.
    """
    async with sessionmaker() as session:
        async with session.begin():
            db_session = await sessions_service.create_session(
                session, user_id=_PREVIEW_USER_ID
            )
            session_id = db_session.id
    cookie_value = sign_session_id(session_id, secret=settings.session_secret)
    return session_id, cookie_value


async def revoke_session(sessionmaker, session_id: uuid.UUID) -> None:
    """Best-effort cleanup; no-op if already gone."""
    async with sessionmaker() as session:
        async with session.begin():
            row = await session.get(DbSession, session_id)
            if row is not None and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)
```

The auth code path is unchanged. The cookie middleware reads `parcel_session`, decodes the session_id via `verify_session_cookie`, calls `lookup` which finds the live `shell.sessions` row pointing at `_PREVIEW_USER_ID`, then `current_user` fetches the active user, then `require_permission` checks the synced role. No special-casing in `auth.*` or `rbac.*`.

### Cookie scope

Cookie domain matches `Settings.public_base_url`'s host. `http://shell:8000` → `shell`. Playwright only navigates within the running shell's origin during render, so cross-origin leakage is moot.

## Settings

One new setting:

| Setting | Env var | Default | Purpose |
|---|---|---|---|
| `Settings.public_base_url` | `PARCEL_PUBLIC_BASE_URL` | `"http://shell:8000"` | Origin Playwright uses to reach the running shell. The shell never reads this for anything except preview rendering. Override to `"http://localhost:8000"` for non-docker dev. |

`MAX_SCREENSHOTS = 30` and `VIEWPORTS = ((375,812),(768,1024),(1280,800))` are module-level constants in `parcel_shell.sandbox.previews.runner`. Not exposed as settings.

## Routes

Three new routes on the existing `parcel_shell.sandbox.router_ui` module:

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/sandbox/{sandbox_id}/previews-fragment` | `sandbox.read` | HTMX poll partial. Returns 404 on missing sandbox. While `preview_status` is non-terminal, the response carries `hx-get` + `hx-trigger="every 2s"` + `hx-target="#previews-section"` + `hx-swap="outerHTML"`. Once terminal, those attributes are absent and polling stops. |
| `POST` | `/sandbox/{sandbox_id}/previews/render` | `sandbox.install` | Re-render trigger. Refuses with 409 + flash if `preview_status='rendering'` (avoids racing tasks). Otherwise clears `previews` + `preview_error`, sets status to `pending`, calls `previews.queue.enqueue`. 303 to detail. 404 on missing or non-`active` sandbox. |
| `GET` | `/sandbox/{sandbox_id}/preview-image/{filename}` | `sandbox.read` | Streams the PNG. Validates `filename` against the row's `previews` list — accepts only filenames whose entry has `status='ok'`. 404 on bad filename. `Content-Type: image/png`, `Cache-Control: private, max-age=3600`. |

No new shell permissions. Existing `sandbox.read` / `sandbox.install` cover the surface.

## UI

The `/sandbox/<id>` detail page gains a "Previews" section between the manifest summary and the gate report. Three states based on `preview_status`:

### Pending / rendering

Heading "Previews", a small spinner, status line. If `previews` is partially populated (some entries already written by the runner), show "Rendering N / M…"; else "Queued". Section root carries `hx-get="/sandbox/<id>/previews-fragment" hx-trigger="every 2s" hx-target="#previews-section" hx-swap="outerHTML"`.

### Ready

Heading "Previews", a tab strip with three tabs (Mobile / Tablet / Desktop) wired through Alpine.js for client-side switching. Inside each tab, a vertical stack of `<figure>` blocks — one per route in alphabetical order — captioned with `route` (or `title` if the module supplied one). Each figure wraps its `<img>` in `<a href="/mod-sandbox/<short>/<path>" target="_blank">` so admins can click through to the live sandbox.

If `seed.py` was absent, a small grey banner above the tab strip reads "No seed.py — module rendered with empty data".

A "Re-render previews" button in the section header, gated by `sandbox.install`, posts to the re-render route.

### Failed (no entries succeeded)

Heading "Previews", a red error banner with `preview_error`, "Re-render previews" button. If at least one entry succeeded, render as `ready` and show errored entries inline as small grey "couldn't render" placeholder cards.

### Templates

```
parcel_shell/sandbox/templates/sandbox/_previews_section.html       # full section, all states
parcel_shell/sandbox/templates/sandbox/_previews_fragment.html      # poll target wrapping section
parcel_shell/sandbox/templates/sandbox/_preview_error.html          # individual errored-entry card
```

`detail.html` includes the fragment at the appropriate spot. The fragment has `id="previews-section"` so HTMX `hx-target` finds it.

### Sidebar

No change. Sandboxes already live under "AI Lab".

## CLI

One new subcommand on the existing `parcel sandbox` group:

```
parcel sandbox previews <uuid>
```

Prints `preview_status`, count of entries by status, and the served-image directory path. Not load-bearing — useful for `parcel sandbox install` workflows where the operator isn't in a browser.

## Contacts seed

`modules/contacts/src/parcel_mod_contacts/seed.py` ships in this phase with ~5 contacts and ~3 organizations, so the reference module produces meaningful previews on first install. Bumps `parcel-mod-contacts` to `0.7.0`.

## Failure isolation

- **Per-route failures** (`page.goto` timeout, `screenshot` exception): caught inside the route loop. The entry is appended with `status='error'` and a truncated message; subsequent routes still render. Mirrors dashboards/reports per-widget isolation.
- **Per-viewport failures** (context creation): caught by an outer `try/finally` per viewport. Other viewports proceed.
- **Whole-job failures** (Chromium never launches, sandbox dir missing, `seed.py` import explodes): caught by the runner's `except BaseException`, recorded as `preview_status='failed'` with the exception text. Admin clicks "Re-render".
- **No retry**. ARQ-level retries are not configured for this job. If the failure is transient (network, image hiccup), the operator re-renders manually.
- **Dismiss-during-render**. If `dismiss_sandbox` runs while a render task is mid-flight, the runner's next DB read sees `status != 'active'` and exits early. The Chromium loop continues for at most one route then unwinds via the `finally`. Files are cleaned up by `dismiss_sandbox` regardless.

## Cap & ordering

`MAX_SCREENSHOTS = 30`. Routes resolved by `routes.resolve` are ordered alphabetically by path and capped to `MAX_SCREENSHOTS // len(VIEWPORTS) = 10` before the viewport loop multiplies them. A module declaring 12 routes loses the last 2 routes' previews entirely (rather than just their desktop screenshot, which would create ragged tabs). Documented in CLAUDE.md.

## Per-pair timeout & job budget

Per-`page.goto` timeout: 10s. Per-screenshot timeout: implicit via Playwright defaults (30s — kept as-is). Worst case 30 × 10s = 5 minutes; ARQ's default `job_timeout=300s` matches but is tight, so `WorkerSettings.functions` for `render_sandbox_previews` sets `job_timeout=600s` for headroom. Inline mode has no timeout — relies on the Playwright per-call timeouts.

## What ships out of scope (deferred)

- **Synthetic data fallback.** Modules without `seed.py` get empty-state screenshots. Polyfactory-style synthetic seeding stays a Future follow-up.
- **AI generator prompt update.** The generator's system prompt is not updated in this phase to emit `seed.py`. Tracked as a one-line follow-up in CLAUDE.md.
- **Per-viewport / per-route ARQ parallelism.** Single-job is right at this scale (~5 min worst case, one Chromium amortised across 30 captures).
- **Object storage for previews.** Local filesystem only.
- **Static-analysis-gate-time enforcement of `preview_routes` correctness.** If a module declares a `preview_routes` entry whose path doesn't exist on the router, the runner just logs a skip — no boot warning. Same opportunistic-validation policy as Phase 9 reports' permission warnings.
- **Worker-side integration test for the queued render path.** Phase 10b's testcontainer-Redis worker test is the canonical lane for ARQ wiring; the inline-mode integration test is the load-bearing one for previews.

## Test surface

| Layer | Test |
|---|---|
| Unit | `routes.resolve` — auto-walk filtering, path-param substitution, `preview_routes` override, JSON-only skip |
| Unit | `storage.filename_for` — deterministic SHA1 prefix, viewport suffix, validation accepts/rejects |
| Unit | `identity.sync_preview_role` — idempotence (run twice, no duplicate rows) |
| Unit | `identity.mint_cookie` — round-trips through the existing session deserializer |
| Unit | `seed_runner.has_seed` / `run` — file-presence detection, schema-patched session, commit semantics |
| Integration | End-to-end inline render against Contacts in a testcontainer Postgres — assert `preview_status='ready'`, file count matches, served image returns 200 with `Content-Type: image/png`, cross-sandbox filename returns 404, dismiss removes files |
| Integration | Re-render endpoint resets `previews`, kicks new task, ends `ready` |
| Integration | Orphan sweep flips a hand-set `'rendering'` row to `'failed'` on next boot |
| Integration | Sandbox without `seed.py` still produces previews (empty-state) |
| Integration | Sandbox with a `seed.py` that raises lands in `preview_status='failed'` with the exception text |

Test count delta: ~450 → ~470.

## CLAUDE.md updates

Locked-in decisions table grows by these rows (compressed):

- **Sandbox preview runner** — `render_sandbox_previews(sandbox_id)` ARQ job, single Chromium per render, three viewport contexts. Inline mode uses `asyncio.create_task` mirroring AI chat's `run_turn` pattern. Inline tasks tracked in `app.state.preview_tasks`, cancelled on lifespan exit. Orphan sweep on boot.
- **Sandbox preview routes (auto-walk)** — `routes.resolve` auto-walks `module.router.routes` for GET/HTML routes, skips JSON-only `response_class`, fabricates path-param values from `module.metadata.tables` first-row PKs. `Module.preview_routes` (new SDK field) overrides the auto-walk when supplied.
- **Sandbox preview seed** — `<module_root>/src/parcel_mod_<name>/seed.py` with `async def seed(session)`, gated like the rest of the module. No synthetic fallback in 11.
- **Sandbox preview identity** — fixed-UUID `sandbox-preview@parcel.local` user (`00000000-0000-0000-0000-000000000011`) + `sandbox-preview` builtin role; permissions synced at render-time via `identity.sync_preview_role`. Hidden from `/users` and `/roles`.
- **Sandbox preview storage** — `var/sandbox/<uuid>/previews/<sha1prefix>_<viewport>.png`. `dismiss_sandbox` cleans everything via the existing `module_root` rmtree.
- **Sandbox preview UI** — three states (`pending|rendering|ready|failed`), Alpine-driven viewport tab strip, `figure` per route with click-through to `/mod-sandbox/<short>/<path>`. HTMX poll at 2s intervals; polling attributes drop on terminal status. "No seed.py" banner when applicable.
- **Sandbox preview cap** — `MAX_SCREENSHOTS = 30`, route list ordered alphabetically and capped to `10` routes before viewport multiplication. Goto timeout 10s. ARQ `job_timeout=600`.
- **Sandbox preview settings** — `PARCEL_PUBLIC_BASE_URL` (default `http://shell:8000`) is the origin Playwright navigates against.

The "Phase 11 — Sandbox preview enrichment" row in the roadmap flips to `✅ done`. The next row becomes the first Future row.
