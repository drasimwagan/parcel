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

## Sandbox & gate (Phase 7a)

A candidate module — a directory tree or a zip — gets run through the static-analysis gate (`parcel-gate`) before it's allowed anywhere near the real schemas. If the gate passes, the candidate is installed under its own Postgres schema and mounted at its own URL; the admin can try it live, then either promote it (copy files to `modules/<name>/` and run the real install path) or dismiss it.

```
candidate ─┬─> extract to var/sandbox/<uuid>/
           │
           ├─> parcel-gate (ruff + bandit + AST policy)
           │        │
           │        ├─ pass → install, mount, add shell.sandbox_installs row
           │        └─ fail → raise GateRejected(report)
           │
admin ─────┴─> dismiss (drop schema, rm files) | promote (copy files → real install)
```

The AST policy's capability vocabulary is minimal on purpose — just four values:

| Capability | Unlocks |
|---|---|
| `filesystem` | `import os`, `open()` |
| `process` | `import subprocess` |
| `network` | `socket`, `urllib`, `http.*`, `httpx`, `requests`, `aiohttp` |
| `raw_sql` | `sqlalchemy.text(...)` |

A set of patterns are **always** blocked regardless of capabilities declared: `import sys`, `import importlib`, anything from `parcel_shell.*`, calls to `eval`/`exec`/`compile`/`__import__`, and attribute access to `__class__`/`__subclasses__`/`__globals__`/`__builtins__`/`__mro__`/`__code__`. Tests and `__pycache__` are excluded from the scan — the gate targets runtime code only.

Sandbox isolation is logical, not physical: the sandbox shares the shell's Python process, FastAPI app, and DB pool. The gate is what prevents a sandboxed module from doing damage. Each sandbox module is loaded with a unique `sys.modules` entry (`parcel_mod_<name>__sandbox_<short-uuid>`) so two sandboxes of the same base name coexist. Before Alembic runs, the manifest's `metadata.schema` is patched in-memory to `mod_sandbox_<uuid>`.

Admin surfaces: HTML at `/sandbox`, JSON at `/admin/sandbox`, CLI at `parcel sandbox install|list|show|promote|dismiss|prune`. Three new permissions (`sandbox.read`/`install`/`promote`) attach to the built-in `admin` role via migration 0004.

## Claude generator (Phase 7b)

The generator wraps the Phase 7a pipeline with a Claude-backed front end. Admin supplies a natural-language prompt; the shell turns it into a candidate module and hands it straight to the existing `create_sandbox` call.

```
POST /admin/ai/generate {"prompt": ...}
      │
      ▼
generate_module(prompt, provider, db, app, settings)
      │
      ▼
provider.generate(prompt, tmp_dir, prior=None)
      │
      ├── AnthropicAPIProvider: SDK call with write_file / submit_module tools
      └── ClaudeCodeCLIProvider: subprocess `claude -p ... --output-format json`
      │
      ▼
zip(files) ──> create_sandbox(...)  [Phase 7a]
      │
   gate pass ──> SandboxInstall (201)
   gate fail ──> retry ONCE with prior gate report attached
             ──> still fails → GenerationFailure(kind="exceeded_retries") (422)
```

**Provider selection** happens at shell startup. `PARCEL_AI_PROVIDER=api` (default) requires `ANTHROPIC_API_KEY`; `PARCEL_AI_PROVIDER=cli` uses the `claude` binary on PATH (no API key needed, but the CLI needs its own auth). If the API provider is selected without a key, the shell still boots — the endpoint returns 503 until a key is configured.

**Safety caps** on the API provider:

- Max 20 tool-use iterations per `generate()` call (runaway prevention).
- 64 KiB max per `write_file` call; 1 MiB total across all files.
- `write_file` paths must be relative POSIX without `..`, no `.sh`/`.exe`/`.so`/`.dll`/`.dylib`.
- The CLI provider's subprocess runs with `cwd` set to a throwaway `tempfile.TemporaryDirectory()` — it never writes directly into `var/sandbox/<uuid>/`.

**The system prompt** lives in the repo at `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` and is loaded via `importlib.resources`. It contains the full reference module scaffold (the seven files `parcel new-module` emits), the tool contract, the capability vocabulary, and the gate's hard-block list — so Claude's first pass has a realistic chance of passing the gate without repair.

**Failure-kind → HTTP status** mapping:

| Kind | Status | Meaning |
|---|---|---|
| `provider_error` | 502 | Network / auth / malformed tool use / subprocess crash |
| `no_files` | 400 | Provider returned zero files |
| `gate_rejected` / `exceeded_retries` | 422 | Gate rejected one or both attempts |

Observability: every generation logs a structured event with `prompt_hash` (first 16 hex of SHA-256), provider, attempt count, duration, and result/failure-kind. No raw prompt text is logged.

New permission `ai.generate` (migration 0005) on the admin role.

## AI chat surface (Phase 7c)

`/ai` is the browser-visible wrapper around the 7b generator. Sessions persist in two new tables (`shell.ai_sessions`, `shell.ai_turns`, migration 0006). Each admin turn is an independent generation — no accumulated Claude context. The chat-like UX comes from rendering the conversation thread, not from multi-turn model context.

```
POST /ai/sessions/<sid>/turns (form: prompt)
  ├─ add_turn(db, sid, prompt) → AITurn(status='generating')
  ├─ asyncio.create_task(run_turn(turn_id, prompt, provider, sessionmaker, app, settings))
  │     ↓
  │   (opens its own session, runs generate_module, writes terminal state)
  └─ 303 → /ai/sessions/<sid>

GET /ai/sessions/<sid>           — full page, includes _turns partial
GET /ai/sessions/<sid>/status    — _turns partial only, HTMX-polled every 1s while generating
```

The polling fragment carries `hx-get` / `hx-trigger="every 1s"` / `hx-target="#turns"` only when at least one turn is still `generating`; when all terminal, those attributes are omitted and the client stops polling automatically.

Background tasks are tracked in `app.state.ai_tasks`. On shell shutdown, outstanding tasks are cancelled and gathered with `return_exceptions=True`. The worker's top-level `except BaseException` handles `CancelledError` cleanly so a task interrupted mid-generation still writes a terminal `failed` row. A boot-time `sweep_orphans` flips any remaining `generating` turns to `failed(process_restart)` — covers crashes, hard kills, and unclean shutdowns.

Cross-owner access returns 404 (not 403) so session existence doesn't leak to other admins. No new permissions — `ai.generate` covers the chat flow as it did the 7b one-shot.
