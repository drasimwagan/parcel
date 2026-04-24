# Architecture

**Status:** Current through Phase 6. Updated as each phase lands.

## Layers

```
┌────────────────────────────────────────────────────────────┐
│  Admin UI (HTMX + Jinja2 + Tailwind, server-rendered)      │
├────────────────────────────────────────────────────────────┤
│  parcel-shell (FastAPI)                                    │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ auth     │ │ RBAC     │ │ modules   │ │ AI authoring │  │
│  │ sessions │ │ registry │ │ loader    │ │ (Phase 7)    │  │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────┘  │
├────────────────────────────────────────────────────────────┤
│  parcel-sdk  (stable surface; includes parcel_sdk.shell_api)│
├────────────────────────────────────────────────────────────┤
│  Modules (pip packages, entry-point discovered)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ contacts │ │   ...    │ │   ...    │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
├────────────────────────────────────────────────────────────┤
│  Postgres (shell schema + mod_<name> per module) · Redis    │
└────────────────────────────────────────────────────────────┘

                 parcel-cli  (typer) — new-module · install · migrate · dev · serve
```

## Key invariants

1. The shell never imports a module by name. Discovery is via `[project.entry-points."parcel.modules"]` only.
2. Modules never import `parcel_shell.*`. They call into the shell through `parcel_sdk.shell_api`, which the shell registers at `create_app()` time via `shell_api.bind(DefaultShellBinding(settings))`.
3. Each module owns its Postgres schema (`mod_<name>`) and its own Alembic directory. Cross-module data access goes through the SDK, never raw SQL or direct ORM references.
4. All state-changing code paths go through a permission check registered by a module's manifest. Permissions attach to the built-in `admin` role at install time.

## The SDK facade (Phase 6)

`parcel_sdk.shell_api` is the dependency-inversion seam. Six functions + one dataclass:

| Symbol | Role |
|---|---|
| `get_session()` | Returns the `AsyncSession` FastAPI dep. |
| `require_permission(name)` | Returns an HTML-auth dep that enforces permission `name`. |
| `effective_permissions(request, user)` | Returns the set of permission names the user currently has. |
| `set_flash(response, flash)` | Sets the signed flash cookie. |
| `get_templates()` | Returns the shared `Jinja2Templates` (module template dirs are prepended on install). |
| `sidebar_for(request, perms)` | Returns the composed sidebar (shell + active modules, filtered). |
| `Flash` | Frozen dataclass (`kind`, `msg`). |

The shell's `DefaultShellBinding` implements this Protocol. Modules import only `parcel_sdk.shell_api` — the SDK wheel is installable on its own.

## Runtime flow

1. `parcel_shell.app.create_app(settings)`:
   - Binds `parcel_sdk.shell_api` with `DefaultShellBinding(settings)`.
   - Registers shell routers (auth, RBAC, modules, UI).
   - In `lifespan`: opens DB engine, syncs permission registry, marks orphan modules inactive, mounts every active module via `sync_active_modules(app)`.
2. `sync_active_modules` iterates entry-point-discovered modules whose `InstalledModule` row is active, calls `mount_module(app, discovered)`:
   - `app.include_router(module.router, prefix="/mod/<name>")`
   - Prepends `module.templates_dir` to the Jinja loader.
   - Registers `module.sidebar_items` under the module's name.
3. HTTP requests into `/mod/<name>/*` hit the module's router. Module handlers use `Depends(shell_api.require_permission(...))` for auth; the bound binding returns the shell's real HTML-auth dep.

## CLI surface (Phase 6)

`parcel-cli` is a typer app with five subcommands. `install` and `migrate` boot the shell in-process via `asgi-lifespan.LifespanManager` and call the same service layer the HTTP admin endpoints use — no HTTP round-trip, works offline and pre-deployment.

| Command | Purpose |
|---|---|
| `parcel new-module <name>` | Scaffold a new module (pyproject, alembic, router, models, templates, smoke test). |
| `parcel install <path-or-git-url>` | `uv pip install` + discover + `install_module` + attach perms to admin. |
| `parcel migrate [--module N]` | `alembic upgrade head` for one or all installed modules. |
| `parcel dev` | `uvicorn parcel_shell.app:create_app --factory --reload`. |
| `parcel serve` | Production uvicorn (no reload, `--workers` configurable). |
