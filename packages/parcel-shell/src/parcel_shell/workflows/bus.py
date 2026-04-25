"""Workflow event bus.

Module endpoints call ``shell_api.emit(session, event, subject)``; events are
queued on ``session.info["pending_events"]`` and dispatched after the
originating commit succeeds.

Two dispatch paths:
- **Inline** (env var ``PARCEL_WORKFLOWS_INLINE=1``): events dispatch
  in-process via ``loop.create_task(dispatch_events(...))`` — the Phase-10a
  behaviour. Used by tests + ``parcel dev``.
- **Queued** (default at runtime): events are JSON-encoded and enqueued to
  Redis as ARQ jobs (``run_event_dispatch``); the worker container consumes
  them and runs ``dispatch_events`` in its own process.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_log = structlog.get_logger("parcel_shell.workflows.bus")
_listener_installed: bool = False


async def _emit_to_session(
    session: AsyncSession,
    event_name: str,
    subject: Any,
    *,
    changed: tuple[str, ...] = (),
) -> None:
    """Append an event to the session's pending-events queue.

    The session's after_commit listener (registered by
    :func:`install_after_commit_listener`) drains and dispatches it.
    """
    pending = session.info.setdefault("pending_events", [])
    pending.append(
        {
            "event": event_name,
            "subject": subject,
            "subject_id": getattr(subject, "id", None) if subject is not None else None,
            "changed": tuple(changed),
        }
    )


def _on_after_commit(sync_session: Session) -> None:
    """SQLAlchemy after_commit listener — runs sync; spawns the async dispatcher."""
    events = sync_session.info.pop("pending_events", None)
    if not events:
        return
    sessionmaker = sync_session.info.get("sessionmaker")
    if sessionmaker is None:
        _log.debug("workflows.dispatch_skipped.no_sessionmaker", event_count=len(events))
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _log.debug("workflows.dispatch_skipped.no_loop", event_count=len(events))
        return

    if os.environ.get("PARCEL_WORKFLOWS_INLINE"):
        # Late import to avoid a cycle (runner imports models which imports ShellBase).
        from parcel_shell.workflows.runner import dispatch_events

        loop.create_task(dispatch_events(events, sessionmaker))
        return

    arq_redis = sync_session.info.get("arq_redis")
    if arq_redis is None:
        _log.warning("workflows.dispatch_skipped.no_arq_redis", event_count=len(events))
        return

    from parcel_shell.workflows.serialize import encode_events

    payload = encode_events(events)
    loop.create_task(arq_redis.enqueue_job("run_event_dispatch", payload))


def install_after_commit_listener() -> None:
    """Register `_on_after_commit` once on the global Session class.

    Idempotent — second call is a no-op.
    """
    global _listener_installed
    if _listener_installed:
        return
    event.listen(Session, "after_commit", _on_after_commit)
    _listener_installed = True
