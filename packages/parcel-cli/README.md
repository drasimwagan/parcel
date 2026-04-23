# parcel-cli

The `parcel` command-line tool for developers and admins.

**Status:** Phase 0 skeleton. Commands implemented in Phase 6.

Planned commands:

- `parcel new-module <name>` — scaffold a new module from a template
- `parcel dev` — run the shell with hot reload watching `modules/`
- `parcel install <git-url>` — clone and install a module from Git
- `parcel migrate` — orchestrate Alembic migrations across all modules
- `parcel serve` — production server (uvicorn behind gunicorn workers)
- `parcel bootstrap` — first-run setup: create the initial admin user
