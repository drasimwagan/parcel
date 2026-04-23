# Parcel

> AI-native, modular business-application platform. Describe a need, get a working module.

**Status:** Pre-alpha. Phase 1 complete — shell runs end-to-end with health endpoints, structured logging, and Alembic-managed Postgres schema. Auth, RBAC, and module loading land in Phases 2–3.

## Vision

Parcel is what Odoo would look like if it were designed in 2026 around large-language-model authoring. An admin describes a business need in plain language; Parcel drafts a module (models, views, migrations, tests), runs it in a sandbox, shows a preview, and installs it on approval. Developers can hand-write the same kind of modules with a typed Python SDK when precision matters. End users just use the apps.

## Architecture (one-liner)

- **Shell** (FastAPI + Postgres + Redis + HTMX) provides auth, RBAC, admin UI, and the module lifecycle.
- **SDK** is the stable Python API every module imports.
- **Modules** are pip-installable packages discovered via entry points. Each owns its own Postgres schema and Alembic migrations.

## Running locally (Phase 1)

Requires Docker.

```bash
cp .env.example .env                       # edit PARCEL_SESSION_SECRET for non-dev use
docker compose up -d postgres redis        # start dependencies
docker compose run --rm shell migrate      # create the `shell` schema
docker compose up -d shell                 # start the FastAPI service
```

Smoke-check:

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

### What Phase 2+ will add

A `parcel bootstrap` CLI (Phase 6) to seed the first admin user, an admin UI (Phase 4), and module install flow (Phase 3). Today the shell is infrastructure only — there is no login or UI to point a browser at.

## Roadmap

See [`CLAUDE.md`](./CLAUDE.md) for the phased roadmap and locked-in decisions.

## License

[MIT](./LICENSE)
