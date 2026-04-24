"""Background task that runs one chat turn.

Called via ``asyncio.create_task`` from the POST /ai/sessions/<id>/turns
handler. Opens its own DB session (the request's session closes the moment
the POST returns), runs ``generate_module``, writes the terminal state back.
Never raises — every exception path (including ``CancelledError`` at
shutdown) funnels through ``mark_failed``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    from parcel_shell.ai.provider import ClaudeProvider
    from parcel_shell.config import Settings

_log = structlog.get_logger("parcel_shell.ai.chat.worker")


async def run_turn(
    *,
    turn_id: uuid.UUID,
    prompt: str,
    provider: "ClaudeProvider",
    sessionmaker: "async_sessionmaker[AsyncSession]",
    app: "FastAPI",
    settings: "Settings",
) -> None:
    from parcel_shell.ai.chat import service as chat_service
    from parcel_shell.ai.generator import GenerationFailure, generate_module
    from parcel_shell.sandbox.models import SandboxInstall

    try:
        async with sessionmaker() as db:
            result = await generate_module(
                prompt,
                provider=provider,
                db=db,
                app=app,
                settings=settings,
            )
            if isinstance(result, SandboxInstall):
                await chat_service.mark_succeeded(
                    db, turn_id, sandbox_id=result.id
                )
            elif isinstance(result, GenerationFailure):
                await chat_service.mark_failed(
                    db,
                    turn_id,
                    kind=result.kind,
                    message=result.message,
                    gate_report=result.gate_report,
                )
            else:  # defensive — keeps the turn from getting stuck
                await chat_service.mark_failed(
                    db,
                    turn_id,
                    kind="provider_error",
                    message=f"unexpected generator result: {type(result).__name__}",
                )
            await db.commit()
    except BaseException as exc:  # noqa: BLE001 — must cover CancelledError
        _log.exception("ai.chat.worker.crashed", turn_id=str(turn_id))
        try:
            async with sessionmaker() as db:
                await chat_service.mark_failed(
                    db,
                    turn_id,
                    kind="provider_error",
                    message=f"background task crashed: {exc!r}",
                )
                await db.commit()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            _log.exception(
                "ai.chat.worker.cleanup_failed", turn_id=str(turn_id)
            )
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            raise
