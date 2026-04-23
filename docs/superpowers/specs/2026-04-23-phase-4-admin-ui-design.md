# Phase 4 — Admin UI Shell Design

**Date:** 2026-04-23
**Phase:** 4 (next after Phase 3 — module system)
**Goal (from `CLAUDE.md`):** Admin UI shell — Jinja base layout, Tailwind, HTMX, dynamic sidebar.

## Scope

Phase 4 gives browser-facing humans the same capabilities Phase 2 and Phase 3 gave `curl`. Login, a dashboard, full CRUD UIs for users/roles/sessions, and the module install/upgrade/uninstall flow — all as server-rendered HTML + HTMX. Every existing JSON endpoint stays as-is; the UI is a parallel HTML surface under its own URL tree.

Phase 4 ships:

- Jinja2 + Tailwind (via Play CDN) + HTMX + Alpine.js (via CDN) stack.
- Base layout: top bar + left sidebar + content slot (layout **A** from brainstorming).
- Three user-selectable themes (`plain`, `blue`, `dark`) switched via `[data-theme]` on `<html>`, persisted in `localStorage`.
- `/login`, `/logout` (POST), `/` (dashboard), `/profile` (change password + theme switcher).
- `/users` — list, new, detail + edit, soft-delete, role assign/unassign; `/users/{id}/sessions` — list + revoke.
- `/roles` — list, new, detail + edit, delete; permission assign/unassign; `is_builtin` rows are read-only.
- `/modules` — list (discovered + installed), install with capability approval, upgrade, uninstall (soft + hard).
- Flash messages via a signed `parcel_flash` HTTP-only cookie, rendered and cleared in the base template.

Phase 4 does **not** deliver: custom-built Tailwind (Play CDN only), a marketplace-quality design system, bulk actions, sort/filter on list pages, server-side theme persistence, pagination UI beyond next/prev, CSRF token middleware, or any module-specific UI (Contacts is Phase 5).

## Locked decisions from brainstorming

| Question | Decision |
|---|---|
| Page set | Full CRUD UIs for users, roles, sessions, modules (option B from Q1) |
| CSS delivery | Tailwind Play CDN for Phase 4; compile-step deferred to a later phase |
| HTML auth | Separate `current_user_html` dep that redirects to `/login?next=<path>` on 401 |
| URL structure | HTML at `/`, `/login`, `/users`, etc. JSON stays at `/auth/*`, `/admin/*`, `/health/*` |
| Layout shell | Option A: top bar + left sidebar + content area |
| Themes | All three user-selectable; `plain` default; `localStorage["parcel_theme"]` |
| Reactivity | HTMX for server-driven swaps + Alpine.js (CDN) for local state (menus, modals, theme picker) |
| Form pattern | Login/logout use traditional POST + redirect; mutating admin forms use `hx-post` returning the updated HTML fragment |
| CSRF | Rely on Phase 2's `SameSite=Lax` cookie; no token middleware this phase |
| Flash messages | Signed `parcel_flash` cookie (`itsdangerous`), rendered by base template, cleared by a middleware |

## Package layout additions

```
packages/parcel-shell/src/parcel_shell/
  ui/
    __init__.py
    dependencies.py          # current_user_html, html_require_permission; flash()/read_flash()
    flash.py                 # sign/verify + set/read/clear of the parcel_flash cookie
    routes/
      __init__.py
      auth.py                # /login, /logout (POST), /profile
      dashboard.py           # / (dashboard)
      users.py               # /users/*, /users/<id>/sessions/*
      roles.py               # /roles/*
      modules.py             # /modules/*
    templates/
      _base.html             # html shell: doctype, head, topbar, sidebar, content, theme init
      _macros.html           # table/row/badge/button helpers
      _alerts.html           # flash renderer
      login.html
      dashboard.html
      profile.html
      users/
        list.html
        new.html
        detail.html
        edit_inline.html     # partial used by HTMX when editing
        row.html             # partial used by HTMX after mutation
      roles/
        list.html
        new.html
        detail.html
        row.html
        permission_row.html  # partial for a permission pill in role detail
      modules/
        list.html
        detail.html
        install_form.html    # partial for the capability-approval modal body
        row.html
    static/
      app.css                # design tokens (--bg, --fg, --accent) per theme
      app.js                 # theme switcher + small glue
```

Test file additions:

```
packages/parcel-shell/tests/
  test_ui_auth.py           # login, logout, /profile, 401 redirect
  test_ui_users.py
  test_ui_roles.py
  test_ui_modules.py
  test_ui_flash.py          # signed cookie round-trip
  test_ui_layout.py         # topbar shows user email; active sidebar item highlighted
```

### Module boundaries

- **`ui/flash.py`** — pure: `pack(kind, msg, *, secret) -> cookie_value`, `unpack(cookie_value, *, secret) -> Flash | None`. No FastAPI, no request/response.
- **`ui/dependencies.py`** — `current_user_html` (redirects on 401), `html_require_permission(name)` factory (flash + redirect on 403), and a `flash(response, kind, msg)` helper that sets the cookie. All thin wrappers over Phase 2's auth deps.
- **`ui/routes/<resource>.py`** — one router per resource. Each route parses form data, calls existing Phase 2/3 services, flashes a message, and returns either `RedirectResponse` (for traditional POST) or `HTMLResponse` with a rendered fragment (for HTMX).
- **`ui/templates/`** — Jinja templates. `_base.html` is the only "full document" template; every page extends it. HTMX partials are standalone templates returned via `HTMLResponse`.
- **`ui/static/`** — served via `StaticFiles` mount at `/static/`. `app.css` defines three `[data-theme]` blocks of custom properties; `app.js` reads `localStorage["parcel_theme"]` on DOMContentLoaded and sets `document.documentElement.dataset.theme`.

## Stack + delivery

### Templates

Jinja2 is added as a shell dep. FastAPI's `Jinja2Templates` renders pages. Templates live in `parcel_shell/ui/templates` and are resolved via a single `Templates` instance exposed through `app.state.templates` so routes can call `templates.TemplateResponse(...)`.

### CSS

Tailwind via Play CDN: `<script src="https://cdn.tailwindcss.com"></script>` in `_base.html`. On top of Tailwind, our own `static/app.css` defines design tokens:

```css
:root {
  /* plain (default) */
  --bg: #fafafa;
  --surface: #ffffff;
  --text: #1a1a1a;
  --text-dim: #666666;
  --border: #e5e5e5;
  --accent: #1a1a1a;
  --accent-text: #fafafa;
  --success: #2f7a59;
  --danger: #b91c1c;
}

[data-theme="blue"] {
  --bg: #f8fafc;
  --surface: #ffffff;
  --text: #0f172a;
  --text-dim: #64748b;
  --border: #e2e8f0;
  --accent: #2563eb;
  --accent-text: #ffffff;
  --success: #166534;
  --danger: #b91c1c;
}

[data-theme="dark"] {
  --bg: #0a0a0a;
  --surface: #0f0f0f;
  --text: #e5e5e5;
  --text-dim: #a3a3a3;
  --border: #262626;
  --accent: #d7b85c;
  --accent-text: #0a0a0a;
  --success: #4ea67e;
  --danger: #ef4444;
}
```

Components use Tailwind utilities for layout/spacing and the CSS variables for color (`bg-[var(--bg)]`, `text-[var(--text)]`, etc.). One small Tailwind `safelist` in `tailwind.config` covers the arbitrary-value classes so the Play CDN doesn't strip them.

### JavaScript

Three script tags in `_base.html` head:

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

Versions pinned via integrity hashes in a later phase; for pre-alpha, the floating version is fine.

Our `app.js` is about 30 lines: initialize `data-theme` from `localStorage` (or fall back to `plain`) before first paint, expose a global `setTheme(name)` function, and register HTMX response-header handling for `HX-Trigger: flash` events (so server can push a flash after a non-redirect HTMX action).

### Theme switcher

In the top bar's user menu (Alpine dropdown), a three-item list: `Plain / Blue / Dark`. Clicking calls `setTheme(name)` which does:

```js
document.documentElement.dataset.theme = name;
localStorage.setItem("parcel_theme", name);
```

A `<script>` block at the very top of `<head>` reads `localStorage.getItem("parcel_theme") || "plain"` and sets `data-theme` synchronously before any paint — this avoids a flash of wrong theme.

## HTML auth: `current_user_html`

```python
# parcel_shell/ui/dependencies.py

async def current_user_html(
    request: Request, db: AsyncSession = Depends(get_session)
) -> User:
    try:
        return await current_user(
            await current_session(request, db=db), db=db
        )
    except HTTPException as exc:
        if exc.status_code == 401:
            next_url = request.url.path
            if request.url.query:
                next_url += "?" + request.url.query
            raise HTMLRedirect(f"/login?next={quote_plus(next_url)}") from exc
        raise
```

`HTMLRedirect` is a custom exception caught by a FastAPI exception handler that returns `RedirectResponse`. Using an exception (instead of returning a response from the dep) keeps the dep signature `-> User` honest for type checkers and route handlers.

`html_require_permission(name)` mirrors Phase 2's `require_permission` but on permission-denied, flashes a message and raises `HTMLRedirect("/")` back to the dashboard.

## URL structure (HTML routes)

| Method | Path | Purpose | Permission |
|---|---|---|---|
| GET | `/login` | Render login form | public |
| POST | `/login` | Authenticate; on success set session cookie + redirect to `next` or `/` | public |
| POST | `/logout` | Revoke current session + redirect to `/login` | authed |
| GET | `/` | Dashboard | authed |
| GET | `/profile` | Change-password form + theme switcher | authed |
| POST | `/profile/password` | Change own password; flash + redirect | authed |
| GET | `/users` | List (with next/prev pagination) | `users.read` |
| GET | `/users/new` | Create-user form | `users.write` |
| POST | `/users` | Create user; redirect to detail | `users.write` |
| GET | `/users/{id}` | Detail + edit form + role assign + session list link | `users.read` |
| POST | `/users/{id}/edit` | Update email/is_active (HTMX returns row partial) | `users.write` |
| POST | `/users/{id}/delete` | Soft delete (HTMX removes row) | `users.write` |
| POST | `/users/{id}/roles` | Add role (HTMX returns role pills partial) | `users.roles.assign` |
| POST | `/users/{id}/roles/{role_id}/remove` | Remove role (HTMX) | `users.roles.assign` |
| GET | `/users/{id}/sessions` | Session list for a user | `sessions.read` |
| POST | `/users/{id}/sessions/revoke` | Revoke all (HTMX updates list) | `sessions.revoke` |
| GET | `/roles` | Role list | `roles.read` |
| GET | `/roles/new` | Create-role form | `roles.write` |
| POST | `/roles` | Create | `roles.write` |
| GET | `/roles/{id}` | Detail + edit form + permission assign | `roles.read` |
| POST | `/roles/{id}/edit` | Update (HTMX returns row partial) | `roles.write` |
| POST | `/roles/{id}/delete` | Delete (HTMX) — 403 with flash for `is_builtin` | `roles.write` |
| POST | `/roles/{id}/permissions` | Add permission (HTMX) | `roles.write` |
| POST | `/roles/{id}/permissions/{name}/remove` | Remove permission (HTMX) | `roles.write` |
| GET | `/modules` | Module list (installed + discovered-only) | `modules.read` |
| GET | `/modules/{name}` | Detail page | `modules.read` |
| POST | `/modules/install` | Install; requires capability approval checkbox set; flash + redirect to detail | `modules.install` |
| POST | `/modules/{name}/upgrade` | Upgrade; flash + redirect | `modules.upgrade` |
| POST | `/modules/{name}/uninstall` | Uninstall; query `drop_data=bool`; flash + redirect | `modules.uninstall` |

JSON endpoints (`/auth/*`, `/admin/*`, `/health/*`) are unchanged. The `/login` HTML path and `/auth/login` JSON path coexist fine.

### Path collision with static

`StaticFiles` mounted at `/static/` serves `app.css`, `app.js`, and anything else under `parcel_shell/ui/static/`. The new HTML routes under `/` must not shadow any existing JSON prefix — they don't, since `/login`, `/logout`, `/`, `/profile`, `/users`, `/roles`, `/modules` are all unused by Phase 2/3 JSON.

## Base layout (`_base.html`)

Structure:

```
<html data-theme="<init-from-localStorage>">
  <head>
    <!-- theme init script (no-flash) -->
    <!-- Tailwind CDN, HTMX, Alpine CDN -->
    <!-- static/app.css, static/app.js -->
    <title>{% block title %}Parcel{% endblock %}</title>
  </head>
  <body class="bg-[var(--bg)] text-[var(--text)]">
    <!-- topbar: brand + env badge + user menu -->
    <header>...</header>

    <!-- flash messages if cookie present -->
    {% include "_alerts.html" %}

    <div class="grid grid-cols-[240px_1fr]">
      <aside><!-- sidebar --></aside>
      <main class="p-6">
        {% block content %}{% endblock %}
      </main>
    </div>
  </body>
</html>
```

The sidebar is a simple jinja loop:

```python
SIDEBAR = [
    ("Overview", [("Dashboard", "/", None)]),
    ("Access", [
        ("Users", "/users", "users.read"),
        ("Roles", "/roles", "roles.read"),
    ]),
    ("System", [("Modules", "/modules", "modules.read")]),
]
```

Items are filtered by `permission in effective_permissions(current_user)`. The active item is highlighted by comparing `request.url.path` against the item's href prefix.

The topbar has the brand (clickable, → `/`), an environment badge (`dev` / `staging` / `prod`), and a user-menu dropdown (Alpine-powered) with: email readout, theme submenu (Plain / Blue / Dark), profile link, logout POST form.

## Data flow per resource

### Mutating an existing user (representative example)

1. GET `/users/{id}` → `detail.html` renders the user's data; the row inside `<tbody>` has an `id="user-{id}-row"`.
2. User clicks "Edit". `<button hx-get="/users/{id}/edit-form" hx-target="#user-{id}-row" hx-swap="outerHTML">`.
3. Server returns `edit_inline.html` partial — a `<tr>` with an inline form.
4. User submits. `<form hx-post="/users/{id}/edit" hx-target="#user-{id}-row" hx-swap="outerHTML">`.
5. Server: calls `service.update_user(...)`, renders `row.html` partial, sends response with `HX-Trigger: {"flash": {"kind":"success","msg":"User updated"}}` header so the flash banner can show without a page refresh.
6. If validation fails, server returns the same partial with error markers and a `4xx` status (HTMX by default swaps only on `2xx`; we configure `htmx:responseError` to swap anyway for form-validation responses).

### Installing a module

1. GET `/modules` → row shows "Install" button for discovered-but-not-installed.
2. Click opens an Alpine modal (`x-show="modal"`) with a `<form hx-post="/modules/install">` containing a checkbox list of declared capabilities plus a required "I approve all listed capabilities" checkbox.
3. Submit: if all capabilities are checked, server calls `service.install_module(...)`. Response is a `RedirectResponse("/modules/{name}", 303)` with a success flash cookie set.
4. If capability checkboxes don't match, server returns the form partial with inline error.

## Flash messages

`parcel_flash` is an HTTP-only cookie with a 60-second max-age carrying a `itsdangerous`-signed JSON blob `{"kind": "success" | "error" | "info", "msg": "<string>"}`.

- **Set:** `response.set_cookie("parcel_flash", sign(payload, secret), httponly=True, secure=env != "dev", samesite="lax", max_age=60)`.
- **Read + clear:** a tiny `FlashMiddleware` pops the cookie from the request, stashes the decoded payload on `request.state.flash`, and sets a delete-cookie on the response after the handler runs. `_alerts.html` renders from `request.state.flash` or nothing.
- **HTMX-friendly alternative:** when the server can't redirect (HTMX partial), it sends `HX-Trigger: flash` and the client-side JS picks the flash message out of a JSON header and shows it in a toast region. Only used where a redirect is inappropriate.

## Testing strategy

### New fixtures

- `html_admin` (function-scoped): a `committing_admin` specialized for HTML routes — already logged in, sets `Accept: text/html` on every request. Cleanup after test.
- Helpers: `assert_flash(response, kind, match)` — decodes the `parcel_flash` cookie on the previous response and asserts the payload matches.

### Coverage (~25 new tests)

1. **test_ui_flash.py**
   - `pack`/`unpack` roundtrip.
   - Tampered cookie → `unpack` returns None.
   - Middleware: response to a request with the cookie sets a delete-cookie.

2. **test_ui_auth.py**
   - `GET /login` renders.
   - `POST /login` valid → 303 to `/` with session cookie.
   - `POST /login` invalid → 200 re-render with error message.
   - `GET /` unauthed → 303 to `/login?next=/`.
   - `GET /users` unauthed → 303 to `/login?next=/users`.
   - `POST /logout` → session revoked, 303 to `/login`.
   - `GET /profile` authed → renders.
   - `POST /profile/password` success → flash cookie set.
   - `POST /profile/password` wrong current → re-render with error.

3. **test_ui_layout.py**
   - Sidebar filters out items the user has no permission for (a plain user sees only "Dashboard").
   - Active item is highlighted.
   - Topbar shows user's email.
   - Theme-init script is present in head.

4. **test_ui_users.py**
   - List page shows users (authed as admin).
   - `POST /users` creates; redirect to detail.
   - HTMX `POST /users/{id}/edit` returns a single `<tr>` partial with updated data.
   - HTMX `POST /users/{id}/delete` returns an empty row (200) and flips `is_active=false`.
   - `POST /users/{id}/roles` with role_id assigns and returns updated pills partial.

5. **test_ui_roles.py**
   - List page shows roles incl. built-in `admin` with "read-only" badge.
   - `POST /roles` creates.
   - `POST /roles/{admin_id}/delete` returns 403 + flash error, row unchanged.
   - Permission assignment HTMX round-trip.

6. **test_ui_modules.py**
   - List page shows both installed and discovered-only modules.
   - Install with incorrect capability approval → form re-rendered with error.
   - Install happy path → redirect to detail, flash set.
   - Upgrade → redirect + flash.
   - Uninstall soft/hard via query param.

Tests use `committing_admin`-style fixtures (real commits; Phase 3's pattern) so the install flow works.

## Dependency additions

`packages/parcel-shell/pyproject.toml`:
- `jinja2>=3.1`
- `python-multipart>=0.0.9` — FastAPI needs this to parse form-encoded POST bodies.

No workspace-root additions. CDN-delivered JS/CSS, no node.

## Definition of done

1. `docker compose up -d shell` and visiting `http://localhost:8000/` shows the login page (redirect from `/`).
2. Login → dashboard. Sidebar shows all six items for admin (Dashboard, Users, Roles, Sessions-via-user, Modules, Profile).
3. User menu → theme submenu works (page re-skins without reload, persists across navigation).
4. Create, edit, delete a user; assign/remove a role; revoke a session — all via browser, no curl.
5. Create a role, assign permissions, delete a non-builtin role. Deleting the `admin` role shows a red flash.
6. Install the fixture module (via pytest fixture or a locally-installed module), upgrade, uninstall with `drop_data=true` — all via browser.
7. `uv run pytest` green across all phases.
8. `uv run ruff check` + `uv run pyright packages/parcel-shell packages/parcel-sdk` clean.
9. CLAUDE.md: Phase 4 ✅, Phase 5 ⏭ next; theme palette + route table noted.

## Out of scope (deferred)

- Tailwind build step (Play CDN only; production CSS pipeline is a later phase).
- CSRF token middleware (relying on `SameSite=Lax`).
- Server-side theme preference (localStorage only).
- Sort, filter, search on list pages. Pagination is simple next/prev only.
- Bulk actions (multi-select delete, bulk role assign).
- Audit log UI.
- Password reset flow.
- File uploads or rich-text editing (no module has needed them yet).
- Accessibility audit. Phase 4 uses semantic HTML and keyboard-operable Alpine dropdowns; a full a11y pass is a later phase.
