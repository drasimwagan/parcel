# Phase 6 — SDK Polish + `parcel` CLI — Design Spec

**Date:** 2026-04-23
**Status:** Drafted, awaiting user review
**Roadmap reference:** CLAUDE.md Phase 6 — "SDK polish + `parcel` CLI"

## Goal

Two deliverables, one phase:

1. **`parcel_sdk.shell_api`** — a stable facade that lets modules interact with the shell (DB sessions, auth/perm checks, flash messages, templates, sidebar composition) **without importing `parcel_shell.*`**. Modules depend only on `parcel-sdk`; the shell depends on the SDK; the dependency direction stops being circular.
2. **`parcel` CLI** — a `typer` app with five subcommands (`new-module`, `install`, `migrate`, `dev`, `serve`) that covers the daily developer loop: scaffold a module, install it from a path or Git URL, run migrations, run dev/prod servers.

## Non-goals

- No AI module generator (Phase 7).
- No module registry / marketplace.
- No CSRF middleware, no API keys, no multi-tenancy.
- No hot-reload of installed modules (still requires process restart, per Phase 5 decision).
- No new runtime dependencies on `parcel-shell` — in fact, `modules/contacts` will drop its `parcel-shell` dep entirely.

---

## Part 1 — `parcel_sdk.shell_api` facade

### The coupling problem today

`modules/contacts/src/parcel_mod_contacts/router.py` imports six symbols from `parcel_shell.*`:

```python
from parcel_shell.db import get_session
from parcel_shell.rbac import service as rbac_service  # effective_permissions
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates
```

Its `pyproject.toml` declares `parcel-shell` as a workspace dep. That means `pip install parcel-mod-contacts` would drag the entire shell in, and any module we ever write would be pinned to the shell's internal module layout.

### The fix: dependency inversion via a bound registry

`parcel-sdk` gains a new `shell_api` submodule that defines the **interface modules need**, plus a `bind(...)` function the shell calls at startup to wire the implementations. Modules only ever import from `parcel_sdk.shell_api`. The SDK does not import `parcel_shell`. The shell depends on the SDK (it already does).

### Facade surface (final)

```python
# parcel_sdk/shell_api.py

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

# Re-exports for convenience (modules already have these via parcel_sdk)
from parcel_sdk.sidebar import SidebarItem

FlashKind = Literal["success", "error", "info"]


@dataclass(frozen=True)
class Flash:
    kind: FlashKind
    msg: str


@dataclass(frozen=True)
class SidebarSection:
    label: str
    items: tuple[SidebarItem, ...]


# --- The three functions a module calls ---

def get_session() -> Callable[..., AsyncIterator[Any]]:
    """Return the FastAPI dependency that yields an AsyncSession.

    Use as: ``db: AsyncSession = Depends(shell_api.get_session())``
    """

def require_permission(name: str) -> Callable[..., Awaitable[Any]]:
    """Return a FastAPI HTML-auth dependency requiring permission ``name``.

    Implies authentication: unauthenticated users get a 303 to /login?next=...;
    authenticated users missing the permission get a 303 to / with an error flash.
    """

def set_flash(response: Any, flash: Flash) -> None:
    """Set the signed flash cookie on ``response``."""

def get_templates() -> Any:
    """Return the shared Jinja2Templates instance.

    Module templates are already visible because ``Module.templates_dir`` is
    prepended to the loader at install time.
    """

def sidebar_for(request: Any, perms: set[str]) -> list[SidebarSection]:
    """Return the composed sidebar (shell sections + per-module sections)
    filtered by ``perms``, for rendering in module templates.
    """

# --- The one function the shell calls ---

class _ShellBinding(Protocol):
    def get_session(self) -> Callable[..., AsyncIterator[Any]]: ...
    def require_permission(self, name: str) -> Callable[..., Awaitable[Any]]: ...
    def set_flash(self, response: Any, flash: Flash) -> None: ...
    def get_templates(self) -> Any: ...
    def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]: ...


def bind(impl: _ShellBinding) -> None:
    """Install the shell implementation. Called once at shell startup.

    Calling before bind() raises RuntimeError with a clear message.
    """
```

**Design notes:**

- `Flash` moves to the SDK as a plain dataclass. The shell's serialized cookie format (`itsdangerous` signed payload with `kind`+`msg`) stays shell-internal.
- `get_session` and `require_permission` return **callables** (not values) because FastAPI's `Depends(...)` wants a callable. This mirrors how modules use them today — `Depends(get_session)`, `Depends(html_require_permission("contacts.read"))` — just flipped to `Depends(shell_api.get_session())` for uniformity.
- `Any` in type hints is deliberate: the SDK must not import FastAPI / SQLAlchemy / Starlette types to stay dependency-light. Modules get real type narrowing at their own call sites.
- `bind()` uses a module-level mutable container (`_impl: _ShellBinding | None = None`); the five functions delegate through it. Double-bind raises unless `force=True` (used by tests that rebuild the app).

### Shell-side changes

- **New file** `parcel_shell/shell_api_impl.py` — class `ShellBinding` with the five methods, each a one-line delegation to existing shell code:
  - `get_session` → `parcel_shell.db.get_session`
  - `require_permission` → `parcel_shell.ui.dependencies.html_require_permission` (already returns a FastAPI dep)
  - `set_flash` → wraps `parcel_shell.ui.dependencies.set_flash` to pass the session secret from app state (fetches it from a captured `settings` ref at bind time)
  - `get_templates` → `parcel_shell.ui.templates.get_templates`
  - `sidebar_for` → `parcel_shell.ui.sidebar.sidebar_for` (converts shell's `SidebarSection` to SDK's `SidebarSection` — same shape, just different import origin)
- **`parcel_shell.app.create_app`** calls `parcel_sdk.shell_api.bind(ShellBinding(settings))` before mounting modules. On test shutdown we don't need to unbind (tests already rebuild the app; a `force=True` rebind handles the rare pytest re-use case).
- **`parcel_shell.ui.flash.Flash`** becomes `from parcel_sdk.shell_api import Flash` (the shell keeps `pack`/`unpack` serialization for the flash cookie middleware, but the dataclass itself lives in the SDK). This avoids two `Flash` types flying around.
- **`parcel_shell.ui.sidebar.SidebarSection`** is kept for shell-internal use, but grows a `to_sdk()` helper. `shell_api_impl.sidebar_for` converts before returning. Alternative would be to move `SidebarSection` to the SDK too — rejected for YAGNI (it's only used by one template and the conversion is trivial).

### Module-side changes (`modules/contacts`)

`router.py` imports collapse to:

```python
from fastapi import APIRouter, Depends, Request
from parcel_sdk import shell_api
from parcel_sdk.shell_api import Flash
```

All call sites change mechanically:

- `Depends(get_session)` → `Depends(shell_api.get_session())`
- `Depends(html_require_permission("contacts.read"))` → `Depends(shell_api.require_permission("contacts.read"))`
- `set_flash(resp, flash, secret=...)` → `shell_api.set_flash(resp, flash)`
- `get_templates()` → `shell_api.get_templates()`
- `sidebar_for(request, perms)` → `shell_api.sidebar_for(request, perms)`
- `rbac_service.effective_permissions(db, user.id)` — this one stays a direct shell import for now, because exposing the full RBAC query helper through the facade is overkill for one call site. **Exception:** contacts' sidebar-filter needs the user's perm set, which `shell_api.require_permission` already validated. We keep the direct import and revisit if/when a second module needs it.

**Actually — correction.** `modules/contacts/src/parcel_mod_contacts/router.py` uses `rbac_service.effective_permissions` in exactly one spot: to compute `perms` for `sidebar_for`. Simpler: **expose `perms` via `require_permission`'s return value** isn't compatible with FastAPI's Depends shape, so instead add one more facade function:

```python
def effective_permissions(request: Any, user: Any) -> Awaitable[set[str]]:
    """Return the set of permission names the user currently has."""
```

This is the sixth and final facade function. Now `modules/contacts` has zero `parcel_shell.*` imports in production code.

### Tests import rules

Tests in `modules/contacts/tests/` **are allowed** to import from `parcel_shell.*` — they exercise integration boundaries (`bootstrap.create_admin_user`, `modules.integration.mount_module`, `modules.discovery.DiscoveredModule`). The coupling we're breaking is runtime/library coupling, not test-infrastructure coupling. This is explicit in the spec: production code = SDK-only; tests = whatever they need.

### `modules/contacts/pyproject.toml`

- Remove `parcel-shell` from `[project.dependencies]`.
- Remove the workspace source entry for `parcel-shell` in the dep constraints block.
- Tests still need it — add `parcel-shell` to `[dependency-groups.dev]` (or equivalent) so `uv sync --all-packages` picks it up but `pip install parcel-mod-contacts` from a wheel doesn't.

---

## Part 2 — `parcel` CLI

### Framework and layout

- **`typer`** ≥ 0.12 (adds to `parcel-cli` deps; `rich` comes along transitively for pretty help).
- **Entry point:** `parcel = "parcel_cli.main:app"` in `packages/parcel-cli/pyproject.toml`.
- **Layout:**
  ```
  packages/parcel-cli/src/parcel_cli/
    __init__.py
    main.py              # typer.Typer() root + subcommand registration
    commands/
      __init__.py
      new_module.py      # parcel new-module <name>
      install.py         # parcel install <path-or-git-url>
      migrate.py         # parcel migrate [--module NAME]
      dev.py             # parcel dev
      serve.py           # parcel serve
    scaffold/
      __init__.py
      template_files.py  # inline string templates for new-module output
  ```

### Shared plumbing

Every command that talks to the DB needs:

- `PARCEL_DATABASE_URL` env var (or `--database-url` flag) — the same `Settings` the shell uses.
- A helper `_bootstrap_shell() -> FastAPI` that imports `parcel_shell.app.create_app`, returns the configured app so commands can reuse startup logic (discovery, mount, bind). For `migrate`/`install` we don't need to run the web server — we just need the app's lifespan to have mounted modules so their routers/migration dirs are addressable. Use `asgi-lifespan.LifespanManager` as an async context manager.

Shared helper lives in `parcel_cli/_shell.py`:

```python
@asynccontextmanager
async def with_shell() -> AsyncIterator[FastAPI]:
    from parcel_shell.app import create_app
    app = create_app()
    async with LifespanManager(app):
        yield app
```

### Command: `parcel new-module <name>`

- **Args:** positional `name` (snake_case, `^[a-z][a-z0-9_]*$`), `--path DIR` (default `./modules`), `--force` (overwrite if dir exists).
- **Behavior:** Creates `<path>/<name>/` with this skeleton:

```
modules/<name>/
  pyproject.toml                     # parcel-sdk dep, entry point to parcel_mod_<name>:module
  README.md                          # one-line description
  alembic.ini                        # standard, points at alembic/ and mod_<name> schema
  alembic/
    env.py                           # imports run_async_migrations from parcel_sdk.alembic_env
    script.py.mako                   # default Alembic template
    versions/
      0001_init.py                   # empty baseline — `op.execute("CREATE SCHEMA IF NOT EXISTS mod_<name>")`
  src/parcel_mod_<name>/
    __init__.py                      # from .module import module
    module.py                        # Module(name=<name>, version="0.1.0", permissions=[], router=None, …)
    models.py                        # declarative Base with schema="mod_<name>"
    router.py                        # APIRouter() with one hello-world GET "/"
    templates/
      <name>/index.html              # trivial {% extends "_base.html" %} page
  tests/
    __init__.py
    test_smoke.py                    # imports module, asserts name == "<name>"
```

- Template files live as inline Python string constants in `scaffold/template_files.py` (keeps the CLI wheel self-contained; no package data files to fuss with).
- Prints a green "Next steps" footer: run `uv sync --all-packages`, run `parcel install ./modules/<name>`, then `parcel dev`.

### Command: `parcel install <source>`

- **Arg:** `<source>` — either a local path (`./modules/contacts`) or a Git URL (`https://github.com/acme/parcel-mod-foo.git`).
- **Flow:**
  1. If Git URL: `uv pip install <url>` into the current environment. Capture stdout/stderr.
  2. If local path: `uv pip install -e <path>`.
  3. After install, re-trigger entry-point discovery: bring up `with_shell()`, enumerate `app.state.active_modules`, find the newly-available distribution name, and call the same service layer the HTTP admin endpoint calls — `parcel_shell.modules.service.install_module(db, distribution_name, approve_capabilities=module.capabilities)`.
  4. Print a summary: module name, version, permissions granted, sidebar items added.
- **Error paths:** distribution already installed AND marked active → no-op with a note. Missing entry point → exit 1 with clear message. Capabilities require admin approval — the CLI auto-approves by setting `approve_capabilities = module.capabilities` (the user is explicitly running this command; prompting would be noise), but prints the list prominently so they see what was approved.

### Command: `parcel migrate [--module NAME]`

- Runs `alembic upgrade head` for all active modules (or just one via `--module`), using the same `parcel_shell.modules.service.run_migrations(db, name)` that the HTTP admin path calls.
- Runs shell migrations first via `alembic -c packages/parcel-shell/alembic.ini upgrade head` (resolved via `importlib.resources` on `parcel_shell`).
- Prints a one-line status per migration target.

### Command: `parcel dev`

- `exec`s `uvicorn parcel_shell.app:app --reload --host 0.0.0.0 --port ${PARCEL_PORT:-8000} --log-level info` with `PARCEL_ENV=dev` forced in the environment.
- `--host`, `--port`, `--reload/--no-reload` flags to override.
- This is a thin wrapper — `uvicorn` is already a shell dep and does the real work.

### Command: `parcel serve`

- Same as `dev` but no `--reload`, `PARCEL_ENV` is not forced (defaults to whatever's in env, typically `prod`), and `--workers N` defaults to `1` (safe for async; ops can bump it).

### Testing approach for the CLI

- `typer.testing.CliRunner` for invocation.
- `new-module` tests: run against `tmp_path`, assert file tree, assert generated `pyproject.toml` has the right entry point, assert `src/parcel_mod_<name>/module.py` imports cleanly.
- `install` tests: use the local-path branch only in CI (Git clone is a network op — mock it); run install against the actual `modules/contacts` source tree and assert it ends up in `app.state.active_modules` via `with_shell()`.
- `migrate` / `dev` / `serve`: unit-test the arg parsing and env construction; don't actually exec uvicorn.

---

## File plan

**Create:**
- `packages/parcel-sdk/src/parcel_sdk/shell_api.py`
- `packages/parcel-cli/src/parcel_cli/main.py`
- `packages/parcel-cli/src/parcel_cli/_shell.py`
- `packages/parcel-cli/src/parcel_cli/commands/{__init__,new_module,install,migrate,dev,serve}.py`
- `packages/parcel-cli/src/parcel_cli/scaffold/{__init__,template_files}.py`
- `packages/parcel-cli/tests/test_new_module.py`
- `packages/parcel-cli/tests/test_install.py`
- `packages/parcel-cli/tests/test_migrate.py`
- `packages/parcel-cli/tests/test_dev_serve.py`
- `packages/parcel-shell/src/parcel_shell/shell_api_impl.py`
- `packages/parcel-sdk/tests/test_shell_api.py`

**Modify:**
- `packages/parcel-sdk/src/parcel_sdk/__init__.py` — export `shell_api` submodule; bump `__version__` to `0.3.0`.
- `packages/parcel-sdk/pyproject.toml` — version bump.
- `packages/parcel-cli/pyproject.toml` — add `typer`, `parcel-sdk`, `parcel-shell` (for `_shell.py`), `asgi-lifespan`; wire `[project.scripts]` entry point.
- `packages/parcel-shell/src/parcel_shell/app.py` — call `parcel_sdk.shell_api.bind(ShellBinding(settings))` during app construction.
- `packages/parcel-shell/src/parcel_shell/ui/flash.py` — `Flash` becomes `from parcel_sdk.shell_api import Flash`; keep `pack`/`unpack` local.
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` — add `SidebarSection.to_sdk()` converter (or a module-level helper).
- `modules/contacts/src/parcel_mod_contacts/router.py` — swap six imports for `parcel_sdk.shell_api`.
- `modules/contacts/pyproject.toml` — drop runtime `parcel-shell` dep, keep as dev/test dep.
- `pyproject.toml` (workspace root) — no changes expected; all packages already in `members`.
- `CLAUDE.md` — mark Phase 6 done, list next phase (Phase 7 — AI generator).

**Delete:** none.

---

## Testing strategy

- **Unit tests for `shell_api` (`parcel-sdk`):** bind/unbind/rebind behavior, RuntimeError when called before bind, `Flash` equality/frozen behavior.
- **Integration test for shell binding:** bring up `create_app()`, assert `parcel_sdk.shell_api.get_session` returns a working FastAPI dep, assert `require_permission` redirects when unauthed.
- **`modules/contacts` full suite** — must still pass unchanged. This is the regression net for the refactor.
- **CLI command tests** — as described in each command's section.
- **`ruff check && ruff format --check && pyright`** — all clean.
- Target: ~20 new tests, total suite remains green.

## Rollout order (informs plan task order)

1. Land `parcel_sdk.shell_api` + `ShellBinding` + `app.py` binding call. Shell still works, modules still use `parcel_shell.*` imports — nothing breaks.
2. Migrate `modules/contacts/router.py` to the facade one symbol at a time (each change = passing test run).
3. Drop `parcel-shell` from contacts' runtime deps; verify `uv sync --all-packages` + full test suite.
4. Build `parcel new-module` first (self-contained, no DB).
5. Build `parcel dev` and `parcel serve` (thin uvicorn wrappers).
6. Build `parcel migrate` (reuses shell service).
7. Build `parcel install` (Git + service reuse).
8. End-to-end smoke: `parcel new-module demo`, `parcel install ./modules/demo`, `parcel migrate`, `parcel dev` → hit http://localhost:8000/mod/demo/.
9. Update CLAUDE.md, merge.

## Open risks

- **Bind-before-import foot-gun.** If a test imports a module's router at import time and the router internally calls `shell_api.get_session()` at import time (not just inside a function body), bind hasn't happened yet. Mitigation: the facade functions are lazy — they read `_impl` at *call* time, not module-import time. Document this in the facade docstring.
- **`typer` pulls `click` and `rich` — two new top-level runtime deps** for `parcel-cli`. These are already common, small, and the CLI is optional (not a server dep). Acceptable. CLAUDE.md dep table will get an entry.
- **`uv pip install <git-url>` semantics vary slightly across uv versions.** Pin `uv` version? No — uv is the dev's own tool, not Parcel's. Document the minimum uv version in the CLI's error message if install fails with a recognizable pattern.
