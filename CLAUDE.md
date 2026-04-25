# Parcel — Claude Code Context

> This file is loaded into every Claude Code session in this repo. Keep it current. If you make a decision that changes anything below, update this file in the same commit.

## What Parcel is

**Parcel** is an AI-native, modular business-application platform. Think Odoo, but with AI as a first-class authoring tool. An admin describes a business need in natural language; Parcel generates a module (models, views, migrations, tests), runs it against a sandbox database, shows a preview, and installs it on approval. Developers can hand-write modules with the same SDK when precision matters. End users never see the authoring layer — they just use the apps.

- **Shell** provides auth, RBAC, admin UI, module lifecycle, AI authoring pipeline.
- **SDK** is the stable API that every module imports.
- **Modules** are pip-installable Python packages that extend the shell.

## Current phase

**Phase 10b — Workflows scheduled triggers + ARQ done.** Workflows now route through ARQ at runtime: `_on_after_commit` enqueues an event-dispatch job to Redis instead of `asyncio.create_task`. A new `worker` compose service (same image as the shell, `command: ["parcel", "worker"]`) consumes the queue, runs sync-trigger workflows in a fresh session, and runs cron-fired workflows on its own scheduler. New trigger `OnSchedule(hour=, minute=, second=, day=, month=, weekday=)` uses ARQ-native kwargs (`int`, `set[int]`, or `None`); subject is always `None` for cron firings. `_matches` returns `False` for `OnSchedule` (mirrors `Manual`). Each `OnSchedule` declaration generates a unique-named wrapper coroutine that closes over `(module_name, slug)` and forwards to `run_scheduled_workflow`; wrappers are registered alongside the canonical handlers in `WorkerSettings.functions` (ARQ's `cron()` doesn't accept `kwargs`). Cron audit auto-names `<module>.<slug>.scheduled`. Worker discovers active modules synchronously at boot via a sync DB query — restart required on new module install (documented limitation). `PARCEL_WORKFLOWS_INLINE=1` env var (set by pytest config + by `parcel dev`) short-circuits the bus to the Phase-10a `loop.create_task(dispatch_events(...))` for tests/dev; cron triggers don't fire in inline mode. Subject serialization: SQLAlchemy instances reduced to `{class_path, id}`; worker re-imports the class via `importlib` and re-fetches the row — if the row's been deleted, the action raises and audit captures the error. SDK bumped to `0.7.0` (adds `OnSchedule`); Contacts bumped to `0.5.0` and ships a reference `daily_audit_summary` workflow at 09:00. Test count: 392 → ~417 (includes one ARQ-end-to-end test via testcontainer Redis).

Next: **Phase 10b-retry** (per-workflow `max_retries` + exponential backoff on top of ARQ's queue) OR **Phase 10c — Workflows rich actions** (`send_email` / `call_webhook` / `run_module_function` / `generate_report` + richer audit UI). Either is a small, well-scoped session. Start a new session; prompt: "Begin Phase 10b-retry per `CLAUDE.md` roadmap." or "Begin Phase 10c per `CLAUDE.md` roadmap." The full upcoming roadmap (10b ARQ ✅ → 10b-retry → 10c → 11) is described below under "Upcoming phases".

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
| Phase 7 decomposition | 7a = gate + sandbox (no AI). 7b = Claude API generator (no chat). 7c = chat UI + preview UX. Separate cycles to keep the static gate battle-tested before AI output feeds into it. |
| Capability vocabulary | 4 values: `filesystem` (unlocks `os`, `open()`), `process` (unlocks `subprocess`), `network` (unlocks `socket`/`urllib`/`http*`/`httpx`/`requests`/`aiohttp`), `raw_sql` (unlocks `sqlalchemy.text(...)`). |
| Gate hard-blocks | `sys`/`importlib` imports, `parcel_shell.*` imports, calls to the four dynamic-code builtins (eval/exec/compile/__import__), dunder-escape attrs (`__class__`/`__subclasses__`/`__globals__`/`__builtins__`/`__mro__`/`__code__`). No capability unlocks these. |
| Gate placement | Runs on the sandbox-install path only. `parcel install` / `POST /admin/modules/install` stay unchanged (trusted input). Tests and `__pycache__` are excluded — runtime code only. |
| `parcel-gate` deps | `ruff>=0.6,<0.9` (subprocess, structured JSON with `--isolated --line-length=100 --ignore=E501,W291,W292,W293`), `bandit>=1.7,<2.0` (in-process via `BanditManager`). |
| Sandbox isolation | Logical only: same Postgres, `mod_sandbox_<uuid>` schema, same process, same DB pool. Files in `var/sandbox/<uuid>/` (gitignored, `var/.gitkeep` tracked). Loaded via `importlib.util.spec_from_file_location` with unique `sys.modules` name (`parcel_mod_<name>__sandbox_<short-uuid>`) to avoid collisions. |
| Sandbox schema Alembic | `module.metadata.schema = "mod_sandbox_<uuid>"` is patched in-memory before `alembic upgrade`; `sys.modules[package_name]` is temporarily aliased to the sandbox copy so env.py's `from parcel_mod_X import module` resolves, then restored in a try/finally. |
| Sandbox lifecycle | 7-day TTL. Dismiss: DROP SCHEMA + rm files + row stays for audit. Promote: copy files → `modules/<target_name>/`, rewrite package-name references, `uv pip install -e`, run `install_module`, then dismiss. Data in the sandbox is NOT copied to the real install. |
| Sandbox UI | `/sandbox` (list) + `/sandbox/new` (upload) + `/sandbox/<uuid>` (detail with gate report); JSON parallel at `/admin/sandbox`. Sidebar section "AI Lab". Permissions `sandbox.read`/`install`/`promote` attached to `admin` role by migration 0004. |
| Sandbox CLI | `parcel sandbox install <path>` / `list` / `show <uuid>` / `promote <uuid> <name> [-c cap …]` / `dismiss <uuid>` / `prune`. All reuse `with_shell()` via asgi-lifespan. |
| AI provider abstraction | `parcel_shell.ai.provider.ClaudeProvider` Protocol with two impls: `AnthropicAPIProvider` (default, SDK + our `write_file`/`submit_module` tool-use loop with 20-iteration cap, 64 KiB per-file + 1 MiB total size caps, path safety against absolute/traversal/executable extensions) and `ClaudeCodeCLIProvider` (subprocess into a throwaway dir, parses `--output-format json`, 180s timeout). Selected at boot via `PARCEL_AI_PROVIDER=api\|cli` (default `api`). |
| Generator orchestration | `parcel_shell.ai.generator.generate_module(prompt, *, provider, db, app, settings)` zips provider output → calls Phase 7a `create_sandbox` → on `GateRejected`, rebuilds a `PriorAttempt` with the report and retries **exactly once**. Failure enum: `provider_error` (502), `no_files` (400), `gate_rejected` / `exceeded_retries` (422). |
| System prompt | Lives at `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` — versioned, reviewable, loaded via `importlib.resources`. Contains the full reference scaffold, tool contract, capability vocabulary, hard-block list, allow-list. |
| AI permission | `ai.generate` added via migration 0005 and attached to the built-in admin role. Required by `POST /admin/ai/generate` and `parcel ai generate`. |
| Generator endpoints | HTTP: `POST /admin/ai/generate {"prompt": "…"}` → 201 with `SandboxOut`, or 503 if no provider, or 4xx/5xx with `GenerateFailure` detail. CLI: `parcel ai generate "<prompt>"` — exit 0 on sandbox, exit 1 on failure. Both block synchronously (30-90s typical); no ARQ queue yet. |
| AI settings | `PARCEL_AI_PROVIDER` (default `api`), `ANTHROPIC_API_KEY` (required if provider is api; shell still boots without it, endpoint returns 503), `PARCEL_ANTHROPIC_MODEL` (default `claude-opus-4-7`). |
| AI chat persistence | Two tables (migration 0006): `shell.ai_sessions` (id, owner_id, title, timestamps) and `shell.ai_turns` (id, session_id, idx, prompt, status, sandbox_id, failure_kind/message/gate_report, timestamps). Title is the first ~40 chars of the first prompt. Sessions and turns cascade-delete; owner `ON DELETE CASCADE`. |
| AI chat turn semantics | Each admin turn is an **independent generation** — no accumulated Claude context across turns. The UX is chat-like; the model sees one prompt (plus 7b's one-turn auto-repair). Multi-turn context accumulation is a future-phase decision. |
| AI chat background task | `asyncio.create_task(run_turn(...))` fires from the POST handler. The task opens its own sessionmaker-backed `AsyncSession`; the request's session is closed by the time the redirect returns. Top-level `except BaseException` catches `CancelledError` during shutdown so turns never stay stuck in `generating`. Tasks tracked in `app.state.ai_tasks`; cancelled + gathered on lifespan exit. |
| AI chat orphan sweep | On every shell boot (after `mount_sandbox_on_boot`), `sweep_orphans` flips any `status='generating'` turn to `failed(process_restart)`. Admin can re-submit the prompt. |
| AI chat URLs | HTML-only, under `/ai` (not `/admin/ai/` — parallel to `/sandbox`, `/modules`). Routes: `GET /ai`, `POST /ai/sessions`, `GET /ai/sessions/<id>`, `POST /ai/sessions/<id>/turns`, `GET /ai/sessions/<id>/status` (HTMX polling fragment). All require `ai.generate`; cross-owner access returns 404, not 403. |
| AI chat polling | `GET /ai/sessions/<id>/status` returns a full turn-list partial. When **any** turn is `generating`, the partial's root `<div id="turns">` carries `hx-get`/`hx-trigger="every 1s"`/`hx-target="#turns"`/`hx-swap="outerHTML"`. When all turns are terminal, those attributes are omitted — client stops polling automatically. |
| Dashboard declaration | `Module.dashboards: tuple[Dashboard, ...] = ()`. Five widget types: `KpiWidget`, `LineWidget`, `BarWidget`, `TableWidget`, `HeadlineWidget`. Data-bearing widgets are frozen dataclasses with `kw_only=True` so `data` stays required despite `Widget.col_span` having a default. Shell auto-mounts `/dashboards/<module>/<slug>` via `app.state.active_modules_manifest` (populated by `mount_module`). Modules write no dashboard routes. |
| Dashboard chart library | Chart.js 4.4.1 via CDN in `_base.html` alongside HTMX/Alpine. KPI/line/bar/table/error partials are each one Jinja template under `parcel_shell/dashboards/templates/dashboards/`. Charts use `tojson` filter for safe data injection. |
| Dashboard permission model | Per-dashboard only. `Dashboard.permission` is a permission the module already owns (e.g., `contacts.read`). No shell-level `dashboards.*` permissions. Unauthorized access returns 404 (consistent with AI chat's cross-owner 404 policy). |
| Dashboard widget isolation | Each widget loads via its own HTMX `hx-get` + `hx-trigger="load"`. Per-widget endpoint wraps both `widget.data(Ctx(...))` AND the `TemplateResponse` render in one try/except; any exception logs + returns `_widget_error.html`, leaving siblings intact. `HeadlineWidget` has no data fn and is rendered inline in `detail.html`. |
| Dashboard SDK helpers | `scalar_query`, `series_query`, `table_query` wrap `sqlalchemy.text()` params-only. Modules avoid the `raw_sql` capability by going through these helpers (they live inside the SDK, trusted code). `series_query` coerces values to `float` (Postgres `numeric` → `Decimal` otherwise, which Chart.js can't handle). `table_query` reads columns from the cursor before consuming rows so empty tables still carry headers. |
| Dashboard sidebar link | Auto-added by `_dashboards_section` in `ui/sidebar.py` — inserts a "Dashboards" section after "Overview" only when the user has permission for ≥ 1 declared dashboard across all mounted modules. No empty page for users without permissions. |
| Report declaration | `Module.reports: tuple[Report, ...] = ()`. `Report` is a frozen `kw_only=True` SDK dataclass with `slug` / `title` / `permission` / `template` / `data` / optional `params: type[BaseModel]` / optional `form_template`. `ReportContext(session, user_id, params)` mirrors dashboards' `Ctx` (the spec's `User` SDK type doesn't exist; `user_id: UUID` is sufficient). Shell auto-mounts via `app.state.active_modules_manifest` populated by `mount_module`; modules write no report routes. |
| Report PDF engine | **Playwright + headless Chromium** (~250 MB browser blob, zero system-lib requirements — Chromium ships statically linked). `parcel_shell.reports.pdf.html_to_pdf(html)` is async, lazy-imports Playwright, launches a short-lived Chromium per request, and returns PDF bytes. `prefer_css_page_size=True` honours each report's `@page` size + margins; page counter renders via `footer_template` because Chromium ignores CSS GCPM (`@top-center` / `@bottom-right`). The Docker image runs `playwright install --with-deps chromium`; locally, devs run `uv run playwright install chromium` once. Phase 11 reuses the same install for sandbox-preview screenshots. Per-request Chromium startup (~500 ms-1 s) is fine at Phase 9 volumes; if it ever matters, switch to a long-lived browser in `app.state` and reuse contexts. |
| Report URLs | Three per declared report: `/reports/<module>/<slug>` (form, auto-rendered or `form_template` override), `/reports/<module>/<slug>/render?<params>` (HTML preview wrapped in admin chrome), `/reports/<module>/<slug>/pdf?<params>` (`application/pdf` stream with `Content-Disposition: attachment; filename="<module>-<slug>-<YYYYMMDD-HHMM>.pdf"`). All three return 404 (never 403) on missing permission, unknown module, or unknown slug. Validation errors re-render the form with HTTP 200 and per-field messages, no DB hit on `report.data`. |
| Report form auto-render | `parcel_shell.reports.forms.render_form(model, values, errors)` walks `model.model_fields` and emits Tailwind-styled controls: text/number/checkbox/date/datetime-local/select for `str`/`int`/`float`/`bool`/`date`/`datetime`/`Literal`/`Enum`. Optional fields drop `required`. `Field(description=...)` becomes helper text. `json_schema_extra={"widget": "textarea"}` swaps in a `<textarea>`. Anything else: set `Report.form_template`; the shell renders it with `{values, errors, model}`. |
| Report base template | Single opinionated `_report_base.html`: A4 portrait, 20mm margins, page-counter footer (`@bottom-right`), title + generated-at + `param_summary` header. Override `{% block page_css %}` for landscape/Letter/custom margins; override `{% block content %}` for the body. Module reports `{% extends "reports/_report_base.html" %}`. |
| Report failure isolation | Per-route try/except mirrors dashboards' widget isolation: `report.data` exceptions and template-render exceptions both surface a friendly red error block (`reports/_error.html`), no 500s. PDF engine exceptions redirect 303 back to the form with a flash error. WeasyPrint `URLFetchingError`, layout errors, and template render errors all funnel through the same catch — no partial PDFs ever leave the server. |
| Report permission model | Per-report only. `Report.permission` references a permission the module already owns (e.g., `contacts.read`). No shell-level `reports.*` permissions, no shell migrations. `mount_module` emits `module.report.unknown_permission` at WARN if the declared permission isn't in the module's `permissions` tuple — the report still mounts, but no user can ever see it. |
| Report sidebar | Auto-injected by `_reports_section` in `ui/sidebar.py` — one entry per visible report (`{Module.capitalize()}: {report.title}`), in module-name order. Inserts after the dashboards section. Returns `None` (and the section disappears) when the user has zero visible reports. |
| Workflow declaration | `Module.workflows: tuple[Workflow, ...] = ()`. `Workflow` is a frozen `kw_only=True` SDK dataclass (`slug`, `title`, `permission`, `triggers`, `actions`, optional `description`). Triggers are frozen dataclasses (`OnCreate`, `OnUpdate(when_changed=())`, `Manual`); actions are frozen dataclasses (`UpdateField`, `EmitAudit`). `WorkflowContext(session, event, subject, subject_id, changed)` is passed to action callables. |
| Workflow event bus | Explicit `shell_api.emit(session, event, subject, *, changed=())` from module endpoints — not SQLAlchemy event listeners. Modules opt their writes into observation; explicit emit is greppable, testable, and avoids accidental fires from migrations / fixtures / bulk inserts. The spec sketched a contextvar-resolved session arg; in implementation, `session` is passed explicitly to mirror `set_flash(response, ...)`. |
| Workflow timing | Post-commit. `emit` queues events on `session.info["pending_events"]`; SQLAlchemy `after_commit` listener (registered once at shell startup) drains the queue and `asyncio.create_task`s `runner.dispatch_events(events, sessionmaker)`. Dispatch opens a fresh session per chain — source write always succeeds independently. The sessionmaker is stashed on `session.info["sessionmaker"]` inside `parcel_shell.db.get_session` so the listener can find it. |
| Workflow failure | Single transaction per chain invocation. Any action raises → chain rolls back, audit row written in a separate session with `status='error'`, `failed_action_index`, and `error_message`. Source write (already committed) is unaffected. No retry in 10a. |
| Workflow audit | New shell table `shell.workflow_audit` (migration 0007). Columns: id, created_at, module, workflow_slug, event, subject_id, status (`ok`/`error`), error_message, failed_action_index, payload jsonb. Index on `(module, workflow_slug, created_at desc)` for the detail-page query. |
| Workflow URLs | Three: `GET /workflows` (list, grouped by module, filtered by permission), `GET /workflows/<module>/<slug>` (declaration summary + last-50 audit), `POST /workflows/<module>/<slug>/run` (manual trigger; only valid when workflow declares a `Manual` trigger). All three return 404 (never 403) on missing permission. Manual-run dispatches by calling `run_workflow` directly (not `dispatch_events`), since `_matches` returns `False` for `Manual` triggers by design. |
| Workflow sidebar | Single aggregate "Workflows" link injected by `_workflows_section` when the user has permission for ≥ 1 declared workflow. Inserted after the Reports section. Mirrors `_dashboards_section`'s aggregate-link pattern (one link, not one entry per workflow). |
| Workflow permission model | Per-workflow only. `Workflow.permission` references a permission the module already owns. No shell-level `workflows.*` permissions. `mount_module` emits `module.workflow.unknown_permission` at WARN if the declared permission isn't in the module's `permissions` tuple. |
| Workflow `OnSchedule` trigger | Frozen kw_only SDK dataclass with `second`/`minute`/`hour`/`day`/`month`/`weekday` (each `int` / `set[int]` / `None`). Construction-time `__post_init__` range validation. Maps directly to `arq.cron.cron(...)`. No `event` field — cron audit auto-names `<module>.<slug>.scheduled`. |
| Workflow ARQ routing | Always-through-ARQ at runtime: `_on_after_commit` enqueues `run_event_dispatch` jobs to Redis. `PARCEL_WORKFLOWS_INLINE=1` short-circuits to inline `asyncio.create_task` (set by pytest config + `parcel dev` CLI). Cron triggers don't fire under inline mode. ArqRedis pool opens in lifespan with `conn_retries=1` so test fake-Redis URLs fail fast without breaking lifespan timeout. |
| Workflow worker container | Same `parcel-shell` image, separate `worker` compose service with `command: ["parcel", "worker"]`. CLI subcommand wraps `arq.run_worker(WorkerSettings)`. `WorkerSettings` is built dynamically by `build_worker_settings(settings)` which sync-queries `InstalledModule.is_active=true` for cron_jobs at boot. Restart required on new module install. |
| Workflow event serialization | `parcel_shell.workflows.serialize` encodes SQLAlchemy subjects as `{class_path, id}` for JSON-safe transport. `decode_event` re-imports the class via `importlib` and `session.get`s the row in the worker session. Missing row → subject=None; subsequent `UpdateField` action raises and audit captures the error. |
| Workflow cron + UpdateField | `OnSchedule` triggers always have `subject=None`. `UpdateField` on a cron firing raises `RuntimeError("UpdateField requires a subject_id")` and audit `status="error"`. Documented; fix in 10c via richer actions that don't require a subject. |
| Workflow cron handler registration | ARQ's `cron()` doesn't accept `kwargs`, so `_build_cron_jobs` generates one wrapper coroutine per `OnSchedule` trigger. Each wrapper has a unique `__name__` (`_cron_<module>_<slug>`) and closes over `(module_name, slug)` to forward to `run_scheduled_workflow`. Wrappers are registered in `WorkerSettings.functions` alongside the canonical handlers so ARQ can resolve them by name when firing. |

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
| 7a | ✅ done | Static-analysis gate + sandbox install (no AI yet) |
| 7b | ✅ done | Claude API generator — API + CLI provider, one-turn auto-repair |
| 7c | ✅ done | Chat UI for the generator — persistent sessions, HTMX polling |
| 8 | ✅ done | Dashboards — module-authored KPI cards, charts, live-query tables |
| 9 | ✅ done | Reports + PDF generation — templated, parameterised, printable/exportable |
| 10a | ✅ done | Workflows engine + sync triggers + minimal actions + read-only UI |
| 10b | ✅ done | Workflows scheduled triggers + ARQ + worker container |
| 10b-retry | ⏭ next | Per-workflow max_retries + exponential backoff (small phase) |
| 10c | | Workflows rich actions (send_email, call_webhook, run_module_function, generate_report) + richer UI |
| 11 |  | Sandbox preview enrichment — sample-record seeding, Playwright screenshots, builds on ARQ |
| Future |  | Multi-tenancy · OIDC/SAML · module registry · in-browser developer module · non-Python DB options |

**Every phase is its own brainstorm → plan → implementation cycle.** Do not skip ahead.

## Upcoming phases — scope and open questions

Every module on Parcel will end up needing some mix of **dashboards** (glance-at-a-KPI, live-query tables), **reports** (printable/exportable point-in-time documents), and **workflows** (state transitions with triggered actions). Today the Contacts module has none of these, which is why they're the next three phases. Each one adds a shell-level primitive the SDK exposes so every future module gets it for free.

### Phase 8 — Dashboards ✅ shipped

Shipped in PR #14. See the "Dashboard *" rows under "Locked-in decisions" for the concrete contracts. Chart library landed as Chart.js 4.4.1 via CDN. Widget data contract is async-function-primary with `scalar_query`/`series_query`/`table_query` SDK helpers for common shapes. Permission model is per-dashboard (module's own permission, e.g. `contacts.read`). Caching deferred — no widget caching in Phase 8; revisit when a widget proves slow, likely riding Phase 10's ARQ/Redis infrastructure.

**Known Phase 8 follow-ups (non-blocking, land opportunistically):**

- AI-generator SQL-string risk: the SDK query helpers accept an arbitrary `sql` string. When Phase 11 wires AI-generated modules into dashboards, the static-analysis gate needs a rule that the first arg to `scalar_query`/`series_query`/`table_query` is a string literal (not an f-string / concatenation).
- `Dashboard.permission` isn't validated against the permission registry at boot — a typo silently mounts a dashboard that no user can see. Add a boot-time `structlog.warning` in `sync_active_modules` when a dashboard's permission isn't registered.
- Chart.js 4.4.1 CDN is loaded from `_base.html` on every admin page (~200 KB). Worth moving to a `{% block head_extra %}` slot that only dashboard detail pages opt into.

### Phase 9 — Reports + PDF generation ✅ shipped

Shipped on the `phase-9-reports` branch. See the "Report *" rows under "Locked-in decisions" for the concrete contracts. PDF engine landed as Playwright + headless Chromium — initial spec called for WeasyPrint, but GTK/Cairo/Pango native libs were a bad fit for a Windows-first dev machine, and Phase 11 was already going to install Chromium anyway. Parameter forms are auto-rendered from a Pydantic `BaseModel` covering eight field types (str/int/float/bool/date/datetime/Literal/Enum) plus a textarea escape hatch and a `Report.form_template` override. Permission model is per-report (module's own permission, e.g. `contacts.read`); 404 (not 403) on missing permission. Boot-time WARN when a `Report.permission` isn't declared by the module — fixes the parallel dashboards follow-up too. Contacts ships `contacts.directory` as the reference report. CSV/XLSX export deferred to Phase 10 (workflow attach actions). Async / queued PDF generation deferred to Phase 10/11 (ARQ).

**Known Phase 9 follow-ups (non-blocking, land opportunistically):**

- The dashboards "permission not in registry" follow-up tracked in CLAUDE.md is now obsolete — Phase 9 added the same boot-time WARN for both reports AND should be extended to dashboards in the same place (`mount_module` in `parcel_shell/modules/integration.py`). Trivial diff.
- AI-generator awareness: when Phase 11 wires AI generation through reports/dashboards, the static-analysis gate needs to (a) ensure `Report.template` resolves to a file the module ships, (b) extend the dashboards "first-arg-string-literal" rule to any new SDK helpers we add. Tracked alongside the existing dashboards follow-up.
- `_report_base.html` is intentionally tight (one `<style>` block). Modules with rich formatting needs (multi-column layouts, custom fonts, watermarks) currently override `{% block page_css %}`. If we ever ship more than two reports per module, consider promoting common CSS to a second base template.

### Phase 10a — Workflows engine + sync triggers ✅ shipped

Shipped on the `phase-10a-workflows` branch. See the "Workflow *" rows under "Locked-in decisions" for the concrete contracts. Engine landed as trigger→action chains (no state machines); sync triggers only (`OnCreate`, `OnUpdate(when_changed=())`, `Manual`); two minimal actions (`UpdateField`, `EmitAudit`); explicit `shell_api.emit(session, event, subject)` at endpoints; post-commit dispatch via SQLAlchemy `after_commit`; single-transaction-per-chain failure with audit-on-error; per-workflow permission gating; read-only admin UI at `/workflows`. Contacts ships `new_contact_welcome` as the reference.

### Phase 10b — Workflows scheduled triggers + ARQ ✅ shipped

Shipped on the `phase-10b-workflows-cron` branch. See the six "Workflow *" rows added in this phase under "Locked-in decisions" for the concrete contracts. ARQ landed as first-class infrastructure: new `worker` compose service, `parcel worker` CLI, `PARCEL_WORKFLOWS_INLINE=1` test/dev short-circuit. `OnSchedule(hour=, minute=, ...)` uses ARQ-native kwargs; cron handlers are unique-named wrapper coroutines (since `arq.cron()` doesn't accept kwargs). Subject reduced to `{class_path, id}` for cross-process serialization. Worker boot path uses a sync DB query for cron_jobs (sidesteps nested-loop concerns). Contacts ships `daily_audit_summary` at 09:00.

### Phase 10b-retry — Per-workflow retry semantics

**Scope.** Add `Workflow.max_retries: int = 0` and `Workflow.retry_backoff: ...`. Threaded through `_on_after_commit` enqueue and the worker's job exec. ARQ's per-task `max_tries` and built-in retry exception bubble through. Audit table gets a `retry_index` or `attempt` column (or new `retry_of` linking column) — schema change → migration 0008. Documented in `module-authoring.md`.

### Phase 10c — Workflows rich actions + UI

**Scope.** Add `send_email`, `call_webhook`, `run_module_function`, `generate_report` actions (the last hooks into Phase 9). Each action declaration carries a capability and re-uses the Phase 7a gate when an AI-generated module declares a workflow. Long-running actions always go through ARQ, never inline. Admin UI gains a richer audit page (filter by status / event / module, retry-failed-invocation button) and a "running instances" view if state-machine semantics land in this phase.

### Phase 11 — Sandbox preview enrichment

**Scope.** Picks up from Phase 7c. When a candidate lands in the sandbox, we seed sample records into its schema (Claude generates a `seed.py` as part of the module), take Playwright screenshots of every declared route at common viewport sizes, and surface the results in the sandbox detail page. Moves the current "click through it live" preview to "look at these 6 screenshots". Uses ARQ (landed in Phase 10) to run the screenshot rendering off-request.

**Key decisions for the brainstorm:**
- **Sample-data source.** Claude emits a `seed.py` with `create_*` calls via the SDK, or the shell generates synthetic data from the model schema using `polyfactory`/similar. Both; Claude-authored by default, synthetic fallback when no seed is supplied.
- **Playwright in the shell image.** Big image bump (~400 MB for Chrome). Worth it — alternative is a separate service, which is more infra than we want here.
- **Screenshot storage.** Local filesystem under `var/sandbox/<uuid>/previews/` (easy, same as sandbox files) vs object storage (clean, but no S3 dep yet). Local for Phase 11; object storage is a Future concern.
- **Viewport matrix.** Mobile (375×), tablet (768×), desktop (1280×). Each route × each viewport = 3 images. Capped at ~30 screenshots per sandbox to bound runtime/storage.

### Why this ordering

Dashboards and reports are both "module output" primitives but have distinct stacks; shipping them separately keeps each phase focused. Workflows lands third because reports can emit a nice side effect for workflow actions ("generate + email report X on the first of every month"). Preview enrichment comes last because it builds on ARQ (introduced in workflows) and isn't a user-facing feature — it's polish on the AI-generator UX. Multi-tenancy, OIDC/SAML, module registry, and non-Python DB options all stay in Future until the platform has real users driving the prioritisation.

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

- Don't add multi-tenancy, OIDC/SAML, or a module registry — all three are in the Future row and stay there until the platform has real users driving the priority. The upcoming phases (8-11) all assume single-tenant, cookie-session auth, and local module discovery.
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
