"""Enqueue a preview render — inline (asyncio task) or ARQ (Redis)."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import structlog

from parcel_shell.config import Settings
from parcel_shell.sandbox.previews.runner import _render

_log = structlog.get_logger("parcel_shell.sandbox.previews.queue")


async def enqueue(sandbox_id: uuid.UUID, app: Any, settings: Settings) -> None:
    """Schedule a render. Inline mode (`PARCEL_WORKFLOWS_INLINE=1`) creates an
    asyncio task tracked on `app.state.preview_tasks`; queued mode pushes a
    job onto the ARQ pool stored at `app.state.arq_redis`."""
    sessionmaker = app.state.sessionmaker
    if os.environ.get("PARCEL_WORKFLOWS_INLINE"):
        task = asyncio.create_task(_render(sandbox_id, sessionmaker, app, settings))
        app.state.preview_tasks.add(task)
        task.add_done_callback(app.state.preview_tasks.discard)
        return

    pool = getattr(app.state, "arq_redis", None)
    if pool is None:
        _log.warning(
            "sandbox.preview.enqueue_skipped.no_arq_redis",
            sandbox_id=str(sandbox_id),
        )
        return
    await pool.enqueue_job("render_sandbox_previews", str(sandbox_id))
