from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.workflows.bus import _emit_to_session, install_after_commit_listener

pytestmark = pytest.mark.asyncio


async def test_emit_to_session_appends_to_pending_events(db_session: AsyncSession) -> None:
    await _emit_to_session(db_session, "x.y.created", subject=None, changed=())
    pending = db_session.info["pending_events"]
    assert len(pending) == 1
    assert pending[0]["event"] == "x.y.created"
    assert pending[0]["subject"] is None
    assert pending[0]["subject_id"] is None
    assert pending[0]["changed"] == ()


async def test_emit_extracts_subject_id_when_present(db_session: AsyncSession) -> None:
    sid = uuid4()

    class Obj:
        id = sid

    await _emit_to_session(db_session, "x.y.created", subject=Obj(), changed=())
    pending = db_session.info["pending_events"]
    assert pending[0]["subject_id"] == sid


async def test_emit_two_events_appends_in_order(db_session: AsyncSession) -> None:
    await _emit_to_session(db_session, "a", subject=None, changed=())
    await _emit_to_session(db_session, "b", subject=None, changed=("x",))
    events = db_session.info["pending_events"]
    assert [e["event"] for e in events] == ["a", "b"]
    assert events[1]["changed"] == ("x",)


def test_install_after_commit_listener_is_idempotent() -> None:
    install_after_commit_listener()
    install_after_commit_listener()
    from parcel_shell.workflows import bus

    assert bus._listener_installed is True
