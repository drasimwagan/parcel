from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from parcel_shell.sandbox.previews import queue


@pytest.mark.asyncio
async def test_inline_creates_task(monkeypatch) -> None:
    monkeypatch.setenv("PARCEL_WORKFLOWS_INLINE", "1")
    sandbox_id = uuid.uuid4()
    app = SimpleNamespace(state=SimpleNamespace(
        sessionmaker=object(), preview_tasks=set(),
    ))
    settings = object()

    fake_render = AsyncMock()
    with patch("parcel_shell.sandbox.previews.queue._render", fake_render):
        await queue.enqueue(sandbox_id, app, settings)
        # Wait for the spawned task to complete.
        for t in list(app.state.preview_tasks):
            await t

    assert fake_render.await_count == 1
    fake_render.assert_awaited_with(sandbox_id, app.state.sessionmaker, app, settings)


@pytest.mark.asyncio
async def test_queued_calls_arq_enqueue(monkeypatch) -> None:
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)
    sandbox_id = uuid.uuid4()
    fake_pool = AsyncMock()
    app = SimpleNamespace(state=SimpleNamespace(
        sessionmaker=object(),
        arq_redis=fake_pool,
        preview_tasks=set(),
    ))
    settings = object()

    await queue.enqueue(sandbox_id, app, settings)

    fake_pool.enqueue_job.assert_awaited_once_with(
        "render_sandbox_previews", str(sandbox_id)
    )


@pytest.mark.asyncio
async def test_queued_no_pool_logs_and_skips(monkeypatch, caplog) -> None:
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)
    sandbox_id = uuid.uuid4()
    app = SimpleNamespace(state=SimpleNamespace(
        sessionmaker=object(),
        arq_redis=None,
        preview_tasks=set(),
    ))
    settings = object()

    await queue.enqueue(sandbox_id, app, settings)
    # No exception; no task scheduled.
