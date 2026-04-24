"""Chat session + turn service.

All functions take ``db: AsyncSession`` and mutate via ``db.add`` /
``db.execute`` / ``db.flush``. The caller is responsible for committing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.chat.models import AISession, AITurn

_TITLE_MAX = 40


async def create_session(db: AsyncSession, *, owner_id: uuid.UUID) -> AISession:
    now = datetime.now(UTC)
    row = AISession(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="(untitled)",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return row


async def list_sessions_for_owner(
    db: AsyncSession, owner_id: uuid.UUID, *, limit: int = 50
) -> Sequence[AISession]:
    stmt = (
        select(AISession)
        .where(AISession.owner_id == owner_id)
        .order_by(AISession.updated_at.desc())
        .limit(limit)
    )
    return (await db.execute(stmt)).scalars().all()


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, *, owner_id: uuid.UUID
) -> AISession | None:
    """Return the session iff ``owner_id`` owns it. Otherwise ``None``.

    Callers map ``None`` to 404 (not 403) so the existence of someone else's
    session does not leak to other admins.
    """
    row = await db.get(AISession, session_id)
    if row is None or row.owner_id != owner_id:
        return None
    return row


async def get_turns(db: AsyncSession, session_id: uuid.UUID) -> Sequence[AITurn]:
    stmt = (
        select(AITurn)
        .where(AITurn.session_id == session_id)
        .order_by(AITurn.idx.asc())
    )
    return (await db.execute(stmt)).scalars().all()


async def count_session_turns(db: AsyncSession, session_id: uuid.UUID) -> int:
    stmt = select(func.count(AITurn.id)).where(AITurn.session_id == session_id)
    return int((await db.execute(stmt)).scalar_one())


async def add_turn(
    db: AsyncSession, session_id: uuid.UUID, prompt: str
) -> AITurn:
    session_row = await db.get(AISession, session_id)
    if session_row is None:
        raise ValueError(f"session not found: {session_id}")

    next_idx = (
        await db.execute(
            select(func.coalesce(func.max(AITurn.idx), 0)).where(
                AITurn.session_id == session_id
            )
        )
    ).scalar_one() + 1

    now = datetime.now(UTC)
    turn = AITurn(
        id=uuid.uuid4(),
        session_id=session_id,
        idx=next_idx,
        prompt=prompt,
        status="generating",
        started_at=now,
    )
    db.add(turn)

    if next_idx == 1 and session_row.title == "(untitled)":
        session_row.title = _title_from_prompt(prompt)
    session_row.updated_at = now

    await db.flush()
    return turn


def _title_from_prompt(prompt: str) -> str:
    trimmed = prompt.strip().splitlines()[0] if prompt.strip() else ""
    if not trimmed:
        return "(untitled)"
    if len(trimmed) <= _TITLE_MAX:
        return trimmed
    return trimmed[: _TITLE_MAX - 1].rstrip() + "…"


async def mark_succeeded(
    db: AsyncSession, turn_id: uuid.UUID, *, sandbox_id: uuid.UUID
) -> None:
    turn = await db.get(AITurn, turn_id)
    if turn is None:
        return
    now = datetime.now(UTC)
    turn.status = "succeeded"
    turn.sandbox_id = sandbox_id
    turn.finished_at = now
    session_row = await db.get(AISession, turn.session_id)
    if session_row is not None:
        session_row.updated_at = now
    await db.flush()


async def mark_failed(
    db: AsyncSession,
    turn_id: uuid.UUID,
    *,
    kind: str,
    message: str,
    gate_report: dict[str, Any] | None = None,
) -> None:
    turn = await db.get(AITurn, turn_id)
    if turn is None:
        return
    now = datetime.now(UTC)
    turn.status = "failed"
    turn.failure_kind = kind
    turn.failure_message = message
    turn.gate_report = gate_report
    turn.finished_at = now
    session_row = await db.get(AISession, turn.session_id)
    if session_row is not None:
        session_row.updated_at = now
    await db.flush()


async def sweep_orphans(db: AsyncSession) -> int:
    """Mark any ``status='generating'`` turns as failed with kind
    ``process_restart``. Returns the count swept.

    Called once at shell lifespan startup so a crash or restart doesn't leave
    turn rows wedged in ``generating`` forever.
    """
    stmt = select(AITurn).where(AITurn.status == "generating")
    rows = list((await db.execute(stmt)).scalars().all())
    now = datetime.now(UTC)
    for row in rows:
        row.status = "failed"
        row.failure_kind = "process_restart"
        row.failure_message = "Shell restarted while this turn was generating."
        row.finished_at = now
    await db.flush()
    return len(rows)
