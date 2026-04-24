from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.chat import service as chat_service
from parcel_shell.ai.chat.models import AISession, AITurn


async def _make_user(db_session: AsyncSession):
    from parcel_shell.auth.hashing import hash_password
    from parcel_shell.rbac.models import User

    u = User(
        id=uuid.uuid4(),
        email=f"chat-{uuid.uuid4().hex[:8]}@test.example.com",
        password_hash=hash_password("password-1234-long"),
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_create_session_returns_empty_session(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    assert s.owner_id == user.id
    assert s.title == "(untitled)"


@pytest.mark.asyncio
async def test_add_turn_sets_index_and_title(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    turn = await chat_service.add_turn(db_session, s.id, "track invoices")
    assert turn.idx == 1
    assert turn.status == "generating"

    refreshed = await db_session.get(AISession, s.id)
    assert refreshed is not None
    assert refreshed.title == "track invoices"


@pytest.mark.asyncio
async def test_add_turn_increments_index(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    t1 = await chat_service.add_turn(db_session, s.id, "first")
    t2 = await chat_service.add_turn(db_session, s.id, "second")
    assert t1.idx == 1
    assert t2.idx == 2


@pytest.mark.asyncio
async def test_mark_succeeded_transitions_turn(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    turn = await chat_service.add_turn(db_session, s.id, "prompt")
    sandbox_id = uuid.uuid4()
    await chat_service.mark_succeeded(db_session, turn.id, sandbox_id=sandbox_id)
    refreshed = await db_session.get(AITurn, turn.id)
    assert refreshed is not None
    assert refreshed.status == "succeeded"
    assert refreshed.sandbox_id == sandbox_id
    assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_mark_failed_records_kind_and_report(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    turn = await chat_service.add_turn(db_session, s.id, "bad prompt")
    report = {"passed": False, "findings": []}
    await chat_service.mark_failed(
        db_session,
        turn.id,
        kind="gate_rejected",
        message="2 errors",
        gate_report=report,
    )
    refreshed = await db_session.get(AITurn, turn.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.failure_kind == "gate_rejected"
    assert refreshed.gate_report == report


@pytest.mark.asyncio
async def test_get_session_rejects_cross_owner(db_session: AsyncSession) -> None:
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=a.id)
    assert (await chat_service.get_session(db_session, s.id, owner_id=b.id)) is None
    assert (await chat_service.get_session(db_session, s.id, owner_id=a.id)) is not None


@pytest.mark.asyncio
async def test_sweep_orphans_marks_generating_as_failed(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    turn = await chat_service.add_turn(db_session, s.id, "stuck")
    # Simulate the orphan state — nothing to do, add_turn already set status
    # to 'generating' and didn't finish.
    swept = await chat_service.sweep_orphans(db_session)
    assert swept == 1
    refreshed = await db_session.get(AITurn, turn.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.failure_kind == "process_restart"


@pytest.mark.asyncio
async def test_title_truncated_for_long_prompt(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    s = await chat_service.create_session(db_session, owner_id=user.id)
    long_prompt = "a" * 200
    await chat_service.add_turn(db_session, s.id, long_prompt)
    refreshed = await db_session.get(AISession, s.id)
    assert refreshed is not None
    assert len(refreshed.title) <= 40
    assert refreshed.title.endswith("…")
