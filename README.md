# Parcel

> AI-native, modular business-application platform. Describe a need, get a working module.

**Status:** Pre-alpha. Phase 4 complete — browser-based admin UI with login, dashboard, users/roles/modules CRUD, and three user-selectable themes. Ships as server-rendered Jinja + HTMX + Alpine.js over Tailwind CDN; no npm build step.

## Vision

Parcel is what Odoo would look like if it were designed in 2026 around large-language-model authoring. An admin describes a business need in plain language; Parcel drafts a module (models, views, migrations, tests), runs it in a sandbox, shows a preview, and installs it on approval. Developers can hand-write the same kind of modules with a typed Python SDK when precision matters. End users just use the apps.

## Architecture (one-liner)

- **Shell** (FastAPI + Postgres + Redis + HTMX) provides auth, RBAC, admin UI, and the module lifecycle.
- **SDK** is the stable Python API every module imports.
- **Modules** are pip-installable packages discovered via entry points. Each owns its own Postgres schema and Alembic migrations.

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

### Inspect module state

```bash
curl -b cookies.txt http://localhost:8000/admin/modules
```

Out of the box this returns `[]` — there are no modules yet. Once Phase 5 ships a real Contacts module, it will appear here and can be installed with:

```bash
curl -b cookies.txt -H 'content-type: application/json' \
  -d '{"name":"contacts","approve_capabilities":[]}' \
  http://localhost:8000/admin/modules/install
```

### What Phase 4+ will add

Admin UI on Jinja/Tailwind/HTMX (Phase 4), a demo Contacts module (Phase 5), a `parcel` CLI (Phase 6), and the AI module generator (Phase 7).

## Roadmap

See [`CLAUDE.md`](./CLAUDE.md) for the phased roadmap and locked-in decisions.

## License

[MIT](./LICENSE)
