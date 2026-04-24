# Parcel — Claude Code Context

> This file is loaded into every Claude Code session in this repo. Keep it current. If you make a decision that changes anything below, update this file in the same commit.

## What Parcel is

**Parcel** is an AI-native, modular business-application platform. Think Odoo, but with AI as a first-class authoring tool. An admin describes a business need in natural language; Parcel generates a module (models, views, migrations, tests), runs it against a sandbox database, shows a preview, and installs it on approval. Developers can hand-write modules with the same SDK when precision matters. End users never see the authoring layer — they just use the apps.

- **Shell** provides auth, RBAC, admin UI, module lifecycle, AI authoring pipeline.
- **SDK** is the stable API that every module imports.
- **Modules** are pip-installable Python packages that extend the shell.

## Current phase

**Phase 6 — SDK polish + `parcel` CLI done.** `parcel-sdk` now exposes `parcel_sdk.shell_api`, a stable facade (6 functions: `get_session`, `require_permission`, `set_flash`, `get_templates`, `sidebar_for`, `effective_permissions`, plus a shared `Flash` dataclass). The shell registers `DefaultShellBinding` via `shell_api.bind()` at `create_app()` time; modules import only `parcel_sdk.*`. `modules/contacts` has zero runtime `parcel_shell` imports and dropped `parcel-shell` from its runtime deps. A new `parcel` CLI (typer) ships `new-module`, `install`, `migrate`, `dev`, `serve`. `install`/`migrate` reuse the shell service layer via `asgi-lifespan.LifespanManager` instead of HTTP. 196-test suite.

Next: **Phase 7 — AI module generator.** Start a new session; prompt: "Begin Phase 7 per `CLAUDE.md` roadmap." Do not begin Phase 7 inside the Phase 6 commit cluster.

## Locked-in decisions

| Area | Decision |
|---|---|
| Name | Parcel |
| Language | Python 3.12+ with FastAPI (async) |
| Frontend | HTMX + Jinja2 + Tailwind CSS (server-rendered, no JS build step for MVP) |
| Database | PostgreSQL 16; single DB, per-module schema (`mod_<name>`); shell owns `shell` schema |
| Migrations | Alembic owned per-module; shell orchestrates run order on install/upgrade |
| Background jobs | ARQ (Redis) |
| Module isolation | In-process Python packages discovered via `[project.entry-points."parcel.modules"]` |
| Module distribution | Git URL install for MVP; central registry deferred |
| Primary users | Tiered: end-users, developers, IT admins — all three |
| Tenancy | Single-tenant for MVP; model built so `tenant_id` can be retrofitted |
| Auth | Email + password + signed-cookie sessions (Argon2) for MVP; OIDC/SAML/API-keys later |
| RBAC | Modules declare permissions in their manifest; shell registers and admins assign to roles |
| AI provider | Cloud LLM (Claude API first); provider abstraction pluggable |
| AI flow | Chat → draft → static-analysis gate → sandbox install → admin preview → approve → install |
| AI safety | ruff + bandit + custom AST policy blocks `os`, `subprocess`, `socket`, `eval`, `exec`, dynamic imports unless manifest declares the capability and admin approves |
| MVP scope | Shell + 1 demo module (Contacts/CRM lite). No marketplace, no multi-tenancy, no AI generator until Phase 7 |
| Demo module | Contacts / CRM lite |
| Dev experience | `parcel` CLI (`new-module`, `install`, `migrate`, `dev`, `serve`) + uvicorn hot reload |
| Deployment | Single `docker compose up` (shell + PG + Redis). Bare-metal & k8s deferred |
| License | MIT |
| Phase 1 shell deps | fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, redis, pydantic, pydantic-settings, structlog |
| Phase 1 test deps | testcontainers[postgres], asgi-lifespan |
| Logging | structlog; ConsoleRenderer in `dev`, JSONRenderer in `staging`/`prod`; `request_id` bound via contextvar |
| Health endpoints | `/health/live` always 200; `/health/ready` pings pg + redis, returns 503 on degraded |
| Migrations | Run explicitly via `docker compose run --rm shell migrate`, never on boot; `alembic_version` lives in `public` so downgrading past the shell-schema baseline is safe |
| Container sync | `uv sync --all-packages` — workspace root has no direct deps on members |
| Phase 2 shell deps | argon2-cffi, itsdangerous, email-validator |
| Session TTLs | 7-day absolute, 24-hour idle; bumped on every authenticated request |
| Session cookie | `parcel_session`; HttpOnly; SameSite=Lax; Secure when env != dev; signed with `PARCEL_SESSION_SECRET` (itsdangerous URLSafeSerializer) |
| Built-in admin role | `admin` is seeded by migration 0002, `is_builtin=true`, holds all 8 shell permissions; the API rejects mutating or deleting it |
| Failed logins | Logged as `auth.login_failed` with reason (`no_user` / `bad_password` / `inactive`); no rate limiting in Phase 2 |
| Request DB session | `get_session` dep commits on success, rolls back on exception — endpoints don't call commit themselves |
| Shell permissions (8) | `users.read`, `users.write`, `users.roles.assign`, `roles.read`, `roles.write`, `sessions.read`, `sessions.revoke`, `permissions.read` |
| Phase 3 SDK deps | sqlalchemy[asyncio], alembic (runtime, so a module's `env.py` can import the helper) |
| Module install model | Explicit — discovery lists candidates; admin calls `POST /admin/modules/install` to activate. `approve_capabilities` must exactly equal `module.capabilities`. |
| Module uninstall | Soft by default (`is_active=false`); `?drop_data=true` runs `alembic downgrade base`, drops `mod_<name>` schema, removes the module's permissions and the row |
| Module migrations | In-process `alembic.command.upgrade` against the module's `alembic.ini`; per-module `alembic_version` lives inside the module's own schema |
| Module orphans at boot | Warn + flip to `is_active=false`; shell never refuses to boot |
| Shell permissions (12) | Phase 2's 8 + `modules.{read,install,upgrade,uninstall}` |
| Phase 4 shell deps | jinja2, python-multipart |
| Phase 4 client deps | Tailwind (Play CDN), HTMX (2.x CDN), Alpine.js (3.x CDN) — no npm build step |
| HTML auth | Separate `current_user_html` dep raises `HTMLRedirect("/login?next=…")`; a global exception handler renders it as a 303 |
| Themes | Three user-selectable (`plain` default / `blue` / `dark`), `[data-theme]` on `<html>`, persisted to `localStorage["parcel_theme"]` |
| Flash messages | Signed `parcel_flash` HTTP-only cookie (itsdangerous), read + cleared by FlashMiddleware |
| URL boundary | HTML at `/`, `/login`, `/profile`, `/users`, `/roles`, `/modules`; JSON stays at `/auth/*`, `/admin/*`, `/health/*` |
| CSRF | Phase 4 relies on Phase 2's `SameSite=Lax` cookie; token middleware deferred |
| Module UI seam | `Module.router`, `Module.templates_dir`, `Module.sidebar_items` (Phase 5 SDK additions) |
| Module URL prefix | `/mod/<name>/*`. Template dir prepended to Jinja loader; sidebar items rendered as a per-module section. |
| Module install + admin role | `install_module` assigns the module's permissions to the built-in `admin` role so admins inherit every capability across shell + modules. |
| Module removal on uninstall | Routes stay mounted until next process restart (FastAPI doesn't support clean router removal). Soft uninstall flips `is_active=false`; next boot skips mounting. |
| Module→shell coupling | Broken in Phase 6. Modules import only `parcel_sdk.*`; the shell registers its implementation with `parcel_sdk.shell_api.bind(DefaultShellBinding(settings))` inside `create_app()`. |
| SDK facade surface | 6 functions: `get_session`, `require_permission`, `set_flash`, `get_templates`, `sidebar_for`, `effective_permissions`. `Flash` dataclass lives in the SDK; shell keeps cookie serialization. Tests bind a default binding at workspace `conftest.py` collection time because FastAPI deps resolve at module-import time. |
| Phase 6 CLI deps | typer ≥ 0.12, asgi-lifespan ≥ 2.1, uvicorn[standard] ≥ 0.30. CLI is optional; not a shell dep. |
| CLI scope | `parcel new-module <name>` scaffolds; `parcel install <path-or-git-url>` pip-installs + activates newly-discovered modules via the shell service layer; `parcel migrate [--module N]` upgrades; `parcel dev`/`serve` wrap `uvicorn.run("parcel_shell.app:create_app", factory=True, …)`. |
| CLI `install` semantics | Talks to the DB directly via `asgi_lifespan.LifespanManager` + `parcel_shell.modules.service.install_module`. Auto-approves capabilities (user explicitly invoked the command) but echoes them so the operator sees the grant. |
| Contacts runtime deps | `parcel-mod-contacts` v0.2.0 runtime deps are `parcel-sdk` + `fastapi` only; `parcel-shell` moved to `[dependency-groups] dev` for tests. |

## Repository layout

```
packages/
  parcel-shell/    # FastAPI app: auth, RBAC, admin UI, module loader, AI pipeline
  parcel-sdk/      # The only thing modules import. Stable surface, versioned separately.
  parcel-cli/      # `parcel` CLI
modules/
  contacts/        # Demo module (Phase 5)
docker/            # Dockerfile + entrypoint
docs/              # architecture.md, module-authoring.md, ai-generation.md
scripts/           # bootstrap.py (first-run admin seed)
```

### Module contract (for future reference)

```python
# modules/<name>/src/parcel_mod_<name>/__init__.py
from parcel_sdk import Module, Permission

module = Module(
    name="contacts",
    version="0.1.0",
    permissions=[
        Permission("contacts.read", "View contacts"),
        Permission("contacts.write", "Create/edit contacts"),
    ],
    capabilities=[],  # e.g., ["http_egress"] — admin approves at install time
)
```

Entry point in the module's `pyproject.toml`:

```toml
[project.entry-points."parcel.modules"]
contacts = "parcel_mod_contacts:module"
```

## Phased roadmap

| Phase | Status | Goal |
|---|---|---|
| 0 | ✅ done | Repo scaffold (this commit) |
| 1 | ✅ done | Shell foundation: FastAPI app, config, async SQLAlchemy, Alembic for shell, logging, health, docker-compose end-to-end |
| 2 | ✅ done | Auth + RBAC: users, sessions, Argon2, roles, permissions registry |
| 3 | ✅ done | Module system: manifest spec, entry-point discovery, migration orchestrator, admin module page |
| 4 | ✅ done | Admin UI shell: Jinja base layout, Tailwind, HTMX, dynamic sidebar |
| 5 | ✅ done | Contacts demo module end-to-end |
| 6 | ✅ done | SDK polish + `parcel` CLI |
| 7 | ⏭ next | AI module generator (Claude API, static gate, sandbox, preview, approve flow) |
| Future |  | Multi-tenancy · OIDC/SAML · module registry · in-browser developer module · non-Python DB options |

**Every phase is its own brainstorm → plan → implementation cycle.** Do not skip ahead.

## Conventions

- **Python**: 3.12+, type hints everywhere, `from __future__ import annotations` at top of each module.
- **Async**: default. Sync code only where a library forces it.
- **Lint/format**: `ruff check` and `ruff format`. Line length 100.
- **Types**: `pyright` (strict on shell + sdk, basic on modules).
- **Tests**: `pytest` with `asyncio_mode=auto`. Every public function gets a test.
- **SQL**: SQLAlchemy 2.0 async; models in each module's `models.py`; no raw SQL in application code.
- **Alembic**: each module has its own `alembic/` directory; migrations scoped to that module's schema; standard `env.py` template comes from `parcel-sdk`.
- **Schemas**: `shell` for shell tables; `mod_<name>` for each module; `public` stays empty for clarity.
- **Secrets**: only via environment (see `.env.example`). Never commit secrets.
- **Commits**: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).
- **One phase per PR/commit cluster.** CLAUDE.md updates go in the same commit as the work that made them true.

## Commands

These will be wired up in later phases. Listed here so they're discoverable.

```bash
# --- Phase 1+ ---
docker compose up -d                    # Start PG + Redis + shell
docker compose logs -f shell            # Tail shell logs
uv sync                                 # Install workspace packages editable
uv run pytest                           # Run all tests
uv run ruff check                       # Lint
uv run ruff format                      # Format
uv run pyright                          # Type-check

# --- Phase 6+ ---
uv run parcel dev                       # Hot-reload dev server
uv run parcel new-module <name>         # Scaffold a new module
uv run parcel install <git-url>         # Install a module from Git
uv run parcel migrate                   # Run migrations across all modules
uv run parcel serve                     # Production server
```

## Things NOT to do

- Don't add multi-tenancy code before Phase 8+. Single-tenant is the MVP contract.
- Don't add OIDC/SAML before Phase 2 is done and stable.
- Don't build a module registry before Phase 7 is done and real users exist.
- Don't introduce new top-level dependencies without updating this file and `pyproject.toml` in the same commit.
- Don't create new top-level directories without updating this file.
- Don't let the AI generator write to production schemas directly. Sandbox first, always.
- Don't share Python module code between modules except via `parcel-sdk`.
- Don't add a separate Celery/RabbitMQ queue — ARQ is the choice.
- Don't write raw SQL. Use SQLAlchemy.
- Don't couple the shell to any specific module. The shell knows zero module names.

## For the AI (future-you)

When the user returns, they'll likely say "start Phase 1" or similar. Before writing code:

1. Read this file.
2. Confirm which phase is current vs. next.
3. Use the **superpowers:brainstorming** skill to clarify phase-specific requirements.
4. Write a plan file in plan mode.
5. Only then execute.

Each phase is small enough to fit in one session. If it's growing beyond a single session, decompose further and update the roadmap here.
