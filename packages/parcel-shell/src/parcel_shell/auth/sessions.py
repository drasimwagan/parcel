from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import IDLE_TTL, Session


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Session:
    s = Session(
        user_id=user_id,
        ip_address=ip,
        user_agent=(user_agent[:500] if user_agent else None),
    )
    db.add(s)
    await db.flush()
    return s


async def lookup(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    s = await db.get(Session, session_id)
    if s is None:
        return None
    if s.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    if s.expires_at <= now:
        return None
    if now - s.last_seen_at > IDLE_TTL:
        return None
    return s


async def bump(db: AsyncSession, session: Session) -> None:
    session.last_seen_at = datetime.now(timezone.utc)
    await db.flush()


async def revoke(db: AsyncSession, session: Session) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    await db.flush()


async def revoke_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Session)
        .where(and_(Session.user_id == user_id, Session.revoked_at.is_(None)))
        .values(revoked_at=now)
    )
