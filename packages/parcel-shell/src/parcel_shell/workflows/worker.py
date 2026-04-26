"""ARQ worker entry points for workflow dispatch + cron firing.

Two job functions are registered with ARQ:
- ``run_event_dispatch(ctx, payload)`` — processes a list of emit-driven events
  enqueued by ``_on_after_commit``.
- ``run_scheduled_workflow(ctx, module_name, slug)`` — fired by ARQ's cron
  scheduler; constructs a synthetic event with ``subject=None``.

The CLI command ``parcel worker`` calls ``arq.run_worker`` against the class
returned by :func:`build_worker_settings`. That function discovers active
modules synchronously at boot to populate ``cron_jobs``; restart the worker
to pick up newly-installed ``OnSchedule`` workflows.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import structlog
from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from parcel_sdk import OnSchedule
from parcel_shell.config import Settings, get_settings
from parcel_shell.workflows.registry import collect_workflows, find_workflow
from parcel_shell.workflows.runner import (
    _matches,
    run_workflow,
    set_active_app,
)
from parcel_shell.workflows.serialize import decode_event

_log = structlog.get_logger("parcel_shell.workflows.worker")


# ---- ARQ-registered job functions ------------------------------------------


async def run_event_dispatch(ctx: dict, payload: list[dict[str, Any]]) -> None:
    """Re-fetch subjects, run matching workflows, raise arq.Retry on error+budget.

    Reads `ctx["job_try"]` (ARQ-provided) and passes it as `attempt` to
    `run_workflow`. As soon as ANY workflow errors with retry budget remaining,
    raises `Retry(defer=...)` and ARQ re-enqueues with `job_try += 1`.

    Multi-event payloads with mixed success/failure will re-run successful
    workflows on retry — known imprecision (see spec "Risks").
    """
    sessionmaker = ctx["sessionmaker"]
    job_try = ctx.get("job_try", 1)

    async with sessionmaker() as session:
        events = [await decode_event(p, session) for p in payload]

    from parcel_shell.workflows.runner import _active_app  # noqa: PLC0415

    for ev in events:
        registered = collect_workflows(_active_app)
        for r in registered:
            if any(_matches(t, ev) for t in r.workflow.triggers):
                outcome = await run_workflow(
                    r.module_name, r.workflow, ev, sessionmaker, attempt=job_try
                )
                if outcome.status == "error" and job_try <= r.workflow.max_retries:
                    delay = r.workflow.retry_backoff_seconds * 2 ** (job_try - 1)
                    raise Retry(defer=timedelta(seconds=delay))


async def run_scheduled_workflow(ctx: dict, module_name: str, slug: str) -> None:
    """Cron-fired workflow run; raise arq.Retry on error+budget."""
    sessionmaker = ctx["sessionmaker"]
    fake_app = ctx["app"]
    registered = collect_workflows(fake_app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None:
        _log.warning("workflows.scheduled.unknown", module=module_name, slug=slug)
        return

    job_try = ctx.get("job_try", 1)
    ev = {
        "event": f"{module_name}.{slug}.scheduled",
        "subject": None,
        "subject_id": None,
        "changed": (),
    }
    outcome = await run_workflow(module_name, hit.workflow, ev, sessionmaker, attempt=job_try)
    if outcome.status == "error" and job_try <= hit.workflow.max_retries:
        delay = hit.workflow.retry_backoff_seconds * 2 ** (job_try - 1)
        raise Retry(defer=timedelta(seconds=delay))


# ---- Lifecycle hooks -------------------------------------------------------


async def _startup(ctx: dict) -> None:
    """ARQ on_startup hook. Creates engine + session factory; mirrors shell
    module discovery into a SimpleNamespace 'fake app'."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker

    manifest = await _discover_active_manifest_async(settings)
    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    ctx["app"] = fake_app
    set_active_app(fake_app)
    _log.info("workflows.worker.started", module_count=len(manifest))


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


# ---- Discovery -------------------------------------------------------------


def _discover_active_manifest_sync(settings: Settings) -> dict[str, Any]:
    """Sync DB query for `InstalledModule.is_active=true`; used by build_worker_settings.

    Uses a sync engine so it doesn't need an outer event loop.
    """
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    discovered = {d.module.name: d for d in discover_modules()}
    sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(InstalledModule).where(InstalledModule.is_active.is_(True))
            ).all()
    finally:
        engine.dispose()
    manifest: dict[str, Any] = {}
    for row in rows:
        d = discovered.get(row.name)
        if d is not None:
            manifest[row.name] = d.module
    return manifest


async def _discover_active_manifest_async(settings: Settings) -> dict[str, Any]:
    """Async equivalent for use inside `_startup` (which already has a loop)."""
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    discovered = {d.module.name: d for d in discover_modules()}
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    select(InstalledModule).where(InstalledModule.is_active.is_(True))
                )
            ).all()
    finally:
        await engine.dispose()
    manifest: dict[str, Any] = {}
    for row in rows:
        d = discovered.get(row.name)
        if d is not None:
            manifest[row.name] = d.module
    return manifest


# ---- Cron-jobs builder -----------------------------------------------------


def _make_cron_handler(module_name: str, slug: str):
    """Build a unique-named coroutine that ARQ can register as a function.

    ARQ's `cron()` doesn't accept extra args/kwargs; the cron coroutine is
    called with just `ctx`. We generate one wrapper per `OnSchedule` trigger,
    each with a distinct `__name__` so ARQ keeps them apart in its registry.
    The wrapper closes over `(module_name, slug)` and forwards to the
    canonical `run_scheduled_workflow`.
    """

    async def _handler(ctx: dict) -> None:
        await run_scheduled_workflow(ctx, module_name, slug)

    _handler.__name__ = f"_cron_{module_name}_{slug}"
    _handler.__qualname__ = _handler.__name__
    return _handler


def _build_cron_jobs(manifest: dict[str, Any]) -> list:
    """One ARQ CronJob (and one wrapper handler) per OnSchedule trigger.

    Returns the cron-jobs list; the wrappers themselves are registered in
    :func:`build_worker_settings` alongside the canonical handlers.
    """
    jobs = []
    for module_name in sorted(manifest):
        module = manifest[module_name]
        for wf in module.workflows:
            for trigger in wf.triggers:
                if isinstance(trigger, OnSchedule):
                    handler = _make_cron_handler(module_name, wf.slug)
                    jobs.append(
                        cron(
                            handler,
                            name=f"{module_name}.{wf.slug}",
                            second=trigger.second,
                            minute=trigger.minute,
                            hour=trigger.hour,
                            day=trigger.day,
                            month=trigger.month,
                            weekday=trigger.weekday,
                        )
                    )
    return jobs


# ---- WorkerSettings builder (called by `parcel worker`) --------------------


def build_worker_settings(settings: Settings) -> type:
    """Return a WorkerSettings class for `arq.run_worker`.

    Discovers active modules synchronously at boot; generates one cron_jobs
    entry per OnSchedule trigger across all installed modules. Restart the
    worker to pick up newly-installed schedules.
    """
    from parcel_shell.sandbox.previews.worker import render_sandbox_previews  # noqa: PLC0415

    manifest = _discover_active_manifest_sync(settings)
    jobs = _build_cron_jobs(manifest)
    # Each cron job's coroutine must also be registered in `functions` so ARQ
    # can resolve it by name when firing.
    cron_handlers = [j.coroutine for j in jobs]

    class WorkerSettings:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        functions = [
            run_event_dispatch,
            run_scheduled_workflow,
            render_sandbox_previews,
            *cron_handlers,
        ]
        cron_jobs = jobs
        on_startup = _startup
        on_shutdown = _shutdown
        job_timeout = 600  # 10 min — covers worst-case 30-screenshot render

    return WorkerSettings
