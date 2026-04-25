# Phase 10b — Workflows scheduled triggers + ARQ

**Status:** approved
**Date:** 2026-04-25
**Builds on:** Phase 10a (Workflows engine + sync triggers).
**Splits into:** 10b-retry (per-workflow retry on top of the queue), 10c (rich actions + richer UI).

## Goal

Add `OnSchedule(hour=, minute=, ...)` triggers; introduce ARQ as first-class infrastructure. `_on_after_commit` enqueues a Redis job instead of `asyncio.create_task`. A new `worker` service consumes the queue, runs sync-trigger workflows, and runs cron-fired workflows on its own scheduler. Tests bypass Redis with `PARCEL_WORKFLOWS_INLINE=1`. Contacts ships a `daily_audit_summary` reference workflow demonstrating cron.

## Non-goals (10b)

- **Retry / max_retries / backoff.** Deferred to 10b-retry. Failing actions still audit `status="error"` once and don't re-run.
- **Hot-add of cron schedules.** New module installs require a worker restart to pick up `OnSchedule` triggers. Documented; no auto-reload mechanism.
- **Multi-worker locking.** A single worker is assumed; `OnSchedule` fires once per scheduler tick. Phase 10c can add `unique=True` ARQ semantics if a deployment runs multiple workers.
- **Rich actions** (`send_email`, `call_webhook`, `run_module_function`, `generate_report`) — 10c.
- **State machines / running-instance UI** — still Phase 10c+ territory.
- **Cron string syntax** (`"0 9 * * 1-5"`). Phase 10b uses ARQ-native kwargs only. `OnSchedule.from_cron(...)` may land later if demand exists.

## Locked decisions

| Area | Decision |
|---|---|
| Phase split | 10b: cron + ARQ + worker. Retry → 10b-retry. Rich actions → 10c. |
| Dispatch routing | Always-through-ARQ at runtime. `_on_after_commit` enqueues a Redis job. `PARCEL_WORKFLOWS_INLINE=1` env var short-circuits to today's `loop.create_task(dispatch_events(...))` for tests/dev. |
| Cron syntax | ARQ-native kwargs: `OnSchedule(*, hour=None, minute=None, second=None, day=None, month=None, weekday=None)`. Each accepts `int`, `set[int]`, or `None`. Maps to `arq.cron.cron(...)` 1:1. No `event` field — cron audit auto-names `<module>.<slug>.scheduled`. |
| Trigger semantics | `OnSchedule` fires from the worker's cron loop, not from emit. `_matches` returns False for `OnSchedule` (mirrors Manual's pattern). Cron firing dispatches via `run_scheduled_workflow(ctx, module_name, slug)` (an ARQ-registered function) which builds a synthetic event `{event: "<module>.<slug>.scheduled", subject: None, subject_id: None, changed: ()}` and calls `run_workflow` directly. |
| Subject for cron | Always `None`. `UpdateField` raises `RuntimeError("UpdateField requires a subject_id; emit() supplied none")` (existing Phase 10a behaviour) and the audit captures the error. Documented: cron + `UpdateField` is a 10c concern (when richer actions arrive). |
| Sync-trigger dispatch via ARQ | `_on_after_commit` builds a JSON-serializable event payload (subject reduced to `{class_path, id}`) and enqueues `run_event_dispatch(events)` to Redis. The worker's job handler re-imports the subject's class, `session.get(cls, id)` re-fetches, then `dispatch_events(events_with_resolved_subjects, sessionmaker)` runs the existing matching logic. |
| Subject serialization | Subjects must be SQLAlchemy mapped instances OR `None`. The bus encodes them as `{"class_path": "<module.path.ClassName>", "id": "<uuid>"}`. The worker re-imports `class_path` via `importlib`, calls `session.get(cls, id)`. If the row's been deleted between commit and worker pickup, the action raises and the audit captures the error. |
| Worker container | Same `parcel-shell` Docker image. New `worker` compose service with `command: ["parcel", "worker"]`, `depends_on: [postgres, redis]`, shared `env_file`. |
| Worker boot path | `parcel_shell.workflows.worker.build_worker_settings(settings)` connects to DB, queries `InstalledModule.is_active=true`, imports each module's manifest, builds a `RegisteredWorkflow` list, generates one ARQ cron job per `OnSchedule` trigger across all modules, returns a `WorkerSettings` class with `functions=(run_event_dispatch, run_scheduled_workflow)`, `cron_jobs=...`, `redis_settings=...`. |
| Module install + worker | `parcel install` continues to mount on the live shell. CLI prints `"module installed; restart 'worker' service to pick up any scheduled triggers"` when the new module declares any `OnSchedule` workflow. Single-line warning, no enforcement. |
| CLI | New `parcel worker` subcommand. Loads settings via `parcel_shell.config.get_settings()`, builds `WorkerSettings`, calls `arq.run_worker(WorkerSettings)`. Same image as shell, no extra build steps. |
| Inline mode | `PARCEL_WORKFLOWS_INLINE` env var. Read in `_on_after_commit`; when truthy, `loop.create_task(dispatch_events(...))` runs in-process exactly as today. **Cron triggers don't fire under inline mode** — no scheduler in the shell process. Tests that need to exercise cron call `run_scheduled_workflow(ctx, module_name, slug)` directly via the same function ARQ would call. The `parcel dev` CLI sets `PARCEL_WORKFLOWS_INLINE=1` by default for ergonomic single-process dev (printed: "workflows inline; cron triggers off — start `parcel worker` for cron"). |
| SDK version | 0.6.0 → **0.7.0** (adds `OnSchedule`). |
| Contacts version | 0.4.0 → **0.5.0** (adds `daily_audit_summary` workflow). |
| Shell deps | `arq>=0.26,<1.0` added to `parcel-shell` runtime deps. |
| Reference workflow | `daily_audit_summary` — `OnSchedule(hour=9, minute=0)` + `EmitAudit("Daily contacts summary; total contacts = {{ ... }}")`. Note: the EmitAudit message can't easily query the DB in 10b's action set; the message is a plain string. The point of this reference is to prove cron fires + audits, not to demonstrate a useful summary. A "richer" version lands in 10c. |
| Auth, audit | Unchanged from 10a. Same `shell.workflow_audit` table; same per-workflow permission model; same 404-on-missing-permission policy. Cron-fired workflows write audit rows like any other invocation. |

## Architecture

```
parcel_shell/
  workflows/
    bus.py                       # _on_after_commit gains ARQ enqueue + INLINE short-circuit
    runner.py                    # unchanged shape; sets active_app at shell AND worker boot
    worker.py                    # NEW — build_worker_settings, run_event_dispatch, run_scheduled_workflow
    serialize.py                 # NEW — encode/decode event payloads (subject ↔ class_path+id)
  cli/
    main.py                      # NEW subcommand: `parcel worker`
parcel-cli (CLI package)
  src/parcel_cli/__init__.py     # registers new `worker` subcommand
docker/
  Dockerfile                     # unchanged (image already has all deps)
  entrypoint.sh                  # unchanged (CLI wraps ARQ; entrypoint stays generic)
docker-compose.yml               # NEW `worker` service entry
modules/contacts/src/parcel_mod_contacts/
  workflows.py                   # adds daily_audit_summary
  __init__.py                    # adds the workflow to manifest, bumps to 0.5.0
```

## SDK surface — `OnSchedule`

```python
# parcel_sdk/workflows.py — adds:

@dataclass(frozen=True, kw_only=True)
class OnSchedule:
    """Fires from the worker's cron scheduler.

    Each field accepts an `int`, a `set[int]`, or `None` (matches any). Fields
    follow ARQ's `cron()` semantics:

    - `second`, `minute`: 0-59
    - `hour`: 0-23
    - `day`: 1-31
    - `month`: 1-12
    - `weekday`: 0-6 (Monday is 0; matches `datetime.weekday()`)

    Examples:
        OnSchedule(hour=9, minute=0)                  # daily at 09:00
        OnSchedule(hour=9, minute=0, weekday={0,1,2,3,4})  # weekdays at 09:00
        OnSchedule(minute={0, 15, 30, 45})            # every 15 minutes
    """

    second: int | set[int] | None = None
    minute: int | set[int] | None = None
    hour: int | set[int] | None = None
    day: int | set[int] | None = None
    month: int | set[int] | None = None
    weekday: int | set[int] | None = None
```

Updated `Trigger` union:

```python
Trigger = OnCreate | OnUpdate | Manual | OnSchedule
```

Range validation happens at SDK construction time (raises `ValueError` early; module won't load with invalid kwargs). The constructor checks each field — when a value is an `int`, the range matches the field; when a `set`, all members are in range.

## Bus — ARQ enqueue + inline short-circuit

```python
# parcel_shell/workflows/bus.py (refactored)

import os
from arq.connections import ArqRedis
from parcel_shell.workflows.serialize import encode_events

def _on_after_commit(sync_session: Session) -> None:
    events = sync_session.info.pop("pending_events", None)
    if not events:
        return
    sessionmaker = sync_session.info.get("sessionmaker")
    if sessionmaker is None:
        _log.debug("workflows.dispatch_skipped.no_sessionmaker", event_count=len(events))
        return

    if os.environ.get("PARCEL_WORKFLOWS_INLINE"):
        _dispatch_inline(events, sessionmaker)
        return

    redis: ArqRedis | None = sync_session.info.get("arq_redis")
    if redis is None:
        _log.warning("workflows.dispatch_skipped.no_arq_redis", event_count=len(events))
        return

    payload = encode_events(events)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(redis.enqueue_job("run_event_dispatch", payload))


def _dispatch_inline(events: list[dict], sessionmaker) -> None:
    """Inline test/dev path — same as Phase 10a."""
    from parcel_shell.workflows.runner import dispatch_events

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(dispatch_events(events, sessionmaker))
```

`get_session` (in `parcel_shell/db.py`) gains a second `session.info` entry:

```python
session.info["sessionmaker"] = session_factory
session.info["arq_redis"] = request.app.state.arq_redis  # set in lifespan
```

The shell's lifespan acquires an `ArqRedis` connection on startup:

```python
from arq import create_pool
from arq.connections import RedisSettings

app.state.arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
```

Cleanup on shutdown: `await app.state.arq_redis.close()`.

## Serializer

```python
# parcel_shell/workflows/serialize.py

from typing import Any
from uuid import UUID

def encode_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert in-memory event dicts into JSON-serializable payloads.

    Subject is reduced to a `{class_path, id}` referent so the worker can
    re-fetch a session-attached copy. None subjects round-trip unchanged.
    """
    out: list[dict[str, Any]] = []
    for ev in events:
        subj = ev.get("subject")
        if subj is None:
            subject_ref = None
        else:
            cls = type(subj)
            subject_ref = {
                "class_path": f"{cls.__module__}.{cls.__qualname__}",
                "id": str(ev["subject_id"]) if ev.get("subject_id") else None,
            }
        out.append(
            {
                "event": ev["event"],
                "subject_ref": subject_ref,
                "subject_id": str(ev["subject_id"]) if ev.get("subject_id") else None,
                "changed": list(ev.get("changed", ())),
            }
        )
    return out


def decode_event(payload: dict[str, Any], session) -> dict[str, Any]:
    """Inverse — re-fetch subject from `class_path` + `id`."""
    subj = None
    subj_id: UUID | None = None
    ref = payload.get("subject_ref")
    if ref and ref.get("id"):
        cls = _import_class(ref["class_path"])
        subj_id = UUID(ref["id"])
        subj = await session.get(cls, subj_id)  # may return None if row deleted
    return {
        "event": payload["event"],
        "subject": subj,
        "subject_id": subj_id,
        "changed": tuple(payload.get("changed", [])),
    }
```

(Pseudo-code. `decode_event` is async because of `session.get`. The worker's `run_event_dispatch` calls it inside its session.)

## Worker

```python
# parcel_shell/workflows/worker.py

import asyncio
from typing import Any
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from parcel_shell.config import Settings
from parcel_shell.workflows.serialize import decode_event
from parcel_shell.workflows.runner import dispatch_events, run_workflow, set_active_app
from parcel_shell.workflows.registry import collect_workflows, find_workflow
from parcel_sdk import OnSchedule


async def run_event_dispatch(ctx: dict, payload: list[dict]) -> None:
    """ARQ-registered job: re-fetch subjects, dispatch events."""
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        events = [await decode_event(p, session) for p in payload]
    await dispatch_events(events, sessionmaker)


async def run_scheduled_workflow(ctx: dict, module_name: str, slug: str) -> None:
    """ARQ-registered job: cron-fired workflow run.

    Called by ARQ's cron scheduler. Builds a synthetic event with no subject;
    delegates to run_workflow which writes the audit row.
    """
    sessionmaker = ctx["sessionmaker"]
    fake_app = ctx["app"]
    registered = collect_workflows(fake_app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None:
        return
    ev = {
        "event": f"{module_name}.{slug}.scheduled",
        "subject": None,
        "subject_id": None,
        "changed": (),
    }
    await run_workflow(module_name, hit.workflow, ev, sessionmaker)


async def _startup(ctx: dict) -> None:
    """ARQ on_startup hook: build a fake-app analog with active_modules_manifest."""
    settings = Settings()  # reads from env
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker

    # Mirror shell's module-loading: discover + filter by InstalledModule.is_active.
    from types import SimpleNamespace
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule
    from sqlalchemy import select

    discovered = {d.module.name: d for d in discover_modules()}
    manifest: dict[str, Any] = {}
    async with sessionmaker() as s:
        rows = (
            (await s.execute(select(InstalledModule).where(InstalledModule.is_active.is_(True))))
            .scalars()
            .all()
        )
    for row in rows:
        d = discovered.get(row.name)
        if d is not None:
            manifest[row.name] = d.module

    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    ctx["app"] = fake_app
    set_active_app(fake_app)


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


def build_worker_settings(settings: Settings) -> type:
    """Build a WorkerSettings class for arq.run_worker.

    Generates one cron_jobs entry per OnSchedule trigger across all active
    modules at boot time. Restart the worker to pick up newly-installed
    workflows.
    """
    # We need to discover modules SYNCHRONOUSLY here (cron_jobs is a class
    # attribute set before ARQ starts). Run a tiny event loop.
    cron_jobs: list = []
    discovered_manifest = _discover_manifest_sync(settings)
    for module_name in sorted(discovered_manifest):
        module = discovered_manifest[module_name]
        for wf in module.workflows:
            for trigger in wf.triggers:
                if isinstance(trigger, OnSchedule):
                    cron_jobs.append(
                        cron(
                            run_scheduled_workflow,
                            name=f"{module_name}.{wf.slug}",
                            second=trigger.second,
                            minute=trigger.minute,
                            hour=trigger.hour,
                            day=trigger.day,
                            month=trigger.month,
                            weekday=trigger.weekday,
                            kwargs={"module_name": module_name, "slug": wf.slug},
                        )
                    )

    class WorkerSettings:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        functions = [run_event_dispatch, run_scheduled_workflow]
        cron_jobs = cron_jobs
        on_startup = _startup
        on_shutdown = _shutdown

    return WorkerSettings


def _discover_manifest_sync(settings: Settings) -> dict[str, Any]:
    """Synchronous wrapper around the async discovery — runs a private loop."""
    return asyncio.run(_discover_manifest(settings))


async def _discover_manifest(settings: Settings) -> dict[str, Any]:
    # mirrors _startup body, returns {name: Module}
    ...
```

(The `_discover_manifest_sync` shape is necessary because `cron_jobs` is set as a class attribute before the worker's main loop starts.)

## CLI — `parcel worker`

```python
# parcel-cli adds:

@app.command()
def worker() -> None:
    """Run the workflow worker."""
    from arq import run_worker
    from parcel_shell.config import get_settings
    from parcel_shell.workflows.worker import build_worker_settings

    settings = get_settings()
    WorkerSettings = build_worker_settings(settings)
    run_worker(WorkerSettings)
```

## docker-compose.yml — new service

```yaml
worker:
  build: .
  command: ["parcel", "worker"]
  env_file: .env
  depends_on:
    postgres: { condition: service_healthy }
    redis:    { condition: service_healthy }
  restart: unless-stopped
```

## Reference workflow — `daily_audit_summary`

```python
# modules/contacts/src/parcel_mod_contacts/workflows.py — adds:

from parcel_sdk import EmitAudit, OnSchedule

daily_audit_summary = Workflow(
    slug="daily_audit_summary",
    title="Daily contacts summary",
    permission="contacts.read",
    triggers=(OnSchedule(hour=9, minute=0),),
    actions=(
        EmitAudit(message="Daily contacts summary at {{ event }}"),
    ),
    description="Writes a daily audit row at 09:00. Reference for OnSchedule.",
)
```

Manifest gains `daily_audit_summary` alongside `welcome_workflow`. Module bumps to `0.5.0`.

## Tests

Target: ~25 new (~417 total). Sync-trigger tests stay inline-mode via the existing fixtures + `PARCEL_WORKFLOWS_INLINE=1` set globally in `conftest`. New coverage:

**SDK** (`packages/parcel-sdk/tests/test_workflows.py` extension)
- `OnSchedule` is frozen, kw_only, supports the six fields, defaults to `None`.
- Range validation: `OnSchedule(hour=25)` raises; `OnSchedule(hour={1, 99})` raises; `OnSchedule(weekday=7)` raises.
- `Trigger` union includes `OnSchedule`.

**Bus** (`packages/parcel-shell/tests/test_workflows_bus.py` extension)
- With `PARCEL_WORKFLOWS_INLINE=1`, after_commit calls `dispatch_events` inline (same Phase 10a path).
- Without inline + with `arq_redis` on session.info, after_commit calls `redis.enqueue_job("run_event_dispatch", ...)` (mocked).
- Without inline + without `arq_redis`, after_commit logs `dispatch_skipped.no_arq_redis` and drops events.

**Serializer** (`packages/parcel-shell/tests/test_workflows_serialize.py`)
- `encode_events` on a Contact instance produces a `{class_path, id}` ref and the right shape.
- `decode_event` re-fetches the row by class_path + id; missing row resolves to `subject=None`.
- Round-trip preserves `event`, `changed`, `subject_id`.

**Worker** (`packages/parcel-shell/tests/test_workflows_worker.py`)
- `build_worker_settings` returns a class with `cron_jobs` populated for every `OnSchedule` trigger across active modules.
- `run_scheduled_workflow(ctx, module_name, slug)` builds the synthetic event and writes an audit row with `event="<m>.<s>.scheduled"` and `subject_id=None`.
- `run_event_dispatch(ctx, payload)` decodes payload, calls `dispatch_events`, audit rows match.

**Worker integration** (`packages/parcel-shell/tests/test_workflows_worker_integration.py`)
- Spin up `arq.Worker.async_run(...)` against testcontainer Redis for ~2 seconds. Enqueue a `run_event_dispatch` job. Assert audit row written.
- Same harness fires `run_scheduled_workflow` (manually triggered via `enqueue_job`, not actual cron — cron's timing is hard to test).

**CLI** (`packages/parcel-cli/tests/test_cli_worker.py`)
- `parcel worker` command exists; `--help` documents it.
- Invocation calls `arq.run_worker` (mocked) with the result of `build_worker_settings`.

**Contacts cron reference** (`modules/contacts/tests/test_contacts_workflow_daily.py`)
- The `daily_audit_summary` workflow is in the manifest.
- Calling `run_scheduled_workflow` directly with `("contacts", "daily_audit_summary")` writes an `ok` audit row with the rendered message containing the synthetic event name.

## Documentation

- `docs/module-authoring.md` "Workflows" section gains an `OnSchedule` subsection: declaration, supported kwargs, the no-subject rule, the worker-restart-required note.
- `CLAUDE.md` rolls 10b → ✅, adds Phase-10b block under Locked-in decisions, updates Current phase + Next pointer (Phase 10b-retry or Phase 10c).
- `docs/index.html` flips 10b to done; 10c becomes next.
- New file `docs/architecture.md` § "Worker container" describes the boot path, the inline-mode env var, and the restart-on-install limitation. (Or fold into module-authoring.md.)

## Migration / compatibility

- No new shell migrations.
- SDK 0.7.0 is additive — existing workflows still type-check.
- New shell dep `arq>=0.26,<1.0` (pulls `croniter` transitively).
- New `worker` compose service. Existing `docker compose up shell` still works for non-cron flows when `PARCEL_WORKFLOWS_INLINE=1` is set.
- `parcel dev` (CLI hot-reload) sets `PARCEL_WORKFLOWS_INLINE=1` automatically with a printed banner.

## Risks and follow-ups

- **`asyncio.run(_discover_manifest(...))` inside `build_worker_settings`.** This nested-loop pattern is fragile. If ARQ is started from inside an existing event loop, `asyncio.run` will raise. Acceptable for `parcel worker` CLI (no outer loop). Tests that import `build_worker_settings` from inside an async test must mock `_discover_manifest_sync`. Document the constraint.
- **Worker restart on module install.** A user who installs a new module via the admin UI then waits for cron schedules will be confused. Mitigation: the install flow prints "restart worker for cron schedules" when the new module declares any `OnSchedule`. Long-term fix: a Redis pub/sub topic the worker subscribes to, or a periodic re-discovery tick. Out of scope for 10b.
- **Subject re-fetch race.** Between `_on_after_commit` enqueueing and the worker dequeueing, the row may be deleted. `decode_event` returns `subject=None`; `UpdateField` then raises and audit captures the error. Acceptable; a retry layer (10b-retry) doesn't help — the row is gone.
- **JSON serialization of arbitrary subjects.** Subjects must be SQLAlchemy mapped instances. Non-mapped subjects (dicts, Pydantic models) won't round-trip. Documented; modules should always emit with a model instance.
- **Single-worker assumption.** Two workers would each fire cron schedules, doubling audit rows. Mitigation in 10c: pass `unique=True` to ARQ's cron, OR add a Postgres advisory lock. Out of scope here.
- **Inline-mode feature gap.** Cron triggers don't fire under inline mode. Documented prominently. The `parcel dev` banner makes this hard to miss.
- **AI-generator awareness.** Phase 11's static-analysis gate will need to validate `OnSchedule` kwargs are constants (not env-derived) so the worker's cron is reproducible from manifest alone. Tracked alongside existing Phase-10a follow-ups.

## Open during implementation

None. All major decisions are locked.
