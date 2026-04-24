# Parcel

> AI-native, modular business-application platform. Describe a need, get a working module.

**Status:** Pre-alpha. Phases 1–6 complete. The SDK now exposes a stable `parcel_sdk.shell_api` facade so modules depend only on `parcel-sdk`; a `parcel` CLI ships `new-module`, `install`, `migrate`, `dev`, and `serve`. The bundled Contacts/CRM-lite demo module shows the pattern end-to-end (Contact + Company entities, live HTMX search, two permissions). 196-test suite. Phase 7 (AI module generator) is next.

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

### What Phase 7 will add

The AI module generator — chat with Claude to draft a module, static-analysis gate (ruff + bandit + AST policy), sandbox install, admin preview, approve-into-production flow.

## Roadmap

See [`CLAUDE.md`](./CLAUDE.md) for the phased roadmap and locked-in decisions.

## License

[MIT](./LICENSE)
