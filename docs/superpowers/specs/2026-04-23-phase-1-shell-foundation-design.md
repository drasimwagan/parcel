# Phase 1 — Shell Foundation Design

**Date:** 2026-04-23
**Phase:** 1 (next after Phase 0 scaffold)
**Goal (from `CLAUDE.md`):** FastAPI app, config, async SQLAlchemy, Alembic for shell, logging, health, docker-compose end-to-end.

## Scope

Phase 1 delivers a runnable `parcel-shell` FastAPI service with:

- Typed configuration loaded from environment
- Async SQLAlchemy engine + session dependency
- Alembic wired to a shell-owned `shell` Postgres schema (empty baseline migration)
- Structured logging with per-request ID binding
- Liveness + readiness health endpoints
- Full end-to-end `docker compose up` path (postgres + redis + shell)
- Pytest suite running against a `testcontainers` Postgres

Phase 1 does **not** deliver: users, sessions, auth, RBAC, admin UI, any shell tables, any module-loading code. Those belong to Phases 2–4.

## Locked decisions from brainstorming

| Question | Decision |
|---|---|
| Shell DB content in Phase 1 | Empty baseline migration: creates `shell` schema, no tables |
| Test database | `testcontainers-python` Postgres per test session |
| Logging | `structlog` — JSON in prod/staging, console renderer in dev |
| Migrations run on boot | No — explicit `docker compose run --rm shell migrate` |

## Package layout

```
packages/parcel-shell/
  src/parcel_shell/
    __init__.py              # exports __version__
    app.py                   # create_app() -> FastAPI; lifespan wiring
    config.py                # Settings (pydantic-settings), @lru_cache get_settings()
    logging.py               # structlog configuration + request_id contextvar
    db.py                    # async engine, sessionmaker, get_session dep, shell MetaData
    middleware.py            # RequestIdMiddleware
    health.py                # APIRouter: /health/live, /health/ready
    alembic/
      env.py                 # async-aware env, imports shell_metadata from parcel_shell.db
      script.py.mako
      versions/
        0001_create_shell_schema.py   # CREATE SCHEMA shell
    alembic.ini
  tests/
    conftest.py              # postgres_container, engine, db_session, client fixtures
    test_config.py
    test_migrations.py
    test_health.py
    test_request_id.py
    test_app_factory.py
  pyproject.toml
```

### Module boundaries

- **`config.py`** — pure: reads env, validates, returns a `Settings` instance. No I/O at import time.
- **`db.py`** — owns engine lifecycle. Exposes `get_session()` FastAPI dependency. Exposes `shell_metadata: MetaData(schema="shell")` for Alembic autogenerate in later phases.
- **`logging.py`** — `configure_logging(settings)` called once at startup; exposes `request_id_var: ContextVar[str]`.
- **`middleware.py`** — `RequestIdMiddleware` reads `X-Request-ID` header (or generates a UUID4), binds it to `request_id_var` and structlog context, echoes it in the response header.
- **`health.py`** — router only. Injects `get_settings` and a redis client factory for readiness checks.
- **`app.py`** — composition root. `create_app()` builds the app, wires lifespan, middleware, routers. The module attribute `app = create_app()` is what uvicorn imports.

## Runtime flow

### Application lifespan

1. Load `Settings`; fail fast if required env vars are missing or invalid.
2. `configure_logging(settings)` — structlog with JSON renderer when `env != "dev"`, console renderer otherwise. Bound processors: timestamp, level, logger name, `request_id` contextvar merge.
3. Create async engine via `create_async_engine(settings.database_url, pool_pre_ping=True)` and sessionmaker; attach both to `app.state`.
4. Create async redis client from `settings.redis_url`; attach to `app.state`.
5. On shutdown: `engine.dispose()`, `redis.aclose()`.

Migrations are **not** executed during lifespan startup. They run via the `migrate` subcommand of `entrypoint.sh`.

### Request flow

```
Request
  -> RequestIdMiddleware (reads or generates X-Request-ID, binds to contextvar + structlog)
  -> Route handler (gets AsyncSession via Depends(get_session) where needed)
  -> Response (X-Request-ID echoed in header)
```

### Health endpoints

- `GET /health/live` — always `200 {"status": "ok"}`. No I/O. Intended for k8s liveness / LB checks.
- `GET /health/ready` — executes `SELECT 1` on the DB engine and `PING` on the redis client. Returns:
  - `200 {"status": "ok", "checks": {"db": "ok", "redis": "ok"}}` when all pass.
  - `503 {"status": "degraded", "checks": {...}}` when any fails, with the failing dep's status string set to `"error: <reason>"`. A 5-second timeout wraps each check.

### Error handling

- Global exception handler catches unhandled exceptions, logs with `request_id` bound, and returns `500 {"error": "internal_server_error", "request_id": "<id>"}`.
- FastAPI's default 422 validation handler is left in place; structlog middleware ensures those responses are logged with `request_id`.

### `entrypoint.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-serve}"
case "$cmd" in
  serve)   exec uv run uvicorn parcel_shell.app:app --host "${PARCEL_HOST:-0.0.0.0}" --port "${PARCEL_PORT:-8000}" --reload ;;
  migrate) exec uv run alembic -c packages/parcel-shell/alembic.ini upgrade head ;;
  shell)   exec /bin/bash ;;
  *)       echo "Usage: $0 {serve|migrate|shell}"; exit 1 ;;
esac
```

Contributor ritual documented in README:

```bash
docker compose up -d postgres redis
docker compose run --rm shell migrate
docker compose up -d shell
```

## Configuration surface

`Settings` (pydantic-settings, reads env + `.env`):

| Field | Env var | Default | Notes |
|---|---|---|---|
| `env` | `PARCEL_ENV` | `"dev"` | `Literal["dev", "staging", "prod"]` |
| `host` | `PARCEL_HOST` | `"0.0.0.0"` | |
| `port` | `PARCEL_PORT` | `8000` | |
| `session_secret` | `PARCEL_SESSION_SECRET` | — (required) | Min length 32 when `env != "dev"` |
| `database_url` | `DATABASE_URL` | — (required) | Must start with `postgresql+asyncpg://` |
| `redis_url` | `REDIS_URL` | — (required) | |
| `log_level` | `PARCEL_LOG_LEVEL` | `"INFO"` | |

- `get_settings()` is `@lru_cache`'d. Tests override via `app.dependency_overrides`.
- `session_secret` is reserved for Phase 2 (session cookie signing); validated now to keep the env schema stable.

## Testing strategy

### Fixtures (`conftest.py`)

- `postgres_container` (session-scoped) — `PostgresContainer("postgres:16-alpine")`.
- `engine` (session-scoped) — async engine against the container; runs `alembic upgrade head` once.
- `db_session` (function-scoped) — SQLAlchemy "join external transaction" pattern: begin connection, begin nested savepoint, yield session, rollback.
- `settings_override` (function-scoped) — overrides `get_settings` to return settings pointing at the testcontainer.
- `client` (function-scoped) — `httpx.AsyncClient(transport=ASGITransport(app=app))` with overrides applied.

### Test inventory

1. **`test_config.py`**
   - Missing `DATABASE_URL` raises `ValidationError`.
   - `session_secret` shorter than 32 chars rejected when `env="prod"`, accepted when `env="dev"`.
   - `database_url` without `+asyncpg` rejected.
2. **`test_migrations.py`**
   - `alembic upgrade head` succeeds on a fresh DB.
   - After upgrade, `shell` schema exists in `information_schema.schemata`.
   - `alembic downgrade base` runs cleanly.
3. **`test_health.py`**
   - `/health/live` returns 200 without any dependency setup.
   - `/health/ready` returns 200 when pg + redis are reachable.
   - `/health/ready` returns 503 with `checks.redis` set to an error string when the redis client is monkeypatched to raise on `ping()`.
4. **`test_request_id.py`**
   - Request with `X-Request-ID: test-123` → response header echoes `test-123`.
   - Request without the header → response header contains a well-formed UUID4.
   - Log capture during a request contains a record with `request_id=test-123` bound.
5. **`test_app_factory.py`**
   - `create_app()` returns a FastAPI instance.
   - Lifespan startup attaches `engine`, `sessionmaker`, `redis` to `app.state`.
   - Lifespan shutdown disposes the engine and closes the redis client.

### CI / local requirements

- `uv run pytest` requires Docker available on the host (for testcontainers). Documented in README.
- No GitHub Actions config added this phase; deferred.

## Dependency changes

`packages/parcel-shell/pyproject.toml` `dependencies`:

- `fastapi>=0.115`
- `uvicorn[standard]>=0.32`
- `sqlalchemy[asyncio]>=2.0.36`
- `asyncpg>=0.30`
- `alembic>=1.14`
- `redis>=5.2`
- `pydantic>=2.10`
- `pydantic-settings>=2.6`
- `structlog>=24.4`

Workspace root `[tool.uv] dev-dependencies` gains:

- `testcontainers[postgres]>=4.8`

Per CLAUDE.md convention ("Don't introduce new top-level dependencies without updating this file"), CLAUDE.md will be updated in the same commit noting these additions as Phase 1 locked dependencies.

## Alembic configuration

- `alembic.ini` points at `script_location = packages/parcel-shell/src/parcel_shell/alembic`.
- `env.py` is async-aware (uses `AsyncEngine` and `run_sync`), imports `shell_metadata` from `parcel_shell.db`, sets `version_table_schema="shell"` and `include_schemas=True` so future autogenerate only sees the `shell` schema.
- `0001_create_shell_schema.py` — `op.execute("CREATE SCHEMA IF NOT EXISTS shell")` up, `op.execute("DROP SCHEMA shell CASCADE")` down.

## Definition of done

1. `docker compose up -d` — postgres, redis, shell all reach healthy state.
2. `docker compose run --rm shell migrate` completes; `shell` schema present in the database.
3. `GET /health/live` → 200.
4. `GET /health/ready` → 200 while both deps are up; 503 after `docker compose stop redis`.
5. Request with `X-Request-ID: test-123` has that ID echoed in the response and present in the log line for the request.
6. `uv run pytest` green.
7. `uv run ruff check` and `uv run pyright` pass cleanly on `packages/parcel-shell`.
8. README updated with the three-command contributor ritual.
9. `CLAUDE.md` Phase 1 row marked ✅ done; Phase 2 marked `⏭ next`; dependency additions noted.

## Out of scope (deferred to later phases)

- User / session / role / permission tables → Phase 2
- Module discovery, manifest loading, per-module Alembic orchestration → Phase 3
- Jinja templates, Tailwind, HTMX, admin UI → Phase 4
- `parcel` CLI commands (`new-module`, `install`, `dev`, `serve`, `migrate`) → Phase 6
- ARQ worker service in docker-compose → Phase 7
