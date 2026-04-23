# Phase 4 — Admin UI Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a browser-facing admin UI — Jinja2 + Tailwind (Play CDN) + HTMX + Alpine.js, with login, dashboard, full CRUD for users/roles/sessions, and the module install/upgrade/uninstall flow. Three user-selectable themes (`plain`, `blue`, `dark`). JSON APIs from Phases 2/3 stay untouched; the UI is a parallel HTML surface under `/` with an `HTMLRedirect` exception that routes unauthenticated users to `/login?next=...`.

**Architecture:** All UI code lives under `parcel_shell/ui/` — templates, routes, dependencies, static assets, flash helpers. HTML routes use a separate `current_user_html` dep that redirects instead of returning 401. Mutating actions use HTMX (`hx-post` → server returns an HTML fragment for in-place swap); login/logout use traditional POST + redirect. Flash messages ride in a signed `parcel_flash` HTTP-only cookie, rendered and cleared by the base template + a small middleware. Themes are CSS custom property blocks switched by `[data-theme]` on `<html>`, persisted to `localStorage`.

**Tech Stack:** Python 3.12 · FastAPI · Jinja2 · python-multipart · Tailwind (Play CDN) · HTMX (CDN) · Alpine.js (CDN) · pytest + testcontainers · httpx · asgi-lifespan.

**Reference spec:** `docs/superpowers/specs/2026-04-23-phase-4-admin-ui-design.md`

---

## File plan

**Create:**
- `packages/parcel-shell/src/parcel_shell/ui/__init__.py`
- `packages/parcel-shell/src/parcel_shell/ui/flash.py`
- `packages/parcel-shell/src/parcel_shell/ui/dependencies.py`
- `packages/parcel-shell/src/parcel_shell/ui/middleware.py`
- `packages/parcel-shell/src/parcel_shell/ui/templates.py`
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/__init__.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/auth.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/dashboard.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/users.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/roles.py`
- `packages/parcel-shell/src/parcel_shell/ui/routes/modules.py`
- `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/_alerts.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/_macros.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/login.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/dashboard.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/profile.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/users/list.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/users/new.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/users/detail.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/users/row.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/users/edit_inline.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/roles/list.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/roles/new.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/roles/detail.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/roles/row.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/modules/list.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/modules/detail.html`
- `packages/parcel-shell/src/parcel_shell/ui/static/app.css`
- `packages/parcel-shell/src/parcel_shell/ui/static/app.js`
- `packages/parcel-shell/tests/test_ui_flash.py`
- `packages/parcel-shell/tests/test_ui_auth.py`
- `packages/parcel-shell/tests/test_ui_layout.py`
- `packages/parcel-shell/tests/test_ui_users.py`
- `packages/parcel-shell/tests/test_ui_roles.py`
- `packages/parcel-shell/tests/test_ui_modules.py`

**Modify:**
- `packages/parcel-shell/pyproject.toml` — add `jinja2>=3.1` and `python-multipart>=0.0.9`
- `packages/parcel-shell/src/parcel_shell/app.py` — mount `StaticFiles`, register UI routers, install flash middleware, register `HTMLRedirect` exception handler
- `CLAUDE.md` — Phase 4 ✅ / Phase 5 ⏭, note new deps + theme system
- `README.md` — replace the "JSON-only" admonition with a one-liner pointing to `http://localhost:8000/`

---

## Task 1: Dependencies

**Files:**
- Modify: `packages/parcel-shell/pyproject.toml`

- [ ] **Step 1: Add Jinja2 + python-multipart**

Open `packages/parcel-shell/pyproject.toml`. Append to the `dependencies` list:

```toml
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
```

- [ ] **Step 2: Sync**

Run: `uv sync --all-packages`
Expected: `jinja2` and `python-multipart` added, no errors.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/pyproject.toml uv.lock
git commit -m "chore(shell): add jinja2 and python-multipart for Phase 4"
```

---

## Task 2: Flash cookie helpers

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/ui/flash.py`
- Create: `packages/parcel-shell/tests/test_ui_flash.py`

- [ ] **Step 1: Create empty `ui/__init__.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/__init__.py` with no content.

- [ ] **Step 2: Write the failing test**

Create `packages/parcel-shell/tests/test_ui_flash.py`:

```python
from __future__ import annotations

from parcel_shell.ui.flash import COOKIE_NAME, Flash, pack, unpack


def test_pack_unpack_roundtrip() -> None:
    token = pack(Flash(kind="success", msg="done"), secret="a" * 32)
    got = unpack(token, secret="a" * 32)
    assert got == Flash(kind="success", msg="done")


def test_unpack_tampered_returns_none() -> None:
    token = pack(Flash(kind="error", msg="oops"), secret="a" * 32)
    tampered = token[:-2] + ("zz" if not token.endswith("zz") else "aa")
    assert unpack(tampered, secret="a" * 32) is None


def test_unpack_wrong_secret_returns_none() -> None:
    token = pack(Flash(kind="info", msg="hi"), secret="a" * 32)
    assert unpack(token, secret="b" * 32) is None


def test_unpack_garbage_returns_none() -> None:
    assert unpack("", secret="a" * 32) is None
    assert unpack("not-a-token", secret="a" * 32) is None


def test_cookie_name_constant() -> None:
    assert COOKIE_NAME == "parcel_flash"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_flash.py -v`
Expected: FAIL — `parcel_shell.ui.flash` not found.

- [ ] **Step 4: Implement `flash.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/flash.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from itsdangerous import BadSignature, URLSafeSerializer

COOKIE_NAME = "parcel_flash"
_SALT = "parcel.flash.v1"

FlashKind = Literal["success", "error", "info"]


@dataclass(frozen=True)
class Flash:
    kind: FlashKind
    msg: str


def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt=_SALT)


def pack(flash: Flash, *, secret: str) -> str:
    return _serializer(secret).dumps({"kind": flash.kind, "msg": flash.msg})


def unpack(token: str, *, secret: str) -> Flash | None:
    if not token:
        return None
    try:
        raw = _serializer(secret).loads(token)
    except BadSignature:
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    msg = raw.get("msg")
    if kind not in ("success", "error", "info") or not isinstance(msg, str):
        return None
    return Flash(kind=kind, msg=msg)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_flash.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/__init__.py packages/parcel-shell/src/parcel_shell/ui/flash.py packages/parcel-shell/tests/test_ui_flash.py
git commit -m "feat(shell/ui): signed parcel_flash cookie helpers"
```

---

## Task 3: Flash middleware

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/middleware.py`

- [ ] **Step 1: Implement `middleware.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/middleware.py`:

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from parcel_shell.ui.flash import COOKIE_NAME, unpack


class FlashMiddleware(BaseHTTPMiddleware):
    """Pop the parcel_flash cookie onto request.state; clear it in the response.

    Routes access the current flash payload via ``request.state.flash`` (may be
    None). After the handler runs, we set a delete-cookie so the message is
    shown exactly once. Handlers that want to enqueue a new flash set their
    own ``parcel_flash`` cookie — Set-Cookie headers added later in the stack
    take precedence over the delete below because FastAPI/Starlette preserves
    both on the response and browsers honor the last Set-Cookie for the name.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        token = request.cookies.get(COOKIE_NAME)
        secret = request.app.state.settings.session_secret
        request.state.flash = unpack(token, secret=secret) if token else None
        response = await call_next(request)
        if token is not None:
            # Clear the cookie so the message doesn't re-appear on the next request.
            response.delete_cookie(COOKIE_NAME, path="/")
        return response
```

- [ ] **Step 2: Sanity check import**

Run: `uv run python -c "from parcel_shell.ui.middleware import FlashMiddleware; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/middleware.py
git commit -m "feat(shell/ui): FlashMiddleware pops and clears the parcel_flash cookie"
```

---

## Task 4: HTML auth dependencies + HTMLRedirect exception

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/dependencies.py`

- [ ] **Step 1: Implement `dependencies.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/dependencies.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from parcel_shell.auth.dependencies import current_session, current_user
from parcel_shell.auth.sessions import bump, lookup
from parcel_shell.auth.cookies import verify_session_cookie
from parcel_shell.auth.dependencies import COOKIE_NAME as SESSION_COOKIE_NAME
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import User
from parcel_shell.ui.flash import COOKIE_NAME as FLASH_COOKIE_NAME
from parcel_shell.ui.flash import Flash, pack


class HTMLRedirect(Exception):
    """Raised by HTML-facing dependencies to signal a redirect.

    A FastAPI exception handler (installed in ``create_app``) converts this into
    a 303 ``RedirectResponse`` at the edge of the request, keeping dep type
    signatures honest (``-> User`` instead of ``User | Response``).
    """

    def __init__(self, location: str, *, flash: Flash | None = None) -> None:
        self.location = location
        self.flash = flash


async def _try_current_user(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    secret = request.app.state.settings.session_secret
    sid = verify_session_cookie(token, secret=secret)
    if sid is None:
        return None
    s = await lookup(db, sid)
    if s is None:
        return None
    await bump(db, s)
    user = await db.get(User, s.user_id)
    if user is None or not user.is_active:
        return None
    return user


async def current_user_html(
    request: Request, db: AsyncSession = Depends(get_session)
) -> User:
    """HTML-route auth: redirect to /login?next=... on 401, otherwise return user."""
    user = await _try_current_user(request, db)
    if user is None:
        next_url = request.url.path
        if request.url.query:
            next_url += "?" + request.url.query
        raise HTMLRedirect(f"/login?next={quote_plus(next_url)}")
    return user


def html_require_permission(name: str) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: User = Depends(current_user_html),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        perms = await service.effective_permissions(db, user.id)
        if name not in perms:
            raise HTMLRedirect(
                "/",
                flash=Flash(kind="error", msg=f"You don't have permission: {name}"),
            )
        return user

    return _dep


def set_flash(response: Response, flash: Flash, *, secret: str) -> None:
    """Set the parcel_flash cookie on the given response."""
    from parcel_shell.ui.flash import pack as _pack

    response.set_cookie(
        key=FLASH_COOKIE_NAME,
        value=_pack(flash, secret=secret),
        max_age=60,
        httponly=True,
        secure=False,  # caller can override; dev leaves False
        samesite="lax",
        path="/",
    )
```

- [ ] **Step 2: Sanity check import**

Run: `uv run python -c "from parcel_shell.ui.dependencies import HTMLRedirect, current_user_html, html_require_permission; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/dependencies.py
git commit -m "feat(shell/ui): current_user_html + html_require_permission + HTMLRedirect"
```

---

## Task 5: Templates module (Jinja2Templates singleton) + sidebar config

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`

- [ ] **Step 1: Implement `templates.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates.py`:

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(_TEMPLATES_DIR))
```

- [ ] **Step 2: Implement `sidebar.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarItem:
    label: str
    href: str
    permission: str | None  # None = visible to all authed users


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
        items=(
            SidebarItem(label="Modules", href="/modules", permission="modules.read"),
        ),
    ),
)


def visible_sections(perms: set[str]) -> list[SidebarSection]:
    out: list[SidebarSection] = []
    for section in SIDEBAR:
        items = tuple(
            i for i in section.items if i.permission is None or i.permission in perms
        )
        if items:
            out.append(SidebarSection(label=section.label, items=items))
    return out
```

- [ ] **Step 3: Sanity check**

Run: `uv run python -c "from parcel_shell.ui.templates import get_templates; from parcel_shell.ui.sidebar import SIDEBAR, visible_sections; print(len(visible_sections(set())), len(visible_sections({'users.read','roles.read','modules.read'})))"`
Expected: `1 3` (unauthed users see only Overview; admin sees all 3 sections).

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/templates.py packages/parcel-shell/src/parcel_shell/ui/sidebar.py
git commit -m "feat(shell/ui): Jinja2Templates singleton and sidebar config"
```

---

## Task 6: Static assets (app.css, app.js)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/static/app.css`
- Create: `packages/parcel-shell/src/parcel_shell/ui/static/app.js`

- [ ] **Step 1: Create `app.css`**

Create `packages/parcel-shell/src/parcel_shell/ui/static/app.css`:

```css
/* Parcel admin-UI design tokens.
   Themes are swapped via [data-theme] on <html>. */

:root {
  --bg: #fafafa;
  --surface: #ffffff;
  --surface-2: #f5f5f5;
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
  --surface-2: #f1f5f9;
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
  --surface-2: #111111;
  --text: #e5e5e5;
  --text-dim: #a3a3a3;
  --border: #262626;
  --accent: #d7b85c;
  --accent-text: #0a0a0a;
  --success: #4ea67e;
  --danger: #ef4444;
}

html, body {
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, -apple-system, "Segoe UI", Inter, system-ui, sans-serif;
}

.surface { background: var(--surface); border: 1px solid var(--border); }
.muted { color: var(--text-dim); }
.rule { border-top: 1px solid var(--border); }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 14px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
}
.btn:hover { border-color: var(--accent); }
.btn.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
.btn.danger { color: var(--danger); border-color: var(--danger); }
.btn.danger:hover { background: var(--danger); color: var(--surface); }

.input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 4px;
  font-size: 14px;
  width: 100%;
}
.input:focus { outline: 2px solid var(--accent); outline-offset: -1px; }

.pill {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
}
.pill.success { color: var(--success); border-color: var(--success); }
.pill.danger  { color: var(--danger);  border-color: var(--danger); }
.pill.info    { color: var(--accent);  border-color: var(--accent); }

table.table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; }
table.table th, table.table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
table.table th { background: var(--surface-2); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); }
table.table tr:last-child td { border-bottom: none; }

/* Sidebar */
aside.sidebar { background: var(--surface-2); border-right: 1px solid var(--border); padding: 16px 12px; }
aside.sidebar .section-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); margin: 14px 6px 6px; }
aside.sidebar a { display: block; padding: 6px 10px; border-radius: 3px; color: var(--text); text-decoration: none; }
aside.sidebar a.active { background: var(--accent); color: var(--accent-text); }
aside.sidebar a:not(.active):hover { background: var(--surface); }

/* Topbar */
header.topbar { background: var(--surface-2); border-bottom: 1px solid var(--border); padding: 0 16px; height: 48px; display: flex; align-items: center; gap: 12px; }
header.topbar .brand { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-weight: 600; }
header.topbar .env-badge { font-size: 11px; padding: 2px 6px; background: var(--border); border-radius: 3px; }
header.topbar .user-menu { margin-left: auto; font-size: 13px; color: var(--text-dim); cursor: pointer; position: relative; }
header.topbar .user-menu .menu-body { position: absolute; right: 0; top: 32px; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; min-width: 180px; padding: 6px; z-index: 50; }
header.topbar .user-menu .menu-body a, header.topbar .user-menu .menu-body button { display: block; width: 100%; text-align: left; padding: 6px 10px; color: var(--text); text-decoration: none; background: none; border: none; cursor: pointer; font-size: 13px; }
header.topbar .user-menu .menu-body a:hover, header.topbar .user-menu .menu-body button:hover { background: var(--surface-2); }
header.topbar .user-menu .menu-body .label { padding: 6px 10px; color: var(--text-dim); font-size: 11px; text-transform: uppercase; }

/* Alerts */
.alert { padding: 10px 14px; border-radius: 4px; margin: 12px 24px; font-size: 14px; border: 1px solid var(--border); background: var(--surface); }
.alert.success { border-color: var(--success); color: var(--success); }
.alert.error   { border-color: var(--danger);  color: var(--danger); }
.alert.info    { border-color: var(--accent);  color: var(--accent); }

/* Modal (Alpine-driven) */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 20px; min-width: 400px; max-width: 560px; }
.modal-card h3 { margin: 0 0 12px; font-size: 16px; }
```

- [ ] **Step 2: Create `app.js`**

Create `packages/parcel-shell/src/parcel_shell/ui/static/app.js`:

```javascript
// Parcel admin UI — small client-side glue.

// Theme switcher (exposed as window.setTheme).
(function () {
  const VALID = ["plain", "blue", "dark"];

  function setTheme(name) {
    if (!VALID.includes(name)) name = "plain";
    document.documentElement.dataset.theme = name;
    try {
      localStorage.setItem("parcel_theme", name);
    } catch (e) {
      /* ignore */
    }
  }

  window.setTheme = setTheme;
  window.parcelTheme = function () {
    try {
      return localStorage.getItem("parcel_theme") || "plain";
    } catch (e) {
      return "plain";
    }
  };
})();

// HTMX flash: servers can push a flash after a non-redirect HTMX action by
// sending `HX-Trigger: {"flash": {"kind":"success","msg":"done"}}`.
document.body.addEventListener("flash", function (evt) {
  const { kind, msg } = evt.detail || {};
  if (!msg) return;
  const container = document.getElementById("toast-region");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "alert " + (kind || "info");
  div.textContent = msg;
  container.appendChild(div);
  setTimeout(() => div.remove(), 4000);
});
```

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/static
git commit -m "feat(shell/ui): design-token CSS + theme-switcher + HX-Trigger flash JS"
```

---

## Task 7: Base template + alerts + macros

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/_alerts.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/_macros.html`

- [ ] **Step 1: Create `_base.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/_base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{% block title %}Parcel{% endblock %}</title>
<script>
  // No-flash theme init: set data-theme before first paint.
  (function () {
    try {
      var t = localStorage.getItem("parcel_theme") || "plain";
      document.documentElement.setAttribute("data-theme", t);
    } catch (e) {
      document.documentElement.setAttribute("data-theme", "plain");
    }
  })();
</script>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script defer src="https://unpkg.com/alpinejs@3.13.7/dist/cdn.min.js"></script>
<link rel="stylesheet" href="/static/app.css" />
<script defer src="/static/app.js"></script>
</head>
<body>
  {% if user %}
  <header class="topbar">
    <a href="/" class="brand">◼ parcel</a>
    <span class="env-badge">{{ settings.env }}</span>
    <div class="user-menu" x-data="{ open: false, theme: window.parcelTheme ? window.parcelTheme() : 'plain' }" x-on:click.outside="open = false">
      <span x-on:click="open = !open">{{ user.email }} ▾</span>
      <div class="menu-body" x-show="open" x-cloak>
        <div class="label">Theme</div>
        <button x-on:click="setTheme('plain'); theme='plain'" :style="theme === 'plain' ? 'font-weight:600' : ''">Plain</button>
        <button x-on:click="setTheme('blue'); theme='blue'" :style="theme === 'blue' ? 'font-weight:600' : ''">Blue</button>
        <button x-on:click="setTheme('dark'); theme='dark'" :style="theme === 'dark' ? 'font-weight:600' : ''">Dark</button>
        <div class="rule" style="margin: 6px 0;"></div>
        <a href="/profile">Profile</a>
        <form method="post" action="/logout" style="margin: 0;">
          <button type="submit">Log out</button>
        </form>
      </div>
    </div>
  </header>
  {% endif %}

  {% include "_alerts.html" %}
  <div id="toast-region" style="position:fixed; bottom:20px; right:20px; z-index:200; display:flex; flex-direction:column; gap:8px;"></div>

  {% if user %}
  <div style="display:grid; grid-template-columns: 240px 1fr; min-height: calc(100vh - 48px);">
    <aside class="sidebar">
      {% for section in sidebar %}
      <div class="section-label">{{ section.label }}</div>
      {% for item in section.items %}
      <a href="{{ item.href }}" class="{% if active_path == item.href or (item.href != '/' and active_path.startswith(item.href)) %}active{% endif %}">{{ item.label }}</a>
      {% endfor %}
      {% endfor %}
    </aside>
    <main style="padding: 24px 32px;">
      {% block content %}{% endblock %}
    </main>
  </div>
  {% else %}
    {% block unauth_content %}{% endblock %}
  {% endif %}
</body>
</html>
```

- [ ] **Step 2: Create `_alerts.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/_alerts.html`:

```html
{% if request.state.flash %}
<div class="alert {{ request.state.flash.kind }}">{{ request.state.flash.msg }}</div>
{% endif %}
```

- [ ] **Step 3: Create `_macros.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/_macros.html`:

```html
{% macro button(label, href=None, kind="default", type="button", hx_post=None, hx_target=None, hx_swap=None, hx_confirm=None) %}
  {% if href and not hx_post %}
    <a class="btn {% if kind != 'default' %}{{ kind }}{% endif %}" href="{{ href }}">{{ label }}</a>
  {% elif hx_post %}
    <button class="btn {% if kind != 'default' %}{{ kind }}{% endif %}" type="button" hx-post="{{ hx_post }}"{% if hx_target %} hx-target="{{ hx_target }}"{% endif %}{% if hx_swap %} hx-swap="{{ hx_swap }}"{% endif %}{% if hx_confirm %} hx-confirm="{{ hx_confirm }}"{% endif %}>{{ label }}</button>
  {% else %}
    <button class="btn {% if kind != 'default' %}{{ kind }}{% endif %}" type="{{ type }}">{{ label }}</button>
  {% endif %}
{% endmacro %}

{% macro user_row(u) %}
<tr id="user-row-{{ u.id }}">
  <td><a href="/users/{{ u.id }}">{{ u.email }}</a></td>
  <td><span class="pill {{ 'success' if u.is_active else 'danger' }}">{{ 'active' if u.is_active else 'inactive' }}</span></td>
  <td>
    {% for r in u.roles %}<span class="pill info">{{ r.name }}</span>{% endfor %}
  </td>
  <td style="text-align: right;">
    <a class="btn" href="/users/{{ u.id }}">Edit</a>
  </td>
</tr>
{% endmacro %}

{% macro role_row(r) %}
<tr id="role-row-{{ r.id }}">
  <td><a href="/roles/{{ r.id }}">{{ r.name }}</a>{% if r.is_builtin %} <span class="pill info">built-in</span>{% endif %}</td>
  <td>{{ r.description or '' }}</td>
  <td>{{ r.permissions|length }} permissions</td>
</tr>
{% endmacro %}
```

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/templates/_base.html packages/parcel-shell/src/parcel_shell/ui/templates/_alerts.html packages/parcel-shell/src/parcel_shell/ui/templates/_macros.html
git commit -m "feat(shell/ui): base template + alerts partial + reusable macros"
```

---

## Task 8: Mount UI in app.py (exception handler, middleware, static, lifespan touch-ups)

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`

- [ ] **Step 1: Replace `app.py`**

Replace the contents of `packages/parcel-shell/src/parcel_shell/app.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from parcel_shell.auth.router import router as auth_router
from parcel_shell.config import Settings, get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.health import router as health_router
from parcel_shell.logging import configure_logging
from parcel_shell.middleware import RequestIdMiddleware
from parcel_shell.modules import service as module_service
from parcel_shell.modules.router_admin import router as modules_router
from parcel_shell.rbac.registry import registry as permission_registry
from parcel_shell.rbac.router_admin import router as admin_router
from parcel_shell.ui.dependencies import HTMLRedirect, set_flash
from parcel_shell.ui.middleware import FlashMiddleware

_UI_STATIC_DIR = (
    Path(__file__).resolve().parent / "ui" / "static"
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(env=settings.env, level=settings.log_level)
    log = structlog.get_logger("parcel_shell")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        sessionmaker = create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        app.state.settings = settings

        async with sessionmaker() as s:
            await permission_registry.sync_to_db(s)
            await s.commit()

        async with sessionmaker() as s:
            await module_service.sync_on_boot(s)
            await s.commit()

        log.info("shell.startup", env=settings.env)
        try:
            yield
        finally:
            await app.state.redis.aclose()
            await engine.dispose()
            log.info("shell.shutdown")

    app = FastAPI(title="Parcel Shell", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(FlashMiddleware)

    # Static assets for the UI.
    app.mount("/static", StaticFiles(directory=str(_UI_STATIC_DIR)), name="static")

    # JSON APIs (Phases 1-3).
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(modules_router)

    # HTML UI (Phase 4). Routers imported lazily to keep circular deps simple.
    from parcel_shell.ui.routes.auth import router as ui_auth_router
    from parcel_shell.ui.routes.dashboard import router as ui_dashboard_router
    from parcel_shell.ui.routes.modules import router as ui_modules_router
    from parcel_shell.ui.routes.roles import router as ui_roles_router
    from parcel_shell.ui.routes.users import router as ui_users_router

    app.include_router(ui_auth_router)
    app.include_router(ui_dashboard_router)
    app.include_router(ui_users_router)
    app.include_router(ui_roles_router)
    app.include_router(ui_modules_router)

    @app.exception_handler(HTMLRedirect)
    async def _html_redirect(request: Request, exc: HTMLRedirect) -> RedirectResponse:
        response = RedirectResponse(url=exc.location, status_code=303)
        if exc.flash is not None:
            set_flash(response, exc.flash, secret=settings.session_secret)
        return response

    return app
```

- [ ] **Step 2: Sanity check**

Run: `uv run python -c "from parcel_shell.app import create_app; print('ok')"`
Expected: FAIL with `ModuleNotFoundError: No module named 'parcel_shell.ui.routes.auth'` (routers don't exist yet).

This is expected; the routers are created in Tasks 9–13. Don't commit yet — we'll commit after the first router is in.

---

## Task 9: /login, /logout, /profile routes

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/__init__.py` (empty)
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/auth.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/login.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/profile.html`
- Create: `packages/parcel-shell/tests/test_ui_auth.py`

- [ ] **Step 1: Create `routes/__init__.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/__init__.py` with no content.

- [ ] **Step 2: Create `login.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/login.html`:

```html
{% extends "_base.html" %}
{% block title %}Sign in — Parcel{% endblock %}
{% block unauth_content %}
<div style="display:flex; align-items:center; justify-content:center; min-height: 100vh; padding: 24px;">
  <form class="surface" method="post" action="/login" style="width: 360px; padding: 24px; border-radius: 6px;">
    <h2 style="margin: 0 0 4px; font-family: ui-monospace, monospace; font-weight: 600;">◼ parcel</h2>
    <p class="muted" style="margin: 0 0 20px; font-size: 13px;">Sign in to continue</p>
    {% if error %}
    <div class="alert error" style="margin: 0 0 14px;">{{ error }}</div>
    {% endif %}
    <input type="hidden" name="next" value="{{ next_url or '/' }}">
    <label style="display:block; font-size: 13px; margin-bottom: 4px;">Email</label>
    <input class="input" type="email" name="email" required autofocus value="{{ email or '' }}" style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin-bottom: 4px;">Password</label>
    <input class="input" type="password" name="password" required style="margin-bottom: 16px;">
    <button class="btn primary" type="submit" style="width: 100%;">Sign in</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `profile.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/profile.html`:

```html
{% extends "_base.html" %}
{% block title %}Profile — Parcel{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">Profile</h2>

<div class="surface" style="padding: 20px; max-width: 520px; border-radius: 6px; margin-bottom: 20px;">
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Email</p>
  <p style="margin: 0;">{{ user.email }}</p>
</div>

<div class="surface" style="padding: 20px; max-width: 520px; border-radius: 6px;">
  <h3 style="margin: 0 0 12px;">Change password</h3>
  {% if pw_error %}<div class="alert error" style="margin: 0 0 12px;">{{ pw_error }}</div>{% endif %}
  <form method="post" action="/profile/password">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Current password</label>
    <input class="input" type="password" name="current_password" required style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">New password (min 12 chars)</label>
    <input class="input" type="password" name="new_password" minlength="12" required style="margin-bottom: 16px;">
    <button class="btn primary" type="submit">Change password</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 4: Implement `auth.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from starlette.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth import sessions as sess
from parcel_shell.auth.cookies import sign_session_id, verify_session_cookie
from parcel_shell.auth.dependencies import COOKIE_NAME as SESSION_COOKIE_NAME
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


def _apply_session_cookie(response: Response, *, request: Request, session_id) -> None:
    secret = request.app.state.settings.session_secret
    env = request.app.state.settings.env
    token = sign_session_id(session_id, secret=secret)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(env != "dev"),
        samesite="lax",
        path="/",
    )


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request, next: str | None = None
) -> Response:
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "user": None,
            "sidebar": [],
            "active_path": request.url.path,
            "settings": request.app.state.settings,
            "next_url": next or "/",
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_session),
) -> Response:
    user = await service.authenticate(db, email=email, password=password)
    if user is None:
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "sidebar": [],
                "active_path": request.url.path,
                "settings": request.app.state.settings,
                "next_url": next,
                "email": email,
                "error": "Invalid email or password.",
            },
            status_code=400,
        )
    s = await sess.create_session(
        db,
        user_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    response = RedirectResponse(url=next or "/", status_code=303)
    _apply_session_cookie(response, request=request, session_id=s.id)
    set_flash(
        response, Flash(kind="success", msg="Welcome back."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sid = verify_session_cookie(token, secret=request.app.state.settings.session_secret)
        if sid is not None:
            s = await sess.lookup(db, sid)
            if s is not None:
                await sess.revoke(db, s)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    set_flash(
        response, Flash(kind="info", msg="Signed out."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    perms = await service.effective_permissions(db, user.id)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "sidebar": visible_sections(perms),
            "active_path": request.url.path,
            "settings": request.app.state.settings,
        },
    )


@router.post("/profile/password")
async def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await service.change_password(
            db, user=user, current_password=current_password, new_password=new_password
        )
    except service.InvalidCredentials:
        perms = await service.effective_permissions(db, user.id)
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "user": user,
                "sidebar": visible_sections(perms),
                "active_path": "/profile",
                "settings": request.app.state.settings,
                "pw_error": "Current password is incorrect.",
            },
            status_code=400,
        )
    except ValueError as e:
        perms = await service.effective_permissions(db, user.id)
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "user": user,
                "sidebar": visible_sections(perms),
                "active_path": "/profile",
                "settings": request.app.state.settings,
                "pw_error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(
        response, Flash(kind="success", msg="Password changed."),
        secret=request.app.state.settings.session_secret,
    )
    return response
```

- [ ] **Step 5: Sanity check app imports**

Run: `uv run python -c "from parcel_shell.app import create_app; print('ok')"`
Expected: `ok` (may warn about missing dashboard/users/roles/modules routers — check by running next).

If the above still fails on missing dashboard router, continue to Task 10; app.py imports all five, so the first `uv run python -c ...` succeeds only after all five are in.

For a narrower check that auth routes are wired without the other routers, run:

```bash
uv run python -c "from parcel_shell.ui.routes.auth import router; print(len(router.routes))"
```

Expected: `5` (login GET/POST, logout, profile GET, profile-password POST).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/routes/__init__.py packages/parcel-shell/src/parcel_shell/ui/routes/auth.py packages/parcel-shell/src/parcel_shell/ui/templates/login.html packages/parcel-shell/src/parcel_shell/ui/templates/profile.html
git commit -m "feat(shell/ui): /login, /logout, /profile routes + templates"
```

---

## Task 10: /dashboard + full app.py wiring

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/dashboard.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/dashboard.html`

- [ ] **Step 1: Create `dashboard.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/dashboard.html`:

```html
{% extends "_base.html" %}
{% block title %}Dashboard — Parcel{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">Dashboard</h2>
<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 16px;">
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Signed in as</p>
  <p style="margin: 0;">{{ user.email }}</p>
</div>
<div class="surface" style="padding: 20px; border-radius: 6px;">
  <p class="muted" style="font-size: 13px; margin: 0 0 8px;">Effective permissions ({{ permissions|length }})</p>
  <div>
    {% for p in permissions|sort %}<span class="pill" style="margin: 2px;">{{ p }}</span>{% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Implement `dashboard.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/dashboard.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from starlette.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    perms = await service.effective_permissions(db, user.id)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "sidebar": visible_sections(perms),
            "active_path": "/",
            "settings": request.app.state.settings,
            "permissions": perms,
        },
    )
```

- [ ] **Step 3: Sanity check**

Run: `uv run python -c "from parcel_shell.ui.routes.dashboard import router; print(len(router.routes))"`
Expected: `1`.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/routes/dashboard.py packages/parcel-shell/src/parcel_shell/ui/templates/dashboard.html
git commit -m "feat(shell/ui): / dashboard route + template"
```

---

## Task 11: /users pages (list / new / detail / edit / delete / role assign)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/users.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/users/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/users/new.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/users/detail.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/users/row.html`

- [ ] **Step 1: Create `users/list.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/list.html`:

```html
{% extends "_base.html" %}
{% from "_macros.html" import user_row %}
{% block title %}Users — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">Users</h2>
  <a class="btn primary" href="/users/new">+ New user</a>
</div>
<table class="table">
  <thead><tr><th>Email</th><th>Status</th><th>Roles</th><th></th></tr></thead>
  <tbody id="users-tbody">
    {% for u in users %}{{ user_row(u) }}{% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 2: Create `users/new.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/new.html`:

```html
{% extends "_base.html" %}
{% block title %}New user — Parcel{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">New user</h2>
<div class="surface" style="padding: 20px; max-width: 520px; border-radius: 6px;">
  {% if error %}<div class="alert error" style="margin: 0 0 12px;">{{ error }}</div>{% endif %}
  <form method="post" action="/users">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Email</label>
    <input class="input" type="email" name="email" required value="{{ email or '' }}" style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Password (min 12 chars)</label>
    <input class="input" type="password" name="password" minlength="12" required style="margin-bottom: 16px;">
    <button class="btn primary" type="submit">Create user</button>
    <a class="btn" href="/users" style="margin-left: 8px;">Cancel</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `users/detail.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/detail.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ target_user.email }} — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">{{ target_user.email }}</h2>
  <a href="/users" class="btn">← All users</a>
</div>

<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 20px;">
  <form hx-post="/users/{{ target_user.id }}/edit" hx-swap="none" hx-on::after-request="if(event.detail.successful) window.location.reload()">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Email</label>
    <input class="input" type="email" name="email" required value="{{ target_user.email }}" style="margin-bottom: 12px;">
    <label style="display:flex; align-items:center; gap: 6px; font-size: 13px; margin-bottom: 16px;">
      <input type="checkbox" name="is_active" {% if target_user.is_active %}checked{% endif %}>
      Active
    </label>
    <button class="btn primary" type="submit">Save</button>
    <button class="btn danger" type="button" hx-post="/users/{{ target_user.id }}/delete" hx-confirm="Deactivate this user?" hx-on::after-request="if(event.detail.successful) window.location='/users'" style="margin-left: 8px;">Deactivate</button>
  </form>
</div>

<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 20px;" id="roles-block">
  <h3 style="margin: 0 0 12px;">Roles</h3>
  <div id="user-roles-pills" style="margin-bottom: 12px;">
    {% for r in target_user.roles %}
    <span class="pill info" style="margin-right: 4px;">
      {{ r.name }}
      <button class="btn" style="font-size:11px; padding:0 4px; margin-left: 4px; border:none; background:transparent; color: var(--danger); cursor: pointer;" hx-post="/users/{{ target_user.id }}/roles/{{ r.id }}/remove" hx-target="#roles-block" hx-swap="outerHTML">×</button>
    </span>
    {% endfor %}
  </div>
  <form hx-post="/users/{{ target_user.id }}/roles" hx-target="#roles-block" hx-swap="outerHTML" style="display:flex; gap: 8px;">
    <select class="input" name="role_id" style="flex: 1;">
      <option value="">Add role…</option>
      {% for r in all_roles %}
        {% set assigned = namespace(found=false) %}
        {% for ur in target_user.roles %}{% if ur.id == r.id %}{% set assigned.found = true %}{% endif %}{% endfor %}
        {% if not assigned.found %}<option value="{{ r.id }}">{{ r.name }}</option>{% endif %}
      {% endfor %}
    </select>
    <button class="btn" type="submit">Add</button>
  </form>
</div>

<p><a href="/users/{{ target_user.id }}/sessions">View sessions</a></p>
{% endblock %}
```

- [ ] **Step 4: Create `users/row.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/row.html`:

```html
{% from "_macros.html" import user_row %}
{{ user_row(u) }}
```

- [ ] **Step 5: Implement `users.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/users.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.auth.sessions import revoke_all_for_user
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.rbac.models import Role, Session as DbSession
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": visible_sections(perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    user=Depends(html_require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    users, _ = await service.list_users(db, offset=0, limit=200)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/list.html",
        {**(await _ctx(request, user, db, "/users")), "users": users},
    )


@router.get("/users/new", response_class=HTMLResponse)
async def users_new_form(
    request: Request,
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/new.html",
        await _ctx(request, user, db, "/users"),
    )


@router.post("/users")
async def users_create(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        new_user = await service.create_user(db, email=email, password=password)
    except ValueError as e:
        tpl = get_templates()
        return tpl.TemplateResponse(
            request, "users/new.html",
            {**(await _ctx(request, user, db, "/users")), "error": str(e), "email": email},
            status_code=400,
        )
    response = RedirectResponse(url=f"/users/{new_user.id}", status_code=303)
    set_flash(response, Flash(kind="success", msg=f"Created {new_user.email}"),
              secret=request.app.state.settings.session_secret)
    return response


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def users_detail(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/detail.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.post("/users/{user_id}/edit")
async def users_edit(
    user_id: uuid.UUID,
    request: Request,
    email: str = Form(...),
    is_active: str | None = Form(None),
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.update_user(
        db, user=target, email=email, is_active=(is_active is not None)
    )
    response = Response(status_code=204)
    set_flash(response, Flash(kind="success", msg="User updated."),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/users/{user_id}/delete")
async def users_delete(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    await service.deactivate_user(db, user=target)
    response = Response(status_code=204)
    set_flash(response, Flash(kind="info", msg="User deactivated."),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/users/{user_id}/roles", response_class=HTMLResponse)
async def users_add_role(
    user_id: uuid.UUID,
    request: Request,
    role_id: uuid.UUID = Form(...),
    user=Depends(html_require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    await service.assign_role_to_user(db, user=target, role=role)
    await db.refresh(target, ["roles"])
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/_roles_block.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.post("/users/{user_id}/roles/{role_id}/remove", response_class=HTMLResponse)
async def users_remove_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("users.roles.assign")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    target = await service.get_user(db, user_id)
    role = await service.get_role(db, role_id)
    if target is None or role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    await service.unassign_role_from_user(db, user=target, role=role)
    await db.refresh(target, ["roles"])
    all_roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/_roles_block.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "all_roles": all_roles,
        },
    )


@router.get("/users/{user_id}/sessions", response_class=HTMLResponse)
async def users_sessions(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("sessions.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    from datetime import datetime, timezone
    target = await service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(DbSession)
            .where(
                DbSession.user_id == user_id,
                DbSession.revoked_at.is_(None),
                DbSession.expires_at > now,
            )
            .order_by(DbSession.last_seen_at.desc())
        )
    ).scalars().all()
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "users/sessions.html",
        {
            **(await _ctx(request, user, db, "/users")),
            "target_user": target,
            "sessions": rows,
        },
    )


@router.post("/users/{user_id}/sessions/revoke")
async def users_sessions_revoke(
    user_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("sessions.revoke")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_all_for_user(db, user_id)
    response = RedirectResponse(url=f"/users/{user_id}/sessions", status_code=303)
    set_flash(response, Flash(kind="success", msg="All sessions revoked."),
              secret=request.app.state.settings.session_secret)
    return response
```

- [ ] **Step 6: Create the two partial templates referenced above**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/_roles_block.html`:

```html
<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 20px;" id="roles-block">
  <h3 style="margin: 0 0 12px;">Roles</h3>
  <div id="user-roles-pills" style="margin-bottom: 12px;">
    {% for r in target_user.roles %}
    <span class="pill info" style="margin-right: 4px;">
      {{ r.name }}
      <button class="btn" style="font-size:11px; padding:0 4px; margin-left: 4px; border:none; background:transparent; color: var(--danger); cursor: pointer;" hx-post="/users/{{ target_user.id }}/roles/{{ r.id }}/remove" hx-target="#roles-block" hx-swap="outerHTML">×</button>
    </span>
    {% endfor %}
  </div>
  <form hx-post="/users/{{ target_user.id }}/roles" hx-target="#roles-block" hx-swap="outerHTML" style="display:flex; gap: 8px;">
    <select class="input" name="role_id" style="flex: 1;">
      <option value="">Add role…</option>
      {% for r in all_roles %}
        {% set assigned = namespace(found=false) %}
        {% for ur in target_user.roles %}{% if ur.id == r.id %}{% set assigned.found = true %}{% endif %}{% endfor %}
        {% if not assigned.found %}<option value="{{ r.id }}">{{ r.name }}</option>{% endif %}
      {% endfor %}
    </select>
    <button class="btn" type="submit">Add</button>
  </form>
</div>
```

Create `packages/parcel-shell/src/parcel_shell/ui/templates/users/sessions.html`:

```html
{% extends "_base.html" %}
{% block title %}Sessions for {{ target_user.email }} — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">Sessions — {{ target_user.email }}</h2>
  <div>
    <a href="/users/{{ target_user.id }}" class="btn">← Back</a>
    <form method="post" action="/users/{{ target_user.id }}/sessions/revoke" style="display:inline;">
      <button class="btn danger" type="submit">Revoke all</button>
    </form>
  </div>
</div>
<table class="table">
  <thead><tr><th>Created</th><th>Last seen</th><th>IP</th><th>User agent</th></tr></thead>
  <tbody>
    {% for s in sessions %}
    <tr>
      <td>{{ s.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
      <td>{{ s.last_seen_at.strftime("%Y-%m-%d %H:%M") }}</td>
      <td>{{ s.ip_address or '—' }}</td>
      <td style="max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ s.user_agent or '—' }}</td>
    </tr>
    {% else %}
    <tr><td colspan="4" class="muted" style="text-align:center;">No active sessions.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/routes/users.py packages/parcel-shell/src/parcel_shell/ui/templates/users/
git commit -m "feat(shell/ui): /users CRUD pages + sessions list/revoke"
```

---

## Task 12: /roles pages

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/roles.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/roles/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/roles/new.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/roles/detail.html`

- [ ] **Step 1: Create `roles/list.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/roles/list.html`:

```html
{% extends "_base.html" %}
{% from "_macros.html" import role_row %}
{% block title %}Roles — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">Roles</h2>
  <a class="btn primary" href="/roles/new">+ New role</a>
</div>
<table class="table">
  <thead><tr><th>Name</th><th>Description</th><th>Permissions</th></tr></thead>
  <tbody>
    {% for r in roles %}{{ role_row(r) }}{% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 2: Create `roles/new.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/roles/new.html`:

```html
{% extends "_base.html" %}
{% block title %}New role — Parcel{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">New role</h2>
<div class="surface" style="padding: 20px; max-width: 520px; border-radius: 6px;">
  {% if error %}<div class="alert error" style="margin: 0 0 12px;">{{ error }}</div>{% endif %}
  <form method="post" action="/roles">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Name</label>
    <input class="input" type="text" name="name" required value="{{ name or '' }}" style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Description</label>
    <input class="input" type="text" name="description" value="{{ description or '' }}" style="margin-bottom: 16px;">
    <button class="btn primary" type="submit">Create role</button>
    <a class="btn" href="/roles" style="margin-left: 8px;">Cancel</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `roles/detail.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/roles/detail.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ role.name }} — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">{{ role.name }} {% if role.is_builtin %}<span class="pill info" style="font-size: 12px;">built-in</span>{% endif %}</h2>
  <a href="/roles" class="btn">← All roles</a>
</div>

<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 20px;">
  <form method="post" action="/roles/{{ role.id }}/edit">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Name</label>
    <input class="input" type="text" name="name" required value="{{ role.name }}" {% if role.is_builtin %}disabled{% endif %} style="margin-bottom: 12px;">
    <label style="display:block; font-size: 13px; margin: 0 0 4px;">Description</label>
    <input class="input" type="text" name="description" value="{{ role.description or '' }}" {% if role.is_builtin %}disabled{% endif %} style="margin-bottom: 16px;">
    {% if not role.is_builtin %}
    <button class="btn primary" type="submit">Save</button>
    <button class="btn danger" type="submit" formaction="/roles/{{ role.id }}/delete" formmethod="post" style="margin-left: 8px;" onclick="return confirm('Delete this role?')">Delete</button>
    {% else %}
    <p class="muted" style="margin:0; font-size: 13px;">Built-in roles cannot be modified or deleted.</p>
    {% endif %}
  </form>
</div>

<div class="surface" style="padding: 20px; border-radius: 6px;" id="role-perms-block">
  <h3 style="margin: 0 0 12px;">Permissions ({{ role.permissions|length }})</h3>
  <div style="margin-bottom: 12px;">
    {% for p in role.permissions|sort(attribute='name') %}
    <span class="pill info" style="margin: 2px;">
      {{ p.name }}
      {% if not role.is_builtin %}
      <button class="btn" style="font-size:11px; padding:0 4px; margin-left: 4px; border:none; background:transparent; color: var(--danger); cursor: pointer;" hx-post="/roles/{{ role.id }}/permissions/{{ p.name }}/remove" hx-target="#role-perms-block" hx-swap="outerHTML">×</button>
      {% endif %}
    </span>
    {% endfor %}
  </div>
  {% if not role.is_builtin %}
  <form hx-post="/roles/{{ role.id }}/permissions" hx-target="#role-perms-block" hx-swap="outerHTML" style="display:flex; gap: 8px;">
    <select class="input" name="permission_name" style="flex: 1;">
      <option value="">Add permission…</option>
      {% for p in all_permissions %}
        {% set assigned = namespace(found=false) %}
        {% for rp in role.permissions %}{% if rp.name == p.name %}{% set assigned.found = true %}{% endif %}{% endfor %}
        {% if not assigned.found %}<option value="{{ p.name }}">{{ p.name }} — {{ p.description }}</option>{% endif %}
      {% endfor %}
    </select>
    <button class="btn" type="submit">Add</button>
  </form>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: Implement `roles.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/roles.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": visible_sections(perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


@router.get("/roles", response_class=HTMLResponse)
async def roles_list(
    request: Request,
    user=Depends(html_require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    roles = await service.list_roles(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "roles/list.html",
        {**(await _ctx(request, user, db, "/roles")), "roles": roles},
    )


@router.get("/roles/new", response_class=HTMLResponse)
async def roles_new_form(
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "roles/new.html",
        await _ctx(request, user, db, "/roles"),
    )


@router.post("/roles")
async def roles_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    new_role = await service.create_role(db, name=name, description=description or None)
    response = RedirectResponse(url=f"/roles/{new_role.id}", status_code=303)
    set_flash(response, Flash(kind="success", msg=f"Created role {new_role.name}"),
              secret=request.app.state.settings.session_secret)
    return response


@router.get("/roles/{role_id}", response_class=HTMLResponse)
async def roles_detail(
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("roles.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "roles/detail.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )


@router.post("/roles/{role_id}/edit")
async def roles_edit(
    role_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.update_role(db, role, name=name, description=description or None)
    except service.BuiltinRoleError:
        response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
        set_flash(response, Flash(kind="error", msg="Built-in roles cannot be modified."),
                  secret=request.app.state.settings.session_secret)
        return response
    response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
    set_flash(response, Flash(kind="success", msg="Role updated."),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/roles/{role_id}/delete")
async def roles_delete(
    role_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.delete_role(db, role)
    except service.BuiltinRoleError:
        response = RedirectResponse(url=f"/roles/{role_id}", status_code=303)
        set_flash(response, Flash(kind="error", msg="Built-in roles cannot be deleted."),
                  secret=request.app.state.settings.session_secret)
        return response
    response = RedirectResponse(url="/roles", status_code=303)
    set_flash(response, Flash(kind="success", msg=f"Deleted role {role.name}"),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/roles/{role_id}/permissions", response_class=HTMLResponse)
async def roles_add_permission(
    role_id: uuid.UUID,
    request: Request,
    permission_name: str = Form(...),
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    try:
        await service.assign_permission_to_role(
            db, role=role, permission_name=permission_name
        )
    except service.PermissionNotRegistered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permission_not_found") from None
    await db.refresh(role, ["permissions"])
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "roles/_perms_block.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )


@router.post("/roles/{role_id}/permissions/{name}/remove", response_class=HTMLResponse)
async def roles_remove_permission(
    role_id: uuid.UUID,
    name: str,
    request: Request,
    user=Depends(html_require_permission("roles.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    role = await service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role_not_found")
    await service.unassign_permission_from_role(db, role=role, permission_name=name)
    await db.refresh(role, ["permissions"])
    all_permissions = await service.list_permissions(db)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "roles/_perms_block.html",
        {
            **(await _ctx(request, user, db, "/roles")),
            "role": role,
            "all_permissions": all_permissions,
        },
    )
```

- [ ] **Step 5: Create the permissions-block partial**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/roles/_perms_block.html`:

```html
<div class="surface" style="padding: 20px; border-radius: 6px;" id="role-perms-block">
  <h3 style="margin: 0 0 12px;">Permissions ({{ role.permissions|length }})</h3>
  <div style="margin-bottom: 12px;">
    {% for p in role.permissions|sort(attribute='name') %}
    <span class="pill info" style="margin: 2px;">
      {{ p.name }}
      {% if not role.is_builtin %}
      <button class="btn" style="font-size:11px; padding:0 4px; margin-left: 4px; border:none; background:transparent; color: var(--danger); cursor: pointer;" hx-post="/roles/{{ role.id }}/permissions/{{ p.name }}/remove" hx-target="#role-perms-block" hx-swap="outerHTML">×</button>
      {% endif %}
    </span>
    {% endfor %}
  </div>
  {% if not role.is_builtin %}
  <form hx-post="/roles/{{ role.id }}/permissions" hx-target="#role-perms-block" hx-swap="outerHTML" style="display:flex; gap: 8px;">
    <select class="input" name="permission_name" style="flex: 1;">
      <option value="">Add permission…</option>
      {% for p in all_permissions %}
        {% set assigned = namespace(found=false) %}
        {% for rp in role.permissions %}{% if rp.name == p.name %}{% set assigned.found = true %}{% endif %}{% endfor %}
        {% if not assigned.found %}<option value="{{ p.name }}">{{ p.name }} — {{ p.description }}</option>{% endif %}
      {% endfor %}
    </select>
    <button class="btn" type="submit">Add</button>
  </form>
  {% endif %}
</div>
```

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/routes/roles.py packages/parcel-shell/src/parcel_shell/ui/templates/roles/
git commit -m "feat(shell/ui): /roles CRUD pages + permission assign/unassign (HTMX)"
```

---

## Task 13: /modules pages

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ui/routes/modules.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/modules/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/modules/detail.html`

- [ ] **Step 1: Create `modules/list.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/modules/list.html`:

```html
{% extends "_base.html" %}
{% block title %}Modules — Parcel{% endblock %}
{% block content %}
<h2 style="margin: 0 0 16px;">Modules</h2>
<table class="table">
  <thead><tr><th>Name</th><th>Version</th><th>Status</th><th></th></tr></thead>
  <tbody>
    {% for m in modules %}
    <tr>
      <td><a href="/modules/{{ m.name }}">{{ m.name }}</a></td>
      <td>{{ m.version }}</td>
      <td>
        {% if m.is_active is none %}
          {% if m.is_discoverable %}<span class="pill">available</span>{% endif %}
        {% elif m.is_active %}
          <span class="pill success">installed</span>
        {% else %}
          <span class="pill danger">inactive</span>{% if not m.is_discoverable %} <span class="pill">missing</span>{% endif %}
        {% endif %}
      </td>
      <td style="text-align: right;"><a class="btn" href="/modules/{{ m.name }}">Details →</a></td>
    </tr>
    {% else %}
    <tr><td colspan="4" class="muted" style="text-align:center;">No modules discovered.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 2: Create `modules/detail.html`**

Create `packages/parcel-shell/src/parcel_shell/ui/templates/modules/detail.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ summary.name }} — Parcel{% endblock %}
{% block content %}
<div style="display:flex; align-items:baseline; justify-content: space-between; margin-bottom: 16px;">
  <h2 style="margin: 0;">{{ summary.name }}</h2>
  <a href="/modules" class="btn">← All modules</a>
</div>

<div class="surface" style="padding: 20px; border-radius: 6px; margin-bottom: 20px;">
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Version</p>
  <p style="margin: 0 0 10px;">{{ summary.version or '—' }}</p>
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Status</p>
  <p style="margin: 0 0 10px;">
    {% if summary.is_active is none %}
      {% if summary.is_discoverable %}<span class="pill">Available — not installed</span>{% else %}<span class="pill danger">unknown</span>{% endif %}
    {% elif summary.is_active %}
      <span class="pill success">Installed and active</span>
    {% else %}
      <span class="pill danger">Inactive</span>{% if not summary.is_discoverable %} <span class="pill">Package missing</span>{% endif %}
    {% endif %}
  </p>
  {% if summary.declared_capabilities %}
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Declared capabilities</p>
  <p style="margin: 0 0 10px;">
    {% for c in summary.declared_capabilities %}<span class="pill info" style="margin: 2px;">{{ c }}</span>{% endfor %}
  </p>
  {% endif %}
  {% if summary.is_active is not none %}
  <p class="muted" style="font-size: 13px; margin: 0 0 4px;">Approved capabilities</p>
  <p style="margin: 0;">
    {% if summary.approved_capabilities %}
      {% for c in summary.approved_capabilities %}<span class="pill info" style="margin: 2px;">{{ c }}</span>{% endfor %}
    {% else %}<span class="muted">none</span>{% endif %}
  </p>
  {% endif %}
</div>

{% if summary.is_active is none and summary.is_discoverable %}
<div class="surface" style="padding: 20px; border-radius: 6px;">
  <h3 style="margin: 0 0 12px;">Install</h3>
  <form method="post" action="/modules/install">
    <input type="hidden" name="name" value="{{ summary.name }}">
    {% if summary.declared_capabilities %}
    <p style="font-size: 13px; margin: 0 0 8px;">This module requires the following capabilities. Check each to approve.</p>
    {% for c in summary.declared_capabilities %}
    <label style="display:flex; align-items:center; gap: 6px; font-size: 13px; margin-bottom: 6px;">
      <input type="checkbox" name="approve_capabilities" value="{{ c }}">
      <code>{{ c }}</code>
    </label>
    {% endfor %}
    {% else %}
    <p style="font-size: 13px; margin: 0 0 12px;" class="muted">This module declares no capabilities.</p>
    {% endif %}
    <button class="btn primary" type="submit" style="margin-top: 8px;">Install</button>
  </form>
</div>
{% elif summary.is_active is not none %}
<div class="surface" style="padding: 20px; border-radius: 6px;">
  <form method="post" action="/modules/{{ summary.name }}/upgrade" style="display:inline; margin-right: 8px;">
    <button class="btn" type="submit" {% if not summary.is_discoverable %}disabled{% endif %}>Run migrations (upgrade)</button>
  </form>
  <form method="post" action="/modules/{{ summary.name }}/uninstall" style="display:inline; margin-right: 8px;">
    <button class="btn" type="submit">Uninstall (soft)</button>
  </form>
  <form method="post" action="/modules/{{ summary.name }}/uninstall?drop_data=true" style="display:inline;" onsubmit="return confirm('Hard uninstall — this will drop the module schema and all its data. Continue?')">
    <button class="btn danger" type="submit">Uninstall + drop data</button>
  </form>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Implement `modules.py`**

Create `packages/parcel-shell/src/parcel_shell/ui/routes/modules.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.db import get_session
from parcel_shell.modules import service as module_service
from parcel_shell.modules.discovery import DiscoveredModule, discover_modules
from parcel_shell.modules.models import InstalledModule
from parcel_shell.modules.schemas import ModuleSummary
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": visible_sections(perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


def _discovered_index() -> dict[str, DiscoveredModule]:
    return {d.module.name: d for d in discover_modules()}


def _summary(name: str, row: InstalledModule | None, d: DiscoveredModule | None) -> ModuleSummary:
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


@router.get("/modules", response_class=HTMLResponse)
async def modules_list(
    request: Request,
    user=Depends(html_require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    rows = (await db.execute(select(InstalledModule))).scalars().all()
    by_name = {r.name: r for r in rows}
    names = sorted(set(index) | set(by_name))
    modules = [_summary(n, by_name.get(n), index.get(n)) for n in names]
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "modules/list.html",
        {**(await _ctx(request, user, db, "/modules")), "modules": modules},
    )


@router.get("/modules/{name}", response_class=HTMLResponse)
async def modules_detail(
    name: str,
    request: Request,
    user=Depends(html_require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    row = await db.get(InstalledModule, name)
    if row is None and name not in index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found")
    summary = _summary(name, row, index.get(name))
    tpl = get_templates()
    return tpl.TemplateResponse(
        request, "modules/detail.html",
        {**(await _ctx(request, user, db, "/modules")), "summary": summary},
    )


@router.post("/modules/install")
async def modules_install(
    request: Request,
    name: str = Form(...),
    user=Depends(html_require_permission("modules.install")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    form = await request.form()
    approved: list[str] = form.getlist("approve_capabilities")
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.install_module(
            db,
            name=name,
            approve_capabilities=approved,
            discovered=index,
            database_url=database_url,
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_discovered") from None
    except module_service.ModuleAlreadyInstalled:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(response, Flash(kind="error", msg="Already installed."),
                  secret=request.app.state.settings.session_secret)
        return response
    except module_service.CapabilityMismatch:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(
            response, Flash(kind="error", msg="Approve all declared capabilities to install."),
            secret=request.app.state.settings.session_secret,
        )
        return response
    except module_service.ModuleMigrationFailed as e:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(response, Flash(kind="error", msg=f"Install failed: {e}"),
                  secret=request.app.state.settings.session_secret)
        return response
    response = RedirectResponse(url=f"/modules/{name}", status_code=303)
    set_flash(response, Flash(kind="success", msg=f"Installed {name}."),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/modules/{name}/upgrade")
async def modules_upgrade(
    name: str,
    request: Request,
    user=Depends(html_require_permission("modules.upgrade")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.upgrade_module(
            db, name=name, discovered=index, database_url=database_url
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from None
    except module_service.ModuleMigrationFailed as e:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(response, Flash(kind="error", msg=f"Upgrade failed: {e}"),
                  secret=request.app.state.settings.session_secret)
        return response
    response = RedirectResponse(url=f"/modules/{name}", status_code=303)
    set_flash(response, Flash(kind="success", msg=f"{name} migrated to head."),
              secret=request.app.state.settings.session_secret)
    return response


@router.post("/modules/{name}/uninstall")
async def modules_uninstall(
    name: str,
    request: Request,
    drop_data: bool = Query(default=False),
    user=Depends(html_require_permission("modules.uninstall")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.uninstall_module(
            db, name=name, drop_data=drop_data, discovered=index, database_url=database_url
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from None
    response = RedirectResponse(url="/modules", status_code=303)
    msg = f"{name} uninstalled" + (" and data dropped" if drop_data else " (soft)") + "."
    set_flash(response, Flash(kind="success", msg=msg),
              secret=request.app.state.settings.session_secret)
    return response
```

- [ ] **Step 4: Verify app.py imports clean**

Run: `uv run python -c "from parcel_shell.app import create_app; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/app.py packages/parcel-shell/src/parcel_shell/ui/routes/modules.py packages/parcel-shell/src/parcel_shell/ui/templates/modules/
git commit -m "feat(shell/ui): /modules UI — list, detail, install/upgrade/uninstall"
```

---

## Task 14: UI tests (auth + layout + flash)

**Files:**
- Create: `packages/parcel-shell/tests/test_ui_auth.py`
- Create: `packages/parcel-shell/tests/test_ui_layout.py`

- [ ] **Step 1: Create `test_ui_auth.py`**

Create `packages/parcel-shell/tests/test_ui_auth.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_login_page_renders(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/login")
    assert r.status_code == 200
    assert "◼ parcel" in r.text
    assert 'name="email"' in r.text


async def test_root_unauthed_redirects_to_login(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login?next=%2F")


async def test_users_unauthed_redirects_with_next(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/users", follow_redirects=False)
    assert r.status_code == 303
    assert "next=%2Fusers" in r.headers["location"]


async def test_login_bad_credentials_re_renders(committing_client: AsyncClient) -> None:
    r = await committing_client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "nope-nope-nope"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Invalid email or password" in r.text


async def test_login_success_redirects_to_dashboard(
    committing_client: AsyncClient, settings
) -> None:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from parcel_shell.rbac import service

    email = f"u-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234"
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            await service.create_user(s, email=email, password=password)
            await s.commit()

        r = await committing_client.post(
            "/login",
            data={"email": email, "password": password, "next": "/"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert "parcel_session" in r.cookies

        r2 = await committing_client.get("/")
        assert r2.status_code == 200
        assert "Dashboard" in r2.text
    finally:
        from sqlalchemy import select
        from parcel_shell.rbac.models import User
        async with factory() as s:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_logout_redirects_to_login(committing_admin) -> None:
    r = await committing_admin.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


async def test_profile_renders_for_authed(committing_admin) -> None:
    r = await committing_admin.get("/profile")
    assert r.status_code == 200
    assert "Change password" in r.text
```

(Note: the `committing_admin` fixture from Phase 3's `conftest.py` is sufficient — it logs in via `/auth/login` and the resulting session cookie is honored by the HTML routes too.)

- [ ] **Step 2: Create `test_ui_layout.py`**

Create `packages/parcel-shell/tests/test_ui_layout.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def test_admin_sees_all_sidebar_sections(committing_admin) -> None:
    r = await committing_admin.get("/")
    assert r.status_code == 200
    assert "Overview" in r.text
    assert "Access" in r.text
    assert "Users" in r.text
    assert "Roles" in r.text
    assert "System" in r.text
    assert "Modules" in r.text


async def test_plain_user_sees_only_dashboard(
    committing_client: AsyncClient, settings
) -> None:
    # Create a non-admin user, log in via HTML form.
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from parcel_shell.rbac import service

    email = f"plain-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234"
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            await service.create_user(s, email=email, password=password)
            await s.commit()

        r = await committing_client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert r.status_code == 303
        r2 = await committing_client.get("/")
        assert r2.status_code == 200
        assert "Dashboard" in r2.text
        # Plain user lacks users.read / roles.read / modules.read — those labels
        # should not be in the sidebar.
        assert ">Users<" not in r2.text
        assert ">Roles<" not in r2.text
        assert ">Modules<" not in r2.text
    finally:
        async with factory() as s:
            from sqlalchemy import select
            from parcel_shell.rbac.models import User
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_theme_init_script_in_head(committing_admin) -> None:
    r = await committing_admin.get("/")
    assert 'localStorage.getItem("parcel_theme")' in r.text
    assert 'data-theme' in r.text


async def test_active_sidebar_highlight(committing_admin) -> None:
    r = await committing_admin.get("/users")
    # The Users link should carry the "active" class.
    assert 'href="/users" class="active"' in r.text or 'class="active"' in r.text
```

- [ ] **Step 3: Run the UI auth + layout tests**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_auth.py packages/parcel-shell/tests/test_ui_layout.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/tests/test_ui_auth.py packages/parcel-shell/tests/test_ui_layout.py
git commit -m "test(shell/ui): auth redirects, sidebar permission filtering, theme init"
```

---

## Task 15: UI tests (users + roles + modules)

**Files:**
- Create: `packages/parcel-shell/tests/test_ui_users.py`
- Create: `packages/parcel-shell/tests/test_ui_roles.py`
- Create: `packages/parcel-shell/tests/test_ui_modules.py`

- [ ] **Step 1: Create `test_ui_users.py`**

Create `packages/parcel-shell/tests/test_ui_users.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def test_users_list_shows_admin(committing_admin) -> None:
    r = await committing_admin.get("/users")
    assert r.status_code == 200
    assert "@test.example.com" in r.text


async def test_create_user_via_form_redirects_to_detail(
    committing_admin, settings
) -> None:
    email = f"new-{uuid.uuid4().hex[:8]}@test.example.com"
    try:
        r = await committing_admin.post(
            "/users",
            data={"email": email, "password": "password-1234"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/users/")
        detail = await committing_admin.get(r.headers["location"])
        assert email in detail.text
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(
                text("DELETE FROM shell.users WHERE email = :e"), {"e": email}
            )
            await s.commit()
        await engine.dispose()


async def test_edit_user_htmx_returns_204(committing_admin, settings) -> None:
    email = f"ed-{uuid.uuid4().hex[:8]}@test.example.com"
    try:
        r = await committing_admin.post(
            "/users",
            data={"email": email, "password": "password-1234"},
            follow_redirects=False,
        )
        uid = r.headers["location"].rsplit("/", 1)[1]
        r2 = await committing_admin.post(
            f"/users/{uid}/edit",
            data={"email": email, "is_active": "on"},
        )
        assert r2.status_code == 204
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(
                text("DELETE FROM shell.users WHERE email = :e"), {"e": email}
            )
            await s.commit()
        await engine.dispose()
```

- [ ] **Step 2: Create `test_ui_roles.py`**

Create `packages/parcel-shell/tests/test_ui_roles.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def test_roles_list_shows_admin_role_as_builtin(committing_admin) -> None:
    r = await committing_admin.get("/roles")
    assert r.status_code == 200
    assert "admin" in r.text
    assert "built-in" in r.text


async def test_create_role_redirects_to_detail(committing_admin, settings) -> None:
    name = f"r-{uuid.uuid4().hex[:6]}"
    try:
        r = await committing_admin.post(
            "/roles",
            data={"name": name, "description": "test role"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/roles/")
        detail = await committing_admin.get(r.headers["location"])
        assert name in detail.text
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(
                text("DELETE FROM shell.roles WHERE name = :n"), {"n": name}
            )
            await s.commit()
        await engine.dispose()


async def test_delete_builtin_role_shows_error_flash(committing_admin) -> None:
    roles = await committing_admin.get("/roles")
    # Find admin role id.
    import re
    m = re.search(r'href="/roles/([^"]+)"[^>]*>admin', roles.text)
    assert m is not None
    admin_id = m.group(1)
    r = await committing_admin.post(
        f"/roles/{admin_id}/delete", follow_redirects=False
    )
    assert r.status_code == 303
    assert "parcel_flash" in r.headers.get("set-cookie", "")
```

- [ ] **Step 3: Create `test_ui_modules.py`**

Create `packages/parcel-shell/tests/test_ui_modules.py`:

```python
from __future__ import annotations


async def test_modules_list_empty_without_patched_entry_points(committing_admin) -> None:
    r = await committing_admin.get("/modules")
    assert r.status_code == 200
    assert "Modules" in r.text


async def test_modules_list_shows_discovered(committing_admin, patch_entry_points) -> None:
    r = await committing_admin.get("/modules")
    assert r.status_code == 200
    assert ">test<" in r.text
    assert "available" in r.text


async def test_install_without_capability_shows_error_flash(
    committing_admin, patch_entry_points
) -> None:
    r = await committing_admin.post(
        "/modules/install",
        data={"name": "test"},  # no approve_capabilities — module declares http_egress
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "parcel_flash" in r.headers.get("set-cookie", "")


async def test_install_happy_path(committing_admin, patch_entry_points) -> None:
    try:
        r = await committing_admin.post(
            "/modules/install",
            data=[("name", "test"), ("approve_capabilities", "http_egress")],
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/modules/test"
        detail = await committing_admin.get("/modules/test")
        assert "Installed and active" in detail.text
    finally:
        await committing_admin.post("/modules/test/uninstall?drop_data=true")


async def test_uninstall_hard_via_query_param(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/modules/install",
        data=[("name", "test"), ("approve_capabilities", "http_egress")],
    )
    r = await committing_admin.post(
        "/modules/test/uninstall?drop_data=true", follow_redirects=False
    )
    assert r.status_code == 303
    detail = await committing_admin.get("/modules/test")
    assert "Available" in detail.text
```

- [ ] **Step 4: Run UI user/role/module tests**

Run: `uv run pytest packages/parcel-shell/tests/test_ui_users.py packages/parcel-shell/tests/test_ui_roles.py packages/parcel-shell/tests/test_ui_modules.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/tests/test_ui_users.py packages/parcel-shell/tests/test_ui_roles.py packages/parcel-shell/tests/test_ui_modules.py
git commit -m "test(shell/ui): users, roles, modules HTML route coverage"
```

---

## Task 16: Full-suite check + Docker verification

**Files:** None (verification only).

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest`
Expected: all tests green — Phase 1 + 2 + 3 + 4.

- [ ] **Step 2: Rebuild shell image and bring up**

```bash
docker compose build shell
docker compose up -d shell
```

Wait for healthy.

- [ ] **Step 3: Open browser**

Point a browser at `http://localhost:8000/`. Expected flow:

1. `/` redirects to `/login?next=%2F`.
2. Log in with `admin@parcel.example.com` / `pw-at-least-12-chars` (the admin from Phase 2 bootstrap).
3. Dashboard loads. Sidebar shows Dashboard / Users / Roles / Modules.
4. User menu (top right) → Theme → `Plain / Blue / Dark`. Page re-skins without reload.
5. Users list renders; click into admin user; edit is_active off, save; flash confirms.
6. Roles list renders with `admin` marked built-in. Delete is disabled.
7. Modules list is empty (or shows the fixture if a module is pip-installed in the container).
8. Logout returns to /login.

No commit for this task.

---

## Task 17: Quality gates + docs

**Files:**
- Modify: `packages/parcel-shell/tests/conftest.py` — if any plan test depends on a fixture that isn't there yet, add it. (The plan leaves `committing_admin`, `committing_client`, `settings`, `patch_entry_points`, `discovered_test_module` unchanged — all already defined in Phase 2/3 conftest.)
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run ruff + pyright**

```bash
uv run ruff check packages/parcel-shell packages/parcel-sdk
uv run ruff format --check packages/parcel-shell packages/parcel-sdk
uv run pyright packages/parcel-shell packages/parcel-sdk
```

If anything fails:

```bash
uv run ruff check packages/parcel-shell packages/parcel-sdk --fix
uv run ruff format packages/parcel-shell packages/parcel-sdk
```

For pyright issues on `committing_admin` fixture or template-response typing, add `# pyright: reportCallIssue=false` or `# pyright: reportGeneralTypeIssues=false` at the top of the offending test file — the same pattern used in Phase 2's `test_config.py`.

- [ ] **Step 2: Update `README.md`**

Replace the "Then log in via the JSON API" section with a "Use the admin UI" section:

```markdown
### Use the admin UI

Open `http://localhost:8000/` in a browser. You'll be redirected to `/login`. Sign in with the admin credentials you bootstrapped above; the dashboard opens and a sidebar gives you access to Users, Roles, Modules.

The JSON API at `/auth/*`, `/admin/*`, and `/health/*` continues to work unchanged — see below if you prefer `curl`.
```

Keep the `curl` section after that for the power-user / scripting audience.

Also update the Status line:

```markdown
**Status:** Pre-alpha. Phase 4 complete — browser-based admin UI with login, dashboard, users/roles/modules CRUD, and three user-selectable themes. Ships as server-rendered Jinja + HTMX; no npm build step.
```

- [ ] **Step 3: Update `CLAUDE.md`**

Change the "Current phase" block to:

```markdown
**Phase 4 — Admin UI shell done.** Server-rendered Jinja templates + Tailwind (Play CDN) + HTMX + Alpine.js. HTML routes at `/login`, `/`, `/profile`, `/users/*`, `/roles/*`, `/modules/*`. Unauthenticated HTML requests redirect to `/login?next=<path>`. Three user-selectable themes (`plain` default, `blue`, `dark`) swapped via `[data-theme]` on `<html>`, persisted to localStorage. Flash messages ride in a signed `parcel_flash` cookie. JSON APIs at `/auth/*`, `/admin/*`, `/health/*` are unchanged.

Next: **Phase 5 — Contacts demo module.** Start a new session; prompt: "Begin Phase 5: Contacts module per `CLAUDE.md` roadmap." Do not begin Phase 5 inside the Phase 4 commit cluster.
```

In the "Phased roadmap" table, change Phase 4 to `✅ done` and Phase 5 to `⏭ next`.

Append to the "Locked-in decisions" table:

```markdown
| Phase 4 shell deps | jinja2, python-multipart |
| Phase 4 client deps | Tailwind (Play CDN), HTMX (2.x CDN), Alpine.js (3.x CDN) — no npm build step |
| HTML auth | Separate `current_user_html` dep raises `HTMLRedirect("/login?next=…")`; a global exception handler renders it as a 303 |
| Themes | Three user-selectable (`plain` default / `blue` / `dark`), `[data-theme]` on `<html>`, persisted to `localStorage["parcel_theme"]` |
| Flash messages | Signed `parcel_flash` HTTP-only cookie (itsdangerous), read + cleared by FlashMiddleware |
| URL boundary | HTML at `/`, `/login`, `/profile`, `/users`, `/roles`, `/modules`; JSON stays at `/auth/*`, `/admin/*`, `/health/*` |
| CSRF | Phase 4 relies on Phase 2's `SameSite=Lax` cookie; token middleware deferred |
```

- [ ] **Step 4: Final commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: close Phase 4, document admin UI + theme system"
```

---

## Verification summary (Phase 4 definition of done)

- [ ] `/` unauthed → 303 to `/login?next=/`.
- [ ] Login form works; successful login sets cookie + redirects; bad creds re-render with error.
- [ ] Dashboard, Users list, Roles list, Modules list all render for admin.
- [ ] User menu theme switcher swaps `data-theme` and persists to `localStorage`.
- [ ] Create user, edit, deactivate, assign role, view sessions, revoke — all via browser.
- [ ] Create role, assign permissions, try to delete `admin` → red flash; delete a non-builtin role → green flash + redirect to list.
- [ ] Install module (via test fixture), upgrade, hard-uninstall with `?drop_data=true` — all via browser.
- [ ] `uv run pytest` green.
- [ ] `uv run ruff check` + `uv run pyright` clean.
- [ ] README + CLAUDE.md updated; Phase 4 ✅, Phase 5 ⏭ next.
