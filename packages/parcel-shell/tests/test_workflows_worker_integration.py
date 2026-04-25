"""End-to-end ARQ worker test.

Spins up a testcontainer Redis, registers ARQ functions, enqueues a
`run_event_dispatch` job, runs the worker in burst mode for ~10s,
asserts the audit row appears.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from arq import Worker, create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from parcel_sdk import EmitAudit, Module, OnCreate, Workflow
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.serialize import encode_events

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def redis_container() -> Iterator[str]:
    """Start a testcontainer Redis; yield the connection URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"


async def test_worker_round_trip_event_dispatch(
    redis_container: str, sessionmaker_factory, monkeypatch
) -> None:
    """Enqueue a run_event_dispatch job; run the worker in burst mode;
    assert an audit row was written."""
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)

    wf = Workflow(
        slug="cap",
        title="C",
        permission="x.read",
        triggers=(OnCreate("integration.test.fired"),),
        actions=(EmitAudit("captured"),),
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    redis_settings = RedisSettings.from_dsn(redis_container)

    # Enqueue the job.
    pool = await create_pool(redis_settings)
    try:
        payload = encode_events(
            [
                {
                    "event": "integration.test.fired",
                    "subject": None,
                    "subject_id": None,
                    "changed": (),
                }
            ]
        )
        await pool.enqueue_job("run_event_dispatch", payload)
    finally:
        await pool.close()

    from parcel_shell.workflows.worker import (
        run_event_dispatch,
        run_scheduled_workflow,
    )

    async def _test_startup(ctx: dict) -> None:
        ctx["sessionmaker"] = sessionmaker_factory
        ctx["app"] = fake_app
        runner.set_active_app(fake_app)

    async def _test_shutdown(ctx: dict) -> None:
        return None

    worker = Worker(
        functions=[run_event_dispatch, run_scheduled_workflow],
        redis_settings=redis_settings,
        on_startup=_test_startup,
        on_shutdown=_test_shutdown,
        burst=True,
        max_jobs=1,
    )
    try:
        await asyncio.wait_for(worker.async_run(), timeout=15.0)
    finally:
        await worker.close()

    async with sessionmaker_factory() as s:
        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].workflow_slug == "cap"
        assert rows[0].status == "ok"
