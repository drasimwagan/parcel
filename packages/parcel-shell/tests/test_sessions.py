from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth import sessions as sess
from parcel_shell.rbac.models import IDLE_TTL, Session


async def test_create_session_persists_row(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id, ip="127.0.0.1", user_agent="pytest")
    got = (await db_session.execute(select(Session).where(Session.id == s.id))).scalar_one()
    assert got.user_id == u.id
    assert got.ip_address == "127.0.0.1"
    assert got.user_agent == "pytest"
    assert got.revoked_at is None
    assert got.expires_at > datetime.now(timezone.utc)


async def test_lookup_returns_session_when_valid(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    await db_session.flush()
    got = await sess.lookup(db_session, s.id)
    assert got is not None and got.id == s.id


async def test_lookup_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    assert await sess.lookup(db_session, uuid.uuid4()) is None


async def test_lookup_returns_none_for_revoked(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    await sess.revoke(db_session, s)
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_lookup_returns_none_when_absolute_expired(
    db_session: AsyncSession, user_factory
) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    s.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_lookup_returns_none_when_idle_expired(
    db_session: AsyncSession, user_factory
) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    s.last_seen_at = datetime.now(timezone.utc) - (IDLE_TTL + timedelta(minutes=1))
    await db_session.flush()
    assert await sess.lookup(db_session, s.id) is None


async def test_bump_advances_last_seen(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    s = await sess.create_session(db_session, user_id=u.id)
    s.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.flush()
    original = s.last_seen_at
    await sess.bump(db_session, s)
    await db_session.flush()
    assert s.last_seen_at > original


async def test_revoke_all_for_user(db_session: AsyncSession, user_factory) -> None:
    u = await user_factory()
    a = await sess.create_session(db_session, user_id=u.id)
    b = await sess.create_session(db_session, user_id=u.id)
    other_user = await user_factory()
    c = await sess.create_session(db_session, user_id=other_user.id)
    # Capture IDs before expiring so we don't need lazy-loaded attribute access later.
    a_id, b_id, c_id = a.id, b.id, c.id
    await db_session.flush()

    await sess.revoke_all_for_user(db_session, u.id)
    await db_session.flush()
    db_session.expire_all()

    assert await sess.lookup(db_session, a_id) is None
    assert await sess.lookup(db_session, b_id) is None
    assert await sess.lookup(db_session, c_id) is not None  # unaffected
