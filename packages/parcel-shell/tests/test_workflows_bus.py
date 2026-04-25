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


async def test_after_commit_enqueues_to_arq_when_not_inline(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without INLINE env var, after_commit calls ArqRedis.enqueue_job."""
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)

    enqueued: list[tuple[str, tuple, dict]] = []

    class FakeArqRedis:
        async def enqueue_job(self, name: str, *args, **kwargs):
            enqueued.append((name, args, kwargs))
            return None

    # Stub the sessionmaker + arq_redis on session.info as the live
    # `get_session` dep would.
    db_session.info["sessionmaker"] = lambda: None
    db_session.info["arq_redis"] = FakeArqRedis()
    await _emit_to_session(db_session, "x.y.created", subject=None, changed=())

    from parcel_shell.workflows.bus import _on_after_commit

    _on_after_commit(db_session.sync_session)
    import asyncio as _asyncio

    await _asyncio.sleep(0.05)
    assert len(enqueued) == 1
    name, args, _kwargs = enqueued[0]
    assert name == "run_event_dispatch"
    payload = args[0]
    assert payload[0]["event"] == "x.y.created"


async def test_after_commit_skips_when_no_arq_redis_and_not_inline(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without INLINE and without arq_redis, dispatch is silently dropped."""
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)
    db_session.info["sessionmaker"] = lambda: None
    db_session.info.pop("arq_redis", None)
    await _emit_to_session(db_session, "x.y.created", subject=None, changed=())

    from parcel_shell.workflows.bus import _on_after_commit

    # Should not raise.
    _on_after_commit(db_session.sync_session)
