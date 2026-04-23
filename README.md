# Parcel

> AI-native, modular business-application platform. Describe a need, get a working module.

**Status:** Pre-alpha. Phase 0 scaffolding only. No application code yet.

## Vision

Parcel is what Odoo would look like if it were designed in 2026 around large-language-model authoring. An admin describes a business need in plain language; Parcel drafts a module (models, views, migrations, tests), runs it in a sandbox, shows a preview, and installs it on approval. Developers can hand-write the same kind of modules with a typed Python SDK when precision matters. End users just use the apps.

## Architecture (one-liner)

- **Shell** (FastAPI + Postgres + Redis + HTMX) provides auth, RBAC, admin UI, and the module lifecycle.
- **SDK** is the stable Python API every module imports.
- **Modules** are pip-installable packages discovered via entry points. Each owns its own Postgres schema and Alembic migrations.

## Quickstart

*Not wired up yet.* Once Phase 1 lands:

```bash
git clone https://github.com/you/parcel
cd parcel
cp .env.example .env
docker compose up -d
uv sync
uv run parcel bootstrap          # create first admin user
open http://localhost:8000
```

## Roadmap

See [`CLAUDE.md`](./CLAUDE.md) for the phased roadmap and locked-in decisions.

## License

[MIT](./LICENSE)
