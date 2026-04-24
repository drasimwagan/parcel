# Parcel

> AI-native, modular business-application platform. Describe a need, get a working module.

**Status:** Pre-alpha. Phases 1–6 + 7a + 7b complete. Phase 7b wires the Claude API (and an optional Claude Code CLI fallback) in front of the 7a gate + sandbox — `POST /admin/ai/generate` or `parcel ai generate "<prompt>"` produces a candidate module and either installs it into a sandbox or returns a structured failure with the gate report. One-turn auto-repair on rejection. 242-test suite. Phase 7c (chat UI + richer preview) is next.

## Vision

Parcel is what Odoo would look like if it were designed in 2026 around large-language-model authoring. An admin describes a business need in plain language; Parcel drafts a module (models, views, migrations, tests), runs it in a sandbox, shows a preview, and installs it on approval. Developers can hand-write the same kind of modules with a typed Python SDK when precision matters. End users just use the apps.

## Architecture (one-liner)

- **Shell** (FastAPI + Postgres + Redis + HTMX) provides auth, RBAC, admin UI, and the module lifecycle.
- **SDK** is the stable Python API every module imports — including `parcel_sdk.shell_api`, the facade the shell registers at startup so modules never need to import `parcel_shell.*`.
- **Modules** are pip-installable packages discovered via entry points. Each owns its own Postgres schema and Alembic migrations.
- **CLI** (`parcel`) scaffolds modules, installs them, runs migrations, and launches the dev/prod server.

## Running locally

Requires Docker.

```bash
git clone https://github.com/drasimwagan/parcel.git
cd parcel
cp .env.example .env                       # edit PARCEL_SESSION_SECRET for non-dev use
docker compose up -d postgres redis        # start dependencies
docker compose run --rm shell migrate      # create the `shell` schema + auth tables
docker compose up -d shell                 # start the FastAPI service
```

Seed the first admin user (Phase 2):

```bash
docker compose run --rm shell bootstrap create-admin \
  --email you@example.com --password 'at-least-twelve-chars'
```

### Use the admin UI

Open `http://localhost:8000/` in a browser. You'll be redirected to `/login`. Sign in with the admin credentials you bootstrapped above; the dashboard opens and a sidebar gives you access to Users, Roles, Modules.

Pick a theme from the user menu (top right): **Plain** (default, greyscale), **Blue** (SaaS blue), or **Dark** (terminal-tinted amber on dark). The choice persists in `localStorage`.

### Or via JSON API

```bash
curl -c cookies.txt -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"at-least-twelve-chars"}' \
  http://localhost:8000/auth/login

curl -b cookies.txt http://localhost:8000/auth/me
curl -b cookies.txt http://localhost:8000/admin/users
```

Health endpoints (no auth required):

```bash
curl http://localhost:8000/health/live     # → {"status":"ok"}
curl http://localhost:8000/health/ready    # → {"status":"ok","checks":{"db":"ok","redis":"ok"}}
```

### Running tests

Tests use [testcontainers](https://testcontainers-python.readthedocs.io/) to spin up an ephemeral Postgres, so Docker must be running.

```bash
uv sync --all-packages
uv run pytest
uv run ruff check
uv run pyright packages/parcel-shell
```

### Build a module with the CLI (Phase 6)

```bash
uv run parcel new-module widgets           # scaffolds modules/widgets/
uv sync --all-packages
uv run parcel install ./modules/widgets    # pip install -e + register + migrate
uv run parcel dev                          # uvicorn with --reload
# visit http://localhost:8000/mod/widgets/
```

Full authoring surface is documented in [`docs/module-authoring.md`](./docs/module-authoring.md).

### Inspect module state via JSON API

```bash
curl -b cookies.txt http://localhost:8000/admin/modules
curl -b cookies.txt -H 'content-type: application/json' \
  -d '{"name":"contacts","approve_capabilities":[]}' \
  http://localhost:8000/admin/modules/install
```

### Demo module: contacts

`modules/contacts` is the bundled Contacts/CRM-lite demo. Install it from `/modules` (no capabilities to approve) or via `parcel install ./modules/contacts`. After a container restart the sidebar grows a **Contacts** section; each entity has list, detail, and create pages with HTMX live search. As of Phase 6 the module depends only on `parcel-sdk` at runtime.

### Sandbox a candidate module (Phase 7a)

```bash
uv run parcel sandbox install ./modules/contacts     # gate + install to mod_sandbox_<uuid>
uv run parcel sandbox list                           # sandboxes with gate verdict + status
uv run parcel sandbox show <uuid>                    # full gate report
uv run parcel sandbox promote <uuid> widgets_alt     # copy files → modules/, real install
uv run parcel sandbox dismiss <uuid>                 # drop schema + rm files
```

The gate (`packages/parcel-gate/`) runs `ruff` + `bandit` + a custom AST policy that blocks `os`/`subprocess`/`socket`/`eval`/`exec`/`compile`/`__import__`/dynamic imports unless a matching capability (`filesystem`, `process`, `network`, `raw_sql`) is declared in the module manifest. Admin UI at `/sandbox` mirrors the CLI.

### Generate a module with Claude (Phase 7b)

Requires `ANTHROPIC_API_KEY` in your `.env` (or set `PARCEL_AI_PROVIDER=cli` to use the Claude Code CLI instead — it must be on PATH).

```bash
uv run parcel ai generate "track invoices with number, amount, date, and status"
# ✓ sandbox <uuid> at /mod-sandbox/<short>/
```

The generator calls the configured provider, zips the result, runs it through the 7a gate, and either installs it into a sandbox or returns the gate report so you can see what was wrong. On a gate rejection it automatically retries **once** with the report attached — most first-pass mistakes (accidentally `import os`, missing an allowed-list import) fix themselves on the second turn.

The same flow is available over HTTP: `POST /admin/ai/generate {"prompt": "..."}` (requires the `ai.generate` permission).

### What Phase 7c will add

The chat UI — a browser surface to iterate on prompts, see intermediate state, and accept or reject candidates without re-running the whole pipeline. Richer preview too: sample records seeded into the sandbox, screenshots of the rendered views, so admins can judge an AI-drafted module without clicking through it live.

## Roadmap

See [`CLAUDE.md`](./CLAUDE.md) for the phased roadmap and locked-in decisions.

## License

[MIT](./LICENSE)
